"""Only creates disposable local test databases; never accepts an existing DSN."""
from contextlib import contextmanager
from pathlib import Path
import socket
import subprocess
import tempfile
from uuid import uuid4

import pytest
import psycopg
from psycopg import sql
from sqlalchemy import URL


def pytest_addoption(parser):
    parser.addoption("--pg-root", default=None, help="PostgreSQL binary directory (bin/ or installation root)")


@pytest.fixture(scope="session")
def postgres_cluster(request):
    configured = request.config.getoption("--pg-root")
    if not configured:
        pytest.fail("DB suite requires --pg-root; tests are not silently skipped")
    pg_root = Path(configured).resolve()
    if (pg_root / "bin").is_dir():
        pg_root /= "bin"
    suffix = ".exe" if __import__("os").name == "nt" else ""
    for name in ("initdb", "pg_ctl", "postgres"):
        if not (pg_root / (name + suffix)).is_file():
            pytest.fail(f"Required PostgreSQL binary missing: {name}")
    with tempfile.TemporaryDirectory(prefix="class-os-test-pg-") as temporary:
        runtime = Path(temporary).resolve()
        data = runtime / "cluster"
        assert data.parent == runtime
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        def run(name, *args):
            result = subprocess.run([str(pg_root / (name + suffix)), *map(str, args)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError(f"Disposable PostgreSQL {name} failed")

        run("initdb", "-D", data, "-U", "class_os_test_root", "--auth=trust", "--encoding=UTF8", "--locale=C")
        running = False
        socket_options = "" if suffix else " -c unix_socket_directories="
        try:
            run("pg_ctl", "-D", data, "-l", runtime / "postgres.log", "-o",
                f"-p {port} -h 127.0.0.1{socket_options} -c shared_buffers=32MB -c max_connections=20", "start", "-w", "-t", "30")
            running = True
            with psycopg.connect(host="127.0.0.1", port=port, user="class_os_test_root", dbname="postgres", autocommit=True) as root:
                root.execute("CREATE ROLE class_os_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
                root.execute("CREATE ROLE class_os_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
                root.execute("CREATE ROLE class_os_identity LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
            yield {"host": "127.0.0.1", "port": port, "user": "class_os_test_root", "dbname": "postgres"}
        finally:
            if running:
                # Only this fixture's fresh directory; never stop a shared service.
                run("pg_ctl", "-D", data, "stop", "-m", "immediate", "-w", "-t", "30")


@pytest.fixture
def database_urls(postgres_cluster):
    name = "class_os_synthetic_" + uuid4().hex
    with psycopg.connect(**postgres_cluster, autocommit=True) as root:
        root.execute(sql.SQL("CREATE DATABASE {} OWNER class_os_migrator").format(sql.Identifier(name)))
    port = postgres_cluster["port"]
    urls = {role: URL.create("postgresql+psycopg", username="class_os_" + role, host="127.0.0.1", port=port, database=name)
            for role in ("migrator", "runtime", "identity")}
    try:
        yield urls
    finally:
        with psycopg.connect(**postgres_cluster, autocommit=True) as root:
            root.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
