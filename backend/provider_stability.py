"""Opt-in, noncommitting free-model replay against an existing synthetic fixture.

Reports contain closed diagnostics only. No keys or model answers are exported.
This is transport/SDK stability evidence, not native UI or formal release admission.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


class OperatorParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid operator arguments; no requests made.\n')


def parse_args(argv=None):
    parser = OperatorParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--fixture', type=UUID, required=True)
    parser.add_argument('--thread', type=UUID, help='Optional existing synthetic conversation; history is retained, never reset')
    parser.add_argument('--rounds', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--interval', type=int, choices=(15, 65), default=65)
    return parser.parse_args(argv)


async def run(args, runtime, services, setup, output):
    import httpx
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.infrastructure.local_model_activation import LocalModelActivation
    from class_os.infrastructure.model_control import ModelController
    from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
    from class_os.interfaces.http.settings import Settings

    cookies = setup.handle({'operation': 'development_access'})['cookies']
    auth = (cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id)
    def business_snapshot():
        current = services.query.context(*auth)
        if current is None:
            raise ValueError('An existing synthetic class is required for classroom replay')
        scope = (current.class_id, current.term_id)
        exams = services.query.classroom_read(auth, *scope)
        if exams['truncated']:
            raise ValueError('Complete synthetic exam inventory required')
        documents = services.query.documents(*auth, *scope)
        value = {'roster': services.query.roster(*auth, *scope),
            'exams': exams,
            'scores': [services.query.classroom_read(auth, *scope, exam_id=row['exam_id']) for row in exams['exams']],
            'seats': services.query.classroom_read(auth, *scope, seating=True),
            'documents': [services.query.document(*auth, *scope, row['document_id']) for row in documents],
            'tasks': [{key: row[key] for key in ('task_id', 'title', 'status', 'version')}
                      for row in services.query.projection(*auth, *scope)['tasks']]}
        return json.dumps(value, sort_keys=True, default=str)
    before = business_snapshot()
    activation = LocalModelActivation(runtime.root, auth[3]).read()
    profile = ModelController.profile(services.query.model_configuration(auth))
    # Explicit approved free profiles only; never infer a paid fallback.
    approved = {('https://generativelanguage.googleapis.com/v1beta/openai/', 'gemini-3.1-flash-lite'),
                ('https://open.bigmodel.cn/api/paas/v4/', 'glm-4-flash-250414')}
    if (profile.base_url, profile.model) not in approved or not activation:
        raise ValueError('Existing approved free activation required')
    diagnostics = []
    sdk = PydanticAgentRuntime(services.query, timeout=45, diagnostics=diagnostics.append)
    controller = ModelController(services.query, services.worker.store.model_secrets, sdk,
        allowed_bases=(profile.base_url,), proxy=activation['proxy'],
        activation=LocalModelActivation(runtime.root, auth[3], proxy=activation['proxy']))
    app = create_workspace_chat_app(Settings(model_api_bases=(profile.base_url,), model_api_proxy=activation['proxy']),
        worker=services.worker, query=services.query, sdk=sdk, model_controller=controller)
    report = {'kind': 'classmatter.provider-stability.v1', 'model': profile.model,
              'attempts': [], 'diagnostics': diagnostics, 'business_commits_requested': 0, 'interval_seconds': args.interval}
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    prompts = ('你好，请简短回答。', '请查询当前班级的成绩和座位，只查询，不修改。',
               '请先查当前学生和任务，再概括未完成工作，只查询，不修改。',
               '请创建文档合成稳定性草稿，正文为：本周收集回执，仍待核对。只准备，不保存。')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000',
            cookies=dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))) as client:
        for index in range(args.rounds * len(prompts)):
            if index:
                await asyncio.sleep(args.interval)
            thread, request = args.thread or uuid4(), uuid4()
            prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{thread}'
            accepted = await client.post(prefix + '/turns', headers=headers,
                json={'request_id': str(request), 'text': prompts[index % len(prompts)]})
            if accepted.status_code != 200:
                raise RuntimeError('Chat acceptance contract failed')
            await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})
            response = await client.get(prefix)
            response.raise_for_status()
            row = response.json()['turns'][-1]
            if row['action_receipt'] is not None:
                raise RuntimeError('Unexpected business receipt without confirmation')
            report['attempts'].append({'request_id': str(request), 'scenario': index % len(prompts),
                'state': row['state'], 'candidate': row['candidate']['command'] if row['candidate'] else None,
                'input_tokens': row['input_tokens'], 'output_tokens': row['output_tokens'],
                'preview_present': row['change_preview'] is not None})
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(report['attempts'][-1]), flush=True)
    report['business_snapshot_unchanged'] = before == business_snapshot()
    report['passed'] = report['business_snapshot_unchanged'] and all(
        row['state'] == 'completed' and (row['scenario'] != 3 or row['candidate'] == 'document.create' and row['preview_present'])
        for row in report['attempts'])
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['passed'] else 1


def main(argv=None):
    args = parse_args(argv)
    if not args.live:
        print(json.dumps({'status': 'blocked', 'reason': 'explicit_live_required', 'requests': 0}))
        return 2
    from class_os.infrastructure.local_runtime import LocalRuntime
    from class_os.infrastructure.native_setup import NativeSetup
    from class_os.infrastructure.workspace_local_runtime import open_services
    fixture = ROOT / 'test-results/live-classroom' / args.fixture.hex
    runtime_root = fixture / 'runtime'
    # Never create or point this operator at the user's normal application instance.
    if not runtime_root.is_dir() or fixture.is_symlink() or runtime_root.is_symlink():
        raise ValueError('Existing isolated synthetic fixture required')
    runtime = LocalRuntime(runtime_root, profile='classroom-work-d4')
    setup = services = None
    runtime.start()
    try:
        setup = NativeSetup(runtime, development=True)
        services = open_services(runtime, local_development=True)
        output = fixture / f'stability-{uuid4().hex}.json'
        print(json.dumps({'report': str(output)}), flush=True)
        return asyncio.run(run(args, runtime, services, setup, output))
    finally:
        if services is not None:
            services.close()
        if setup is not None:
            setup.close()
        runtime.stop()


if __name__ == '__main__':
    raise SystemExit(main())
