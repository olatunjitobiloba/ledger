"""Shared execution-context validation for reservation-bound evidence."""

from __future__ import annotations

import argparse
import re
import sys
import unittest
import uuid
from collections.abc import Mapping
from typing import Any


VERSION = "ledger-execution-context-v1"
RESERVATION_ENV = "LEDGER_SPEND_RESERVATION_ID"
PLAN_ENV = "LEDGER_SPEND_PLAN_SHA256"


def _normalize_reservation(reservation_id: object) -> str:
    try:
        return str(uuid.UUID(str(reservation_id)))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Invalid reservation ID.") from None


def _normalize_plan(plan_sha256: object) -> str:
    if not isinstance(plan_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", plan_sha256
    ) is None:
        raise ValueError("Invalid plan hash.")
    return plan_sha256


def make_context(reservation_id: object, plan_sha256: object) -> dict[str, str]:
    return {
        "version": VERSION,
        "reservation_id": _normalize_reservation(reservation_id),
        "plan_sha256": _normalize_plan(plan_sha256),
    }


def context_from_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    if environment is None:
        import os

        environment = os.environ

    reservation = environment.get(RESERVATION_ENV)
    plan = environment.get(PLAN_ENV)
    if reservation is None and plan is None:
        return None
    if reservation is None or plan is None or not reservation or not plan:
        raise ValueError("Execution context environment is incomplete.")
    return make_context(reservation, plan)


def validate_context(
    stored: object, reservation_id: object, plan_sha256: object
) -> dict[str, str]:
    expected = make_context(reservation_id, plan_sha256)
    if stored != expected:
        raise ValueError("Stored execution context does not match reservation.")
    return expected


def require_candidate_context(
    connection: Any,
    candidate_id: uuid.UUID,
    reservation_id: object,
    plan_sha256: object,
) -> None:
    row = connection.execute(
        "SELECT config FROM ledger_eval_runs WHERE run_id = %s",
        (candidate_id,),
    ).fetchone()
    if row is None or not isinstance(row[0], dict):
        raise ValueError("Candidate execution context is missing.")
    config = row[0]
    validate_context(config.get("execution_context"), reservation_id, plan_sha256)


class ExecutionContextTests(unittest.TestCase):
    def reservation(self) -> str:
        return "11111111-1111-4111-8111-111111111111"

    def digest(self) -> str:
        return "a" * 64

    def test_unbound_execution(self):
        self.assertIsNone(context_from_environment({}))

    def test_complete_environment(self):
        context = context_from_environment(
            {
                RESERVATION_ENV: self.reservation(),
                PLAN_ENV: self.digest(),
            }
        )
        self.assertEqual(context["reservation_id"], self.reservation())

    def test_partial_environment_rejected(self):
        with self.assertRaises(ValueError):
            context_from_environment({RESERVATION_ENV: self.reservation()})

    def test_empty_environment_value_rejected(self):
        with self.assertRaises(ValueError):
            context_from_environment(
                {
                    RESERVATION_ENV: "",
                    PLAN_ENV: self.digest(),
                }
            )

    def test_invalid_hash_rejected(self):
        with self.assertRaises(ValueError):
            make_context(self.reservation(), "not-a-hash")

    def test_matching_context(self):
        context = make_context(self.reservation(), self.digest())
        self.assertEqual(
            validate_context(context, self.reservation(), self.digest()),
            context,
        )

    def test_wrong_reservation_rejected(self):
        context = make_context(self.reservation(), self.digest())
        with self.assertRaises(ValueError):
            validate_context(context, uuid.uuid4(), self.digest())

    def test_missing_candidate_binding_rejected(self):
        from unittest.mock import Mock

        connection = Mock()
        connection.execute.return_value.fetchone.return_value = (
            {"execution_context": None},
        )
        with self.assertRaises(ValueError):
            require_candidate_context(
                connection, uuid.uuid4(), self.reservation(), self.digest()
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("test")
    args = parser.parse_args(argv)

    if args.command == "test":
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ExecutionContextTests)
        )
        return 0 if result.wasSuccessful() else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
