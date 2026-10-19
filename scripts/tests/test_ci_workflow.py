"""GitHub Actions must keep publication checks mandatory and CI read-only."""
import copy
from pathlib import Path
import re
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTION = re.compile(r"(?:actions/(?:checkout|setup-python|setup-node)|astral-sh/setup-uv)@[0-9a-f]{40}")


def validate(document):
    jobs = document.get("jobs", {})
    if set(jobs) != {"public-safety", "baseline"}:
        raise ValueError("Only mandatory public-safety and conditional full baseline jobs")
    if document.get("permissions") != {"contents": "read"}:
        raise ValueError("Read-only workflow required")
    events = document.get("on", {})
    if set(events) != {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("No elevated pull request or chained workflow trigger")
    if events["push"] != {"branches": ["main"]}:
        raise ValueError("No duplicate feature branch push builds")
    if document.get("concurrency", {}).get("cancel-in-progress") is not True:
        raise ValueError("Stale runs must be cancellable")

    safety, full = jobs["public-safety"], jobs["baseline"]
    if safety.get("if") or safety.get("needs"):
        raise ValueError("Public safety must never be conditional on another job")
    if safety.get("runs-on") != "ubuntu-24.04":
        raise ValueError("Mandatory public checks must run on Ubuntu")
    if safety.get("outputs", {}).get("docs_only") != "${{ steps.scope.outputs.docs_only }}":
        raise ValueError("Explicit classifier output required")

    if full.get("needs") != "public-safety":
        raise ValueError("Full baseline must depend on mandatory public safety")
    if full.get("if") != "needs.public-safety.outputs.docs_only != 'true'":
        raise ValueError("Only the reviewed docs-only decision may skip full engineering")
    if full["strategy"].get("fail-fast") is not False or full["strategy"]["matrix"]["os"] != ["ubuntu-24.04", "windows-2025"]:
        raise ValueError("Declared cross-host baseline required")

    for name, job in jobs.items():
        if any(job.get(key) for key in ("permissions", "continue-on-error", "environment")):
            raise ValueError("No elevated permissions, deployment or suppressed failure")
        steps = job["steps"]
        if not steps or steps[0].get("with") != {"persist-credentials": False, "fetch-depth": 0}:
            raise ValueError("No persisted credentials; full reachable history is mandatory")
        for step in steps:
            if step.get("continue-on-error"):
                raise ValueError("Failure must remain visible")
            action = step.get("uses")
            if action and not ACTION.fullmatch(action):
                raise ValueError("Reviewed SHA-pinned action required")

    serialized = yaml.safe_dump(document)
    if "secrets." in serialized or "-Suite all" in serialized or "-Suite security" in serialized:
        raise ValueError("Not a secret-enabled or formal-release workflow")

    public_steps = safety["steps"]
    if sum(step.get("id") == "scope" and "scripts/ci_change_scope.py" in step.get("run", "") for step in public_steps) != 1:
        raise ValueError("A single fail-closed scope classifier is required")
    public_commands = "\n".join(step.get("run", "") for step in public_steps)
    for command in ("scripts/public_guard.py --require-license", "scripts/scan_public.py --history",
                    "test_ci_change_scope.py", "-Suite docs"):
        if command not in public_commands:
            raise ValueError("Mandatory publication/documentation check missing: " + command)

    baseline_commands = "\n".join(step.get("run", "") for step in full["steps"])
    for command in ("--frozen-lockfile", "-Suite backend", "-Suite web", "-Suite db",
                    "unittest discover", "task-graph", "development", "fixtures", "eval-meta", "gate-graph"):
        if command not in baseline_commands:
            raise ValueError("Full engineering verification missing: " + command)


class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load((ROOT / ".github/workflows/synthetic-ci.yml").read_text(encoding="utf-8"))

    def test_readonly_cross_host_baseline(self):
        validate(self.document)

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
        for mutate in (lambda d: d["permissions"].update(contents="write"),
                       lambda d: d["jobs"].update(deploy={"permissions": {"contents": "write"}})):
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.assertRaises(ValueError):
                validate(document)

    def test_elevated_trigger_rejected(self):
        self.document["on"]["pull_request_target"] = None
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_floating_action_rejected(self):
        self.document["jobs"]["public-safety"]["steps"][0]["uses"] = "actions/checkout@v7"
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
        for step in self.document["jobs"]["public-safety"]["steps"]:
            if "scripts/public_guard.py" in step.get("run", ""):
                step["run"] = "echo missing-check"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_missing_history_secret_scan_rejected(self):
        for step in self.document["jobs"]["public-safety"]["steps"]:
            if "scripts/scan_public.py --history" in step.get("run", ""):
                step["run"] = step["run"].replace("scripts/scan_public.py --history", "scripts/scan_public.py")
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_missing_classifier_rejected(self):
        for step in self.document["jobs"]["public-safety"]["steps"]:
            if step.get("id") == "scope":
                step["run"] = "echo docs_only=true"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_public_safety_conditional_rejected(self):
        self.document["jobs"]["public-safety"]["if"] = "false"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_full_baseline_bypass_rejected(self):
        self.document["jobs"]["baseline"]["if"] = "false"
        with self.assertRaises(ValueError):
            validate(self.document)

    def test_shallow_history_rejected(self):
        self.document["jobs"]["public-safety"]["steps"][0]["with"]["fetch-depth"] = 1
        with self.assertRaises(ValueError):
            validate(self.document)
