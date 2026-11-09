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
    parser.add_argument("command", choices=("init", "prepare-chat", "start", "stop", "migrate", "upgrade-workbench", "upgrade-chat", "upgrade-classroom", "serve", "bootstrap", "initialize-control", "doctor", "support", "backup", "backup-list", "backup-check"))
    parser.add_argument("--profile", choices=("r1", "conversation-d1", "workbench-d2", "workspace-chat-d3", "classroom-work-d4"), default="r1",
                        help="Explicit isolated runtime; never upgrades the other profile")
    parser.add_argument("--pg-root")
    parser.add_argument("--backup-id", type=UUID, help="Owned checkpoint UUID; no arbitrary file paths")
    parser.add_argument("--model-api-base-url", action="append", default=[],
                        help="Explicit trusted endpoint for synthetic model testing; does not enable a model or load keys")
    parser.add_argument("--model-api-proxy", help="Explicit http://127.0.0.1:PORT proxy for model calls only")
    args = parser.parse_args()
    if args.command == 'prepare-chat' and (args.profile != 'conversation-d1' or not args.pg_root):
        parser.error('prepare-chat requires conversation-d1 and --pg-root for a fresh local developer instance')
    if args.command == 'upgrade-workbench' and args.profile not in ('conversation-d1', 'workbench-d2'):
        parser.error('upgrade-workbench requires the existing owned D1/D2 profile')
    if args.command == 'upgrade-chat' and args.profile not in ('conversation-d1', 'workbench-d2', 'workspace-chat-d3'):
        parser.error('upgrade-chat requires the existing owned D1/D2/D3 profile')
    if args.command == 'upgrade-classroom' and args.profile not in ('workspace-chat-d3', 'classroom-work-d4'):
        parser.error('upgrade-classroom requires the existing owned D3/D4 profile')
    if args.profile in ('workbench-d2', 'workspace-chat-d3', 'classroom-work-d4') and args.command in ('init', 'migrate', 'bootstrap', 'initialize-control'):
        parser.error('D2 requires verified in-place upgrade; no new world or identity bootstrap')
    if args.command == "initialize-control":
        if args.profile != "conversation-d1":
            parser.error("initialize-control requires explicit conversation-d1 profile")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("Control initialization requires the owner's interactive terminal")
    if args.profile != "r1" and args.command in ("doctor", "support"):
        parser.error("doctor/support inspect the configured service, not a selected database profile")
    if (args.command == "backup-check") != (args.backup_id is not None):
        parser.error("backup-check requires --backup-id; other commands do not accept it")
    if (args.model_api_base_url or args.model_api_proxy is not None) and args.command != "serve":
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
    runtime = LocalRuntime(profile=args.profile)
    if args.command == 'prepare-chat':
        from class_os.infrastructure.workspace_upgrade import prepare_workspace_chat
        current = prepare_workspace_chat(runtime, args.pg_root)
        print(json.dumps({'schema_version': 'classmatter.workspace-chat-prepared.v1', 'profile': current.profile,
                          'development_no_password': True, 'data_mode': 'synthetic-only'}))
        return 0
    elif args.command == "init":
        if not args.pg_root:
            parser.error("init requires --pg-root")
        runtime.initialize(args.pg_root)
    elif args.command == "start":
        runtime.start()
    elif args.command == "stop":
        runtime.stop()
    elif args.command == "migrate":
        runtime.upgrade()
    elif args.command == 'upgrade-classroom':
        from class_os.infrastructure.classroom_upgrade import upgrade_classroom, verify_upgrade_receipt
        current = upgrade_classroom(runtime)
        print(json.dumps({'schema_version': 'classmatter.owned-classroom-work-upgraded.v1',
            'profile': current.profile, 'backup_id': verify_upgrade_receipt(current)['backup_id'],
            'complete_exit': False, 'activation_allowed': False}))
        return 0
    elif args.command == 'upgrade-chat':
        from class_os.infrastructure.workspace_upgrade import upgrade_workspace_chat, verify_upgrade_receipt
        current = upgrade_workspace_chat(runtime)
        print(json.dumps({'schema_version': 'classmatter.owned-workspace-chat-upgraded.v1',
            'profile': current.profile, 'backup_id': verify_upgrade_receipt(current)['backup_id'],
            'complete_exit': False, 'activation_allowed': False}))
        return 0
    elif args.command == 'upgrade-workbench':
        from class_os.infrastructure.workbench_upgrade import upgrade_workbench, verify_upgrade_receipt
        current = upgrade_workbench(runtime)
        print(json.dumps({'schema_version': 'classmatter.owned-workbench-upgraded.v1',
            'profile': current.profile, 'backup_id': verify_upgrade_receipt(current)['backup_id'],
            'complete_exit': False, 'activation_allowed': False}))
        return 0
    elif args.command in ("backup", "backup-list", "backup-check"):
        from class_os.infrastructure.operator_backup import SyntheticBackup
        backup = SyntheticBackup(runtime, profile=args.profile)
        if args.command == "backup":
            created = {"schema_version": "class-os.synthetic-backup-created.v1",
                       "backup_id": str(backup.create()), "portable": False, "complete_exit": False}
            if args.profile != "r1":
                created.update(schema_version="classmatter.conversation-backup-created.v1", activation_allowed=False)
                if args.profile == 'classroom-work-d4':
                    created['schema_version'] = 'classmatter.classroom-work-backup-created.v1'
                elif args.profile == 'workspace-chat-d3':
                    created['schema_version'] = 'classmatter.workspace-chat-backup-created.v1'
            print(json.dumps(created))
        elif args.command == "backup-list":
            print(json.dumps(backup.catalog()))
        else:
            if args.profile == "r1":
                print(json.dumps(backup.check(args.backup_id)))
            else:
                if args.profile in ('workspace-chat-d3', 'classroom-work-d4'):
                    from class_os.infrastructure.workspace_local_runtime import open_services
                elif args.profile == 'workbench-d2':
                    from class_os.infrastructure.workbench_local_runtime import open_services
                else:
                    from class_os.infrastructure.durable_local_runtime import open_services
                services = open_services(runtime)
                try:
                    services.readiness()
                    print(json.dumps(backup.check_current_restrictions(args.backup_id, services.restrictions)))
                finally:
                    services.close()
        return 0
    elif args.command == "serve":
        import uvicorn
        settings = Settings.from_env({"CLASS_OS_PORT": "8001", **os.environ} if args.profile != "r1" else os.environ)
        from dataclasses import replace
        settings = replace(settings, model_api_bases=tuple(args.model_api_base_url), model_api_proxy=args.model_api_proxy)
        if args.profile in ('workspace-chat-d3', 'classroom-work-d4'):
            from class_os.infrastructure.workspace_local_runtime import compose as compose_chat
            app = compose_chat(settings, runtime)
        elif args.profile == 'workbench-d2':
            from class_os.infrastructure.workbench_local_runtime import compose as compose_workbench
            app = compose_workbench(settings, runtime)
        elif args.profile == "conversation-d1":
            from class_os.infrastructure.durable_local_runtime import compose as compose_d1
            app = compose_d1(settings, runtime)
        else:
            app = compose(settings, runtime)
        from class_os.interfaces.http.web import mount_web
        mount_web(app, Path(__file__).resolve().parents[1] / "apps/web/dist")
        uvicorn.run(app, host=settings.bind_host, port=settings.port, reload=False, proxy_headers=False, access_log=False)
    elif args.command == "initialize-control":
        import secrets
        from uuid import uuid4
        from class_os.domain.conversation_control import InitializeConversationControl
        from class_os.infrastructure.durable_local_runtime import open_services
        services = open_services(runtime)
        try:
            client = secrets.token_urlsafe(32)
            login = services.identity.login(getpass.getpass("Current Owner password: "), client)
            try:
                auth = (login.token, client, login.csrf, login.subject.workspace_id)
                proposal = services.worker.preview(*auth, InitializeConversationControl(uuid4()))
                print("Initialize this new D1 instance's protected conversation control (Risk X).")
                print(json.dumps({"proposal_id": str(proposal.proposal_id), "payload_hash": proposal.payload_hash,
                                  "command": proposal.command.canonical()}, ensure_ascii=False))
                if input("Type INITIALIZE D1 to approve, otherwise cancel: ") != "INITIALIZE D1":
                    print("Cancelled; no authority initialized.")
                    return 0
                approval = services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash)
                receipt = services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
                services.readiness()
            finally:
                services.identity.logout(login.token, client, login.csrf)
            print(json.dumps({"schema_version": "classmatter.conversation-control-initialized.v1",
                              "receipt_id": str(receipt.receipt_id)}))
        finally:
            services.close()
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
