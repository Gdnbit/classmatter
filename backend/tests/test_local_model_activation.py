"""Local model continuity, not permission to change a model or replay a turn."""
from uuid import uuid4

import pytest

from class_os.domain.model_configuration import ConfigurationRejected
from class_os.domain.model_control import ModelControl
from class_os.infrastructure.local_model_activation import LocalModelActivation
from class_os.infrastructure.model_control import ModelController
from test_model_secrets import fixture_codec
from test_model_control import controlled, save, roster, identity, URL


def test_activation_contains_only_exact_nonsecret_selection_and_disable(tmp_path):
    workspace, candidate = uuid4(), uuid4()
    store = LocalModelActivation(tmp_path, workspace, proxy='http://127.0.0.1:7890', codec=fixture_codec)
    assert store.read() is None
    row = {'candidate_id': candidate, 'version': 1, 'base_url': URL}
    store.write(row)
    selected = store.read()
    assert selected['candidate_id'] == str(candidate)
    assert set(selected) == {'kind', 'workspace_id', 'candidate_id', 'version', 'base_url', 'proxy'}
    assert selected['proxy'] == 'http://127.0.0.1:7890'
    with pytest.raises(ConfigurationRejected):
        LocalModelActivation(tmp_path, uuid4(), codec=fixture_codec).read()
    store.write(None)
    assert store.read() is None
    assert not list(tmp_path.glob('*.pending'))
    store.path.write_bytes(b'not-a-valid-selection')
    with pytest.raises(ConfigurationRejected):
        store.read()


@pytest.mark.db
async def test_restart_restores_only_tested_enabled_version_and_disable_persists(controlled, roster, tmp_path):
    controller, vault, runtime, calls, _, _ = controlled
    business, query, _, auth, _, _, clock = roster
    store = LocalModelActivation(tmp_path, auth[3], codec=fixture_codec)
    controller.activation = store
    command, _ = save(roster, vault)
    assert store.read() is None  # Saving a Key is not permission to invoke it.
    assert await controller.test(auth, command.candidate_id, 1, uuid4())
    await controller.enable(auth, command.candidate_id, 1)
    count = len(calls)
    resumed = ModelController(query, vault, runtime, allowed_bases=(URL,), client_factory=controller.client_factory,
        clock=lambda: clock[0], activation=store)
    status = await resumed.status(auth)
    assert status['mode'] == 'configured-api' and not status['test_passed']
    assert len(calls) == count  # Restore/status never tests, invokes or replays.
    blocked = ModelController(query, vault, runtime, allowed_bases=(), activation=store)
    assert (await blocked.status(auth))['mode'] == 'stale'
    clear = ModelControl('model_configuration.clear', uuid4(), 1)
    proposal = business.preview(*auth, clear)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    business.commit(*auth, proposal.proposal_id, uuid4(), approval)
    assert (await resumed.status(auth))['mode'] == 'stale'
    with pytest.raises(ConfigurationRejected):
        async with resumed.context(auth, None):
            pytest.fail('Stale selection must not yield a real or fake model')
    await resumed.disable(auth)
    reopened = ModelController(query, vault, runtime, allowed_bases=(URL,), activation=store)
    assert (await reopened.status(auth))['mode'] == 'offline'
    assert len(calls) == count
