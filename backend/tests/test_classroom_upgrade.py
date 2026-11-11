"""Owned Windows checkpointed pack upgrade and retry; synthetic fixture only."""
import os
from uuid import uuid4
import pytest
from class_os.infrastructure.workspace_upgrade import upgrade_workspace_chat
from class_os.infrastructure.classroom_upgrade import upgrade_classroom, verify_upgrade_receipt, UpgradeRejected
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure.operator_backup import SyntheticBackup
from class_os.domain.classroom_work import CreateExam, RecordScore, CreateSeatLayout, AssignSeat
from test_workbench_upgrade import owned_upgrade


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI checkpoint')
def test_d4_upgrade_keeps_world_and_checkpoint_restores_pack(owned_upgrade):
    original = owned_upgrade
    d3 = upgrade_workspace_chat(original.runtime)
    current = upgrade_classroom(d3)
    assert current.root == original.runtime.root and current.profile == 'classroom-work-d4'
    assert verify_upgrade_receipt(current)['backup_id']
    assert upgrade_classroom(current).root == current.root
    native = NativeSetup(current, development=True)
    try:
        cookies = native.handle({'operation': 'development_access'})['cookies']
        assert native.status()['ready']
    finally:
        native.close()
    credentials = cookies['session'], cookies['client'], cookies['csrf'], original.workspace_id
    services = open_services(current, local_development=True)
    try:
        assert services.owner_id == original.owner_id
        assert services.query.context(*credentials).class_id == original.classroom.class_id
        assert services.query.roster(*credentials, original.classroom.class_id, original.classroom.term_id)[0].student_id == original.student_id
        def commit(command):
            proposal = services.worker.preview(*credentials, command)
            approval = services.worker.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
            services.worker.commit(*credentials, proposal.proposal_id, uuid4(), approval)
        c, t = original.classroom.class_id, original.classroom.term_id
        exam, layout = uuid4(), uuid4()
        commit(CreateExam(exam, c, t, '合成迁移月考', '数学', '100'))
        commit(RecordScore(exam, c, t, original.student_id, 0, 'scored', '88.50'))
        commit(CreateSeatLayout(layout, c, t, 2, 3))
        commit(AssignSeat(layout, c, t, 1, original.student_id, 1, 2))
        backup = SyntheticBackup(current, profile='classroom-work-d4')
        artifact = backup.create()
        packet, _ = backup._open(artifact)
        assert packet['inventory']['class_exam']['rows'] == 1
        assert packet['inventory']['exam_result_revision']['rows'] == 1
        assert packet['inventory']['seat_revision']['rows'] == 12
        checked = backup.check_current_restrictions(artifact, services.restrictions)
        assert checked['snapshot_integrity_verified'] and not checked['activation_allowed']
        assert checked['schema_version'] == 'classmatter.classroom-work-backup-check.v1'
    finally:
        services.close()
    services = open_services(current, local_development=True)
    try:
        assert services.query.classroom_read(credentials, c, t, exam_id=exam)['average'] == '88.50'
        assert services.query.classroom_read(credentials, c, t, seating=True)['seats'][1]['student_id'] == original.student_id
        assert len(services.query.conversation_page(*credentials, c, t, original.thread_id).value.history.messages) == 2
    finally:
        services.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI checkpoint')
def test_d4_failed_descriptor_publish_resumes_without_recreating_data(owned_upgrade, monkeypatch):
    from class_os.infrastructure import classroom_upgrade as upgrade
    d3 = upgrade_workspace_chat(owned_upgrade.runtime)
    before = d3.manifest.read_bytes()
    publish = upgrade.publish_manifest
    def unavailable(*args):
        raise OSError('Synthetic descriptor failure')
    monkeypatch.setattr(upgrade, 'publish_manifest', unavailable)
    with pytest.raises(UpgradeRejected):
        upgrade_classroom(d3)
    assert d3.manifest.read_bytes() == before
    monkeypatch.setattr(upgrade, 'publish_manifest', publish)
    current = upgrade_classroom(d3)
    services = open_services(current)
    try:
        assert services.owner_id == owned_upgrade.owner_id
    finally:
        services.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Owned Windows DPAPI checkpoint')
def test_revision29_comparison_upgrade_checkpoints_preserves_chat_and_rolls_back(owned_upgrade, monkeypatch):
    from sqlalchemy import text
    from class_os.infrastructure import classroom_upgrade as upgrade
    from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
    current = upgrade_classroom(upgrade_workspace_chat(owned_upgrade.runtime))
    native = NativeSetup(current, development=True)
    try:
        cookies = native.handle({'operation': 'development_access'})['cookies']
    finally:
        native.close()
    auth = cookies['session'], cookies['client'], cookies['csrf'], owned_upgrade.workspace_id
    services = open_services(current, local_development=True)
    thread, request = uuid4(), uuid4()
    try:
        chats = WorkspaceChatBusinessGateway(services.worker.identity, services.worker.store)
        chats.send(auth, thread, request, '合成旧版历史')
        chats.finish(auth, chats.claim(auth, thread, request), 'completed', '合成旧版回答')
    finally:
        services.close()
    # Reconstruct the exact pre-feature D4 schema in this disposable fixture.
    owner = current.database('migrator')
    try:
        with owner.transaction() as connection:
            connection.execute(text('ALTER TABLE class_os.workspace_chat_turn DROP COLUMN change_preview'))
            connection.execute(text("UPDATE class_os.alembic_version SET version_num='0029'"))
        old_backup = SyntheticBackup(current, profile='classroom-work-d4', legacy_classroom=True)
        checkpoint = old_backup.create()
        assert old_backup.check(checkpoint)['snapshot_integrity_verified']
        migrate = upgrade.migrate
        def fail_after_migration(*args, **kwargs):
            migrate(*args, **kwargs)
            raise RuntimeError('Synthetic interrupted additive migration')
        monkeypatch.setattr(upgrade, 'migrate', fail_after_migration)
        with pytest.raises(UpgradeRejected):
            upgrade_classroom(current)
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() == '0029'
        monkeypatch.setattr(upgrade, 'migrate', migrate)
        upgrade_classroom(current)
        services = open_services(current, local_development=True)
        try:
            row = WorkspaceChatQueryGateway(services.query.identity, services.query.store).turn(auth, thread, request)[1]
            assert row['assistant_text'] == '合成旧版回答' and row['change_preview'] is None
            from class_os.domain.roster import ChangeClass
            context = services.query.context(*auth)
            chats = WorkspaceChatBusinessGateway(services.worker.identity, services.worker.store)
            comparison_request = uuid4()
            chats.send(auth, thread, comparison_request, '合成升级后改班名')
            result = chats.finish(auth, chats.claim(auth, thread, comparison_request), 'completed', '请核对。',
                ChangeClass('class.update', context.class_id, context.term_id, context.version, '合成升级后班').canonical())
            assert result['change_preview']['fields'][0]['before'] == context.name
            backup = SyntheticBackup(current, profile='classroom-work-d4')
            artifact = backup.create()
            assert backup.check_current_restrictions(artifact, services.restrictions)['snapshot_integrity_verified']
        finally:
            services.close()
    finally:
        owner.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI runtime')
def test_d4_native_chat_grades_seats_survive_application_restart(owned_upgrade):
    import socket
    import subprocess
    from pathlib import Path
    current = upgrade_classroom(upgrade_workspace_chat(owned_upgrade.runtime))
    setup = NativeSetup(current, development=True)
    try:
        cookies = setup.handle({'operation': 'development_access'})['cookies']
    finally:
        setup.close()
    auth = cookies['session'], cookies['client'], cookies['csrf'], owned_upgrade.workspace_id
    services = open_services(current, local_development=True)
    try:
        def commit(command):
            proposal = services.worker.preview(*auth, command)
            approval = services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash)
            services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
        c, t = owned_upgrade.classroom.class_id, owned_upgrade.classroom.term_id
        exam, layout = uuid4(), uuid4()
        commit(CreateExam(exam, c, t, '合成桌面月考', '数学', '100'))
        commit(RecordScore(exam, c, t, owned_upgrade.student_id, 0, 'scored', '88.50'))
        commit(CreateSeatLayout(layout, c, t, 2, 3))
        commit(AssignSeat(layout, c, t, 1, owned_upgrade.student_id, 1, 2))
    finally:
        services.close()
    desktop = Path(__file__).resolve().parents[2] / 'apps/desktop'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    built = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'classroom-work-d4'], cwd=desktop,
        capture_output=True, text=True, encoding='utf-8', timeout=120, creationflags=flags)
    assert built.returncode == 0, built.stdout + built.stderr
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    result = subprocess.run(['node', 'tests/workspace-chat-integration.cjs'], cwd=desktop,
        env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(current.root), CLASSMATTER_TEST_SERVICE_PORT=str(port), CLASSMATTER_TEST_PROFILE='classroom-work-d4'),
        capture_output=True, text=True, encoding='utf-8', timeout=180, creationflags=flags)
    assert result.returncode == 0, result.stdout + result.stderr
