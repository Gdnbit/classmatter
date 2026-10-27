"""Fixed synthetic desktop service entry. No database init/migrate/bootstrap."""
import argparse
import os
from pathlib import Path
import re
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main():
    parser = argparse.ArgumentParser(description="ClassMatter synthetic desktop service")
    parser.add_argument("--ui-root", required=True, type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--profile", choices=("r1", "conversation-d1"), default="r1")
    parser.add_argument("--parent-pipe", action="store_true")
    args = parser.parse_args()
    key = os.environ.pop("CLASSMATTER_DESKTOP_PROCESS_KEY", "")
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Desktop process proof required")
    # Credentials remain in the existing current-user DPAPI runtime; no new
    # owner/database is created and no migration or PostgreSQL lifecycle runs.
    from class_os.interfaces.http.settings import Settings
    from class_os.infrastructure.local_runtime import LocalRuntime, compose
    from class_os.interfaces.http.web import mount_web
    from class_os.interfaces.http.desktop_host import install_desktop_proof
    import uvicorn
    settings = Settings.from_env(os.environ)
    runtime = LocalRuntime(args.runtime_root, profile=args.profile)
    if args.profile == "conversation-d1":
        from class_os.infrastructure.durable_local_runtime import compose as compose_d1
        app = compose_d1(settings, runtime)
    else:
        app = compose(settings, runtime)
    install_desktop_proof(app, key)
    mount_web(app, args.ui_root)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.bind_host, port=settings.port, proxy_headers=False, access_log=False, log_level="critical"))
    if args.parent_pipe:
        # Parent owns an empty stdin pipe. EOF (including parent crash) or any
        # unexpected byte requests shutdown; stdin never carries commands.
        def parent_closed():
            try:
                os.read(sys.stdin.fileno(), 1)
            finally:
                server.should_exit = True
        threading.Thread(target=parent_closed, daemon=True).start()
    server.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Desktop service unavailable; existing runtime preserved. Initialize/start it with the documented operator workflow.", file=sys.stderr)
        sys.exit(1)
