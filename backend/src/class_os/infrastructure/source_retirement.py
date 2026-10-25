"""Fixed append-once source retirement evidence outside SQL checkpoints."""
from hashlib import sha256
import json
import os
import stat
import tempfile

import rfc8785

from class_os.domain.source_retirement import RetirementFence, decode_retirement_fence
from .conversation_restrictions import ProtectedConversationRestrictions
from .source_transfer import _unique


FILE_NAME = "conversation-retirement.dpapi"
KIND = "classmatter.source-retirement.v1"
LIMIT = 16384


class RetirementUnavailable(Exception):
    def __init__(self):
        super().__init__("Retirement evidence unavailable; source remains frozen")


class ProtectedSourceRetirement:
    def __init__(self, restrictions):
        if type(restrictions) is not ProtectedConversationRestrictions:
            raise ValueError("Owned restriction port required")
        self.restrictions = restrictions

    def present(self):
        try:
            path = self.restrictions._root() / FILE_NAME
            return path.exists() or path.is_symlink() or path.is_junction()
        except Exception:
            raise RetirementUnavailable() from None

    def _packet(self, root, fence):
        if (type(fence) is not RetirementFence or fence.source.fence.workspace_id != self.restrictions.workspace_id
                or fence.source.root_binding != self.restrictions._binding(root)):
            raise RetirementUnavailable()
        return {"schema_version": KIND, "root_binding": self.restrictions._binding(root), "fence": fence.canonical()}

    def digest(self, fence):
        return sha256(rfc8785.dumps(self._packet(self.restrictions._root(), fence))).hexdigest()

    def _read(self, root):
        path = root / FILE_NAME
        before = self.restrictions._safe_file(path)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or not 0 < opened.st_size <= 2 * LIMIT):
                raise RetirementUnavailable()
            sealed = source.read(2 * LIMIT + 1)
        if len(sealed) > 2 * LIMIT:
            raise RetirementUnavailable()
        plain = self.restrictions.codec(sealed, decrypt=True)
        if type(plain) is not bytes or not 0 < len(plain) <= LIMIT:
            raise RetirementUnavailable()
        packet = json.loads(plain.decode("utf-8"), object_pairs_hook=_unique)
        if type(packet) is not dict or set(packet) != {"schema_version", "root_binding", "fence"}:
            raise RetirementUnavailable()
        fence = decode_retirement_fence(packet["fence"])
        if self._packet(root, fence) != packet or rfc8785.dumps(packet) != plain:
            raise RetirementUnavailable()
        return fence

    def read(self):
        try:
            with self.restrictions._locked() as root:
                return self._read(root)
        except Exception:
            raise RetirementUnavailable() from None

    def retire(self, fence):
        pending = None
        try:
            with self.restrictions._locked() as root:
                path = root / FILE_NAME
                self.restrictions._safe_file(path, absent=True)
                packet = rfc8785.dumps(self._packet(root, fence))
                if path.exists():
                    if self._read(root) != fence:
                        raise RetirementUnavailable()
                    return sha256(packet).hexdigest()
                if len(packet) > LIMIT:
                    raise RetirementUnavailable()
                sealed = self.restrictions.codec(packet)
                if type(sealed) is not bytes or not 0 < len(sealed) <= 2 * LIMIT:
                    raise RetirementUnavailable()
                with tempfile.NamedTemporaryFile(dir=root, prefix=".source-retirement-", suffix=".pending", delete=False) as output:
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
                return sha256(packet).hexdigest()
        except Exception:
            raise RetirementUnavailable() from None
        finally:
            if pending is not None:
                try:
                    os.unlink(pending)
                except OSError:
                    raise RetirementUnavailable() from None
