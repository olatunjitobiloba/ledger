"""Stable, compatibility-first command-line interface for Ledger."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import sys
import uuid
from pathlib import Path
from typing import Callable

REQUIRED_FILES = (
    Path("runtime-config.json"),
    Path("evaluation-budget.json"),
    Path("datasets/golden-v1.json"),
    Path("migrations/001_ledger_schema.sql"),
)
REQUIRED_MODULES = ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "groq")
SECRET_VARIABLES = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "DATABASE_URL",
    "LEDGER_DATABASE_URL",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the parser without starting services or opening connections."""
    parser = argparse.ArgumentParser(prog="ledger", description="Ledger operations")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser(
        "doctor",
        help="Run read-only local readiness checks.",
        description="Run read-only checks without connecting to a database by default.",
    )
    doctor.add_argument(
        "--check-database",
        action="store_true",
        help="Also test a database connection without writing schema or data.",
    )
    commands.add_parser("serve", help="Start the existing Ledger API with Uvicorn.")
    commands.add_parser("worker", help="Start the existing Ledger worker.")

    evidence = commands.add_parser(
        "evidence", help="Export or restore verified evidence bundles."
    )
    evidence_commands = evidence.add_subparsers(
        dest="evidence_command", required=True
    )
    export = evidence_commands.add_parser("export", help="Export a reservation bundle.")
    export.add_argument("--reservation", required=True, type=uuid.UUID)
    export.add_argument("--output", required=True, type=Path)
    restore = evidence_commands.add_parser("restore", help="Restore a bundle.")
    restore.add_argument("--bundle", required=True, type=Path)

    return parser


def _report_check(passed: bool, label: str) -> bool:
    print(f"[{'PASS' if passed else 'FAIL'}] {label}")
    return passed


def _local_secret_names(path: Path = Path(".env")) -> set[str]:
    """Return configured secret variable names without loading or displaying values."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return set()

    present: set[str] = set()
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            if name.strip() in SECRET_VARIABLES and value.strip().strip("'\""):
                present.add(name.strip())
        elif line.startswith("sk-or-v1-"):
            present.add("OPENROUTER_API_KEY")
        elif line.startswith("gsk_"):
            present.add("GROQ_API_KEY")
        elif line.startswith("sk-"):
            present.add("OPENAI_API_KEY")
    return present


def _database_connect():
    """Import the evaluation run store only for an explicit database check without leaking loader output."""
    with contextlib.redirect_stderr(io.StringIO()):
        from ledger.pipeline.evaluation_runs import connect

    return connect()


def _serve() -> int | None:
    """Start Uvicorn only after the user explicitly selects the serve command."""
    import uvicorn

    return uvicorn.run("ledger_api.main:app")


def worker_main() -> int | None:
    """Load and run the existing worker only after explicit dispatch."""
    from ledger.observability.worker import main as delegate

    return delegate()


def export_reservation(args: argparse.Namespace) -> int:
    """Load the Day 22 export facade only when the command is executed."""
    from ledger.evaluation.evidence import export_reservation as delegate

    return delegate(args)


def restore_bundle(args: argparse.Namespace) -> int:
    """Load the Day 22 restore facade only when the command is executed."""
    from ledger.evaluation.evidence import restore_bundle as delegate

    return delegate(args)


def run_doctor(*, check_database: bool) -> int:
    """Run diagnostic checks without changing application data or schema."""
    successful = True
    locally_configured_secrets = _local_secret_names()

    successful &= _report_check(
        sys.version_info >= (3, 11),
        f"Python {sys.version_info.major}.{sys.version_info.minor} is supported (requires 3.11+)",
    )

    for required_file in REQUIRED_FILES:
        successful &= _report_check(required_file.is_file(), f"required file: {required_file}")

    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            successful &= _report_check(False, f"required module: {module_name}")
        else:
            _report_check(True, f"required module: {module_name}")

    for variable in SECRET_VARIABLES:
        status = "present" if os.getenv(variable) or variable in locally_configured_secrets else "missing"
        print(f"[INFO] secret {variable}: {status}")

    if check_database:
        try:
            with _database_connect():
                pass
        except (Exception, SystemExit) as exc:
            successful &= _report_check(
                False, f"database connection: failed ({type(exc).__name__})"
            )
        else:
            _report_check(True, "database connection: reachable (read-only check)")
    else:
        print("[SKIP] database connection: use --check-database to test it")

    return 0 if successful else 1


def _delegate(delegate: Callable[[argparse.Namespace], int | None], args: argparse.Namespace) -> int:
    """Preserve explicit delegate return codes while normalizing None to success."""
    result = delegate(args)
    return 0 if result is None else result


def main(argv: list[str] | None = None) -> int:
    """Parse *argv* and dispatch to Ledger's existing implementations."""
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        return run_doctor(check_database=args.check_database)
    if args.command == "serve":
        result = _serve()
        return 0 if result is None else result
    if args.command == "worker":
        result = worker_main()
        return 0 if result is None else result
    if args.evidence_command == "export":
        return _delegate(export_reservation, args)
    if args.evidence_command == "restore":
        return _delegate(restore_bundle, args)

    raise RuntimeError("Unknown Ledger command.")
