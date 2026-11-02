"""Explicit synthetic engineering diagnostics; no HTTP activation or real data."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))
from pydantic import SecretStr
from class_os.domain.model_configuration import ModelConfiguration, Protocol, validate_model_proxy
from class_os.infrastructure.model_provider import GOOGLE_COMPAT_BASE, configured_client, model_for_configuration
from class_os.infrastructure.provider_evaluation import evaluate, compare


class DiagnosticParser(argparse.ArgumentParser):
    def error(self, message):
        # An accidentally supplied secret in an unsupported argument is not echoed.
        if 'unrecognized arguments' in message or 'invalid choice' in message:
            message = 'Invalid diagnostic options; see --help.'
        super().error(message)


def main():
    parser = DiagnosticParser(description=__doc__)
    parser.add_argument('command', choices=('offline', 'live', 'compare'))
    parser.add_argument('--confirm-free-tier', action='store_true')
    parser.add_argument('--provider', choices=('google', 'zhipu'), default='google')
    parser.add_argument('--local-key', '--local-google-key', dest='local_key', action='store_true', help='Read only the existing selected-provider current-user protected diagnostic key')
    parser.add_argument('--proxy', help='Explicit loopback proxy; never inherited')
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    args = parser.parse_args()
    if args.command != 'live' and (args.confirm_free_tier or args.local_key or args.proxy):
        parser.error('Network/key flags require live')
    if args.command == 'compare':
        if not args.before or not args.after:
            parser.error('compare requires both reports')
        result = compare(json.loads(args.before.read_text(encoding='utf-8')), json.loads(args.after.read_text(encoding='utf-8')))
        print(json.dumps(result))
        return 2 if result['regressions'] else 0
    if args.before or args.after:
        parser.error('Report inputs require compare')
    live = args.command == 'live'
    if live and not args.confirm_free_tier:
        parser.error('live requires explicit --confirm-free-tier; never enables billing')
    validate_model_proxy(args.proxy)
    # Explicit selection only: no automatic cross-provider fallback or paid model.
    model = 'gemini-3.1-flash-lite' if args.provider == 'google' else 'glm-4.7-flash'
    base = GOOGLE_COMPAT_BASE if args.provider == 'google' else 'https://open.bigmodel.cn/api/paas/v4/'
    key = None
    if live:
        if args.local_key:
            if os.name != 'nt':
                parser.error('Protected local key requires Windows')
            from class_os.infrastructure.local_runtime import protect
            path = Path(os.environ['LOCALAPPDATA']) / 'ClassMatter/connector-secrets' / (args.provider + '-standard.dpapi')
            if path.is_symlink() or not 1 <= path.stat().st_size <= 16384:
                raise ValueError('Invalid protected local profile')
            profile = json.loads(protect(path.read_bytes(), decrypt=True))
            kind = 'classmatter.connector-provider-secret.pending.v1' if args.provider == 'google' else 'classmatter.connector-provider-secret.v1'
            if (profile.get('provider') != args.provider or profile.get('base_url') != base or profile.get('kind') != kind):
                raise ValueError('Invalid protected local profile')
            key = profile.get('api_key')
        else:
            key = os.environ.get('CLASSMATTER_EVAL_' + args.provider.upper() + '_KEY')
        if type(key) is not str or not 8 <= len(key) <= 2048 or any(not 33 <= ord(c) <= 126 for c in key):
            parser.error('Missing/invalid explicitly selected diagnostic key; no argument accepts a secret')
    config = ModelConfiguration(Protocol.CHAT, model, base)
    settings = None if args.provider == 'google' else {'max_tokens': 512, 'temperature': 0.1, 'timeout': 30,
                                                       'extra_body': {'thinking': {'type': 'disabled'}}}
    @asynccontextmanager
    async def context(case):
        async with configured_client(config, SecretStr(key), proxy=args.proxy) as session:
            yield model_for_configuration(config, session)
    reports = ROOT / 'test-results'
    reports.mkdir(exist_ok=True)
    path = reports / ('provider-' + args.command + '-' + str(uuid4()) + '.json')
    # Preserve completed case evidence even if interrupted; never overwrite a baseline.
    report = {'kind': 'classmatter.provider-evidence.pending.v1', 'formal_gate': False, 'results': []}
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report))
    def notify(row):
        report['results'].append(row)
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)
    final = asyncio.run(evaluate(context, live=True, notify=notify, settings=settings) if live else evaluate(notify=notify, settings=settings))
    final.update(model=model if live else 'offline-function-model', provider=args.provider if live else 'offline',
                 created_at=datetime.now(timezone.utc).isoformat(),
                 adapter_digest=__import__('hashlib').sha256((ROOT / 'backend/src/class_os/infrastructure/model_provider.py').read_bytes()).hexdigest())
    path.write_text(json.dumps(final, indent=2), encoding='utf-8')
    print(json.dumps({'report': path.name, 'summary': final['summary'], 'formal_gate': False}))
    return 0 if final['summary']['passed'] == 12 and not final['metrics']['application_latency_exceeded'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # No provider body, key, profile path, request text or traceback on CLI errors.
        print('Provider diagnostics unavailable; no automatic retry or fallback.', file=sys.stderr)
        raise SystemExit(2) from None
