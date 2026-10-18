import base64
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest

from class_os.domain.model_configuration import ModelConfiguration, Protocol, ConfigurationRejected
from class_os.infrastructure.model_secrets import ModelSecrets


def fixture_codec(value, *, decrypt=False):
    """Serialization fixture ONLY, not encryption/deployment evidence."""
    return base64.b64decode(value) if decrypt else base64.b64encode(value)


def test_staged_secret_bound_to_session_expiry_and_closed_command():
    clock = [datetime(2026, 10, 14, tzinfo=timezone.utc)]
    vault = ModelSecrets(fixture_codec, clock=lambda: clock[0])
    auth = ("synthetic-token", "synthetic-client", "synthetic-csrf", uuid4())
    profile = ModelConfiguration(Protocol.CHAT, "synthetic", "http://127.0.0.1/v1")
    command = vault.stage(auth, profile, "synthetic-secret-canary", 0)
    assert "synthetic-secret-canary" not in str(command.canonical())
    binding = vault.binding(auth)
    blob = vault.get(binding, command)
    assert b"synthetic-secret-canary" not in blob
    assert vault.open(auth[3], command.candidate_id, 1, profile, blob).get_secret_value() == "synthetic-secret-canary"
    with pytest.raises(ConfigurationRejected):
        vault.get(vault.binding(("other", *auth[1:])), command)
    clock[0] += timedelta(minutes=10)
    with pytest.raises(ConfigurationRejected):
        vault.get(binding, command)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI evidence only")
def test_real_dpapi_model_secret_round_trip_and_wrong_binding():
    from class_os.infrastructure.local_runtime import protect
    vault = ModelSecrets(protect)
    auth = ("synthetic-token", "synthetic-client", "synthetic-csrf", uuid4())
    profile = ModelConfiguration(Protocol.RESPONSES, "synthetic", "https://provider.invalid/v1")
    command = vault.stage(auth, profile, "synthetic-dpapi-model-secret", 0)
    blob = vault.get(vault.binding(auth), command)
    assert b"synthetic-dpapi-model-secret" not in blob
    assert vault.open(auth[3], command.candidate_id, 1, profile, blob).get_secret_value() == "synthetic-dpapi-model-secret"
    for workspace, version in ((uuid4(), 1), (auth[3], 2)):
        with pytest.raises(ConfigurationRejected):
            vault.open(workspace, command.candidate_id, version, profile, blob)
