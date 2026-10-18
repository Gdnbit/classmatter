"""Bounded concrete adapter for signed artifact references.

This module is synthetic development evidence.  The rooted artifact store is a
local transport adapter, and ``InMemoryIdentityLedger`` is deliberately a test
double.  Neither is a production registry, authorization service, or proof of
PostgreSQL durability.
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from signature_envelope import (
    ARTIFACT_POLICIES,
    AdmissionError,
    ExpectedContext,
    VerifiedArtifactReference,
    VerifiedGenericClosure,
    VerifiedRegistrySnapshot,
    canonicalize_payload,
    sha256_hex,
    verify_admission,
)


ARTIFACT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _windows_opened_path(descriptor: int) -> Path:
    """Return the resolved target of the opened handle, never a checked pathname."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_path = kernel32.GetFinalPathNameByHandleW
    get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_path.restype = wintypes.DWORD
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_path(handle, buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise AdmissionError("opened artifact path cannot be verified")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    else:
        raise AdmissionError("opened artifact path has an unsupported form")
    return Path(value)


def _windows_open_no_follow(path: Path) -> int:
    """Open the final component itself and reject a reparse-point handle."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [("file_attributes", wintypes.DWORD), ("reparse_tag", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # FILE_SHARE_READ/WRITE/DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise AdmissionError("artifact URI could not be opened")
    try:
        info = FileAttributeTagInfo()
        if not get_info(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise AdmissionError("opened artifact attributes cannot be verified")
        if info.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise AdmissionError("opened artifact is a reparse point")
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close_handle(handle)
        raise
    return descriptor


class ArtifactIdentityLedger(Protocol):
    """Port for durable artifact-id and nonce uniqueness enforcement."""

    def observe(self, artifact_id: str, nonce: str, payload_digest: str) -> None: ...


class InMemoryIdentityLedger:
    """Deterministic collision fake; never evidence of durable uniqueness."""

    def __init__(self) -> None:
        self._by_artifact: dict[str, tuple[str, str]] = {}
        self._by_nonce: dict[str, str] = {}
        self._lock = threading.RLock()

    def observe(self, artifact_id: str, nonce: str, payload_digest: str) -> None:
        with self._lock:
            prior = self._by_artifact.get(artifact_id)
            if prior is not None and prior != (nonce, payload_digest):
                raise AdmissionError("artifact id collision in identity ledger")
            nonce_owner = self._by_nonce.get(nonce)
            if nonce_owner is not None and nonce_owner != artifact_id:
                raise AdmissionError("nonce collision in identity ledger")
            self._by_artifact[artifact_id] = (nonce, payload_digest)
            self._by_nonce[nonce] = artifact_id


class RootedArtifactStore:
    """Read bounded bytes from one named root through a non-file URI scheme."""

    def __init__(self, root: Path, *, store_id: str, max_bytes: int = 1024 * 1024) -> None:
        self._root = Path(root).resolve(strict=True)
        if not self._root.is_dir():
            raise AdmissionError("artifact store root must be a directory")
        if not ARTIFACT_ID_RE.fullmatch(store_id):
            raise AdmissionError("artifact store id is invalid")
        if not isinstance(max_bytes, int) or max_bytes < 1:
            raise AdmissionError("artifact size limit must be positive")
        self._store_id = store_id
        self._max_bytes = max_bytes

    def fetch(self, uri: str) -> bytes:
        if not isinstance(uri, str):
            raise AdmissionError("artifact URI must be a string")
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "classos-artifact"
            or parsed.netloc != self._store_id
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
        ):
            raise AdmissionError("artifact URI scheme or authority is not allowed")

        decoded = unquote(parsed.path[1:])
        parts = decoded.split("/")
        if (
            not decoded
            or len(parts) != 1
            or any(part in {"", ".", ".."} for part in parts)
            or any("\\" in part or ":" in part or "\x00" in part for part in parts)
        ):
            raise AdmissionError("artifact URI path is invalid")

        candidate = self._root.joinpath(*parts)
        cursor = self._root
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise AdmissionError("artifact URI may not resolve through a symlink")
            if os.name == "nt":
                try:
                    attributes = os.lstat(cursor).st_file_attributes
                except OSError as exc:
                    raise AdmissionError("artifact URI cannot be inspected") from exc
                if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise AdmissionError("artifact URI may not traverse a reparse point")
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise AdmissionError("artifact URI cannot be resolved") from exc
        if not resolved.is_relative_to(self._root) or not resolved.is_file():
            raise AdmissionError("artifact URI escapes the configured store")

        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = _windows_open_no_follow(candidate) if os.name == "nt" else os.open(resolved, flags)
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise AdmissionError("artifact URI must open a regular file")
            if os.name == "nt" and not _windows_opened_path(descriptor).is_relative_to(self._root):
                raise AdmissionError("opened artifact escaped the configured store")
            post_open_path = resolved.resolve(strict=True)
            if not post_open_path.is_relative_to(self._root):
                raise AdmissionError("artifact URI escaped the configured store during open")
            path_state = post_open_path.stat()
            if (opened.st_dev, opened.st_ino) != (path_state.st_dev, path_state.st_ino):
                raise AdmissionError("artifact changed identity while it was being opened")
            chunks: list[bytes] = []
            remaining = self._max_bytes + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
        except AdmissionError:
            raise
        except OSError as exc:
            raise AdmissionError("artifact URI could not be read") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if len(raw) > self._max_bytes:
            raise AdmissionError("artifact exceeds configured size limit")
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AdmissionError("artifact changed while it was being read")
        return raw


def _strict_json_object(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AdmissionError("artifact envelope is not strict UTF-8") from exc

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AdmissionError(f"duplicate JSON member in artifact envelope: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise AdmissionError(f"non-I-JSON number in artifact envelope: {value}")

    try:
        value = json.loads(text, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except AdmissionError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise AdmissionError("artifact envelope is invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"payloadType", "payload", "signatures"}:
        raise AdmissionError("artifact envelope fields are invalid")
    return value


@dataclass
class _ResolutionSession:
    stack: list[tuple[str, str]]
    nodes: int = 0


_SESSION: ContextVar[_ResolutionSession | None] = ContextVar(
    "class_os_reference_resolution_session", default=None
)


class ReferenceResolver:
    """Fetch, hash and fully verify a referenced DSSE artifact."""

    def __init__(
        self,
        store: RootedArtifactStore,
        registry_snapshot: VerifiedRegistrySnapshot,
        now: datetime,
        *,
        identity_ledger: ArtifactIdentityLedger | None,
        max_depth: int = 8,
        max_nodes: int = 64,
    ) -> None:
        if not isinstance(registry_snapshot, VerifiedRegistrySnapshot):
            raise AdmissionError("reference resolver requires a verified registry snapshot")
        if max_depth < 1 or max_nodes < 1:
            raise AdmissionError("reference graph limits must be positive")
        self._store = store
        self._snapshot = registry_snapshot
        self._now = now
        self._identity_ledger = identity_ledger
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    def __call__(
        self, reference: dict[str, Any], parent_expected: ExpectedContext, expected_type: str
    ) -> VerifiedArtifactReference:
        if self._identity_ledger is None:
            raise AdmissionError("reference resolver requires an identity ledger")
        if not isinstance(reference, dict):
            raise AdmissionError("artifact reference must be an object")
        artifact_id = reference.get("artifact_id")
        uri = reference.get("artifact_uri")
        expected_digest = reference.get("sha256")
        if not isinstance(artifact_id, str) or not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise AdmissionError("artifact reference id is invalid")
        if not isinstance(uri, str):
            raise AdmissionError("artifact URI must be a string")
        if not isinstance(expected_digest, str) or not SHA256_RE.fullmatch(expected_digest):
            raise AdmissionError("artifact reference digest is invalid")
        if expected_type not in ARTIFACT_POLICIES:
            raise AdmissionError("unsupported referenced artifact type")

        session = _SESSION.get()
        root_token = None
        if session is None:
            session = _ResolutionSession(stack=[])
            root_token = _SESSION.set(session)
        identity = (artifact_id, uri)
        try:
            if len(session.stack) >= self._max_depth:
                raise AdmissionError("artifact reference graph exceeds depth limit")
            if session.nodes >= self._max_nodes:
                raise AdmissionError("artifact reference graph exceeds node limit")
            if any(item[0] == artifact_id or item[1] == uri for item in session.stack):
                raise AdmissionError("artifact reference cycle is forbidden")
            session.stack.append(identity)
            session.nodes += 1
            try:
                envelope = _strict_json_object(self._store.fetch(uri))
                expected = self._expected_for_reference(parent_expected, expected_type)
                decision = verify_admission(
                    envelope,
                    self._snapshot,
                    self._now,
                    expected,
                    reference_verifier=self,
                )
                canonical_payload = canonicalize_payload(decision.payload)
                digest = sha256_hex(canonical_payload)
                if decision.artifact_id != artifact_id:
                    raise AdmissionError("verified artifact id does not match reference")
                if digest != expected_digest:
                    raise AdmissionError("verified artifact digest does not match reference")
                nonce = decision.payload.get("nonce")
                if not isinstance(nonce, str):
                    raise AdmissionError("verified artifact nonce is missing")
                self._identity_ledger.observe(artifact_id, nonce, digest)
                return VerifiedArtifactReference(
                    artifact_id=artifact_id,
                    artifact_type=expected_type,
                    lifecycle=decision.lifecycle,
                    digest=digest,
                    canonical_payload=canonical_payload,
                    registry_generation=self._snapshot.generation,
                    registry_sha256=self._snapshot.sha256,
                    verified_roles=decision.roles,
                )
            finally:
                session.stack.pop()
        finally:
            if root_token is not None:
                _SESSION.reset(root_token)

    def resolve_generic_closure(
        self,
        parent_artifact_id: str,
        parent_payload_sha256: str,
        catalog_reference: dict[str, Any],
        bindings: tuple[dict[str, Any], ...],
        parent_expected: ExpectedContext,
    ) -> VerifiedGenericClosure:
        if self._identity_ledger is None:
            raise AdmissionError("generic reference closure requires an identity ledger")
        session = _SESSION.get()
        root_token = None
        if session is None:
            session = _ResolutionSession(stack=[(parent_artifact_id, "")], nodes=1)
            root_token = _SESSION.set(session)
        elif not session.stack or session.stack[-1][0] != parent_artifact_id:
            raise AdmissionError("generic reference parent is not the active artifact")
        try:
            catalog = self(catalog_reference, parent_expected, "reference-catalog")
            entries = json.loads(catalog.canonical_payload)["entries"]
            locations = {entry["artifact_id"]: entry["artifact_uri"] for entry in entries}
            resolved: list[tuple[str, str, str]] = []
            for binding in bindings:
                artifact_id = binding["artifact_id"]
                uri = locations.get(artifact_id)
                if uri is None:
                    raise AdmissionError("unresolved generic catalog reference")
                reference = {
                    "artifact_id": artifact_id,
                    "artifact_uri": uri,
                    "sha256": binding["sha256"],
                }
                verified = self(reference, parent_expected, binding["artifact_type"])
                resolved.append((verified.artifact_id, verified.artifact_type, verified.digest))
            return VerifiedGenericClosure(
                parent_artifact_id=parent_artifact_id,
                parent_payload_sha256=parent_payload_sha256,
                catalog_artifact_id=catalog.artifact_id,
                catalog_payload_sha256=catalog.digest,
                registry_generation=self._snapshot.generation,
                registry_sha256=self._snapshot.sha256,
                expected_context=parent_expected,
                resolved=tuple(resolved),
            )
        finally:
            if root_token is not None:
                _SESSION.reset(root_token)

    @staticmethod
    def _expected_for_reference(
        parent: ExpectedContext, artifact_type: str
    ) -> ExpectedContext:
        policy = ARTIFACT_POLICIES[artifact_type]
        fields = policy.required_fields | policy.optional_fields
        return replace(
            parent,
            artifact_type=artifact_type,
            definition_bundle_sha256=(
                parent.definition_bundle_sha256
                if "definition_bundle_sha256" in fields
                else None
            ),
            environment_digest=(
                parent.environment_digest if "environment_digest" in fields else None
            ),
            deployment_id=(parent.deployment_id if "deployment_id" in fields else None),
            workspace_id=(parent.workspace_id if "workspace_id" in fields else None),
        )
