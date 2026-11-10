"""Opt-in real-model/native-UI acceptance in a fresh synthetic instance.

Reuses only an already enabled, explicitly approved free model. Never accepts
keys, changes the source model selection, or runs in default tests/CI.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
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


def main():
    parser = OperatorParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--source-runtime-root', type=Path)
    parser.add_argument('--pg-root', type=Path)
    parser.add_argument('--resume-runtime-root', type=Path, help='Reuse only a prior isolated, empty-classroom acceptance fixture')
    parser.add_argument('--provider', choices=('google', 'zhipu'), default='google', help='Explicit registered free model only; never an automatic fallback')
    parser.add_argument('--attempts-per-turn', type=int, choices=(1, 2, 3), default=1, help='Explicit test-only UI resends after failed turns; all attempts remain in the report')
    parser.add_argument('--scenario', choices=('classroom', 'full-workbench'), default='classroom', help='Full workbench starts empty; all class/student creation uses the original conversation UI')
    args = parser.parse_args()
    if not args.live or not args.source_runtime_root or not args.pg_root:
        print(json.dumps({'status': 'blocked', 'reason': 'explicit_live_source_and_pg_required', 'requests': 0}))
        return 2
    if args.scenario == 'full-workbench' and args.resume_runtime_root:
        print(json.dumps({'status': 'blocked', 'reason': 'full_workbench_requires_fresh_fixture', 'requests': 0}))
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
    source = LocalRuntime(args.source_runtime_root, profile='classroom-work-d4')
    services = setup = target_services = runtime = None
    phase = 'source-preflight'
    output = ROOT / 'test-results/live-classroom' / uuid4().hex
    output.mkdir(parents=True)
    try:
        setup = NativeSetup(source, development=True)
        cookies = setup.handle({'operation': 'development_access'})['cookies']
        services = open_services(source, local_development=True)
        auth = (cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id)
        if args.provider == 'google':
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
            profile = ModelConfiguration(Protocol.CHAT, 'glm-4-flash-250414', packet['base_url'])
            key, proxy = SecretStr(packet['api_key']), None
            del packet
        services.close(); services = None
        setup.close(); setup = None
        phase = 'isolated-preparation'
        if args.resume_runtime_root:
            resume = args.resume_runtime_root.resolve()
            if not resume.is_relative_to((ROOT / 'test-results/live-classroom').resolve()) or resume.name != 'runtime':
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
            if context is None or context.name != '合成联测班':
                raise ValueError('Expected original synthetic fixture context')
            c, t = context.class_id, context.term_id
            if target_services.query.classroom_read(auth, c, t)['exams'] or target_services.query.classroom_read(auth, c, t, seating=True) is not None:
                raise ValueError('Resume cannot reset or overwrite classroom work')
        elif args.scenario == 'classroom':
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
        env = dict(os.environ, CLASSMATTER_RUN_LIVE_CLASSROOM='1', CLASSMATTER_LIVE_STAGE=str(stage), CLASSMATTER_LIVE_REPORT=str(output / 'report.json'), CLASSMATTER_LIVE_MODEL=profile.model, CLASSMATTER_LIVE_ATTEMPTS=str(args.attempts_per_turn), CLASSMATTER_LIVE_SCENARIO=args.scenario)
        phase = 'native-acceptance'
        result = subprocess.run(['node', 'tests/live-classroom-acceptance.cjs'], cwd=desktop, env=env,
            capture_output=True, text=True, encoding='utf-8', timeout=1500, creationflags=subprocess.CREATE_NO_WINDOW)
        (output / 'ui.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print(json.dumps({'status': 'passed' if result.returncode == 0 else 'failed', 'report': str(output / 'report.json'), 'test_attempt_limit': args.attempts_per_turn, 'application_automatic_retry': False}))
        return 0 if result.returncode == 0 else 1
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
