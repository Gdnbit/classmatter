"""Fixed, append-once source freeze evidence. Never releases target admission."""
from hashlib import sha256
import json
import os
import stat
import tempfile

import rfc8785

from class_os.domain.source_transfer import SourceFence, decode_fence
from .conversation_restrictions import ProtectedConversationRestrictions


FILE_NAME = "conversation-transfer.dpapi"
KIND = "classmatter.source-transfer.v1"
PLAIN_LIMIT = 16384
SEALED_LIMIT = 32768


class TransferUnavailable(Exception):
    def __init__(self):
        super().__init__("Source transfer evidence unavailable; source must remain frozen")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TransferUnavailable()
        result[key] = value
    return result


class ProtectedSourceTransfer:
    def __init__(self, restrictions):
        if type(restrictions) is not ProtectedConversationRestrictions:
            raise ValueError("Owned restriction port required")
        self.restrictions = restrictions

    def present(self):
        """Any directory/link/bad file at the fixed path also freezes source."""
        try:
            root = self.restrictions._root()
            path = root / FILE_NAME
            return path.exists() or path.is_symlink() or path.is_junction()
        except Exception:
            raise TransferUnavailable() from None

    def _packet(self, root, fence):
        if type(fence) is not SourceFence or fence.workspace_id != self.restrictions.workspace_id:
            raise TransferUnavailable()
        return {"schema_version": KIND, "root_binding": self.restrictions._binding(root), "fence": fence.canonical()}

    def digest(self, fence):
        return sha256(rfc8785.dumps(self._packet(self.restrictions._root(), fence))).hexdigest()

    def _read(self, root):
        path = root / FILE_NAME
        before = self.restrictions._safe_file(path)
        if not 0 < before.st_size <= SEALED_LIMIT:
            raise TransferUnavailable()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or not 0 < opened.st_size <= SEALED_LIMIT):
                raise TransferUnavailable()
            sealed = source.read(SEALED_LIMIT + 1)
        if len(sealed) > SEALED_LIMIT:
            raise TransferUnavailable()
        plain = self.restrictions.codec(sealed, decrypt=True)
        if type(plain) is not bytes or not 0 < len(plain) <= PLAIN_LIMIT:
            raise TransferUnavailable()
        packet = json.loads(plain.decode("utf-8"), object_pairs_hook=_unique)
        if type(packet) is not dict or set(packet) != {"schema_version", "root_binding", "fence"}:
            raise TransferUnavailable()
        fence = decode_fence(packet["fence"])
        if self._packet(root, fence) != packet or rfc8785.dumps(packet) != plain:
            raise TransferUnavailable()
        return fence

    def read(self):
        try:
            with self.restrictions._locked() as root:
                return self._read(root)
        except Exception:
            raise TransferUnavailable() from None

    def seal(self, fence):
        """File-first, exclusive. A failed SQL commit must not undo this file."""
        pending = None
        try:
            with self.restrictions._locked() as root:
                path = root / FILE_NAME
                self.restrictions._safe_file(path, absent=True)
                if path.exists():
                    if self._read(root) != fence:
                        raise TransferUnavailable()
                    return self.digest(fence)
                plain = rfc8785.dumps(self._packet(root, fence))
                if len(plain) > PLAIN_LIMIT:
                    raise TransferUnavailable()
                sealed = self.restrictions.codec(plain)
                if type(sealed) is not bytes or not 0 < len(sealed) <= SEALED_LIMIT:
                    raise TransferUnavailable()
                with tempfile.NamedTemporaryFile(dir=root, prefix=".source-transfer-", suffix=".pending", delete=False) as output:
                    pending = output.name
                    output.write(sealed)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(pending, path)
                if os.name != "nt":
                    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                return self.digest(fence)
        except Exception:
            raise TransferUnavailable() from None
        finally:
            if pending is not None:
                try:
                    os.unlink(pending)
                except OSError:
                    raise TransferUnavailable() from None
