"""Database backup and recovery drill.

Proves that a Day 23 reconciliation package works with a restored PostgreSQL
database, not just the original database. The drill restores a backup into an
isolated destination, then runs the Day 24 recovery drill against it.

python -m ledger.pipeline.database_recovery test
python -m ledger.pipeline.database_recovery backup --output PATH.dump
python -m ledger.pipeline.database_recovery drill \
    --backup PATH.dump --package PATH.zip --confirm-isolated-target
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from ledger.pipeline.evidence_bundle import (
    publish_no_overwrite,
)

VERSION = "ledger-database-backup-v1"
DRILL_VERSION = "ledger-database-recovery-drill-v1"


def now() -> str:
    return datetime.now(UTC).isoformat()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} through your normal secret-management process.")
    return value


def postgres_environment(
    connection_string: str, read_only: bool = False
) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGDATABASE"] = connection_string
    if read_only:
        existing = environment.get("PGOPTIONS", "")
        environment["PGOPTIONS"] = (
            existing + " -c default_transaction_read_only=on"
        ).strip()
    return environment


def source_database(connection_string: str) -> str:
    with psycopg.connect(connection_string) as connection, connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        return connection.execute("SELECT current_database()").fetchone()[0]


def require_safe_target(
    source_name: str, target_name: str, superuser: bool, occupied: bool
) -> None:
    if source_name == target_name:
        raise ValueError(
            "Destination must have a different database name from the source."
        )
    if superuser:
        raise ValueError("Use a non-superuser destination role.")
    if occupied:
        raise ValueError(
            "Destination contains user objects. Provision a fresh database."
        )


def inspect_target(connection_string: str, source_name: str) -> str:
    with psycopg.connect(connection_string) as connection, connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        target_name, superuser = connection.execute(
            """
            SELECT current_database(), rolsuper
            FROM pg_roles WHERE rolname = current_user
            """
        ).fetchone()

        occupied = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname NOT LIKE 'pg_%'
                      AND n.nspname <> 'information_schema'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_proc p
                    JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname NOT LIKE 'pg_%'
                      AND n.nspname <> 'information_schema'
                )
                OR EXISTS (
                    SELECT 1 FROM pg_namespace
                    WHERE nspname NOT LIKE 'pg_%'
                      AND nspname NOT IN ('information_schema', 'public')
                )
                OR EXISTS (
                    SELECT 1 FROM pg_extension
                    WHERE extname <> 'plpgsql'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE n.nspname NOT LIKE 'pg_%'
                      AND n.nspname <> 'information_schema'
                )
            """
        ).fetchone()[0]

        require_safe_target(source_name, target_name, superuser, occupied)
    return target_name


def run_logged(
    command: list[str], environment: dict[str, str], directory: Path, label: str
) -> int:
    with (
        (directory / f"{label}.stdout.log").open("w") as stdout,
        (directory / f"{label}.stderr.log").open("w") as stderr,
    ):
        return subprocess.run(
            command,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            text=True,
            check=False,
        ).returncode


def metadata_path(dump_path: Path) -> Path:
    return Path(str(dump_path) + ".json")


def verify_backup(path: Path, metadata: dict[str, Any]) -> None:
    if metadata.get("version") != VERSION:
        raise ValueError("Unsupported database backup manifest.")
    if not isinstance(metadata.get("source_database"), str):
        raise TypeError("Backup manifest lacks a source database name.")
    if file_hash(path) != metadata.get("dump_sha256"):
        raise ValueError("Database dump hash differs from its manifest.")


def restore_environment(connection_string: str) -> dict[str, str]:
    try:
        settings = conninfo_to_dict(connection_string)
    except psycopg.ProgrammingError as exc:
        raise ValueError(f"Invalid connection string: {exc}") from exc
    supported = {
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "sslrootcert": "PGSSLROOTCERT",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "application_name": "PGAPPNAME",
        "passfile": "PGPASSFILE",
        "options": "PGOPTIONS",
    }

    unsupported = set(settings) - set(supported) - {"dbname"}
    if unsupported:
        raise ValueError(
            "Destination uses unsupported connection options: "
            + ", ".join(sorted(unsupported))
        )

    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("PG")
    }
    for key, variable in supported.items():
        if key in settings:
            environment[variable] = settings[key]
    return environment


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise ValueError(f"{name} is not installed or not on PATH.")


def backup(args: argparse.Namespace) -> int:
    require_tool("pg_dump")
    source = required_environment("DATABASE_URL")
    source_name = source_database(source)

    destination = Path(args.output)
    manifest_path = metadata_path(destination)
    if destination.exists() or manifest_path.exists():
        raise ValueError("Choose a new backup output path.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    log_directory = Path("results/day25") / str(uuid.uuid4())
    log_directory.mkdir(parents=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=".ledger-dump-", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)

    try:
        code = run_logged(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(temporary),
            ],
            postgres_environment(source, read_only=True),
            log_directory,
            "backup",
        )
        if code != 0:
            raise ValueError(f"pg_dump failed. Inspect logs in {log_directory}.")

        digest = file_hash(temporary)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = {
        "version": VERSION,
        "created_at": now(),
        "source_database": source_name,
        "dump_sha256": digest,
        "format": "postgresql-custom",
        "ownership_and_permissions_preserved": False,
        "signed": False,
    }
    publish_no_overwrite(
        manifest_path,
        json.dumps(manifest, indent=2).encode("utf-8"),
    )

    print(f"Backup: {destination}")
    print(f"Manifest: {manifest_path}")
    print(f"SHA-256: {digest}")
    return 0


def drill(args: argparse.Namespace) -> int:
    if not args.confirm_isolated_target:
        raise ValueError(
            "Provide --confirm-isolated-target only after verifying "
            "the destination is a dedicated disposable database."
        )
    require_tool("pg_restore")
    target = required_environment("RESTORE_DATABASE_URL")

    directory = Path("results/day25") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    summary: dict[str, Any] = {
        "version": DRILL_VERSION,
        "started_at": now(),
        "status": "FAILED",
        "database_restored": False,
        "evidence_drill_passed": False,
        "reasons": [],
    }

    try:
        dump_path = Path(args.backup)
        metadata = json.loads(metadata_path(dump_path).read_text(encoding="utf-8"))
        verify_backup(dump_path, metadata)
        target_name = inspect_target(target, metadata["source_database"])

        summary.update(
            {
                "source_database": metadata["source_database"],
                "destination_database": target_name,
                "dump_sha256": metadata["dump_sha256"],
            }
        )

        code = run_logged(
            [
                "pg_restore",
                "--dbname",
                target_name,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "--single-transaction",
                str(dump_path),
            ],
            restore_environment(target),
            directory,
            "restore",
        )
        if code != 0:
            raise ValueError("Database restoration failed. Inspect restore.stderr.log.")
        summary["database_restored"] = True

        child_environment = os.environ.copy()
        child_environment["DATABASE_URL"] = target
        existing = child_environment.get("PGOPTIONS", "")
        child_environment["PGOPTIONS"] = (
            existing + " -c default_transaction_read_only=on"
        ).strip()

        code = run_logged(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.recovery_drill",
                "drill",
                "--package",
                str(Path(args.package).resolve()),
            ],
            child_environment,
            directory,
            "evidence-drill",
        )
        if code != 0:
            raise ValueError(
                "Database restored, but Day 24 failed. "
                "Inspect evidence-drill logs and its report."
            )

        summary["evidence_drill_passed"] = True
        summary["status"] = "PASSED"

    except Exception as exc:  # noqa: BLE001
        summary["reasons"].append(
            str(exc)
            if isinstance(exc, ValueError)
            else f"Operation failed ({type(exc).__name__}); inspect private logs."
        )

    summary["finished_at"] = now()
    report_path = directory / "report.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Database recovery drill: {summary['status']}")
    print(f"Report: {report_path}")
    for reason in summary["reasons"]:
        print(f"- {reason}")
    return 0 if summary["status"] == "PASSED" else 3


class DatabaseRecoveryTests(unittest.TestCase):
    def test_distinct_empty_target(self) -> None:
        require_safe_target("ledger", "ledger_drill", False, False)

    def test_same_database_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_safe_target("ledger", "ledger", False, False)

    def test_superuser_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_safe_target("ledger", "ledger_drill", True, False)

    def test_occupied_target_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_safe_target("ledger", "ledger_drill", False, True)

    def test_modified_dump_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.dump"
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                verify_backup(
                    path,
                    {
                        "version": VERSION,
                        "source_database": "ledger",
                        "dump_sha256": "0" * 64,
                    },
                )

    def test_unsupported_connection_option_rejected(self) -> None:
        with self.assertRaises(ValueError):
            restore_environment("postgresql://user@host/db?unknown=1")

    def test_supported_connection_options_accepted(self) -> None:
        env = restore_environment(
            "postgresql://user:pass@host:5432/db?sslmode=require&connect_timeout=30"
        )
        self.assertIn("PGHOST", env)
        self.assertIn("PGPORT", env)
        self.assertIn("PGUSER", env)
        self.assertIn("PGPASSWORD", env)
        self.assertIn("PGSSLMODE", env)
        self.assertIn("PGCONNECT_TIMEOUT", env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    exporter = commands.add_parser("backup")
    exporter.add_argument("--output", required=True)

    restorer = commands.add_parser("drill")
    restorer.add_argument("--backup", required=True)
    restorer.add_argument("--package", required=True)
    restorer.add_argument("--confirm-isolated-target", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "test":
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(DatabaseRecoveryTests)
        )
        return 0 if result.wasSuccessful() else 1

    try:
        return backup(args) if args.command == "backup" else drill(args)
    except Exception as exc:  # noqa: BLE001
        print(
            str(exc)
            if isinstance(exc, ValueError)
            else f"Operation failed ({type(exc).__name__}). Inspect private logs.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
