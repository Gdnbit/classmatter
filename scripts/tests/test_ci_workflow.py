"""CI is a read-only engineering baseline, never synthetic release authority."""
import copy
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml


ROOT = Path(__file__).resolve().parents[2]


def validate(document):
    if set(document.get("jobs", {})) != {"baseline"}:
        raise ValueError("Only the declared baseline job")
    if document.get("permissions") != {"contents": "read"}:
        raise ValueError("Read-only workflow required")
    if set(document.get("on", {})) != {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("No elevated pull request or chained workflow trigger")
    job = document["jobs"]["baseline"]
    budget = job.get("timeout-minutes")
    if type(budget) is not int or budget != 45:
        raise ValueError("Explicit bounded engineering job budget required")
    if job.get("permissions") or job.get("continue-on-error") or job.get("environment"):
        raise ValueError("No elevated permissions, deployment or suppressed failure")
    if job["strategy"]["matrix"]["os"] != ["ubuntu-24.04", "windows-2025"]:
        raise ValueError("Declared cross-host baseline required")
    steps = job["steps"]
    for step in steps:
        if step.get("continue-on-error"):
            raise ValueError("Failure must remain visible")
        action = step.get("uses")
        if action and not re.fullmatch(r"(?:actions/(?:checkout|setup-python|setup-node)|astral-sh/setup-uv)@[0-9a-f]{40}", action):
            raise ValueError("Reviewed SHA-pinned action required")
    if steps[0]["with"] != {"persist-credentials": False, "fetch-depth": 0}:
        raise ValueError("No persisted credentials; scan all reachable publication history")
    serialized = yaml.safe_dump(document)
    if "secrets." in serialized or "-Suite all" in serialized or "-Suite security" in serialized:
        raise ValueError("Not a secret-enabled or formal-release job")
    runs = "\n".join(step.get("run", "") for step in steps)
    required = ("--frozen-lockfile", "-Suite backend", "-Suite web", "-Suite db", "unittest discover", "task-graph", "development", "fixtures", "docs", "scripts/public_guard.py", "scripts/scan_public.py --history")
    if any(command not in runs for command in required):
        raise ValueError("Baseline verification missing")
    if 'postgresql-client-18=18.6-1.pgdg24.04+2' not in runs:
        raise ValueError("PostgreSQL server/client exact versions must match")
    if 'install -m 0644 infra/ci/ubuntu.mirrors /etc/apt/apt-mirrors.txt' not in runs:
        raise ValueError('Reviewed archive failover list required')
    if runs.count('Acquire::Retries=2') != 2 or runs.count('Acquire::https::Timeout=20') != 2 or 'APT::Update::Error-Mode=any update' not in runs:
        raise ValueError('Bounded transport and failed-index refusal required')
    if any(value in runs.lower() for value in ('allowunauthenticated', '--allow-unauthenticated', 'allowinsecurerepositories',
            'trusted=yes', 'trusted: yes', 'verify-peer=false', 'curl --insecure', 'curl -k ')):
        raise ValueError('Archive or TLS verification cannot be disabled')
    key_download_arguments(document)


def key_download_arguments(document):
    runs = '\n'.join(step.get('run', '') for step in document['jobs']['baseline']['steps'])
    commands = [shlex.split(line.strip()) for line in runs.splitlines()
                if line.strip().startswith('sudo curl ')]
    if len(commands) != 1:
        raise ValueError('One official key download required')
    args = commands[0][2:]
    for option, value in (('--connect-timeout', '10'), ('--max-time', '30'), ('--retry', '3'),
                          ('--retry-delay', '2'), ('--retry-max-time', '90'),
                          ('--output', '/usr/share/postgresql-common/pgdg/class-os-postgresql.asc')):
        if args.count(option) != 1 or args[args.index(option) + 1:args.index(option) + 2] != [value]:
            raise ValueError('Bounded key download required')
    if not {'--fail', '--silent', '--show-error', '--retry-all-errors'}.issubset(args):
        raise ValueError('Transport failure must be retried and ultimately fail closed')
    if args[-1] != 'https://www.postgresql.org/media/keys/ACCC4CF8.asc':
        raise ValueError('Official HTTPS signing key source required')
    return args


class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load((ROOT / ".github/workflows/synthetic-ci.yml").read_text(encoding="utf-8"))

    def test_readonly_cross_host_baseline(self):
        validate(self.document)

    def test_postgres_client_does_not_float_to_newer_minor(self):
        document = copy.deepcopy(self.document)
        for step in document['jobs']['baseline']['steps']:
            if 'run' in step:
                step['run'] = step['run'].replace(' postgresql-client-18=18.6-1.pgdg24.04+2', '')
        with self.assertRaises(ValueError):
            validate(document)

    def test_signing_key_transfer_limits_and_official_source_cannot_be_removed(self):
        for before, after in (('--retry-all-errors', ''), ('--max-time 30', ''),
                              ('--connect-timeout 10', ''), ('--retry 3', '--retry 99'),
                              ('--retry-max-time 90', '--retry-max-time 0'),
                              ('--retry-delay 2', '--retry-delay 0'),
                              ('https://www.postgresql.org/media/keys/', 'http://example.invalid/')):
            document = copy.deepcopy(self.document)
            for step in document['jobs']['baseline']['steps']:
                if 'run' in step:
                    step['run'] = step['run'].replace(before, after)
            with self.subTest(before=before), self.assertRaises(ValueError):
                validate(document)

    def test_actual_curl_recovers_partial_transfer_and_refuses_exhausted_failure(self):
        executable = shutil.which('curl.exe' if os.name == 'nt' else 'curl')
        self.assertIsNotNone(executable, 'CI transport prerequisite curl is required')
        payload = b'synthetic transport fixture, not a trusted signing key\n'
        for recover, expected_count in ((True, 2), (False, 4)):
            calls = []

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    calls.append(self.path)
                    if recover and len(calls) == 2:
                        self.send_response(200)
                        self.send_header('Content-Length', str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                    else:
                        self.send_response(200)
                        self.send_header('Content-Length', '1000')
                        self.end_headers()
                        self.wfile.write(b'partial must not prefix the recovered key')
                        self.close_connection = True

                def log_message(self, *args):
                    pass

            with self.subTest(recover=recover), ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, tempfile.TemporaryDirectory() as directory:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    args = key_download_arguments(self.document)
                    args[-1] = f'http://127.0.0.1:{server.server_port}/synthetic-key'
                    target = Path(directory) / 'key.asc'
                    args[args.index('--output') + 1] = str(target)
                    # The real command/limits are exercised; only destination is a loopback fixture.
                    result = subprocess.run([executable, '-q', '--noproxy', '*', *args], capture_output=True, timeout=35)
                    self.assertEqual(expected_count, len(calls))
                    if recover:
                        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
                        self.assertEqual(payload, target.read_bytes())
                    else:
                        self.assertNotEqual(0, result.returncode)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)

    def test_reviewed_mirror_list_uses_distinct_https_hosts_and_real_priorities(self):
        raw = (ROOT / 'infra/ci/ubuntu.mirrors').read_bytes()
        self.assertNotIn(b'\r', raw)
        self.assertEqual([
            ['https://archive.ubuntu.com/ubuntu', 'priority:1'],
            ['https://mirrors.edge.kernel.org/ubuntu', 'priority:2'],
        ], [line.split('\t') for line in raw.decode('utf-8').splitlines()])

    def test_failover_does_not_suppress_errors_or_relax_archive_verification(self):
        for before, after in (
                ('install -m 0644 infra/ci/ubuntu.mirrors', 'install -m 0644 /tmp/unknown-mirrors'),
                ('Acquire::Retries=2', 'Acquire::Retries=999'),
                ('APT::Update::Error-Mode=any update', 'update'),
                ('apt-get -o Acquire::Retries=2', 'apt-get --allow-unauthenticated -o Acquire::Retries=2')):
            document = copy.deepcopy(self.document)
            for step in document['jobs']['baseline']['steps']:
                if 'run' in step:
                    step['run'] = step['run'].replace(before, after)
            with self.subTest(after=after), self.assertRaises(ValueError):
                validate(document)

    def test_full_regression_budget_is_explicit_and_bounded(self):
        self.assertEqual(45, self.document["jobs"]["baseline"]["timeout-minutes"])
        for budget in (None, True, 0, 19, 30, 31, 44, 46, "45"):
            document = copy.deepcopy(self.document)
            document["jobs"]["baseline"]["timeout-minutes"] = budget
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                validate(document)

    def test_exact_byte_fixtures_are_lf_even_on_windows_checkout(self):
        fixtures = sorted((ROOT / "evals/class-os-v1/fixtures/r1").glob("*.synthetic.json"))
        self.assertEqual(6, len(fixtures))
        for fixture in fixtures:
            result = subprocess.run(["git", "-C", str(ROOT), "check-attr", "eol", "--", fixture.relative_to(ROOT).as_posix()],
                                    capture_output=True, text=True, check=True)
            self.assertTrue(result.stdout.rstrip().endswith(": eol: lf"), result.stdout)

    def test_standalone_identity_validator_is_lf_for_exact_drift_check(self):
        for path in ("apps/web/src/runtime/identity-validators.cjs", "apps/web/src/runtime/model-configuration-validator.cjs"):
            result = subprocess.run(["git", "-C", str(ROOT), "check-attr", "eol", "--", path],
                                    capture_output=True, text=True, check=True)
            self.assertTrue(result.stdout.rstrip().endswith(": eol: lf"), result.stdout)

    def test_database_steps_are_linux_owned_fixture_not_shared_dsn(self):
        steps = self.document["jobs"]["baseline"]["steps"]
        for phrase in ("postgresql-18=18.6-1.pgdg24.04+2", "playwright install --with-deps chromium", "-Suite db"):
            matches = [step for step in steps if phrase in step.get("run", "")]
            self.assertEqual(1, len(matches))
            self.assertEqual("matrix.os == 'ubuntu-24.04'", matches[0].get("if"))
        database_run = next(step["run"] for step in steps if "-Suite db" in step.get("run", ""))
        self.assertIn("-PostgresRoot /usr/lib/postgresql/18/bin", database_run)
        self.assertNotIn("DSN", database_run)
        repository = (ROOT / "infra/ci/pgdg.sources").read_text(encoding="utf-8")
        self.assertIn("Suites: noble-pgdg", repository)
        self.assertIn("Signed-By: /usr/share/postgresql-common/pgdg/class-os-postgresql.asc", repository)

    def test_elevated_permission_rejected(self):
        for mutate in (lambda document: document["permissions"].update(contents="write"),
                       lambda document: document["jobs"].update(deploy={"permissions": {"contents": "write"}})):
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.assertRaises(ValueError):
                validate(document)

    def test_elevated_trigger_rejected(self):
        self.document["on"]["pull_request_target"] = None
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_floating_action_rejected(self):
        self.document["jobs"]["baseline"]["steps"][0]["uses"] = "actions/checkout@v7"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_suppressed_failure_or_secret_rejected(self):
        for addition in ({"continue-on-error": True}, {"run": "echo ${{ secrets.TEST }}"}):
            with self.subTest(addition=addition):
                document = copy.deepcopy(self.document)
                document["jobs"]["baseline"]["steps"].append(addition)
                with self.assertRaises(ValueError):
                    validate(document)

    def test_missing_locked_install_rejected(self):
        for step in self.document["jobs"]["baseline"]["steps"]:
            if "--frozen-lockfile" in step.get("run", ""):
                step["run"] = "pnpm install"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_missing_publication_guard_rejected(self):
        for step in self.document["jobs"]["baseline"]["steps"]:
            if "scripts/public_guard.py" in step.get("run", ""):
                step["run"] = "echo missing-check"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_shallow_history_rejected(self):
        self.document["jobs"]["baseline"]["steps"][0]["with"]["fetch-depth"] = 1
        with self.assertRaises(ValueError):
            validate(self.document)
