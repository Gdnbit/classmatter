"""Explicit local synthetic evaluation operator. Never takes an API key.

Reuse a UI-saved, DPAPI-protected provider configuration and the existing
ISB/controller test+enable path. Business fixtures use disposable pytest PG.
No initialization, migration or class queries against the provider source.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--provider-runtime-root", type=Path)
    parser.add_argument("--pg-root")
    parser.add_argument("--allow-base-url")
    parser.add_argument("--input-cny-per-million")
    parser.add_argument("--output-cny-per-million")
    parser.add_argument("--price-source-url")
    parser.add_argument("--price-verified-at")
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument("--supplier-cap-confirmed", action="store_true")
    parser.add_argument("--compare-report", type=Path)
    args = parser.parse_args()
    from class_os.infrastructure import provider_evaluation as evaluation
    required = (args.live, args.provider_runtime_root, args.pg_root, args.allow_base_url,
                args.input_cny_per_million, args.output_cny_per_million, args.price_source_url,
                args.price_verified_at, args.confirm_cost, args.supplier_cap_confirmed)
    if not all(required):
        print(json.dumps({"status": "blocked", "reason": "explicit_configuration_price_and_cost_consent_required",
                          "cases": 12, "repetitions": 3, "budget_cny": 10, "paid_requests": 0,
                          "dataset_hash": evaluation.DATASET_HASH}))
        return 2
    identity_db = business_db = boundary = authenticated = None
    try:
        verified = datetime.fromisoformat(args.price_verified_at)
        now = datetime.now(timezone.utc)
        if not verified.utcoffset() == timedelta(0) or not now - timedelta(hours=24) <= verified <= now or not args.price_source_url.startswith("https://"):
            raise evaluation.EvalBlocked()
        budget = evaluation.Budget(args.input_cny_per_million, args.output_cny_per_million)
        budget.preflight()
        pg_bin = Path(args.pg_root).resolve()
        if (pg_bin / "bin").is_dir():
            pg_bin /= "bin"
        if os.name != "nt" or not all((pg_bin / (name + ".exe")).is_file() for name in ("initdb", "postgres", "pg_ctl")):
            raise evaluation.EvalBlocked()
        previous = None
        if args.compare_report:
            previous = json.loads(args.compare_report.read_text(encoding="utf-8"))
            evaluation.validate_report(previous)
        from class_os.infrastructure.local_runtime import LocalRuntime, protect
        from class_os.infrastructure.identity import PostgresIdentityStore
        from class_os.application.identity import IdentityBoundary
        from class_os.infrastructure.roster import PostgresBusinessStore
        from class_os.application.roster import QueryGateway
        from class_os.infrastructure.model_control import ModelController
        from class_os.infrastructure.model_secrets import ModelSecrets
        from class_os.infrastructure.agent import PydanticAgentRuntime
        from pwdlib import PasswordHash
        from sqlalchemy import text
        source = LocalRuntime(args.provider_runtime_root)
        source.configuration()  # Existing synthetic manifest; no init/start/migrate.
        identity_db = source.database("identity")
        business_db = source.database("runtime")
        with business_db.transaction(read_only=True) as connection:
            if connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one() != "synthetic-only":
                raise evaluation.EvalBlocked()
        boundary = IdentityBoundary(PostgresIdentityStore(identity_db), PasswordHash.recommended())
        client = secrets.token_urlsafe(32)
        authenticated = boundary.login(getpass.getpass("Owner password (not API key): "), client)
        credentials = (authenticated.token, client, authenticated.csrf, authenticated.subject.workspace_id)
        query = QueryGateway(boundary, PostgresBusinessStore(business_db))
        controller = ModelController(query, ModelSecrets(protect), PydanticAgentRuntime(query), allowed_bases=(args.allow_base_url,))
        async def activate():
            state = await controller.status(credentials)
            if not state["key_configured"] or not state["network_permitted"] or not state["configuration"]:
                raise evaluation.EvalBlocked()
            # Existing protocol probe has a hard two-request limit. Reserve it
            # even if it fails or returns no usage; never refund unknown cost.
            budget.reserve(); budget.reserve()
            candidate = UUID(state["candidate_id"])
            if not await controller.test(credentials, candidate, state["version"], uuid4()):
                raise evaluation.EvalBlocked()
            await controller.enable(credentials, candidate, state["version"])
            return state
        state = asyncio.run(activate())
        evaluation.LIVE_SOURCE = {"controller": controller, "credentials": credentials, "budget": budget}
        evaluation.RESULTS.clear()
        import pytest
        code = pytest.main([str(ROOT / "tests/test_provider_evaluation.py"), "-q", "--tb=no", "-m", "db", "--pg-root", args.pg_root])
        rows = evaluation.RESULTS
        from class_os.application.agent import Mode, DraftKind
        from class_os.application.agent_tool_contracts import for_mode
        tool_contracts = [for_mode(Mode.READ, DraftKind.TASK), for_mode(Mode.DRAFT, DraftKind.TASK), for_mode(Mode.DRAFT, DraftKind.RECORD_NOTE), for_mode(Mode.CHAT, DraftKind.TASK)]
        configuration_hash = hashlib.sha256(json.dumps(state["configuration"], sort_keys=True).encode()).hexdigest()
        report = {"schema_version": "classmatter.synthetic-provider-eval.v1",
                  "status": "needs-human-review" if code == 0 and len(rows) == 36 else "failed-or-incomplete",
                  "formal_release_evidence": False, "dataset_hash": evaluation.DATASET_HASH,
                  "environment": evaluation.environment_fingerprint(),
                  "code_sha": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
                  "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
                  "agent_source_sha256": hashlib.sha256((ROOT / "src/class_os/infrastructure/agent.py").read_bytes()).hexdigest(),
                  "configuration_hash": configuration_hash, "price_source": args.price_source_url,
                  "resolved_models": sorted({name for row in rows for name in row["resolved_models"]}),
                  "tool_contract_sha256": hashlib.sha256(json.dumps(tool_contracts, sort_keys=True).encode()).hexdigest(),
                  "price_verified_at": args.price_verified_at, "reserved_cny": str(budget.reserved),
                  "budget_cny": 10, "probe_usage": "unknown-reserved", "results": rows,
                  "summary": evaluation.summarize(rows),
                  "input_cny_per_million": str(budget.input_rate), "output_cny_per_million": str(budget.output_rate),
                  "model_settings": dict(evaluation.MODEL_SETTINGS),
                  "supplier_bill_guaranteed": False}
        report["comparison"] = evaluation.compare_reports(report, previous) if previous else {"status": "first-baseline-no-improvement-claim"}
        target = ROOT.parent / "test-results/provider-evaluation"
        target.mkdir(parents=True, exist_ok=True)
        output = target / (uuid4().hex + ".json")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": report["status"], "result_id": output.stem, "reserved_cny": str(budget.reserved)}))
        return 0 if code == 0 else 1
    except (Exception, KeyboardInterrupt):
        # No raw exception, configuration, credential, DSN or provider response.
        print(json.dumps({"status": "blocked-or-failed", "reason": "operator_preflight_or_execution_failed",
                          "paid_requests_may_have_occurred": authenticated is not None,
                          "budget_cny": 10, "automatic_retry": False}))
        return 2
    finally:
        evaluation.LIVE_SOURCE = None
        if boundary is not None and authenticated is not None:
            try:
                boundary.logout(authenticated.token, client, authenticated.csrf)
            except Exception:
                pass
        if identity_db is not None:
            identity_db.close()
        if business_db is not None:
            business_db.close()


if __name__ == "__main__":
    raise SystemExit(main())
