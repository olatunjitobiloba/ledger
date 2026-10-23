"""Reserve estimated spend and enforce single-use execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.execution_context import (
    PLAN_ENV,
    RESERVATION_ENV,
    require_candidate_context,
    validate_context,
)
from ledger.pipeline.spend_plan import (
    build_payload,
    canonical_hash,
    money,
    validate_plan,
)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS ledger_spend_budgets (
        budget_id TEXT PRIMARY KEY,
        limit_usd NUMERIC NOT NULL CHECK (limit_usd >= 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger_spend_reservations (
        reservation_id UUID PRIMARY KEY,
        budget_id TEXT NOT NULL REFERENCES ledger_spend_budgets(budget_id),
        plan_sha256 TEXT NOT NULL UNIQUE,
        plan JSONB NOT NULL,
        reserved_usd NUMERIC NOT NULL CHECK (reserved_usd >= 0),
        state TEXT NOT NULL CHECK (
            state IN ('RESERVED', 'RUNNING', 'FINISHED', 'UNKNOWN')
        ),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        exit_code INTEGER,
        candidate_run_id UUID,
        rehearsal_report TEXT,
        rehearsal_report_sha256 TEXT
    )
    """,
]


def execution_args(plan: dict[str, Any]) -> argparse.Namespace:
    payload = plan["payload"]
    execution = payload["execution"]
    repeats = execution["repeats"]
    if type(repeats) is not int or repeats not in range(1, 6):
        raise ValueError("Unsupported repeat count.")
    return argparse.Namespace(
        image=payload["image_reference"],
        baseline=uuid.UUID(payload["baseline_run_id"]),
        app_version=execution["app_version"],
        reviewed_by=execution["reviewed_by"],
        repeats=repeats,
        allowed_drop=execution["allowed_drop"],
        quality_floor=execution["quality_floor"],
    )


def checked_plan(plan: dict[str, Any]) -> Decimal:
    current = build_payload(execution_args(plan))
    validate_plan(plan, current, datetime.now(UTC))
    return money(current["cost_plan"]["estimated_total_usd"])


def admission(limit: Decimal, already_reserved: Decimal, proposed: Decimal) -> Decimal:
    if any(
        not value.is_finite() or value < 0
        for value in (limit, already_reserved, proposed)
    ):
        raise ValueError("Invalid reservation amounts.")
    if already_reserved + proposed > limit:
        raise ValueError("Shared estimated-reservation budget exceeded.")
    return limit - already_reserved - proposed


def initialize(args: argparse.Namespace) -> int:
    limit = money(args.limit_usd)
    with connect() as connection, connection.transaction():
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute(
            """
                INSERT INTO ledger_spend_budgets (budget_id, limit_usd)
                VALUES (%s, %s)
                ON CONFLICT (budget_id) DO NOTHING
                """,
            (args.budget_id, limit),
        )
        saved = connection.execute(
            """
                SELECT limit_usd FROM ledger_spend_budgets
                WHERE budget_id = %s
                """,
            (args.budget_id,),
        ).fetchone()[0]
        if saved != limit:
            raise ValueError(
                "Budget already exists with a different limit. "
                "This command does not modify existing budgets."
            )
    print(f"Budget initialized: {args.budget_id}")
    return 0


def reserve(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    amount = checked_plan(plan)
    digest = canonical_hash(plan)
    reservation_id = uuid.uuid4()

    with connect() as connection, connection.transaction():
        budget = connection.execute(
            """
                SELECT limit_usd FROM ledger_spend_budgets
                WHERE budget_id = %s FOR UPDATE
                """,
            (args.budget_id,),
        ).fetchone()
        if budget is None:
            raise ValueError("Initialize this budget first.")

        duplicate = connection.execute(
            """
                SELECT reservation_id FROM ledger_spend_reservations
                WHERE plan_sha256 = %s
                """,
            (digest,),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(
                f"Plan already reserved: {duplicate[0]}. "
                "Use that reservation; do not recreate its approval."
            )

        used = connection.execute(
            """
                SELECT COALESCE(SUM(reserved_usd), 0)
                FROM ledger_spend_reservations WHERE budget_id = %s
                """,
            (args.budget_id,),
        ).fetchone()[0]
        remaining = admission(budget[0], used, amount)

        connection.execute(
            """
                INSERT INTO ledger_spend_reservations (
                    reservation_id, budget_id, plan_sha256,
                    plan, reserved_usd, state
                ) VALUES (%s, %s, %s, %s, %s, 'RESERVED')
                """,
            (reservation_id, args.budget_id, digest, Jsonb(plan), amount),
        )

    print(f"Reservation: {reservation_id}")
    print(f"Estimated USD reserved: {amount}")
    print(f"Estimated reservation capacity remaining USD: {remaining}")
    return 0


def claim(connection: Any, reservation_id: uuid.UUID) -> None:
    row = connection.execute(
        """
        UPDATE ledger_spend_reservations
        SET state = 'RUNNING', started_at = now()
        WHERE reservation_id = %s AND state = 'RESERVED'
        RETURNING reservation_id
        """,
        (reservation_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Reservation is already claimed or is not executable.")


def find_rehearsal_report(stdout: str) -> Path:
    paths = [
        line.removeprefix("Report: ").strip()
        for line in stdout.splitlines()
        if line.startswith("Report: ")
        and line.removeprefix("Report: ")
        .strip()
        .replace("\\", "/")
        .startswith("results/day14/")
    ]
    if len(paths) != 1:
        raise ValueError("Could not identify one orchestration report.")

    root = Path.cwd().resolve()
    resolved = Path(paths[0]).resolve()
    if (
        not resolved.is_relative_to(root)
        or resolved.name != "report.json"
        or not resolved.is_file()
        or resolved.parent.parent.name != "day14"
    ):
        raise ValueError("Unexpected rehearsal report location.")
    return resolved


def associate(
    report: dict[str, Any], plan: dict[str, Any], code: int
) -> uuid.UUID | None:
    payload = plan["payload"]
    expected = {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}
    if expected.get(report.get("decision")) != code:
        raise ValueError("Rehearsal decision and process exit disagree.")
    if report.get("baseline_run_id") != payload["baseline_run_id"]:
        raise ValueError("Rehearsal baseline differs from reservation.")
    if report.get("source_commit") != payload["source_commit"]:
        raise ValueError("Rehearsal source differs from reservation.")
    if (
        report.get("execution_container", {}).get("image_reference")
        != payload["image_reference"]
    ):
        raise ValueError("Rehearsal image differs from reservation.")

    candidate = report.get("candidate_run_id")
    return uuid.UUID(candidate) if candidate is not None else None


def run(args: argparse.Namespace) -> int:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT plan, plan_sha256 FROM ledger_spend_reservations
            WHERE reservation_id = %s
            """,
            (args.reservation,),
        ).fetchone()
    if row is None:
        raise ValueError("Reservation does not exist.")
    plan, digest = row
    if canonical_hash(plan) != digest:
        raise ValueError("Stored reservation plan and hash disagree.")

    checked_plan(plan)
    child_environment = os.environ.copy()
    child_environment[RESERVATION_ENV] = str(args.reservation)
    child_environment[PLAN_ENV] = digest

    directory = Path("results/day18") / str(args.reservation)
    directory.mkdir(parents=True, exist_ok=True)
    plan_path = directory / "reserved-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    with connect() as connection, connection.transaction():
        claim(connection, args.reservation)

    code = 3
    state = "UNKNOWN"
    candidate = None
    rehearsal_path = None
    rehearsal_hash = None

    try:
        stdout_path = directory / "execution.stdout.log"
        stderr_path = directory / "execution.stderr.log"
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ledger.pipeline.spend_plan",
                    "run",
                    "--plan",
                    str(plan_path),
                    "--approve-spend",
                ],
                stdout=stdout,
                stderr=stderr,
                text=True,
                env=child_environment,
            )

        code = completed.returncode
        if code not in (0, 1, 2, 3):
            code = 3
            raise ValueError("Execution terminated unexpectedly.")

        output = stdout_path.read_text(encoding="utf-8")
        path = find_rehearsal_report(output)
        raw = path.read_bytes()
        report = json.loads(raw)
        validate_context(
            report.get("execution_context"),
            args.reservation,
            digest,
        )
        candidate = associate(report, plan, code)
        if candidate is not None:
            with connect() as connection:
                require_candidate_context(
                    connection,
                    candidate,
                    args.reservation,
                    digest,
                )
        rehearsal_path = str(path)
        rehearsal_hash = hashlib.sha256(raw).hexdigest()
        state = "FINISHED"

    except Exception as exc:
        code = 3
        print(
            f"Execution association incomplete ({type(exc).__name__}). "
            "Reservation remains consumed; inspect local logs.",
            file=sys.stderr,
        )

    with connect() as connection, connection.transaction():
        updated = connection.execute(
            """
                UPDATE ledger_spend_reservations
                SET state = %s, finished_at = now(), exit_code = %s,
                    candidate_run_id = %s, rehearsal_report = %s,
                    rehearsal_report_sha256 = %s
                WHERE reservation_id = %s AND state = 'RUNNING'
                RETURNING reservation_id
                """,
            (
                state,
                code,
                candidate,
                rehearsal_path,
                rehearsal_hash,
                args.reservation,
            ),
        ).fetchone()
        if updated is None:
            raise ValueError("Reservation finalization failed.")

    print(f"Reservation state: {state}")
    print(f"Candidate: {candidate}")
    print(f"Execution logs: {directory}")
    return code


def status(args: argparse.Namespace) -> int:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT reservation_id, state, reserved_usd, exit_code,
                   candidate_run_id, rehearsal_report
            FROM ledger_spend_reservations
            WHERE budget_id = %s ORDER BY created_at
            """,
            (args.budget_id,),
        ).fetchall()
    for reservation, state, amount, code, candidate, path in rows:
        print(
            json.dumps(
                {
                    "reservation_id": str(reservation),
                    "state": state,
                    "reserved_usd": str(amount),
                    "exit_code": code,
                    "candidate_run_id": str(candidate) if candidate else None,
                    "rehearsal_report": path,
                }
            )
        )
    return 0


class ReservationTests(unittest.TestCase):
    def test_exact_limit(self) -> None:
        self.assertEqual(
            admission(Decimal(1), Decimal("0.8"), Decimal("0.2")),
            Decimal(0),
        )

    def test_over_limit(self) -> None:
        with self.assertRaises(ValueError):
            admission(Decimal(1), Decimal("0.9"), Decimal("0.2"))

    def test_negative_amount(self) -> None:
        with self.assertRaises(ValueError):
            admission(Decimal(1), Decimal(0), Decimal(-1))

    def test_nonfinite_amount(self) -> None:
        with self.assertRaises(ValueError):
            admission(Decimal(1), Decimal(0), Decimal("NaN"))

    def test_plan_identity_ignores_json_key_order(self) -> None:
        self.assertEqual(
            canonical_hash({"a": 1, "b": 2}),
            canonical_hash({"b": 2, "a": 1}),
        )

    def test_claim_rejects_second_execution(self) -> None:
        from unittest.mock import Mock

        connection = Mock()
        connection.execute.return_value.fetchone.return_value = None
        with self.assertRaises(ValueError):
            claim(connection, uuid.uuid4())


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    initializer = commands.add_parser("init")
    initializer.add_argument("--budget-id", required=True)
    initializer.add_argument("--limit-usd", required=True)

    reservation = commands.add_parser("reserve")
    reservation.add_argument("--budget-id", required=True)
    reservation.add_argument("--plan", required=True)

    runner = commands.add_parser("run")
    runner.add_argument("--reservation", required=True, type=uuid.UUID)
    runner.add_argument("--approve-spend", action="store_true")

    viewer = commands.add_parser("status")
    viewer.add_argument("--budget-id", required=True)

    args = parser.parse_args()
    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReservationTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.command == "run" and not args.approve_spend:
        parser.error("Execution requires explicit --approve-spend.")

    try:
        return {
            "init": initialize,
            "reserve": reserve,
            "run": run,
            "status": status,
        }[args.command](args)
    except ValueError as exc:
        print(f"Reservation gate rejected: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(
            f"Reservation operation failed ({type(exc).__name__}). "
            "Inspect database state before retrying execution.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
