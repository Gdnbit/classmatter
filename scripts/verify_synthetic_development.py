"""Owner-approved development scope check; never a release/runtime authorizer."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verify_manifests import ManifestError, _load_yaml, validate_task_graph

POLICY = '.ai/development/synthetic-policy.yaml'
RECORD = 'docs/changes/2026-10-08-synthetic-development-admission.md'
EXPECTED = {
    'schema_version': 1,
    'profile': 'synthetic-development-v1',
    'release': 'class-os-r1',
    'owner_development_approved': True,
    'authorization_record': RECORD,
    'data_mode': 'synthetic-only',
    'bind_host': '127.0.0.1',
    'model_provider': 'fake',
    'real_data_allowed': False,
    'production_credentials_allowed': False,
    'public_exposure_allowed': False,
    'agent_business_write_allowed': False,
    'release_promotion_allowed': False,
}


class DevelopmentError(RuntimeError):
    pass


def check_development(root: Path, task_id: str) -> dict:
    """Validate local engineering scope, not human identity or signed approval."""
    try:
        policy = _load_yaml(root / POLICY)
        if (policy != EXPECTED or set(policy) != set(EXPECTED)
                or any(type(policy[key]) is not type(value) for key, value in EXPECTED.items())):
            raise DevelopmentError('synthetic development policy does not match approved scope')
        if not (root / RECORD).is_file():
            raise DevelopmentError('owner decision record is missing')
        graph = validate_task_graph(root)
        tasks = _load_yaml(root / '.ai/gates/release-1-task-definitions.yaml')['task_definitions']
        if task_id not in {entry['task_id'] for entry in tasks}:
            raise DevelopmentError('task must be a canonical R1 task')
    except (ManifestError, OSError, ValueError, KeyError) as exc:
        raise DevelopmentError('development inputs are invalid') from exc
    return {
        'profile': EXPECTED['profile'], 'task_id': task_id,
        'synthetic_development_eligible': True,
        'formal_tasks_complete': graph['before_feature_tasks_complete'],
        'release_authorized': False, 'real_data_authorized': False,
        'limitations': 'scope check only; not runtime authorization or a signed approval',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = check_development(args.repo_root, args.task)
    except DevelopmentError as exc:
        print(f'DEVELOPMENT SCOPE ERROR: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
