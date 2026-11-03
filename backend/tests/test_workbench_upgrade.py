"""Owned Windows upgrade drills only; no user's runtime or external Provider."""
import asyncio
from dataclasses import dataclass
from datetime import date
import json
import importlib.util
import os
from pathlib import Path
import secrets
import socket
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.domain.roster import CreateClass, CreateStudent
from class_os.infrastructure.local_runtime import LocalRuntime, PROFILES
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure import workbench_upgrade as upgrade


def test_d2_is_same_root_and_database_and_cannot_initialize_an_empty_world(tmp_path):
    assert PROFILES['workbench-d2'][1:] == PROFILES['conversation-d1'][1:]
    runtime = LocalRuntime(tmp_path / 'never-created', profile='workbench-d2')
    with pytest.raises(RuntimeError, match='in-place upgrade'):
        runtime.initialize('not-a-binary-path')
    with pytest.raises(RuntimeError, match='verified workbench upgrade'):
        runtime.upgrade()
    assert not runtime.root.exists()


def test_descriptor_only_patches_profile_preserving_crlf_bytes(tmp_path):
    runtime = LocalRuntime(tmp_path / 'descriptor', profile='conversation-d1')
    runtime.root.mkdir()
    value = {'profile': PROFILES['conversation-d1'][0], 'pg_bin': 'synthetic-binaries',
             'port': 23456, 'database': PROFILES['conversation-d1'][1]}
    raw = json.dumps(value, indent=2).replace('\n', '\r\n').encode('utf-8')
    runtime.manifest.write_bytes(raw)
    current, (source, target) = upgrade.descriptor(runtime)
    assert current.profile == 'conversation-d1' and source == raw
    assert target.replace(PROFILES['workbench-d2'][0].encode(), PROFILES['conversation-d1'][0].encode()) == raw
    assert b'\r\n' in target and not target.startswith(b'\xef\xbb\xbf')
    runtime.manifest.write_bytes(target)
    current, again = upgrade.descriptor(runtime)
    assert current.profile == 'workbench-d2' and again == (source, target)


def test_known_owned_service_listener_blocks_upgrade_preflight(tmp_path, monkeypatch):
    repository = tmp_path / 'repository'
    monkeypatch.setattr(upgrade, '__file__', str(repository / 'backend/src/class_os/infrastructure/workbench_upgrade.py'))
    root = tmp_path / 'owned-root'
    source = repository / 'apps/desktop/.build/runtime-d1/runtime-source.json'
    source.parent.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        source.write_text(json.dumps({'runtimeRoot': str(root), 'servicePort': listener.getsockname()[1]}), encoding='utf-8')
        with pytest.raises(upgrade.UpgradeRejected):
            upgrade.known_service_stopped(SimpleNamespace(root=root.resolve()))
        upgrade.known_service_stopped(SimpleNamespace(root=(tmp_path / 'different-root').resolve()))


@pytest.mark.parametrize('arguments', [
    ['upgrade-workbench'], ['init', '--profile', 'workbench-d2'],
    ['migrate', '--profile', 'workbench-d2'], ['bootstrap', '--profile', 'workbench-d2'],
    ['initialize-control', '--profile', 'workbench-d2'],
])
def test_operator_rejects_wrong_profile_and_d2_bootstrap_before_runtime(arguments, monkeypatch):
    spec = importlib.util.spec_from_file_location('classmatter_upgrade_cli_test', Path(__file__).resolve().parents[1] / 'local.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(sys, 'argv', ['local.py', *arguments])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


@dataclass
class Owned:
    runtime: LocalRuntime
    classroom: CreateClass
    student_id: object
    thread_id: object
    owner_id: object
    workspace_id: object
    password: str


@pytest.fixture
def owned_upgrade(tmp_path, request):
    from class_os.infrastructure.durable_local_runtime import open_services
    from class_os.infrastructure.durable_agent import DurableChatRuntime
    from class_os.infrastructure.agent import PydanticAgentRuntime
    runtime = LocalRuntime(tmp_path / 'owned-upgrade', profile='conversation-d1')
    runtime.initialize(request.config.getoption('--pg-root')); runtime.start()
    setup, services = NativeSetup(runtime, development=True), None
    try:
        cookies = setup.handle({'operation': 'development_access'})['cookies']
        password = setup._developer_password()
        services = open_services(runtime)
        credentials = (cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id)
        classroom = CreateClass(uuid4(), uuid4(), '合成原班级', '合成学期', date(2026, 9, 1), date(2027, 6, 30))
        proposal = services.worker.preview(*credentials, classroom)
        approval = services.worker.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
        services.worker.commit(*credentials, proposal.proposal_id, uuid4(), approval)
        student_id = uuid4()
        proposal = services.worker.preview(*credentials, CreateStudent(student_id, classroom.class_id, classroom.term_id, 1, '合成原学生'))
        services.worker.commit(*credentials, proposal.proposal_id, uuid4())
        thread = uuid4()
        services.worker.create_conversation(*credentials, classroom.class_id, classroom.term_id, thread, uuid4(), '合成原对话')
        sdk = DurableChatRuntime(services.worker, services.query, PydanticAgentRuntime(services.query))
        async def turn():
            events = [event async for event in sdk.stream(credentials, classroom.class_id, classroom.term_id,
                thread, uuid4(), '合成升级前消息', 'chat')]
            assert any(event.type == 'run.completed' for event in events)
        asyncio.run(turn())
        value = Owned(runtime, classroom, student_id, thread, services.owner_id, services.restrictions.workspace_id, password)
        services.close(); services = None
        setup.close()
        yield value
    finally:
        if services is not None:
            services.close()
        setup.close()
        marker = json.loads(runtime.manifest.read_text(encoding='utf-8'))['profile']
        profile = 'workbench-d2' if marker == PROFILES['workbench-d2'][0] else 'conversation-d1'
        LocalRuntime(runtime.root, profile=profile).stop()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual owned Windows SCRAM/DPAPI upgrade')
def test_verified_upgrade_preserves_owner_class_student_and_completed_chat(owned_upgrade):
    from class_os.infrastructure.workbench_local_runtime import open_services
    value = owned_upgrade
    source = value.runtime.manifest.read_bytes()
    current = upgrade.upgrade_workbench(value.runtime)
    assert current.root == value.runtime.root and current.configuration()['database'] == PROFILES['conversation-d1'][1]
    assert upgrade.verify_upgrade_receipt(current)['backup_id']
    assert source != current.manifest.read_bytes()
    services = open_services(current)
    try:
        client = secrets.token_urlsafe(32)
        auth = services.identity.login(value.password, client)
        credentials = (auth.token, client, auth.csrf, value.workspace_id)
        assert auth.subject.owner_id == value.owner_id
        assert services.query.context(*credentials).class_id == value.classroom.class_id
        assert services.query.roster(*credentials, value.classroom.class_id, value.classroom.term_id)[0].student_id == value.student_id
        history = services.query.conversation_page(*credentials, value.classroom.class_id, value.classroom.term_id, value.thread_id)
        assert len(history.value.history.messages) == 2 and history.value.history.title == '合成原对话'
        assert services.query.page(*credentials, value.classroom.class_id, value.classroom.term_id)['data'] == ()
        from class_os.infrastructure.workbench_local_runtime import compose
        from class_os.interfaces.http.settings import Settings
        import httpx
        app = compose(Settings(), current)
        async def inspect():
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000') as api:
                    for name, item in zip(('session', 'client', 'csrf'), credentials[:3]):
                        api.cookies.set('class_os_' + name, item, path='/api')
                    base = f'/api/workspaces/{value.workspace_id}'
                    response = await api.get(base + '/workbench-d2/capabilities')
                    assert response.status_code == 200 and response.json()['profile'] == 'workbench-d2'
                    assert response.json()['complete_exit'] is False
                    assert (await api.get(base + '/conversation-d1/capabilities')).status_code == 404
                    response = await api.get(base + f'/classes/{value.classroom.class_id}/terms/{value.classroom.term_id}/documents')
                    assert response.status_code == 200 and response.json()['data'] == []
        asyncio.run(inspect())
        services.identity.logout(auth.token, client, auth.csrf)
    finally:
        services.close()
    assert upgrade.upgrade_workbench(current).root == current.root
    native = NativeSetup(current, development=True)
    try:
        first = native.handle({'operation': 'development_access'})['cookies']
        rotated = native.handle({'operation': 'development_reauthenticate', **first})['cookies']
        assert rotated['client'] == first['client'] and rotated['session'] != first['session']
        assert native.status() == {'owner_present': True, 'ready': True}
        assert native._developer_password() == value.password
        with pytest.raises(ValueError, match='Owner already exists'):
            native.create_owner(secrets.token_urlsafe(48))
        personal = NativeSetup(current)
        with pytest.raises(ValueError, match='Explicit local development'):
            personal.development_access()
        personal.close()
    finally:
        native.close()
    journal = current.root / upgrade.JOURNAL
    original = journal.read_bytes()
    try:
        journal.write_bytes(b'corrupted synthetic upgrade proof')
        with pytest.raises(Exception):
            open_services(current)
    finally:
        journal.write_bytes(original)


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual owned Windows SCRAM/DPAPI upgrade')
def test_sql_commit_then_descriptor_failure_resumes_forward_without_reset(owned_upgrade, monkeypatch):
    value = owned_upgrade
    source = value.runtime.manifest.read_bytes()
    original = upgrade.publish_manifest
    monkeypatch.setattr(upgrade, 'publish_manifest', lambda *args: (_ for _ in ()).throw(OSError()))
    with pytest.raises(upgrade.UpgradeRejected):
        upgrade.upgrade_workbench(value.runtime)
    assert value.runtime.manifest.read_bytes() == source
    database = value.runtime.database('migrator')
    try:
        with database.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() == '0027'
            assert connection.execute(text('SELECT count(*) FROM class_os.student')).scalar_one() == 1
    finally:
        database.close()
    old_plan = upgrade.load_plan(value.runtime, *upgrade.descriptor(value.runtime)[1])
    monkeypatch.setattr(upgrade, 'publish_manifest', original)
    current = upgrade.upgrade_workbench(value.runtime)
    assert upgrade.verify_upgrade_receipt(current)['backup_id'] == old_plan['backup_id']


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual owned Windows SCRAM/DPAPI upgrade')
def test_failed_migration_rolls_back_and_keeps_verified_backup(owned_upgrade, monkeypatch):
    value = owned_upgrade
    source = value.runtime.manifest.read_bytes()
    original = upgrade.migrate
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('synthetic post-DDL fault before commit')
    monkeypatch.setattr(upgrade, 'migrate', interrupted)
    with pytest.raises(upgrade.UpgradeRejected):
        upgrade.upgrade_workbench(value.runtime)
    assert value.runtime.manifest.read_bytes() == source
    database = value.runtime.database('migrator')
    try:
        with database.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() == '0026'
            assert connection.execute(text("SELECT to_regclass('class_os.working_document')")).scalar_one() is None
    finally:
        database.close()
    assert (value.runtime.root / upgrade.JOURNAL).is_file()
    monkeypatch.setattr(upgrade, 'migrate', original)
    assert upgrade.upgrade_workbench(value.runtime).profile == 'workbench-d2'
    assert len(list((value.runtime.root / 'upgrade-history').glob('*.dpapi'))) == 1


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual owned Windows SCRAM/DPAPI upgrade')
def test_connected_application_blocks_upgrade_without_creating_checkpoint(owned_upgrade):
    value = owned_upgrade
    source = value.runtime.manifest.read_bytes()
    client = value.runtime.database('runtime')
    try:
        with client.engine.connect() as connection:
            connection.execute(text('SELECT 1')); connection.commit()
            with pytest.raises(upgrade.UpgradeRejected):
                upgrade.upgrade_workbench(value.runtime)
        assert value.runtime.manifest.read_bytes() == source
        assert not (value.runtime.root / upgrade.JOURNAL).exists()
    finally:
        client.close()
