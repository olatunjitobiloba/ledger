"""Release-readiness policy over stored evaluation evidence.

    python -m ledger.pipeline.release_policy test
    python -m ledger.pipeline.release_policy check --baseline <UUID> --candidate <UUID>

No provider calls are made. Security findings request review; they do not
automatically establish that an input or output was malicious.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import unittest
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.costs import PRICE_VERSION
from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.injection_scan import RULESET_SHA256, SCANNER_VERSION
from ledger.pipeline.regression import compare, load_run

POLICY_VERSION = "ledger-release-policy-v1"


def assess(
    relative: dict[str, Any],
    candidate_results: Sequence[Mapping[Any, Any]],
    security: Sequence[Mapping[Any, Any]],
    quality_floor: float,
) -> dict[str, Any]:
    if not math.isfinite(quality_floor) or not 0 <= quality_floor <= 1:
        raise ValueError("Quality floor must be finite and between 0 and 1.")

    report: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "quality_floor": quality_floor,
        "decision": "INCONCLUSIVE",
        "reasons": [],
        "quality_failures": [],
        "security_reviews": [],
        "coverage_failures": [],
        "relative_gate": relative,
    }

    if relative["decision"] == "INCONCLUSIVE":
        report["reasons"] = relative["reasons"]
        return report

    if not candidate_results or not security:
        report["coverage_failures"].append(
            "Candidate evaluations or security coverage are empty."
        )

    for result in candidate_results:
        score = result.get("eval_score")
        if (
            result.get("status") != "completed"
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            report["coverage_failures"].append(
                f"Invalid evaluation: {result['case_id']}/{result['trial']}"
            )
        elif not result["passed"] or score < quality_floor:
            report["quality_failures"].append(
                {
                    "case_id": result["case_id"],
                    "trial": result["trial"],
                    "score": score,
                    "judge_passed": result["passed"],
                }
            )

    for item in security:
        label = f"{item['case_id']}/{item['field_name']}"
        risk = item.get("risk_index")
        if (
            item.get("scan_status") != "scanned"
            or not isinstance(risk, (int, float))
            or isinstance(risk, bool)
            or not math.isfinite(risk)
            or not 0 <= risk <= 1
        ):
            report["coverage_failures"].append(
                f"Missing, unscanned, or invalid security finding: {label}"
            )
        elif risk > 0:
            report["security_reviews"].append(
                {
                    "case_id": item["case_id"],
                    "field_name": item["field_name"],
                    "risk_index": risk,
                    "matched_rules": item.get("matched_rules", []),
                }
            )

    if report["coverage_failures"]:
        report["decision"] = "INCONCLUSIVE"
        report["reasons"] = ["Required evidence is incomplete or invalid."]
    elif relative["decision"] == "BLOCK" or report["quality_failures"]:
        report["decision"] = "BLOCK"
        report["reasons"] = [
            "Relative regression or absolute quality requirements failed."
        ]
    elif report["security_reviews"]:
        report["decision"] = "REVIEW"
        report["reasons"] = [
            "Security patterns matched; human context review is required."
        ]
    else:
        report["decision"] = "READY"
        report["reasons"] = [
            (
                "Configured checks passed on the tested cases; "
                "this does not establish production safety."
            )
        ]

    return report


def load_security(connection: Any, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = uuid.UUID(candidate["run_id"])
    cases = candidate["dataset"]["cases"]
    answers = dict(
        connection.execute(
            """
            SELECT case_id, answer
            FROM ledger_application_outputs
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchall()
    )

    items: list[dict[str, Any]] = []
    for case in cases:
        for field_name, text in (
            ("question", case["question"]),
            ("answer", answers.get(case["case_id"])),
        ):
            item: dict[str, Any] = {
                "case_id": case["case_id"],
                "field_name": field_name,
                "scan_status": "missing",
                "risk_index": None,
            }

            if text is None or (
                field_name == "answer" and text != case["candidate_answer"]
            ):
                items.append(item)
                continue

            text_hash = hashlib.sha256(text.encode()).hexdigest()
            row = connection.execute(
                """
                SELECT scan_status, risk_index, findings
                FROM ledger_injection_findings
                WHERE run_id = %s AND case_id = %s AND field_name = %s
                  AND scanner_version = %s AND ruleset_sha256 = %s
                  AND text_sha256 = %s
                """,
                (
                    run_id,
                    case["case_id"],
                    field_name,
                    SCANNER_VERSION,
                    RULESET_SHA256,
                    text_hash,
                ),
            ).fetchone()

            if row:
                status, risk, finding = row
                item.update(
                    {
                        "scan_status": status,
                        "risk_index": risk,
                        "matched_rules": finding.get("matched_rules", []),
                    }
                )
            items.append(item)

    return items


def load_cost_coverage(connection: Any, run_id: uuid.UUID) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            count(*) AS evaluations,
            count(c.run_id) AS attributed,
            count(*) FILTER (WHERE c.cost_status = 'estimated') AS estimated,
            count(*) FILTER (
                WHERE c.run_id IS NULL OR c.cost_status = 'unknown'
            ) AS unknown_or_missing,
            sum(c.estimated_cost_usd) AS known_subtotal
        FROM ledger_eval_results r
        LEFT JOIN ledger_eval_costs c
          ON c.run_id = r.run_id
         AND c.case_id = r.case_id
         AND c.trial = r.trial
         AND c.pricing_version = %s
        WHERE r.run_id = %s
        """,
        (PRICE_VERSION, run_id),
    ).fetchone()

    return {
        "usage_role": "judge",
        "pricing_version": PRICE_VERSION,
        "evaluations": row[0],
        "attributed_records": row[1],
        "estimated_records": row[2],
        "unknown_or_missing_records": row[3],
        "known_estimated_subtotal_usd": (str(row[4]) if row[4] is not None else None),
        "affects_release_decision": False,
    }


class ReleaseTests(unittest.TestCase):
    def fixtures(
        self,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        return (
            {"decision": "PASS", "reasons": []},
            [
                {
                    "case_id": "one",
                    "trial": 1,
                    "status": "completed",
                    "eval_score": 0.9,
                    "passed": True,
                }
            ],
            [
                {
                    "case_id": "one",
                    "field_name": "answer",
                    "scan_status": "scanned",
                    "risk_index": 0,
                }
            ],
        )

    def test_ready(self) -> None:
        self.assertEqual(assess(*self.fixtures(), 0.75)["decision"], "READY")

    def test_absolute_quality_blocks_equal_but_poor_runs(self) -> None:
        relative, results, security = self.fixtures()
        results[0].update(eval_score=0.5, passed=False)
        self.assertEqual(assess(relative, results, security, 0.75)["decision"], "BLOCK")

    def test_relative_regression_blocks(self) -> None:
        relative, results, security = self.fixtures()
        relative["decision"] = "BLOCK"
        self.assertEqual(assess(relative, results, security, 0.75)["decision"], "BLOCK")

    def test_security_match_requests_review(self) -> None:
        relative, results, security = self.fixtures()
        security[0]["risk_index"] = 0.6
        self.assertEqual(
            assess(relative, results, security, 0.75)["decision"], "REVIEW"
        )

    def test_missing_scan_is_inconclusive(self) -> None:
        relative, results, security = self.fixtures()
        security[0].update(scan_status="missing", risk_index=None)
        self.assertEqual(
            assess(relative, results, security, 0.75)["decision"], "INCONCLUSIVE"
        )

    def test_incompatible_runs_are_inconclusive(self) -> None:
        relative, results, security = self.fixtures()
        relative.update(decision="INCONCLUSIVE", reasons=["Rubric changed."])
        self.assertEqual(
            assess(relative, results, security, 0.75)["decision"], "INCONCLUSIVE"
        )

    def test_judge_correctness_failure_still_blocks(self) -> None:
        relative, results, security = self.fixtures()
        results[0]["passed"] = False
        self.assertEqual(assess(relative, results, security, 0.75)["decision"], "BLOCK")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")
    check = commands.add_parser("check")
    check.add_argument("--baseline", required=True, type=uuid.UUID)
    check.add_argument("--candidate", required=True, type=uuid.UUID)
    check.add_argument("--allowed-drop", type=float, default=0.05)
    check.add_argument("--quality-floor", type=float, default=0.75)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)

    try:
        with connect() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            baseline = load_run(connection, args.baseline)
            candidate = load_run(connection, args.candidate)
            relative = compare(baseline, candidate, args.allowed_drop)

            quality_rows = connection.execute(
                """
                    SELECT case_id, trial, status, eval_score, passed
                    FROM ledger_eval_results
                    WHERE run_id = %s
                    """,
                (args.candidate,),
            ).fetchall()
            results = [
                dict(
                    zip(
                        ("case_id", "trial", "status", "eval_score", "passed"),
                        row,
                    )
                )
                for row in quality_rows
            ]
            security = load_security(connection, candidate)
            costs = load_cost_coverage(connection, args.candidate)
            report = assess(relative, results, security, args.quality_floor)
            report["judge_cost_coverage"] = costs
    except Exception as exc:
        report = {
            "policy_version": POLICY_VERSION,
            "decision": "INCONCLUSIVE",
            "reasons": [
                (
                    f"Check could not complete ({type(exc).__name__}). "
                    "Verify database setup, run IDs, and arguments."
                )
            ],
        }

    report.update(
        {
            "baseline_run_id": str(args.baseline),
            "candidate_run_id": str(args.candidate),
            "checked_at": datetime.now(UTC).isoformat(),
            "scanner_version": SCANNER_VERSION,
            "ruleset_sha256": RULESET_SHA256,
        }
    )
    output = Path("results/day9")
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    print(f"Decision: {report['decision']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Report: {path}")
    raise SystemExit(
        {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}[report["decision"]]
    )


if __name__ == "__main__":
    main()
