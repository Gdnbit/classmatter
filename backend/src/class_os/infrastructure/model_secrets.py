"""Bounded protected candidates; codec is explicitly owned by composition."""
from datetime import datetime, timedelta, timezone
import json
from threading import RLock
from uuid import UUID, uuid4

from pydantic import SecretStr

from class_os.application.identity import digest
from class_os.domain.model_configuration import ConfigurationRejected, ModelConfiguration
from class_os.domain.model_control import ModelControl


class ModelSecrets:
    def __init__(self, codec, *, clock=lambda: datetime.now(timezone.utc)):
        self.codec, self.clock = codec, clock
        self._items, self._lock = {}, RLock()

    @staticmethod
    def binding(credentials):
        return (digest(credentials[0]), digest(credentials[1]), digest(credentials[2]), credentials[3])

    def stage(self, credentials, profile, key, version):
        if (type(profile) is not ModelConfiguration or type(key) is not str or not 1 <= len(key) <= 2048
                or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            raise ConfigurationRejected()
        command = ModelControl("model_configuration.save", uuid4(), version, profile.protocol.value, profile.model, profile.base_url)
        packet = {"kind": "class-os.model-secret.v1", "workspace_id": str(credentials[3]),
                  "candidate_id": str(command.candidate_id), "version": version + 1,
                  "protocol": profile.protocol.value, "model": profile.model, "base_url": profile.base_url, "key": key}
        try:
            sealed = self.codec(json.dumps(packet, separators=(",", ":")).encode())
            if type(sealed) is not bytes or not 1 <= len(sealed) <= 16384:
                raise ConfigurationRejected()
        except Exception:
            raise ConfigurationRejected() from None
        with self._lock:
            now = self.clock()
            self._items = {k: v for k, v in self._items.items() if now < v[0]}
            if len(self._items) >= 32:
                raise ConfigurationRejected()
            self._items[command.candidate_id] = (now + timedelta(minutes=10), self.binding(credentials), command, sealed)
        return command

    def get(self, binding, command):
        if type(binding) is dict:
            binding = (binding["session_digest"], binding["client_digest"], binding["csrf_digest"], binding["workspace_id"])
        with self._lock:
            item = self._items.get(command.candidate_id)
            if item is None or self.clock() >= item[0] or item[1] != binding or item[2] != command:
                raise ConfigurationRejected()
            return item[3]

    def open(self, workspace, candidate, version, profile, blob):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ConfigurationRejected()
                result[key] = value
            return result
        try:
            if (type(workspace) is not UUID or type(candidate) is not UUID or type(version) is not int
                    or version < 1 or type(profile) is not ModelConfiguration):
                raise ConfigurationRejected()
            if type(blob) is not bytes or not 1 <= len(blob) <= 16384:
                raise ConfigurationRejected()
            packet = json.loads(self.codec(blob, decrypt=True), object_pairs_hook=unique)
            expected = {"kind": "class-os.model-secret.v1", "workspace_id": str(workspace), "candidate_id": str(candidate),
                        "version": version, "protocol": profile.protocol.value, "model": profile.model, "base_url": profile.base_url}
            if (type(packet) is not dict or set(packet) != {*expected, "key"}
                    or any(packet[k] != v for k, v in expected.items()) or type(packet["version"]) is not int
                    or type(packet["key"]) is not str or not 1 <= len(packet["key"]) <= 2048
                    or any(ord(c) < 33 or ord(c) > 126 for c in packet["key"])):
                raise ConfigurationRejected()
            return SecretStr(packet["key"])
        except Exception:
            raise ConfigurationRejected() from None
