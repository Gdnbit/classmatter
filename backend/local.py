"""Explicit local operator commands; never prints database credentials."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from class_os.interfaces.http.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="ClassMatter owned synthetic Windows runtime; no real data")
    parser.add_argument("command", choices=("init", "start", "stop", "migrate", "serve", "bootstrap", "doctor", "support", "backup", "backup-check"))
    parser.add_argument("--pg-root")
    parser.add_argument("--backup-id", type=UUID, help="Owned checkpoint UUID; no arbitrary file paths")
    parser.add_argument("--model-api-base-url", action="append", default=[],
                        help="Explicit trusted endpoint for synthetic model testing; does not enable a model or load keys")
    args = parser.parse_args()
    if (args.command == "backup-check") != (args.backup_id is not None):
        parser.error("backup-check requires --backup-id; other commands do not accept it")
    if args.model_api_base_url and args.command != "serve":
        parser.error("model API endpoints are only accepted for serve")
    if args.command == "support" and args.pg_root:
        parser.error("support does not accept runtime paths")
    if args.command == "doctor":
        from class_os.interfaces.operator.doctor import diagnose
        result = diagnose(Settings.from_env(os.environ))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ready"] else 1
    if args.command == "support":
        from class_os.interfaces.operator.support import collect
        result = collect(Settings.from_env(os.environ))
        print(result.model_dump_json())
        return 0 if result.health.ready else 1
    # Read-only doctor/support/help must not import the database/model runtime.
    # Keep their startup bounded independently of optional SDK import costs.
    from class_os.infrastructure.local_runtime import LocalRuntime, compose
    runtime = LocalRuntime()
    if args.command == "init":
        if not args.pg_root:
            parser.error("init requires --pg-root")
        runtime.initialize(args.pg_root)
    elif args.command == "start":
        runtime.start()
    elif args.command == "stop":
        runtime.stop()
    elif args.command == "migrate":
        runtime.upgrade()
    elif args.command in ("backup", "backup-check"):
        from class_os.infrastructure.operator_backup import SyntheticBackup
        backup = SyntheticBackup(runtime)
        if args.command == "backup":
            print(json.dumps({"schema_version": "class-os.synthetic-backup-created.v1",
                              "backup_id": str(backup.create()), "portable": False, "complete_exit": False}))
        else:
            print(json.dumps(backup.check(args.backup_id)))
        return 0
    elif args.command == "serve":
        import uvicorn
        settings = Settings.from_env(os.environ)
        from dataclasses import replace
        settings = replace(settings, model_api_bases=tuple(args.model_api_base_url))
        app = compose(settings, runtime)
        from class_os.interfaces.http.web import mount_web
        mount_web(app, Path(__file__).resolve().parents[1] / "apps/web/dist")
        uvicorn.run(app, host=settings.bind_host, port=settings.port, reload=False, proxy_headers=False, access_log=False)
    elif args.command == "bootstrap":
        # Trusted local console only, never a public bootstrap/arming route.
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("Bootstrap requires the owner's interactive terminal")
        import secrets
        from pwdlib import PasswordHash
        from class_os.application.identity import IdentityBoundary
        from class_os.infrastructure.identity import PostgresIdentityStore
        database = runtime.database("identity")
        try:
            identity = IdentityBoundary(PostgresIdentityStore(database), PasswordHash.recommended())
            password = getpass.getpass("Owner password (16+ characters): ")
            if password != getpass.getpass("Repeat password: "):
                raise ValueError("Passwords did not match")
            client = secrets.token_urlsafe(32)
            result = identity.bootstrap(identity.arm_bootstrap(), password, client)
            print("Save these one-time recovery codes offline. They will not be shown again:")
            for code in result.recovery_codes:
                print(code)
            identity.logout(result.token, client, result.csrf)
        finally:
            database.close()
    print("Local operation completed (synthetic-only).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Database exceptions may include connection details; no traceback dump.
        print("Local operation failed; runtime was preserved. Check command and local service state.", file=sys.stderr)
        sys.exit(1)
