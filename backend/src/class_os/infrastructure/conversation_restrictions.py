"""Owned local restriction evidence, NOT a business store or read authorization.

BCG integration must persist the returned head, validate scope and audit the clear.
An ahead file never authorizes a read. Missing files must not be auto-initialized.
No same-host file proves freshness after rollback of the entire host filesystem.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from uuid import UUID

import rfc8785

from .local_runtime import protect


KIND = "classmatter.conversation-restrictions.v1"
MAX_ENTRIES = 4096
PLAIN_LIMIT = 1024 * 1024
SEALED_LIMIT = 2 * PLAIN_LIMIT
FILE_NAME = "conversation-restrictions.dpapi"
LOCK_NAME = ".conversation-restrictions.lock"


class RestrictionUnavailable(Exception):
    def __init__(self):
        super().__init__("Conversation restriction control unavailable; no history release authorized")


def _uuid(value):
    if type(value) is not UUID:
        raise ValueError("Invalid restriction identifier")


@dataclass(frozen=True)
class RestrictionHead:
    authority_id: UUID
    workspace_id: UUID
    epoch: int
    digest: str

    def __post_init__(self):
        _uuid(self.authority_id)
        _uuid(self.workspace_id)
        if (type(self.epoch) is not int or not 0 <= self.epoch <= MAX_ENTRIES
                or type(self.digest) is not str or len(self.digest) != 64
                or any(c not in "0123456789abcdef" for c in self.digest)):
            raise ValueError("Invalid restriction head")


@dataclass(frozen=True)
class ClearMarker:
    thread_id: UUID
    version_after: int
    restricted_at: datetime

    def __post_init__(self):
        _uuid(self.thread_id)
        if (type(self.version_after) is not int or not 2 <= self.version_after <= 2147483647
                or type(self.restricted_at) is not datetime or self.restricted_at.tzinfo is None
                or self.restricted_at.utcoffset() != timedelta(0)):
            raise ValueError("Invalid restriction marker")

    def canonical(self):
        return {"thread_id": str(self.thread_id), "version_after": self.version_after,
                "restricted_at": self.restricted_at.isoformat()}


@dataclass(frozen=True)
class RestrictionSnapshot:
    head: RestrictionHead
    markers: tuple[ClearMarker, ...]


@dataclass(frozen=True)
class RestrictionComparison:
    # one-ahead is an unresolved restriction, not a successful business clear.
    state: str
    snapshot: RestrictionSnapshot
    pending: ClearMarker | None = None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RestrictionUnavailable()
        result[key] = value
    return result


class ProtectedConversationRestrictions:
    """Fixed-file port for a trusted composition; never accepts a caller filename.

    File locking protects cooperating processes only. This is not defense against
    malicious code running as the same OS user. Owner ACLs are provided by the
    existing owned runtime; the portable test codec is not encryption evidence.
    """
    def __init__(self, root, workspace_id, *, codec=protect):
        _uuid(workspace_id)
        root = Path(root)
        if not root.is_absolute():
            raise ValueError("Owned restriction root must be absolute")
        self.root, self.workspace_id, self.codec = root, workspace_id, codec

    def _root(self):
        # Check BEFORE resolve: resolving first would hide a supplied symlink.
        if (not self.root.is_dir() or any(p.is_symlink() or p.is_junction()
                                         for p in (self.root, *self.root.parents))):
            raise RestrictionUnavailable()
        return self.root.resolve()

    @staticmethod
    def _safe_file(path, *, absent=False):
        if path.is_symlink() or path.is_junction():
            raise RestrictionUnavailable()
        try:
            value = path.lstat()
        except FileNotFoundError:
            if absent:
                return None
            raise RestrictionUnavailable() from None
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise RestrictionUnavailable()
        return value

    @contextmanager
    def _locked(self):
        root = self._root()
        path = root / LOCK_NAME
        self._safe_file(path, absent=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        locked = False
        try:
            current, opened = self._safe_file(path), os.fstat(descriptor)
            if (opened.st_nlink != 1 or not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
                raise RestrictionUnavailable()
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            yield root
        finally:
            try:
                if locked:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _binding(self, root):
        return hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()

    def _packet(self, root, authority, markers):
        return {"schema_version": KIND, "root_binding": self._binding(root),
                "authority_id": str(authority), "workspace_id": str(self.workspace_id),
                "entries": [marker.canonical() for marker in markers]}

    def _snapshot(self, root, authority, markers):
        digest = hashlib.sha256(rfc8785.dumps(self._packet(root, authority, markers))).hexdigest()
        return RestrictionSnapshot(RestrictionHead(authority, self.workspace_id, len(markers), digest), markers)

    def _read(self, root):
        path = root / FILE_NAME
        before = self._safe_file(path)
        if not 0 < before.st_size <= SEALED_LIMIT:
            raise RestrictionUnavailable()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or not 0 < opened.st_size <= SEALED_LIMIT):
                raise RestrictionUnavailable()
            sealed = source.read(SEALED_LIMIT + 1)
        if len(sealed) > SEALED_LIMIT:
            raise RestrictionUnavailable()
        plain = self.codec(sealed, decrypt=True)
        if type(plain) is not bytes or not 0 < len(plain) <= PLAIN_LIMIT:
            raise RestrictionUnavailable()
        packet = json.loads(plain.decode("utf-8"), object_pairs_hook=_unique)
        if (type(packet) is not dict
                or set(packet) != {"schema_version", "root_binding", "authority_id", "workspace_id", "entries"}
                or packet["schema_version"] != KIND or packet["root_binding"] != self._binding(root)
                or packet["workspace_id"] != str(self.workspace_id)
                or type(packet["authority_id"]) is not str
                or type(packet["entries"]) is not list or len(packet["entries"]) > MAX_ENTRIES):
            raise RestrictionUnavailable()
        authority = UUID(packet["authority_id"])
        if str(authority) != packet["authority_id"]:
            raise RestrictionUnavailable()
        markers, seen = [], set()
        for row in packet["entries"]:
            if (type(row) is not dict or set(row) != {"thread_id", "version_after", "restricted_at"}
                    or type(row["thread_id"]) is not str or type(row["restricted_at"]) is not str):
                raise RestrictionUnavailable()
            marker = ClearMarker(UUID(row["thread_id"]), row["version_after"],
                                 datetime.fromisoformat(row["restricted_at"]))
            if (marker.canonical() != row or marker.thread_id in seen
                    or markers and marker.restricted_at < markers[-1].restricted_at):
                raise RestrictionUnavailable()
            markers.append(marker)
            seen.add(marker.thread_id)
        if rfc8785.dumps(packet) != plain:
            raise RestrictionUnavailable()
        return self._snapshot(root, authority, tuple(markers))

    def _publish(self, root, snapshot, *, initial=False):
        plain = rfc8785.dumps(self._packet(root, snapshot.head.authority_id, snapshot.markers))
        if len(plain) > PLAIN_LIMIT:
            raise RestrictionUnavailable()
        sealed = self.codec(plain)
        if type(sealed) is not bytes or not 0 < len(sealed) <= SEALED_LIMIT:
            raise RestrictionUnavailable()
        path, pending = root / FILE_NAME, None
        try:
            with tempfile.NamedTemporaryFile(dir=root, prefix=".restriction-", suffix=".pending", delete=False) as output:
                pending = Path(output.name)
                output.write(sealed)
                output.flush()
                os.fsync(output.fileno())
            self._safe_file(path, absent=initial)
            if initial:
                # Never replace an existing authority, including on ID collision.
                os.link(pending, path)
            else:
                os.replace(pending, path)
            if os.name != "nt":
                descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    def initialize(self, authority_id):
        """Explicit first-use only; caller must prove fresh DB/no existing anchor.

        No existence fallback or implicit reset. An uncertain result must be read
        and reconciled, never retried with a new authority to overwrite the file.
        """
        try:
            _uuid(authority_id)
            with self._locked() as root:
                if (root / FILE_NAME).exists():
                    raise RestrictionUnavailable()
                snapshot = self._snapshot(root, authority_id, ())
                self._publish(root, snapshot, initial=True)
                return snapshot.head
        except Exception:
            raise RestrictionUnavailable() from None

    def read(self):
        try:
            with self._locked() as root:
                return self._read(root)
        except Exception:
            raise RestrictionUnavailable() from None

    def advance(self, expected, marker):
        """Append before DB commit; never roll back this evidence on DB failure."""
        try:
            if type(expected) is not RestrictionHead or type(marker) is not ClearMarker:
                raise RestrictionUnavailable()
            with self._locked() as root:
                current = self._read(root)
                if (current.head != expected or len(current.markers) >= MAX_ENTRIES
                        or any(item.thread_id == marker.thread_id for item in current.markers)
                        or current.markers and marker.restricted_at < current.markers[-1].restricted_at):
                    raise RestrictionUnavailable()
                result = self._snapshot(root, current.head.authority_id, (*current.markers, marker))
                self._publish(root, result)
                return result.head
        except Exception:
            raise RestrictionUnavailable() from None

    def compare(self, expected):
        """Exact or one pending step only. This never grants activation/read access."""
        try:
            if type(expected) is not RestrictionHead:
                raise RestrictionUnavailable()
            with self._locked() as root:
                current = self._read(root)
                if current.head == expected:
                    return RestrictionComparison("aligned", current)
                if current.markers and self._snapshot(root, current.head.authority_id, current.markers[:-1]).head == expected:
                    return RestrictionComparison("one-ahead", current, current.markers[-1])
                raise RestrictionUnavailable()
        except Exception:
            raise RestrictionUnavailable() from None

    def require_current(self, expected):
        result = self.compare(expected)
        if result.state != "aligned":
            raise RestrictionUnavailable()
        return result.snapshot.head
