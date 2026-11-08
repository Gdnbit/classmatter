"""Explicitly enabled model preference for the current local desktop only.

No keys, messages, business facts, tools or arbitrary settings are stored here.
The controller still checks the exact current QG configuration before each run.
"""
import json
import os
from uuid import UUID, uuid4

from class_os.domain.model_configuration import ModelConfiguration, Protocol, ConfigurationRejected, validate_model_proxy
from .local_runtime import protect


class LocalModelActivation:
    def __init__(self, root, workspace_id, *, proxy=None, codec=protect):
        self.path = root / 'model-activation.dpapi'
        self.workspace_id, self.proxy, self.codec = workspace_id, validate_model_proxy(proxy), codec

    def read(self):
        if not self.path.exists():
            return None
        try:
            if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > 8192:
                raise ConfigurationRejected()
            value = json.loads(self.codec(self.path.read_bytes(), decrypt=True))
            if (type(value) is not dict or set(value) != {'kind', 'workspace_id', 'candidate_id', 'version', 'base_url', 'proxy'}
                    or value['kind'] != 'classmatter.local-model-activation.v1'
                    or value['workspace_id'] != str(self.workspace_id)):
                raise ConfigurationRejected()
            if value['candidate_id'] is None:
                if value['version'] != 0 or value['base_url'] is not None or value['proxy'] is not None:
                    raise ConfigurationRejected()
                return None
            UUID(value['candidate_id'])
            if type(value['version']) is not int or not 1 <= value['version'] <= 2147483647:
                raise ConfigurationRejected()
            ModelConfiguration(Protocol.CHAT, 'local-activation', value['base_url'])
            validate_model_proxy(value['proxy'])
            return value
        except Exception:
            raise ConfigurationRejected() from None

    def write(self, row):
        value = {'kind': 'classmatter.local-model-activation.v1', 'workspace_id': str(self.workspace_id),
            'candidate_id': str(row['candidate_id']) if row else None, 'version': row['version'] if row else 0,
            'base_url': row['base_url'] if row else None, 'proxy': self.proxy if row else None}
        # Atomic replacement preserves the previous preference on failure.
        temporary = self.path.with_name(self.path.name + '.' + uuid4().hex + '.pending')
        try:
            with temporary.open('xb') as target:
                target.write(self.codec(json.dumps(value).encode('utf-8')))
                target.flush(); os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.is_file() and not temporary.is_symlink():
                temporary.unlink()
