"""Reconcile a finished reservation without changing database state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.execution_context import validate_context
from ledger.pipeline.reservation_recovery import validate_candidate, validate_report
from ledger.pipeline.spend_plan import canonical_hash

VERSION = "ledger-reservation-reconciliation-v1"
CHILD_EXIT_CODES = {
    "RECONCILED_RECORDS": 0,
    "PARTIAL": 2,
    "INCONCLUSIVE": 3,
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require_finished_candidate(state: object, candidate: object) -> uuid.UUID:
    if state != "FINISHED" or candidate is None:
        raise ValueError("Reservation must be finished with a candidate.")
    try:
        return uuid.UUID(str(candidate))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Reservation candidate is invalid.") from None


def read_saved_report(path: object, expected_hash: object) -> dict[str, Any]:
    if not isinstance(path, str) or not path:
        raise ValueError("Reservation has no rehearsal report path.")

    root = Path("results/day14").resolve()
    resolved = Path(path).resolve()
    if (
        not resolved.is_relative_to(root)
        or resolved.name != "report.json"
        or not resolved.is_file()
    ):
        raise ValueError(
            "Saved rehearsal report is unavailable or outside results/day14."
        )

    raw = resolved.read_bytes()
    if sha256(raw) != expected_hash:
        raise ValueError("Saved rehearsal report hash differs from the ledger.")
    report = json.loads(raw)
    if not isinstance(report, dict):
        raise ValueError("Saved rehearsal report is not an object.")
    return report


def validate_association(
    reservation_id: object,
    plan: dict[str, Any],
    plan_hash: object,
    candidate_id: uuid.UUID,
    exit_code: object,
    report: dict[str, Any],
) -> None:
    if canonical_hash(plan) != plan_hash:
        raise ValueError("Stored plan and reservation hash disagree.")
    validate_context(report.get("execution_context"), reservation_id, plan_hash)
    candidate, inferred_code = validate_report(report, plan)
    if candidate != candidate_id:
        raise ValueError("Rehearsal candidate does not match reservation.")
    if inferred_code != exit_code:
        raise ValueError("Rehearsal exit code differs from reservation.")


def child_report_path(output: str) -> Path:
    matches = [
        line.removeprefix("Report: ")
        for line in output.splitlines()
        if line.startswith("Report: ")
    ]
    if len(matches) != 1 or not matches[0]:
        raise ValueError("Child reconciliation did not provide exactly one report.")

    supplied = Path(matches[0])
    if supplied.is_absolute() or supplied.suffix != ".json":
        raise ValueError("Child report path is invalid.")
    root = Path("results/day17").resolve()
    resolved = supplied.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Child report is unavailable or outside results/day17.")
    return resolved


def validate_child(
    report: dict[str, Any],
    returncode: int,
    candidate_id: uuid.UUID,
    payload_hash: str,
) -> str:
    status = report.get("status")
    if status not in CHILD_EXIT_CODES:
        raise ValueError("Child reconciliation status is invalid.")
    if CHILD_EXIT_CODES[status] != returncode:
        raise ValueError("Child reconciliation exit code is inconsistent.")
    if report.get("candidate_run_id") != str(candidate_id):
        raise ValueError("Child reconciliation candidate is inconsistent.")
    if status != "INCONCLUSIVE" and report.get("plan_payload_sha256") != payload_hash:
        raise ValueError("Child reconciliation plan hash is inconsistent.")
    return status


def _json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def reconcile(args: argparse.Namespace) -> int:
    directory = Path("results/day21") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    summary: dict[str, Any] = {
        "version": VERSION,
        "reservation_id": str(args.reservation),
        "started_at": datetime.now(UTC).isoformat(),
        "status": "INCONCLUSIVE",
        "association_verified": False,
        "reasons": [],
        "model_calls_made": False,
        "database_modified": False,
        "budget_capacity_released": False,
        "provider_invoice_reconciled": False,
    }
    try:
        with connect() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            row = connection.execute(
                """
                    SELECT budget_id, state, plan, plan_sha256,
                           reserved_usd, candidate_run_id, exit_code,
                           rehearsal_report, rehearsal_report_sha256
                    FROM ledger_spend_reservations
                    WHERE reservation_id = %s
                    """,
                (args.reservation,),
            ).fetchone()
            if row is None:
                raise ValueError("Reservation does not exist.")
            (
                budget_id,
                state,
                plan,
                plan_hash,
                reserved_usd,
                candidate,
                exit_code,
                rehearsal_path,
                rehearsal_hash,
            ) = row
            candidate_id = require_finished_candidate(state, candidate)
            report = read_saved_report(rehearsal_path, rehearsal_hash)
            validate_association(
                args.reservation,
                plan,
                plan_hash,
                candidate_id,
                exit_code,
                report,
            )
            candidate_row = connection.execute(
                """
                    SELECT config, reviewed_by
                    FROM ledger_eval_runs WHERE run_id = %s
                    """,
                (candidate_id,),
            ).fetchone()
            if candidate_row is None:
                raise ValueError("Candidate run does not exist.")
            validate_context(
                candidate_row[0].get("execution_context")
                if isinstance(candidate_row[0], dict)
                else None,
                args.reservation,
                plan_hash,
            )
            validate_candidate(candidate_row[0], candidate_row[1], plan)

        summary.update(
            {
                "budget_id": str(budget_id),
                "reservation_state": state,
                "reserved_estimate_usd": _json_value(reserved_usd),
                "candidate_run_id": str(candidate_id),
                "plan_sha256": plan_hash,
                "rehearsal_report": rehearsal_path,
                "rehearsal_report_sha256": rehearsal_hash,
                "association_verified": True,
                "association_snapshot_scope": (
                    "Read-only database snapshot before cost reconciliation"
                ),
            }
        )
        plan_path = directory / "reserved-plan.json"
        plan_path.write_text(
            json.dumps(plan, indent=2, allow_nan=False), encoding="utf-8"
        )
        stdout_path = directory / "day17.stdout.log"
        stderr_path = directory / "day17.stderr.log"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.cost_reconciliation",
                "reconcile",
                "--plan",
                str(plan_path),
                "--candidate",
                str(candidate_id),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        child_path = child_report_path(result.stdout + result.stderr)
        child_raw = child_path.read_bytes()
        child_report = json.loads(child_raw)
        status = validate_child(
            child_report, result.returncode, candidate_id, plan["payload_sha256"]
        )
        summary.update(
            {
                "status": status,
                "reasons": child_report.get("reasons", []),
                "child_report": str(child_path),
                "child_report_sha256": sha256(child_raw),
                "cost_reconciliation": child_report.get(
                    "cost_reconciliation",
                    child_report,
                ),
            }
        )
    except ValueError as exc:
        summary["reasons"] = [str(exc)]
    except Exception as exc:
        summary["reasons"] = [
            (f"Reconciliation could not complete ({type(exc).__name__}); "
            "verify stored evidence, policy, database access, and local logs.")
        ]

    summary["finished_at"] = datetime.now(UTC).isoformat()
    report_path = directory / "report.json"
    report_path.write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"Association verified: {summary['association_verified']}")
    print(f"Status: {summary['status']}")
    for reason in summary["reasons"]:
        print(f"- {reason}")
    print(f"Report: {report_path}")
    return CHILD_EXIT_CODES[summary["status"]]


class ReservationReconciliationTests(unittest.TestCase):
    def test_finished_candidate(self):
        candidate = uuid.uuid4()
        self.assertEqual(
            require_finished_candidate("FINISHED", candidate), candidate
        )

    def test_running_rejected(self):
        with self.assertRaises(ValueError):
            require_finished_candidate("RUNNING", uuid.uuid4())

    def test_missing_candidate_rejected(self):
        with self.assertRaises(ValueError):
            require_finished_candidate("FINISHED", None)

    def test_matching_child_report(self):
        candidate = uuid.uuid4()
        report = {
            "status": "RECONCILED_RECORDS",
            "candidate_run_id": str(candidate),
            "plan_payload_sha256": "a" * 64,
        }
        self.assertEqual(
            validate_child(report, 0, candidate, "a" * 64),
            "RECONCILED_RECORDS",
        )

    def test_wrong_candidate_rejected(self):
        report = {
            "status": "PARTIAL",
            "candidate_run_id": str(uuid.uuid4()),
            "plan_payload_sha256": "a" * 64,
        }
        with self.assertRaises(ValueError):
            validate_child(report, 2, uuid.uuid4(), "a" * 64)

    def test_wrong_plan_rejected(self):
        candidate = uuid.uuid4()
        report = {
            "status": "PARTIAL",
            "candidate_run_id": str(candidate),
            "plan_payload_sha256": "b" * 64,
        }
        with self.assertRaises(ValueError):
            validate_child(report, 2, candidate, "a" * 64)

    def test_inconsistent_exit_rejected(self):
        candidate = uuid.uuid4()
        report = {
            "status": "RECONCILED_RECORDS",
            "candidate_run_id": str(candidate),
            "plan_payload_sha256": "a" * 64,
        }
        with self.assertRaises(ValueError):
            validate_child(report, 3, candidate, "a" * 64)

    def test_inconclusive_can_lack_plan_hash(self):
        candidate = uuid.uuid4()
        report = {
            "status": "INCONCLUSIVE",
            "candidate_run_id": str(candidate),
        }
        self.assertEqual(
            validate_child(report, 3, candidate, "a" * 64),
            "INCONCLUSIVE",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")
    command = commands.add_parser("reconcile")
    command.add_argument("--reservation", required=True, type=uuid.UUID)
    args = parser.parse_args(argv)
    if args.command == "test":
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(
                ReservationReconciliationTests
            )
        )
        return 0 if result.wasSuccessful() else 1
    return reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main())
