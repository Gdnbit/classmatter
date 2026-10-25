"""Trusted local synthetic checkpoints, never an upload/import or Agent API.

pg_restore executes source SQL: only this owned runtime's DPAPI artifacts are
accepted. This is not a portable exit package, production backup or PITR.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import UUID, uuid4

from psycopg import sql
from sqlalchemy import text

from .local_runtime import protect
from .persistence.database import Database
from .persistence.schema_inventory import REGISTERED_TABLES, validate_surface, schema_profile
from .persistence.role_guards import validate_role_guards


HEAD = "0016"
MIB = 1024 * 1024
ARCHIVE_LIMIT = 16 * MIB
PACKET_LIMIT = 32 * MIB
CATALOG_LIMIT = 128
CATALOG_BYTES = 64 * MIB


class BackupRejected(Exception):
    def __init__(self):
        super().__init__("Owned synthetic backup operation rejected; source and existing backups preserved")


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise BackupRejected()
        value[key] = item
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class SyntheticBackup:
    def __init__(self, runtime, *, codec=protect, profile="r1"):
        if profile not in ("r1", "conversation-d1"):
            raise ValueError("Unsupported checkpoint profile")
        self.head, self.tables = schema_profile(profile)
        self.profile = profile
        self.kind = "class-os.owned-synthetic-backup.v1" if profile == "r1" else "classmatter.owned-conversation-backup.v1"
        self.runtime, self.codec = runtime, codec

    def _binding(self):
        binding = {"root": str(self.runtime.root.resolve()), "configuration": self.runtime.configuration()}
        if self.profile != "r1":
            binding["schema_profile"] = self.profile
        return hashlib.sha256(encoded(binding)).hexdigest()

    def _directory(self, *, create=True):
        root = self.runtime.root.resolve()
        directory = root / "backups"
        if directory.is_symlink() or directory.is_junction() or directory.resolve().parent != root:
            raise BackupRejected()
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
        return directory

    def _publish(self, artifact, sealed):
        directory = self._directory()
        destination = directory / (str(artifact) + ".dpapi")
        pending = None
        try:
            # Write and sync encrypted bytes before an atomic, exclusive link.
            # Never replace an existing checkpoint, even on an ID collision.
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".checkpoint-", suffix=".pending", delete=False) as output:
                pending = Path(output.name)
                output.write(sealed); output.flush(); os.fsync(output.fileno())
            os.link(pending, destination)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    def catalog(self):
        """Bounded metadata inspection only; does not connect to PostgreSQL."""
        try:
            directory = self._directory(create=False)
            entries, pending, unrecognized, total = [], 0, 0, 0
            if directory.exists():
                with os.scandir(directory) as candidates:
                    for number, candidate in enumerate(candidates, start=1):
                        if number > CATALOG_LIMIT:
                            raise BackupRejected()
                        name = candidate.name
                        if re.fullmatch(r"\.checkpoint-[a-z0-9_]+\.pending", name):
                            pending += 1
                            continue
                        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.dpapi", name):
                            unrecognized += 1
                            continue
                        artifact = UUID(name[:-6])
                        row = {"backup_id": str(artifact), "status": "rejected", "restore_verified": False}
                        # Preflight an aggregate bound before reading protected packets.
                        total += candidate.stat(follow_symlinks=False).st_size
                        if total > CATALOG_BYTES:
                            raise BackupRejected()
                        try:
                            packet, _ = self._open(artifact)
                            row.update(status="metadata-verified", created_at=packet["created_at"])
                        except BackupRejected:
                            pass
                        entries.append(row)
            result = {"schema_version": "class-os.synthetic-backup-catalog.v1", "portable": False,
                    "complete_exit": False, "checkpoints": sorted(entries, key=lambda row: row["backup_id"]),
                    "pending_files": pending, "unrecognized_files": unrecognized}
            if self.profile != "r1":
                result.update(schema_version="classmatter.conversation-backup-catalog.v1", activation_allowed=False)
            return result
        except Exception:
            raise BackupRejected() from None

    @staticmethod
    def _state(connection, *, profile="r1"):
        head, _ = schema_profile(profile)
        validate_surface(connection, complete=True, profile=profile)
        if (connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != head
                or connection.execute(text("SELECT data_mode FROM class_os.database_state WHERE singleton=true")).scalar_one() != "synthetic-only"):
            raise BackupRejected()
        validate_role_guards(connection, profile=profile)
        if profile != "r1":
            from .conversation_integrity import validate_conversation_integrity
            validate_conversation_integrity(connection)
            from .target_import_store import validate_import_integrity
            validate_import_integrity(connection)

    @staticmethod
    def _inventory(connection, *, profile="r1"):
        result, total = {}, 0
        _, tables = schema_profile(profile)
        for table in sorted(tables):
            # Closed source registry, never a caller/model-selected identifier.
            rows, size = connection.execute(text(f"SELECT count(*),coalesce(sum(octet_length(to_jsonb(t)::text)),0) FROM class_os.{table} t")).one()
            total += size
            if rows > 10000 or total > 12 * MIB:
                raise BackupRejected()
            data = connection.execute(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb) FROM class_os.{table} t")).scalar_one()
            result[table] = {"rows": rows, "sha256": hashlib.sha256(encoded(data)).hexdigest()}
        return result

    def _pg(self, binary, database, *arguments, archive=None):
        config = self.runtime.configuration()
        if (binary not in ("pg_dump", "pg_restore") or not re.fullmatch(r"class_os_synthetic_[a-z0-9_]{1,40}", database)
                or type(config["port"]) is not int or not 1024 <= config["port"] <= 65535):
            raise BackupRejected()
        executable = Path(config["pg_bin"]) / (binary + (".exe" if os.name == "nt" else ""))
        if not executable.is_file():
            raise BackupRejected()
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH", "LANG") if key in os.environ}
        environment.update(PGPASSWORD=self.runtime.password("migrator"), PGCONNECT_TIMEOUT="3", PGSSLMODE="disable",
                           PGAPPNAME="class-os-owned-backup", PGOPTIONS="-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=15000")
        try:
            completed = subprocess.run([str(executable), "--host=127.0.0.1", f"--port={config['port']}",
                "--username=class_os_migrator", f"--dbname={database}", "--no-password", *arguments],
                input=archive, capture_output=True, timeout=45, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode or completed.stderr or len(completed.stdout) > ARCHIVE_LIMIT:
                raise BackupRejected()
            return completed.stdout
        except (OSError, subprocess.SubprocessError):
            raise BackupRejected() from None
        finally:
            environment.clear()

    def create(self):
        database = self.runtime.database("migrator")
        artifact = uuid4()
        try:
            with database.transaction(read_only=True) as connection:
                connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                if not connection.execute(text("SELECT pg_try_advisory_xact_lock_shared(607103003)")).scalar_one():
                    raise BackupRejected()
                self._state(connection, profile=self.profile)
                if connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one() > 32 * MIB:
                    raise BackupRejected()
                snapshot = connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
                if not re.fullmatch(r"[0-9A-Fa-f-]{1,80}", snapshot):
                    raise BackupRejected()
                # Bound logical data before a subprocess captures the archive;
                # a physically small TOAST-compressed DB may expand substantially.
                inventory = self._inventory(connection, profile=self.profile)
                archive = self._pg("pg_dump", database.engine.url.database, "--format=custom", "--no-large-objects", f"--snapshot={snapshot}")
                if not archive.startswith(b"PGDMP") or len(archive) > ARCHIVE_LIMIT:
                    raise BackupRejected()
            packet = {"kind": self.kind, "id": str(artifact), "head": self.head,
                      "created_at": datetime.now(timezone.utc).isoformat(), "binding": self._binding(),
                      "archive_sha256": hashlib.sha256(archive).hexdigest(),
                      "archive": base64.b64encode(archive).decode("ascii"), "inventory": inventory}
            if self.profile != "r1":
                packet.update(schema_profile=self.profile, activation_allowed=False)
            sealed = self.codec(encoded(packet))
            if type(sealed) is not bytes or not 1 <= len(sealed) <= PACKET_LIMIT:
                raise BackupRejected()
            directory = self._directory()
            if shutil.disk_usage(directory).free < len(sealed) + MIB:
                raise BackupRejected()
            self._publish(artifact, sealed)
            return artifact
        except Exception:
            raise BackupRejected() from None
        finally:
            database.close()

    def _open(self, artifact):
        try:
            if type(artifact) is not UUID:
                raise BackupRejected()
            path = self._directory(create=False) / (str(artifact) + ".dpapi")
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise BackupRejected()
            with path.open("rb") as source:
                sealed = source.read(PACKET_LIMIT + 1)
            if not 1 <= len(sealed) <= PACKET_LIMIT:
                raise BackupRejected()
            plain = self.codec(sealed, decrypt=True)
            if type(plain) is not bytes or not 1 <= len(plain) <= PACKET_LIMIT:
                raise BackupRejected()
            packet = json.loads(plain, object_pairs_hook=unique)
            fields = {"kind", "id", "head", "created_at", "binding", "archive_sha256", "archive", "inventory"}
            if self.profile != "r1":
                fields |= {"schema_profile", "activation_allowed"}
            if (type(packet) is not dict or set(packet) != fields
                    or packet["kind"] != self.kind or packet["id"] != str(artifact)
                    or packet["head"] != self.head or packet["binding"] != self._binding()
                    or (self.profile != "r1" and (packet["schema_profile"] != self.profile or packet["activation_allowed"] is not False))
                    or type(packet["created_at"]) is not str or len(packet["created_at"]) > 50
                    or datetime.fromisoformat(packet["created_at"]).utcoffset() != timedelta(0)
                    or type(packet["archive"]) is not str or len(packet["archive"]) > 24 * MIB
                    or type(packet["inventory"]) is not dict or set(packet["inventory"]) != self.tables):
                raise BackupRejected()
            for value in packet["inventory"].values():
                if (type(value) is not dict or set(value) != {"rows", "sha256"} or type(value["rows"]) is not int
                        or not 0 <= value["rows"] <= 10000 or type(value["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
                    raise BackupRejected()
            archive = base64.b64decode(packet["archive"], validate=True)
            if not archive.startswith(b"PGDMP") or len(archive) > ARCHIVE_LIMIT or hashlib.sha256(archive).hexdigest() != packet["archive_sha256"]:
                raise BackupRejected()
            return packet, archive
        except Exception:
            raise BackupRejected() from None

    def check(self, artifact):
        return self._check(artifact)

    def check_current_restrictions(self, artifact, restrictions):
        """Trusted same-runtime point-in-time preflight, NOT import authority.

        Requires the actual protected file port, never a caller's proof dict.
        A source change during restore fails closed. No lock/lease is returned
        for a later import: that must establish its own commit-time authority.
        """
        from .conversation_restrictions import ProtectedConversationRestrictions
        if (self.profile != "conversation-d1" or type(restrictions) is not ProtectedConversationRestrictions
                or restrictions.root != self.runtime.root):
            raise BackupRejected()
        return self._check(artifact, restrictions=restrictions)

    def _current_restrictions(self, database, restrictions):
        from .conversation_integrity import restriction_head, validate_restriction_snapshot
        with database.transaction(read_only=True) as connection:
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self._state(connection, profile=self.profile)
            head = restriction_head(connection, restrictions.workspace_id)
            compared = restrictions.compare(head)
            if compared.state != "aligned":
                raise BackupRejected()
            validate_restriction_snapshot(connection, compared.snapshot)
            # Recheck the file after inspecting metadata; a race is refusal,
            # not a promise of a durable lease past this observation.
            restrictions.require_current(head)
            return compared.snapshot

    def _check(self, artifact, *, restrictions=None):
        packet, archive = self._open(artifact)  # Never create a DB for an invalid artifact.
        temporary = "class_os_synthetic_restore_" + uuid4().hex
        database = self.runtime.database("migrator")
        created = False
        try:
            current = self._current_restrictions(database, restrictions) if restrictions is not None else None
            with self.runtime.admin() as root:
                root.execute(sql.SQL("CREATE DATABASE {} OWNER class_os_migrator TEMPLATE template0").format(sql.Identifier(temporary)))
                created = True
                root.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(temporary)))
                root.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO class_os_migrator,class_os_identity,class_os_runtime").format(sql.Identifier(temporary)))
            self._pg("pg_restore", temporary, "--no-owner", "--single-transaction", "--exit-on-error", archive=archive)
            restored = Database(database.engine.url.set(database=temporary), migration=True, profile=self.profile)
            try:
                with restored.transaction(read_only=True) as connection:
                    self._state(connection, profile=self.profile)
                    if self._inventory(connection, profile=self.profile) != packet["inventory"]:
                        raise BackupRejected()
                    if current is not None:
                        from .conversation_integrity import validate_restriction_snapshot
                        validate_restriction_snapshot(connection, current)
            finally:
                restored.close()
            if current is not None and self._current_restrictions(database, restrictions) != current:
                raise BackupRejected()
            result = {"schema_version": "class-os.synthetic-backup-check.v1", "verified": True,
                    "source_preserved": True, "temporary_clone_removed": True,
                    "portable": False, "complete_exit": False, "table_count": len(self.tables)}
            if self.profile != "r1":
                result.pop("verified")
                result.update(schema_version="classmatter.conversation-backup-check.v1",
                              snapshot_integrity_verified=True, activation_allowed=False)
                if current is not None:
                    result.update(current_restrictions_verified_at_check=True, observation_only=True)
            return result
        except Exception:
            raise BackupRejected() from None
        finally:
            database.close()
            if created:
                # Exact random DB allocated above; never a caller-selected target.
                if not re.fullmatch(r"class_os_synthetic_restore_[0-9a-f]{32}", temporary) or temporary == self.runtime.configuration()["database"]:
                    raise BackupRejected()
                with self.runtime.admin() as root:
                    root.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(temporary)))
