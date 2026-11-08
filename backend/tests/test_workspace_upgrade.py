"""Actual owned-root upgrade and descriptor-failure recovery, synthetic only."""
import asyncio
import os
from uuid import uuid4

import pytest

from class_os.infrastructure import workspace_upgrade as upgrade
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from test_workbench_upgrade import owned_upgrade
from class_os.infrastructure.local_runtime import LocalRuntime


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI runtime')
def test_d1_upgrade_and_workspace_chat_survive_restart(owned_upgrade):
    value = owned_upgrade
    current = upgrade.upgrade_workspace_chat(value.runtime)
    assert current.profile == 'workspace-chat-d3' and current.root == value.runtime.root
    assert upgrade.verify_upgrade_receipt(current)['backup_id']
    assert upgrade.upgrade_workspace_chat(current).root == current.root
    native = NativeSetup(current, development=True)
    try:
        cookies = native.handle({'operation': 'development_access'})['cookies']
        assert native.status() == {'owner_present': True, 'ready': True}
    finally:
        native.close()
    auth = (cookies['session'], cookies['client'], cookies['csrf'], value.workspace_id)
    thread, request = uuid4(), uuid4()
    services = open_services(current)
    try:
        assert services.owner_id == value.owner_id
        assert services.query.context(*auth).class_id == value.classroom.class_id
        # Inspect the preserved legacy component through its original validator.
        with services.query.store.atomic() as tx:
            tx.authorized_at = services.query.clock()
            tx.conversation_page({'workspace_id': value.workspace_id, 'actor_id': value.owner_id},
                value.classroom.class_id, value.classroom.term_id, value.thread_id)
        legacy = services.query.conversation_page(*auth, value.classroom.class_id, value.classroom.term_id, value.thread_id)
        assert len(legacy.value.history.messages) == 2
        business = WorkspaceChatBusinessGateway(services.identity, services.worker.store)
        query = WorkspaceChatQueryGateway(services.identity, services.query.store)
        business.send(auth, thread, request, '合成持久化工作区聊天')
        runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(services.query))
        async def run():
            events = [event async for event in runtime.stream_queued(auth, thread, request)]
            assert any(event.type == 'run.completed' for event in events)
        asyncio.run(run())
    finally:
        services.close()
    services = open_services(current)
    try:
        query = WorkspaceChatQueryGateway(services.identity, services.query.store)
        history = query.history(auth, thread)
        assert history['turns'][0]['state'] == 'completed'
        assert history['turns'][0]['user_text'] == '合成持久化工作区聊天'
    finally:
        services.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI runtime')
def test_d3_descriptor_failure_resumes_forward(owned_upgrade, monkeypatch):
    current = upgrade.upgrade_workbench(owned_upgrade.runtime)
    source = current.manifest.read_bytes()
    publish = upgrade.publish_manifest
    def reject(*args):
        raise OSError('Synthetic publication failure')
    monkeypatch.setattr(upgrade, 'publish_manifest', reject)
    with pytest.raises(upgrade.UpgradeRejected):
        upgrade.upgrade_workspace_chat(current)
    assert current.manifest.read_bytes() == source
    monkeypatch.setattr(upgrade, 'publish_manifest', publish)
    resumed = upgrade.upgrade_workspace_chat(current)
    services = open_services(resumed)
    try:
        assert services.owner_id == owned_upgrade.owner_id
    finally:
        services.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI runtime')
def test_fresh_developer_preparation_is_one_explicit_non_overwriting_operation(tmp_path, request):
    runtime = LocalRuntime(tmp_path / 'fresh-workspace-chat', profile='conversation-d1')
    current = upgrade.prepare_workspace_chat(runtime, request.config.getoption('--pg-root'))
    try:
        assert current.profile == 'workspace-chat-d3'
        assert (current.root / 'developer-identity.dpapi').is_file()
        setup = NativeSetup(current, development=True)
        try:
            assert setup.status() == {'owner_present': True, 'ready': True}
        finally:
            setup.close()
        with pytest.raises(upgrade.UpgradeRejected):
            upgrade.prepare_workspace_chat(runtime, request.config.getoption('--pg-root'))
    finally:
        current.stop()
