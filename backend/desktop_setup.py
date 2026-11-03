"""Private, bounded stdio transport for the native first-run window only."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def main():
    key = os.environ.pop('CLASSMATTER_SETUP_PROCESS_KEY', '')
    if re.fullmatch('[a-f0-9]{64}', key) is None:
        return 1
    class PrivateParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError('Invalid native startup arguments')
    parser = PrivateParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--development-no-password', action='store_true')
    args = parser.parse_args()
    from class_os.infrastructure.local_runtime import LocalRuntime
    from class_os.infrastructure.native_setup import NativeSetup
    setup = NativeSetup(LocalRuntime(args.runtime_root, profile='conversation-d1'), development=args.development_no_password)
    try:
        for _ in range(32):
            line = sys.stdin.buffer.readline(8193)
            if not line:
                break
            identifier = None
            try:
                if len(line) > 8192 or not line.endswith(b'\n'):
                    raise ValueError('Bounded line required')
                envelope = json.loads(line.decode('utf-8'), object_pairs_hook=unique)
                if (type(envelope) is not dict or set(envelope) != {'id', 'key', 'request'}
                        or type(envelope['id']) is not str or re.fullmatch('[a-f0-9]{32}', envelope['id']) is None
                        or envelope['key'] != key):
                    raise ValueError('Private native proof required')
                identifier = envelope['id']
                result = {'id': identifier, 'ok': True, 'result': setup.handle(envelope['request'])}
            except Exception:
                result = {'id': identifier, 'ok': False, 'code': 'setup_not_completed'}
            sys.stdout.write(json.dumps(result, ensure_ascii=True) + '\n')
            sys.stdout.flush()
            if len(line) > 8192 or not line.endswith(b'\n'):
                break
    finally:
        try:
            setup.close()
        except Exception:
            pass  # Never disclose a connection exception or private response.
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
