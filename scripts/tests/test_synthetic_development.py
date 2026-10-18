from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_synthetic_development import check_development, DevelopmentError


class SyntheticDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('.ai/development', '.ai/gates', 'docs/specs/class-os-v1', 'evals/class-os-v1'):
            shutil.copytree(ROOT / name, self.root / name)
        target = self.root / 'docs/changes'
        target.mkdir(parents=True)
        shutil.copy(ROOT / 'docs/changes/2026-10-08-synthetic-development-admission.md', target)
        self.policy = self.root / '.ai/development/synthetic-policy.yaml'

    def tearDown(self):
        self.temp.cleanup()

    def test_development_is_not_release_or_real_data_authorization(self):
        result = check_development(self.root, 'T-RPLT-001')
        self.assertTrue(result['synthetic_development_eligible'])
        self.assertFalse(result['release_authorized'])
        self.assertFalse(result['real_data_authorized'])
        self.assertFalse(result['formal_tasks_complete'])

    def test_dangerous_profile_mutations_rejected(self):
        original = self.policy.read_text(encoding='utf-8')
        mutations = [('data_mode: synthetic-only', 'data_mode: approved-real-pilot'),
                     ('bind_host: 127.0.0.1', 'bind_host: 0.0.0.0'),
                     ('model_provider: fake', 'model_provider: external'),
                     ('owner_development_approved: true', 'owner_development_approved: false')]
        for key in ('real_data_allowed', 'production_credentials_allowed',
                    'public_exposure_allowed', 'agent_business_write_allowed', 'release_promotion_allowed'):
            mutations.append((f'{key}: false', f'{key}: true'))
        for before, after in mutations:
            with self.subTest(after=after):
                self.policy.write_text(original.replace(before, after), encoding='utf-8')
                with self.assertRaises(DevelopmentError):
                    check_development(self.root, 'T-RPLT-001')

    def test_unknown_key_duplicate_key_and_wrong_types_rejected(self):
        original = self.policy.read_text(encoding='utf-8')
        for suffix in ('unknown: yes\n', 'profile: synthetic-development-v1\n'):
            self.policy.write_text(original + suffix, encoding='utf-8')
            with self.assertRaises(DevelopmentError):
                check_development(self.root, 'T-RPLT-001')
        self.policy.write_text(original.replace('real_data_allowed: false', 'real_data_allowed: 0'), encoding='utf-8')
        with self.assertRaises(DevelopmentError):
            check_development(self.root, 'T-RPLT-001')

    def test_unknown_future_and_missing_task_rejected(self):
        for task in ('T-EVO-001', 'T-FAKE-001', '', 'T-RPLT-001,T-RPLT-002'):
            with self.subTest(task=task), self.assertRaises(DevelopmentError):
                check_development(self.root, task)

    def test_missing_owner_record_rejected(self):
        (self.root / 'docs/changes/2026-10-08-synthetic-development-admission.md').unlink()
        with self.assertRaises(DevelopmentError):
            check_development(self.root, 'T-RPLT-001')

    def test_formal_gate_definitions_are_not_modified(self):
        before = {p: p.read_bytes() for p in (self.root / '.ai/gates').glob('*.yaml')}
        check_development(self.root, 'T-RPLT-001')
        self.assertEqual(before, {p: p.read_bytes() for p in before})


if __name__ == '__main__':
    unittest.main()
