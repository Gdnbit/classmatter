"""Fixed target-pending evidence; no activation, reset or caller paths."""
from hashlib import sha256
import json
import os
import stat
import tempfile

import rfc8785

from class_os.domain.target_import import TargetFence, decode_target
from .conversation_restrictions import ProtectedConversationRestrictions
from .source_transfer import _unique


FILE_NAME = "conversation-import.dpapi"
KIND = "classmatter.target-import.v1"
LIMIT = 16384


class ImportUnavailable(Exception):
    def __init__(self):
        super().__init__("Target import evidence unavailable; no admission")


class ProtectedTargetImport:
    def __init__(self, restrictions):
        if type(restrictions) is not ProtectedConversationRestrictions:
            raise ValueError("Owned restriction port required")
        self.restrictions = restrictions

    def present(self):
        try:
            path = self.restrictions._root() / FILE_NAME
            return path.exists() or path.is_symlink() or path.is_junction()
        except Exception:
            raise ImportUnavailable() from None

    def _packet(self, root, fence):
        if type(fence) is not TargetFence or fence.workspace_id != self.restrictions.workspace_id:
            raise ImportUnavailable()
        return {"schema_version": KIND, "root_binding": self.restrictions._binding(root), "fence": fence.canonical()}

    def _read(self, root):
        path = root / FILE_NAME
        before = self.restrictions._safe_file(path)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or not 0 < opened.st_size <= 2 * LIMIT):
                raise ImportUnavailable()
            sealed = source.read(2 * LIMIT + 1)
        if len(sealed) > 2 * LIMIT:
            raise ImportUnavailable()
        plain = self.restrictions.codec(sealed, decrypt=True)
        if type(plain) is not bytes or not 0 < len(plain) <= LIMIT:
            raise ImportUnavailable()
        packet = json.loads(plain.decode("utf-8"), object_pairs_hook=_unique)
        if type(packet) is not dict or set(packet) != {"schema_version", "root_binding", "fence"}:
            raise ImportUnavailable()
        fence = decode_target(packet["fence"])
        if self._packet(root, fence) != packet or rfc8785.dumps(packet) != plain:
            raise ImportUnavailable()
        return fence

    def read(self):
        try:
            with self.restrictions._locked() as root:
                return self._read(root)
        except Exception:
            raise ImportUnavailable() from None

    def stage(self, fence):
        pending = None
        try:
            with self.restrictions._locked() as root:
                path = root / FILE_NAME
                self.restrictions._safe_file(path, absent=True)
                packet = rfc8785.dumps(self._packet(root, fence))
                if path.exists():
                    if self._read(root) != fence:
                        raise ImportUnavailable()
                    return sha256(packet).hexdigest()
                if len(packet) > LIMIT:
                    raise ImportUnavailable()
                sealed = self.restrictions.codec(packet)
                if type(sealed) is not bytes or not 0 < len(sealed) <= 2 * LIMIT:
                    raise ImportUnavailable()
                with tempfile.NamedTemporaryFile(dir=root, prefix=".target-import-", suffix=".pending", delete=False) as out:
                    pending = out.name
                    out.write(sealed)
                    out.flush()
                    os.fsync(out.fileno())
                os.link(pending, path)
                if os.name != "nt":
                    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                return sha256(packet).hexdigest()
        except Exception:
            raise ImportUnavailable() from None
        finally:
            if pending is not None:
                try:
                    os.unlink(pending)
                except OSError:
                    raise ImportUnavailable() from None
