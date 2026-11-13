"""Opt-in real-model/native-UI acceptance in a fresh synthetic instance.

Reuses only an already enabled, explicitly approved free model. Never accepts
keys, changes the source model selection, or runs in default tests/CI.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from uuid import UUID, uuid4
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


class OperatorParser(argparse.ArgumentParser):
    def error(self, message):
        # Never echo accidentally supplied credentials in unsupported arguments.
        super().error('Invalid acceptance options; use --help.')


def daily_recovery_checkpoint(history, world, documents):
    """Accept only the original saved fact and its failed/pending linked follow-up."""
    if (history['thread']['status'] != 'active' or history['next_before'] is not None
            or not history['turns'] or len(world['records']) != 1 or world['tasks'] or documents):
        return False
    saved = [turn for turn in history['turns'] if turn['action_receipt']]
    if (len(saved) != 1 or saved[0]['candidate']['command'] != 'record.create'
            or str(world['records'][0]['record_id']) != str(saved[0]['action_receipt']['resource_id'])):
        return False
    last = history['turns'][-1]
    if last['user_text'] != '继续完成上面的任务，只处理尚未完成的步骤。':
        return False
    pending = [turn for turn in history['turns'] if turn['candidate'] and not turn['action_receipt']]
    if last['state'] == 'failed':
        return not pending
    candidate = last['candidate']
    return (last['state'] == 'completed' and isinstance(candidate, dict) and pending == [last]
        and candidate['command'] == 'task.create' and candidate['title'] == '合成作品核对'
        and str(candidate['source_record_id']) == str(world['records'][0]['record_id'])
        and str(candidate['student_id']) == str(world['records'][0]['student_id']))


def main():
    parser = OperatorParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--source-runtime-root', type=Path)
    parser.add_argument('--pg-root', type=Path)
    parser.add_argument('--artifacts-root', type=Path, help='Optional absolute non-system local drive for fresh synthetic acceptance artifacts')
    parser.add_argument('--resume-runtime-root', type=Path, help='Prior isolated fixture only; each scenario validates its declared business checkpoint without resetting data')
    parser.add_argument('--resume-thread-id', type=UUID, help='Existing synthetic conversation for an explicit recovery scenario only')
    parser.add_argument('--provider', choices=('google', 'zhipu', 'zhipu-flash47'), default='google', help='Explicit registered free model only; never an automatic fallback')
    parser.add_argument('--attempts-per-turn', type=int, choices=(1, 2, 3), default=1, help='Explicit test-only UI resends after failed turns; all attempts remain in the report')
    parser.add_argument('--turn-interval-seconds', type=int, choices=(0, 15, 65), default=0, help='Explicit test-only pacing for free provider rate limits; not application latency or automatic retry')
    parser.add_argument('--scenario', choices=('classroom', 'classroom-documents', 'classroom-recovery', 'full-workbench', 'daily-work', 'daily-work-recovery'), default='classroom', help='Daily work checks record/follow-up/wait/end/summary; explicit recovery verifies its original saved checkpoint')
    args = parser.parse_args()
    if not args.live or not args.source_runtime_root or not args.pg_root:
        print(json.dumps({'status': 'blocked', 'reason': 'explicit_live_source_and_pg_required', 'requests': 0}))
        return 2
    if args.scenario in ('full-workbench', 'daily-work') and args.resume_runtime_root:
        print(json.dumps({'status': 'blocked', 'reason': 'daily_work_requires_fresh_fixture' if args.scenario == 'daily-work' else 'full_workbench_requires_fresh_fixture', 'requests': 0}))
        return 2
    if (args.scenario in ('classroom-recovery', 'daily-work-recovery') and (not args.resume_runtime_root or not args.resume_thread_id)
            or args.resume_thread_id and args.scenario not in ('classroom-recovery', 'daily-work-recovery')):
        print(json.dumps({'status': 'blocked', 'reason': 'explicit_recovery_fixture_and_thread_required', 'requests': 0}))
        return 2
    if args.artifacts_root is not None:
        try:
            valid_artifacts = (args.artifacts_root.is_absolute()
                and re.fullmatch(r'[D-Zd-z]:', args.artifacts_root.drive) is not None
                and re.fullmatch(r'[D-Zd-z]:', args.artifacts_root.resolve().drive) is not None)
        except (OSError, RuntimeError, ValueError):
            valid_artifacts = False
        if not valid_artifacts:
            print(json.dumps({'status': 'blocked', 'reason': 'non_system_local_artifacts_root_required', 'requests': 0}))
            return 2
    if os.name != 'nt':
        return 2
    os.environ['PYDANTIC_AI_NO_BANNER'] = '1'
    from class_os.infrastructure.local_runtime import LocalRuntime
    from class_os.infrastructure.native_setup import NativeSetup
    from class_os.infrastructure.workspace_local_runtime import open_services
    from class_os.infrastructure.workspace_upgrade import prepare_workspace_chat
    from class_os.infrastructure.classroom_upgrade import upgrade_classroom
    from class_os.infrastructure.model_control import ModelController
    from class_os.infrastructure.local_model_activation import LocalModelActivation
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.domain.roster import CreateClass, CreateStudent
    services = setup = target_services = runtime = None
    phase = 'source-preflight'
    artifacts = args.artifacts_root or ROOT / 'test-results/live-classroom'
    output = artifacts / uuid4().hex
    output.mkdir(parents=True)
    try:
        if args.provider == 'google':
            source = LocalRuntime(args.source_runtime_root, profile='classroom-work-d4')
            setup = NativeSetup(source, development=True)
            cookies = setup.handle({'operation': 'development_access'})['cookies']
            services = open_services(source, local_development=True)
            auth = (cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id)
            row = services.query.model_configuration(auth)
            selected = LocalModelActivation(source.root, auth[3]).read()
            if not row or not selected or (str(row['candidate_id']), row['version']) != (selected['candidate_id'], selected['version']):
                raise ValueError('Existing enabled model required')
            profile = ModelController.profile(row)
            if profile.model != 'gemini-3.1-flash-lite' or profile.base_url != 'https://generativelanguage.googleapis.com/v1beta/openai/':
                raise ValueError('Existing approved free Gemini configuration required')
            key = services.worker.store.model_secrets.open(auth[3], row['candidate_id'], row['version'], profile, bytes(row['sealed']))
            proxy = selected['proxy']
        else:
            phase = 'registered-provider-preflight'
            # Fixed free model listed in the supplier's model overview. Reuse
            # the user's registered standard key without changing their UI selection.
            from class_os.infrastructure.local_runtime import protect
            from class_os.domain.model_configuration import ModelConfiguration, Protocol
            from pydantic import SecretStr
            registered = Path(os.environ['LOCALAPPDATA']) / 'ClassMatter/connector-secrets/zhipu-standard.dpapi'
            if registered.is_symlink() or not 1 <= registered.stat().st_size <= 16384:
                raise ValueError('Registered provider profile required')
            packet = json.loads(protect(registered.read_bytes(), decrypt=True))
            if packet.get('provider') != 'zhipu' or packet.get('base_url') != 'https://open.bigmodel.cn/api/paas/v4/':
                raise ValueError('Registered standard provider binding required')
            profile = ModelConfiguration(Protocol.CHAT, 'glm-4.7-flash' if args.provider == 'zhipu-flash47' else 'glm-4-flash-250414', packet['base_url'])
            key, proxy = SecretStr(packet['api_key']), None
            del packet
        if services is not None:
            services.close(); services = None
        if setup is not None:
            setup.close(); setup = None
        phase = 'isolated-preparation'
        if args.resume_runtime_root:
            resume = args.resume_runtime_root.resolve()
            if not resume.is_relative_to(artifacts.resolve()) or resume.name != 'runtime':
                raise ValueError('Only a prior isolated acceptance root may resume')
            runtime = LocalRuntime(resume, profile='classroom-work-d4')
            runtime.start()
        else:
            runtime = LocalRuntime(output / 'runtime', profile='conversation-d1')
            runtime = upgrade_classroom(prepare_workspace_chat(runtime, args.pg_root))
        setup = NativeSetup(runtime, development=True)
        cookies = setup.handle({'operation': 'development_access'})['cookies']
        target_services = open_services(runtime, local_development=True)
        auth = (cookies['session'], cookies['client'], cookies['csrf'], target_services.restrictions.workspace_id)
        def commit(command):
            proposal = target_services.worker.preview(*auth, command)
            approval = target_services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash) if proposal.risk == 'W2' else None
            return target_services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
        # Explicit synthetic preconditions, not claimed as Agent-created data.
        if args.resume_runtime_root:
            context = target_services.query.context(*auth)
            expected_names = ('合成联测班', '合成联测修订班') if args.scenario in ('classroom-documents', 'classroom-recovery') else ('合成联测班',)
            if context is None or context.name not in expected_names:
                raise ValueError('Expected original synthetic fixture context')
            c, t = context.class_id, context.term_id
            if args.scenario != 'classroom-recovery' and (target_services.query.classroom_read(auth, c, t)['exams'] or target_services.query.classroom_read(auth, c, t, seating=True) is not None):
                raise ValueError('Resume cannot reset or overwrite classroom work')
            if args.scenario == 'classroom-documents' and target_services.query.documents(*auth, c, t):
                raise ValueError('Resume cannot reset or overwrite documents')
            if args.scenario == 'daily-work-recovery':
                from class_os.application.workspace_chat import WorkspaceChatQueryGateway
                history = WorkspaceChatQueryGateway(target_services.query.identity, target_services.query.store).history(auth, args.resume_thread_id)
                world = target_services.query.projection(*auth, c, t)
                if not daily_recovery_checkpoint(history, world, target_services.query.documents(*auth, c, t)):
                    raise ValueError('Only the original failed-followup checkpoint may resume')
        elif args.scenario in ('classroom', 'classroom-documents', 'daily-work'):
            c, t = uuid4(), uuid4()
            commit(CreateClass(c, t, '合成联测班', '合成联测学期', date(2026, 9, 1), date(2027, 1, 30)))
            for name in ('合成学生甲', '合成学生乙'):
                commit(CreateStudent(uuid4(), c, t, target_services.query.context(*auth).version, name))
        sdk = PydanticAgentRuntime(target_services.query)
        from class_os.infrastructure.model_provider import configured_client
        @asynccontextmanager
        async def observed_client(configuration, secret, *, proxy=None):
            async with configured_client(configuration, secret, proxy=proxy) as client:
                try:
                    yield client
                except BaseException as error:
                    print(json.dumps({'phase': 'protocol-probe', 'error_type': type(error).__name__,
                        'http_status': getattr(error, 'status_code', None)}), flush=True)
                    raise
        controller = ModelController(target_services.query, target_services.worker.store.model_secrets, sdk,
            allowed_bases=(profile.base_url,), proxy=proxy,
            client_factory=observed_client,
            activation=LocalModelActivation(runtime.root, auth[3], proxy=proxy))
        async def activate():
            if args.resume_runtime_root:
                state = await controller.status(auth)
                saved = target_services.query.model_configuration(auth)
                if controller.profile(saved) != profile:
                    raise ValueError('Prior enabled fixture model required')
                if state['mode'] != 'configured-api':
                    if not await controller.test(auth, saved['candidate_id'], saved['version'], uuid4()):
                        raise ValueError('Real model protocol probe failed')
                    await controller.enable(auth, saved['candidate_id'], saved['version'])
                return
            command = await controller.stage(auth, profile, key.get_secret_value(), 0)
            commit(command)
            if not await controller.test(auth, command.candidate_id, 1, uuid4()):
                raise ValueError('Real model protocol probe failed')
            await controller.enable(auth, command.candidate_id, 1)
        phase = 'protocol-probe'
        asyncio.run(activate())
        del key
        target_services.close(); target_services = None
        setup.close(); setup = None
        phase = 'native-build'
        desktop = ROOT / 'apps/desktop'
        built = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'classroom-work-d4'], cwd=desktop,
            capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        if built.returncode:
            raise ValueError('Native build failed')
        stage = output / 'desktop'
        shutil.copytree(desktop / '.build/runtime-d4', stage)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        descriptor = stage / 'runtime-source.json'
        config = json.loads(descriptor.read_text(encoding='utf-8'))
        config.update(runtimeRoot=str(runtime.root), servicePort=port)
        descriptor.write_text(json.dumps(config), encoding='utf-8')
        env = dict(os.environ, CLASSMATTER_OPERATOR_METADATA='1', CLASSMATTER_RUN_LIVE_CLASSROOM='1', CLASSMATTER_LIVE_STAGE=str(stage), CLASSMATTER_LIVE_REPORT=str(output / 'report.json'), CLASSMATTER_LIVE_MODEL=profile.model, CLASSMATTER_LIVE_ATTEMPTS=str(args.attempts_per_turn), CLASSMATTER_LIVE_SCENARIO=args.scenario, CLASSMATTER_LIVE_TURN_INTERVAL=str(args.turn_interval_seconds), CLASSMATTER_LIVE_RESUMED='1' if args.resume_runtime_root else '0', CLASSMATTER_LIVE_THREAD=str(args.resume_thread_id) if args.resume_thread_id else '')
        phase = 'native-acceptance'
        result = subprocess.run(['node', 'tests/live-classroom-acceptance.cjs'], cwd=desktop, env=env,
            capture_output=True, text=True, encoding='utf-8', timeout=1500, creationflags=subprocess.CREATE_NO_WINDOW)
        (output / 'ui.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        report_path = output / 'report.json'
        observed = json.loads(report_path.read_bytes()) if report_path.is_file() and report_path.stat().st_size <= 1024 * 1024 else {}
        from class_os.infrastructure.operator_run_metadata import read_packets
        request_ids = {row['request_id'] for row in observed.get('rows', []) if row.get('request_id')}
        metadata = read_packets(runtime.root, sorted(request_ids))
        (output / 'operator-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        metadata_complete = bool(request_ids) and {row['run_id'] for row in metadata} == request_ids
        passed = result.returncode == 0 and metadata_complete
        print(json.dumps({'status': 'passed' if passed else 'failed', 'ui_passed': result.returncode == 0,
            'operator_metadata_complete': metadata_complete, 'failure_categories': sorted({row['category'] for row in metadata if row.get('category')}),
            'scenario': args.scenario, 'report': str(output / 'report.json'), 'test_attempt_limit': args.attempts_per_turn,
            'application_automatic_retry': False, 'resumed_isolated_fixture': bool(args.resume_runtime_root),
            'prior_failures_retained': any(row.get('prior_failure') for row in observed.get('rows', []))}))
        return 0 if passed else 1
    except Exception as error:
        print(json.dumps({'status': 'blocked-or-failed', 'phase': phase, 'error_type': type(error).__name__, 'report_directory': str(output), 'automatic_retry': False}))
        return 1
    finally:
        for item in (target_services, services, setup):
            if item is not None:
                item.close()
        if runtime is not None:
            runtime.stop()


if __name__ == '__main__':
    raise SystemExit(main())
