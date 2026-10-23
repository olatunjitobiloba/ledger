"""Recover interrupted reservations from existing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unittest
import uuid
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.spend_plan import VERSION as PLAN_VERSION, canonical_hash
from ledger.pipeline.spend_reservations import associate
from ledger.pipeline.execution_context import require_candidate_context, validate_context


RECOVERABLE = {"RUNNING", "UNKNOWN"}
EXIT_CODES = {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_spend_recovery_events (
    event_id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL
        REFERENCES ledger_spend_reservations(reservation_id),
    recovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    database_actor TEXT NOT NULL DEFAULT current_user,
    operator_label TEXT NOT NULL,
    reason TEXT NOT NULL,
    previous_state TEXT NOT NULL,
    evidence JSONB NOT NULL
)
"""


def require_recoverable(state: object) -> None:
    if state not in RECOVERABLE:
        raise ValueError("Only RUNNING or UNKNOWN reservations can be recovered.")


def validate_report(
    report: dict[str, Any], plan: dict[str, Any]
) -> tuple[uuid.UUID | None, int]:
    if plan.get("version") != PLAN_VERSION:
        raise ValueError("Unsupported stored plan.")
    if plan.get("payload_sha256") != canonical_hash(plan.get("payload")):
        raise ValueError("Stored plan payload hash is invalid.")
    if report.get("version") != "ledger-rehearsal-v1":
        raise ValueError("Unsupported rehearsal report.")

    decision = report.get("decision")
    if decision not in EXIT_CODES:
        raise ValueError("Unknown rehearsal decision.")
    if report.get("deployment_performed") is not False:
        raise ValueError("Unexpected deployment flag.")

    try:
        uuid.UUID(report["rehearsal_id"])
    except (KeyError, ValueError, TypeError):
        raise ValueError("Invalid rehearsal ID.") from None

    execution = plan["payload"]["execution"]
    for field in ("repeats", "allowed_drop", "quality_floor"):
        if report.get(field) != execution[field]:
            raise ValueError(f"Rehearsal settings differ: {field}.")

    code = EXIT_CODES[decision]
    candidate = associate(report, plan, code)
    if candidate is None and decision != "INCONCLUSIVE":
        raise ValueError("A conclusive decision requires a candidate.")
    return candidate, code


def validate_candidate(
    config: dict[str, Any], reviewer: object, plan: dict[str, Any]
) -> None:
    payload = plan["payload"]
    execution = payload["execution"]
    checks = [
        (
            config.get("application_provenance", {}).get("commit_sha"),
            payload["source_commit"],
            "source commit",
        ),
        (
            config.get("container_binding", {}).get("image_reference"),
            payload["image_reference"],
            "runtime image",
        ),
        (
            config.get("application_version"),
            execution["app_version"],
            "application version",
        ),
        (
            config.get("source_dataset_sha256"),
            payload["source_dataset_sha256"],
            "source dataset",
        ),
        (
            config.get("application_model"),
            payload["cost_plan"]["application"]["requested_model"],
            "application model",
        ),
        (reviewer, execution["reviewed_by"], "reviewer"),
    ]
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f"Candidate differs from reservation: {label}.")


def load_report(path: str) -> tuple[str, str, dict[str, Any]]:
    supplied = Path(path)
    resolved = supplied.resolve()
    root = Path("results/day14").resolve()
    if (
        not resolved.is_relative_to(root)
        or resolved.name != "report.json"
        or not resolved.is_file()
    ):
        raise ValueError("Choose an existing results/day14/.../report.json file.")

    raw = resolved.read_bytes()
    report = json.loads(raw)
    if (
        not isinstance(report, dict)
        or resolved.parent.name != report.get("rehearsal_id")
    ):
        raise ValueError("Report path does not match its rehearsal identity.")
    return (
        str(resolved.relative_to(Path.cwd().resolve())),
        hashlib.sha256(raw).hexdigest(),
        report,
    )


def initialize() -> int:
    with connect() as connection:
        with connection.transaction():
            connection.execute(AUDIT_SCHEMA)
    print("Recovery audit table initialized.")
    return 0


def recover(args: argparse.Namespace) -> int:
    operator = args.operator.strip()
    reason = args.reason.strip()
    if not operator or not reason:
        raise ValueError("Operator and recovery reason cannot be empty.")

    report_path, report_hash, report = load_report(args.report)
    event_id = uuid.uuid4()

    with connect() as connection:
        with connection.transaction():
            row = connection.execute(
                """
                SELECT state, plan, plan_sha256
                FROM ledger_spend_reservations
                WHERE reservation_id = %s
                FOR UPDATE
                """,
                (args.reservation,),
            ).fetchone()
            if row is None:
                raise ValueError("Reservation does not exist.")

            previous_state, plan, plan_hash = row
            require_recoverable(previous_state)
            if canonical_hash(plan) != plan_hash:
                raise ValueError("Stored plan and reservation hash disagree.")

            validate_context(
                report.get("execution_context"),
                args.reservation,
                plan_hash,
            )
            candidate, code = validate_report(report, plan)
            if candidate is not None:
                candidate_row = connection.execute(
                    """
                    SELECT config, reviewed_by
                    FROM ledger_eval_runs WHERE run_id = %s
                    """,
                    (candidate,),
                ).fetchone()
                if candidate_row is None:
                    raise ValueError(
                        "Candidate run does not exist. Leave the reservation unresolved."
                    )
                validate_candidate(candidate_row[0], candidate_row[1], plan)
                require_candidate_context(
                    connection,
                    candidate,
                    args.reservation,
                    plan_hash,
                )

            evidence = {
                "rehearsal_id": report["rehearsal_id"],
                "report_path": report_path,
                "report_sha256": report_hash,
                "execution_context": report["execution_context"],
                "candidate_run_id": str(candidate) if candidate else None,
                "decision": report["decision"],
                "exit_code_basis": "inferred from saved report decision",
                "process_exit_independently_verified": False,
                "model_calls_made_by_recovery": False,
                "budget_capacity_released": False,
            }

            connection.execute(
                """
                INSERT INTO ledger_spend_recovery_events (
                    event_id, reservation_id, operator_label,
                    reason, previous_state, evidence
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    event_id,
                    args.reservation,
                    operator,
                    reason,
                    previous_state,
                    Jsonb(evidence),
                ),
            )
            connection.execute(
                """
                UPDATE ledger_spend_reservations
                SET state = 'FINISHED', finished_at = now(),
                    exit_code = %s, candidate_run_id = %s,
                    rehearsal_report = %s,
                    rehearsal_report_sha256 = %s
                WHERE reservation_id = %s
                """,
                (
                    code,
                    candidate,
                    report_path,
                    report_hash,
                    args.reservation,
                ),
            )

    print(f"Recovered reservation: {args.reservation}")
    print(f"Audit event: {event_id}")
    print(f"Candidate: {candidate}")
    print(f"Saved decision: {report['decision']}")
    print("Reserved capacity unchanged. No execution was started.")
    return 0


class RecoveryTests(unittest.TestCase):
    def fixtures(self) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "baseline_run_id": str(uuid.uuid4()),
            "source_commit": "a" * 40,
            "image_reference": "example/runtime@sha256:" + "b" * 64,
            "execution": {
                "repeats": 1,
                "allowed_drop": 0.05,
                "quality_floor": 0.75,
            },
        }
        plan = {
            "version": PLAN_VERSION,
            "payload": payload,
            "payload_sha256": canonical_hash(payload),
        }
        report = {
            "version": "ledger-rehearsal-v1",
            "rehearsal_id": str(uuid.uuid4()),
            "baseline_run_id": payload["baseline_run_id"],
            "source_commit": payload["source_commit"],
            "execution_container": {
                "image_reference": payload["image_reference"],
            },
            "candidate_run_id": str(uuid.uuid4()),
            "decision": "READY",
            "deployment_performed": False,
            **payload["execution"],
        }
        return report, plan

    def test_running_is_recoverable(self) -> None:
        require_recoverable("RUNNING")

    def test_finished_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_recoverable("FINISHED")

    def test_valid_report(self) -> None:
        candidate, code = validate_report(*self.fixtures())
        self.assertIsInstance(candidate, uuid.UUID)
        self.assertEqual(code, 0)

    def test_changed_execution_rejected(self) -> None:
        report, plan = self.fixtures()
        report["repeats"] = 2
        with self.assertRaises(ValueError):
            validate_report(report, plan)

    def test_ready_without_candidate_rejected(self) -> None:
        report, plan = self.fixtures()
        report["candidate_run_id"] = None
        with self.assertRaises(ValueError):
            validate_report(report, plan)

    def test_inconclusive_without_candidate(self) -> None:
        report, plan = self.fixtures()
        report["candidate_run_id"] = None
        report["decision"] = "INCONCLUSIVE"
        self.assertEqual(validate_report(report, plan), (None, 3))

    def test_changed_plan_hash_rejected(self) -> None:
        report, plan = self.fixtures()
        plan["payload"]["execution"]["repeats"] = 2
        with self.assertRaises(ValueError):
            validate_report(report, plan)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")
    commands.add_parser("init")

    recovery = commands.add_parser("recover")
    recovery.add_argument("--reservation", required=True, type=uuid.UUID)
    recovery.add_argument("--report", required=True)
    recovery.add_argument("--operator", required=True)
    recovery.add_argument("--reason", required=True)
    recovery.add_argument("--confirm-process-stopped", action="store_true")
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.command == "recover" and not args.confirm_process_stopped:
        parser.error(
            "Verify the original runner and its child processes have stopped, "
            "then provide --confirm-process-stopped."
        )

    try:
        return initialize() if args.command == "init" else recover(args)
    except ValueError as exc:
        print(f"Recovery rejected: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(
            f"Recovery could not complete ({type(exc).__name__}). "
            "Inspect reservation state and database setup.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
