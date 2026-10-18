"""Owned Windows synthetic runtime. No production secrets or shared clusters.

Generated credentials are protected with Windows current-user DPAPI, not .env.
This is an explicit local operator tool, never imported by an HTTP route.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess

import psycopg
from psycopg import sql
from sqlalchemy import URL, text

from .persistence.database import Database, migrate
from .persistence.role_guards import validate_role_guards


ROOT = Path(__file__).resolve().parents[4] / ".local-runtime" / "synthetic-v1"
ROLES = ("root", "migrator", "identity", "runtime")


def protect(value, *, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("This operator profile requires Windows DPAPI")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("Local credential protection failed")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class LocalRuntime:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.cluster = self.root / "cluster"
        self.manifest = self.root / "runtime.json"

    def configuration(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        if (set(data) != {"profile", "pg_bin", "port", "database"}
                or data["profile"] != "class-os-owned-synthetic-v1"
                or type(data["port"]) is not int or not 1024 <= data["port"] <= 65535
                or data["database"] != "class_os_synthetic_local"):
            raise RuntimeError("Unknown local runtime")
        return data

    def password(self, role):
        if role not in ROLES:
            raise ValueError("Unknown credential consumer")
        return protect((self.root / (role + ".dpapi")).read_bytes(), decrypt=True).decode("ascii")

    def run(self, binary, *arguments, input=None):
        config = self.configuration()
        path = Path(config["pg_bin"]) / (binary + ".exe")
        result = subprocess.run([str(path), *map(str, arguments)], input=input,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(f"Local PostgreSQL {binary} failed; no automatic reset attempted")

    def initialize(self, pg_root):
        if os.name != "nt" or self.root.exists():
            raise RuntimeError("Initialization requires a new owned Windows runtime directory")
        binaries = Path(pg_root).resolve()
        if (binaries / "bin").is_dir():
            binaries /= "bin"
        for name in ("initdb", "pg_ctl", "postgres"):
            if not (binaries / (name + ".exe")).is_file():
                raise RuntimeError("Required PostgreSQL binary missing")
        version = subprocess.run([str(binaries / "postgres.exe"), "--version"], capture_output=True,
                                 timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        if version.returncode or b"PostgreSQL) 18." not in version.stdout:
            raise RuntimeError("PostgreSQL 18 required")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.root.mkdir(parents=True)
        # ACL applies before any encrypted credential or database is generated.
        owner = subprocess.run(["whoami"], capture_output=True, text=True, check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        subprocess.run(["icacls", str(self.root), "/inheritance:r", "/grant:r", owner + ":(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        config = {"profile": "class-os-owned-synthetic-v1", "pg_bin": str(binaries),
                  "port": port, "database": "class_os_synthetic_local"}
        self.manifest.write_text(json.dumps(config, indent=2), encoding="utf-8")
        for role in ROLES:
            (self.root / (role + ".dpapi")).write_bytes(protect(secrets.token_urlsafe(48).encode("ascii")))
        password = self.password("root")
        # No listener exists during single-user provisioning. Start from reject
        # authentication, set the password through stdin, then enable SCRAM.
        # No plaintext pwfile, command-line password or persisted environment.
        self.run("initdb", "-D", self.cluster, "-U", "class_os_local_root", "-A", "reject",
                 "--encoding=UTF8", "--locale=C")
        self.run("postgres", "--single", "-D", self.cluster, "postgres",
                 input=("ALTER ROLE class_os_local_root PASSWORD '" + password + "';\n").encode())
        (self.cluster / "pg_hba.conf").write_text(
            "host all all 127.0.0.1/32 scram-sha-256\nhost all all ::1/128 reject\n",
            encoding="utf-8")
        self.start()
        try:
            with self.admin() as connection:
                for role in ROLES[1:]:
                    connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}")
                                       .format(sql.Identifier("class_os_" + role), sql.Literal(self.password(role))))
                connection.execute("CREATE DATABASE class_os_synthetic_local OWNER class_os_migrator")
                connection.execute("REVOKE CONNECT ON DATABASE class_os_synthetic_local FROM PUBLIC")
                connection.execute("GRANT CONNECT ON DATABASE class_os_synthetic_local TO class_os_migrator,class_os_identity,class_os_runtime")
            self.upgrade()
        finally:
            self.stop()

    def admin(self):
        config = self.configuration()
        return psycopg.connect(host="127.0.0.1", port=config["port"], user="class_os_local_root",
                               password=self.password("root"), dbname="postgres", autocommit=True,
                               connect_timeout=3)

    def start(self):
        config = self.configuration()
        self.run("pg_ctl", "-D", self.cluster, "-l", self.root / "postgres.log", "-o",
                 f"-p {config['port']} -h 127.0.0.1 -c shared_buffers=32MB -c max_connections=30 -c log_statement=none",
                 "start", "-w", "-t", "30")

    def stop(self):
        self.configuration()
        self.run("pg_ctl", "-D", self.cluster, "stop", "-m", "fast", "-w", "-t", "30")

    def database(self, role):
        if role not in ROLES[1:]:
            raise ValueError("Application cannot obtain administrator connection")
        config = self.configuration()
        url = URL.create("postgresql+psycopg", username="class_os_" + role,
                         password=self.password(role), host="127.0.0.1", port=config["port"], database=config["database"])
        return Database(url, migration=role == "migrator", identity=role == "identity")

    def upgrade(self):
        database = self.database("migrator")
        try:
            migrate(database)
        finally:
            database.close()


def compose(settings, runtime):
    """Composition owns adapters; never expose administrator/migrator to app."""
    from pwdlib import PasswordHash
    from class_os.application.identity import IdentityBoundary
    from class_os.application.roster import BusinessGateway, QueryGateway
    from class_os.infrastructure.identity import PostgresIdentityStore
    from class_os.infrastructure.roster import PostgresBusinessStore
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.interfaces.http.app import create_app

    identity_database, business_database = runtime.database("identity"), runtime.database("runtime")
    identity = IdentityBoundary(PostgresIdentityStore(identity_database), PasswordHash.recommended())
    from .model_secrets import ModelSecrets
    from .model_control import ModelController
    vault = ModelSecrets(protect) if os.name == "nt" else None
    store = PostgresBusinessStore(business_database, model_secrets=vault)

    def readiness():
        with business_database.transaction(read_only=True) as connection:
            if connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != "0016":
                raise RuntimeError("Runtime schema version not current")
            validate_role_guards(connection)
            for column in ("name", "start_date", "end_date"):
                if not connection.execute(text("SELECT pg_catalog.has_column_privilege(current_user, 'class_os.academic_term', :column, 'UPDATE')"), {"column": column}).scalar_one():
                    raise RuntimeError("Runtime feature privileges not current")
            row = connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one()
            connection.execute(text("SELECT student_id,version FROM class_os.student LIMIT 0"))
            connection.execute(text("SELECT proposal_id,payload_hash FROM class_os.command_proposal LIMIT 0"))
            connection.execute(text("SELECT record_id,version FROM class_os.record_revision LIMIT 0"))
            connection.execute(text("SELECT task_id,status FROM class_os.manual_task LIMIT 0"))
            connection.execute(text("SELECT export_id,package_hash FROM class_os.export_job LIMIT 0"))
            connection.execute(text("SELECT version,protocol,sealed FROM class_os.model_configuration LIMIT 0"))
            if not connection.execute(text("SELECT pg_catalog.has_column_privilege(current_user, 'class_os.student', 'name', 'UPDATE')")).scalar_one():
                raise RuntimeError("Runtime feature privileges not current")
            if not connection.execute(text("SELECT pg_catalog.has_column_privilege(current_user, 'class_os.student_identifier', 'valid_to', 'UPDATE')")).scalar_one():
                raise RuntimeError("Runtime feature privileges not current")
            if not connection.execute(text("SELECT pg_catalog.has_column_privilege(current_user, 'class_os.manual_task', 'title', 'UPDATE') AND pg_catalog.has_column_privilege(current_user, 'class_os.manual_task', 'due_at', 'UPDATE')")).scalar_one():
                raise RuntimeError("Runtime feature privileges not current")
            if row != "synthetic-only":
                raise RuntimeError("Runtime schema not current")
        with identity_database.transaction(read_only=True) as connection:
            connection.execute(text("SELECT owner_id FROM class_os.owner_account LIMIT 1"))
            connection.execute(text("SELECT request_id,client_digest,csrf_digest FROM class_os.identity_audit LIMIT 0"))

    query = QueryGateway(identity, store)
    agent = PydanticAgentRuntime(query)
    controller = ModelController(query, vault, agent, allowed_bases=settings.model_api_bases) if vault else None
    if controller:
        agent.model_context = controller.context
        agent.provider_label = "managed-model"
        agent.provider_state = controller.label
    return create_app(settings, identity=identity, business=BusinessGateway(identity, store),
                      query=query, readiness=readiness, agent=agent, model_controller=controller)
