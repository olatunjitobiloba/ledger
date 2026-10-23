"""Reconcile a spend plan with saved evaluation usage."""

from __future__ import annotations

import argparse
import json
import unittest
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ledger.pipeline.costs import PRICE_VERSION
from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.spend_plan import (
    POLICY_FILE,
    calculate,
    canonical_hash,
    hash_bytes,
    money,
)
from ledger.pipeline.spend_plan import (
    VERSION as PLAN_VERSION,
)

REPORT_VERSION = "ledger-cost-reconciliation-v1"
MILLION = Decimal(1000000)


def application_cost(usage: object, rates: dict[str, Any]) -> Decimal | None:
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if (
        type(input_tokens) is not int
        or type(output_tokens) is not int
        or input_tokens < 0
        or output_tokens < 0
    ):
        return None

    return (
        Decimal(input_tokens) * money(rates["input_usd_per_million"])
        + Decimal(output_tokens) * money(rates["output_usd_per_million"])
    ) / MILLION


def load_plan(path: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if plan.get("version") != PLAN_VERSION:
        raise ValueError("Unsupported spend plan.")

    payload = plan.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Plan payload is invalid.")
    if plan.get("payload_sha256") != canonical_hash(payload):
        raise ValueError("Plan content and hash disagree.")

    policy_bytes = POLICY_FILE.read_bytes()
    expected_policy_hash = payload.get("spend_policy_sha256")
    if not isinstance(expected_policy_hash, str):
        raise ValueError("Spend plan has no policy hash.")
    if hash_bytes(policy_bytes) != expected_policy_hash:
        raise ValueError(
            "Current spending policy differs from the plan. "
            "Restore the exact policy in a separate checkout before reconciling."
        )

    policy = json.loads(policy_bytes)
    expected = calculate(
        policy,
        payload["case_count"],
        payload["execution"]["repeats"],
    )
    if expected != payload["cost_plan"]:
        raise ValueError("Plan estimate disagrees with its spending policy.")

    return plan, payload, policy


def validate_candidate(
    config: object,
    reviewer: object,
    dataset: object,
    payload: dict[str, Any],
    outputs: list[tuple[Any, ...]],
    results: list[tuple[Any, ...]],
) -> set[str]:
    if not isinstance(config, dict) or not isinstance(dataset, dict):
        raise ValueError("Candidate configuration or dataset is invalid.")
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
            "container image",
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
        (reviewer, execution["reviewed_by"], "reviewer"),
        (
            config.get("application_model"),
            payload["cost_plan"]["application"]["requested_model"],
            "application model",
        ),
    ]
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f"Candidate differs from plan: {label}.")

    cases = dataset.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Candidate dataset is invalid.")
    case_ids = {case["case_id"] for case in cases}
    output_ids = {row[0] for row in outputs}
    if (
        len(cases) != payload["case_count"]
        or len(case_ids) != len(cases)
        or len(outputs) != len(case_ids)
        or output_ids != case_ids
    ):
        raise ValueError("Candidate application coverage differs from plan.")

    wanted = {
        (case_id, trial)
        for case_id in case_ids
        for trial in range(1, execution["repeats"] + 1)
    }
    observed = {(row[0], row[1]) for row in results}
    if observed != wanted or len(results) != len(wanted):
        raise ValueError("Candidate judge coverage differs from plan.")

    return case_ids


def summarize_application(
    outputs: list[tuple[Any, ...]],
    rates: dict[str, Any],
    planned: str,
) -> dict[str, Any]:
    known = Decimal(0)
    unknown: list[str] = []
    records = []

    for case_id, usage in outputs:
        cost = application_cost(usage, rates)
        if cost is None:
            unknown.append(case_id)
        else:
            known += cost
        records.append(
            {
                "case_id": case_id,
                "usage_complete": cost is not None,
                "estimated_usd": str(cost) if cost is not None else None,
            }
        )

    return {
        "pricing_basis": "spend-plan policy rates",
        "planned_usd": planned,
        "recorded_usage_estimated_subtotal_usd": str(known),
        "unknown_usage_cases": unknown,
        "recorded_usage_coverage_complete": not unknown,
        "recorded_usage_variance_usd": (
            str(known - money(planned)) if not unknown else None
        ),
        "records": records,
    }


def reconcile(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "version": REPORT_VERSION,
        "candidate_run_id": str(args.candidate),
        "plan_file": str(Path(args.plan)),
        "status": "INCONCLUSIVE",
        "reasons": [],
        "provider_invoice_reconciled": False,
        "release_policy_changed": False,
    }

    try:
        plan, payload, policy = load_plan(args.plan)
        report["plan_payload_sha256"] = plan["payload_sha256"]

        with connect() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            row = connection.execute(
                """
                    SELECT config, reviewed_by, dataset_snapshot
                    FROM ledger_eval_runs WHERE run_id = %s
                    """,
                (args.candidate,),
            ).fetchone()
            if row is None:
                raise ValueError("Candidate run does not exist.")

            outputs = connection.execute(
                """
                    SELECT case_id, usage
                    FROM ledger_application_outputs
                    WHERE run_id = %s ORDER BY case_id
                    """,
                (args.candidate,),
            ).fetchall()

            results = connection.execute(
                """
                    SELECT case_id, trial, status
                    FROM ledger_eval_results WHERE run_id = %s
                    ORDER BY case_id, trial
                    """,
                (args.candidate,),
            ).fetchall()

            validate_candidate(row[0], row[1], row[2], payload, outputs, results)

            costs = connection.execute(
                """
                    SELECT r.case_id, r.trial, c.cost_status,
                           c.estimated_cost_usd
                    FROM ledger_eval_results r
                    LEFT JOIN ledger_eval_costs c
                      ON c.run_id = r.run_id
                     AND c.case_id = r.case_id
                     AND c.trial = r.trial
                     AND c.pricing_version = %s
                    WHERE r.run_id = %s
                    ORDER BY r.case_id, r.trial
                    """,
                (PRICE_VERSION, args.candidate),
            ).fetchall()

        application = summarize_application(
            outputs,
            policy["application"],
            payload["cost_plan"]["application"]["estimated_usd"],
        )

        judge_subtotal = Decimal(0)
        unknown_judge = []
        for case_id, trial, status, value in costs:
            if status != "estimated" or value is None:
                unknown_judge.append({"case_id": case_id, "trial": trial})
                continue
            judge_subtotal += money(str(value))

        failed_judgments = [
            {"case_id": case_id, "trial": trial, "status": status}
            for case_id, trial, status in results
            if status != "completed"
        ]

        report.update(
            {
                "application": application,
                "judge": {
                    "pricing_basis": "cost attribution",
                    "pricing_version": PRICE_VERSION,
                    "planned_usd": payload["cost_plan"]["judge"]["estimated_usd"],
                    "attributed_estimated_subtotal_usd": str(judge_subtotal),
                    "unknown_or_missing_records": unknown_judge,
                    "failed_evaluations": failed_judgments,
                    "variance_calculated": False,
                    "reason": (
                        "Cost rates have not been verified against the "
                        "spend-plan judge pricing policy."
                    ),
                },
                "combined_known_estimated_subtotal_usd": str(
                    Decimal(application["recorded_usage_estimated_subtotal_usd"])
                    + judge_subtotal
                ),
                "combined_subtotal_uses_mixed_pricing_bases": True,
                "planned_total_usd": payload["cost_plan"]["estimated_total_usd"],
                "total_spend_variance_usd": None,
                "unrecorded_attempt_costs_possible": True,
            }
        )

        incomplete = (
            application["unknown_usage_cases"] or unknown_judge or failed_judgments
        )
        report["status"] = "PARTIAL" if incomplete else "RECONCILED_RECORDS"
        report["reasons"] = [
            (
                "Reconciled saved records only; retry/failed-attempt charges "
                "and provider billing remain outside this report."
            )
        ]

    except ValueError as exc:
        report["reasons"] = [str(exc)]
    except Exception as exc:
        report["reasons"] = [
            (
                f"Reconciliation could not complete ({type(exc).__name__}). "
                "Verify the plan, exact policy, run evidence, and database."
            )
        ]

    report["checked_at"] = datetime.now(UTC).isoformat()
    directory = Path("results/day17")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Status: {report['status']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Report: {path}")
    return {
        "RECONCILED_RECORDS": 0,
        "PARTIAL": 2,
        "INCONCLUSIVE": 3,
    }[report["status"]]


class ReconciliationTests(unittest.TestCase):
    def rates(self) -> dict[str, str]:
        return {
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
        }

    def test_recorded_cost(self) -> None:
        cost = application_cost(
            {"prompt_tokens": 100, "completion_tokens": 50},
            self.rates(),
        )
        self.assertEqual(cost, Decimal("0.0002"))

    def test_missing_usage_is_unknown(self) -> None:
        self.assertIsNone(application_cost({}, self.rates()))

    def test_zero_tokens_are_valid(self) -> None:
        self.assertEqual(
            application_cost(
                {"prompt_tokens": 0, "completion_tokens": 0},
                self.rates(),
            ),
            Decimal(0),
        )

    def test_boolean_tokens_rejected(self) -> None:
        self.assertIsNone(
            application_cost(
                {"prompt_tokens": True, "completion_tokens": 10},
                self.rates(),
            )
        )

    def test_partial_coverage_has_no_variance(self) -> None:
        result = summarize_application([("one", {})], self.rates(), "0.01")
        self.assertIsNone(result["recorded_usage_variance_usd"])
        self.assertEqual(result["unknown_usage_cases"], ["one"])

    def test_positive_variance(self) -> None:
        result = summarize_application(
            [("one", {"prompt_tokens": 100, "completion_tokens": 50})],
            self.rates(),
            "0.0001",
        )
        self.assertEqual(
            Decimal(result["recorded_usage_variance_usd"]),
            Decimal("0.0001"),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    command = commands.add_parser("reconcile")
    command.add_argument("--plan", required=True)
    command.add_argument("--candidate", required=True, type=uuid.UUID)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReconciliationTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    return reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main())
