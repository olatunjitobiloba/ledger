"""Relative regression gate over stored evaluation runs.

    python -m ledger.pipeline.regression test
    python -m ledger.pipeline.regression compare --baseline <UUID> --candidate <UUID> --allowed-drop 0.05

Exit codes: 0 PASS, 1 BLOCK, 2 INCONCLUSIVE.

This compares stored results only. It does not call Groq and it cannot prove the
application improved; it measures relative movement under a compatible evaluator.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from ledger.pipeline.evaluation_runs import connect

GATE_VERSION = "ledger-regression-v1"
COMPATIBILITY_FIELDS = (
    "rubric_version",
    "rubric_sha256",
    "evaluator_source_sha256",
    "requested_model",
    "temperature",
    "pass_threshold",
    "repeats",
)


def case_contract(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = dataset.get("cases", [])
    if not cases:
        raise ValueError("Dataset has no cases.")

    contract: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case["case_id"]
        if case_id in contract:
            raise ValueError(f"Duplicate dataset case: {case_id}")
        contract[case_id] = {
            "question": case["question"],
            "reference": case["reference"],
        }
    return contract


def validate_results(
    run: dict[str, Any], contract: dict[str, dict[str, Any]]
) -> tuple[dict[str, list[float]], set[str]]:
    repeats = run["config"]["repeats"]
    if type(repeats) is not int or repeats < 1:
        raise ValueError("Invalid repeat count.")

    expected = {
        (case_id, trial) for case_id in contract for trial in range(1, repeats + 1)
    }
    seen: set[tuple[str, int]] = set()
    grouped: dict[str, list[float]] = {case_id: [] for case_id in contract}
    models: set[str] = set()

    for result in run["results"]:
        key = (result["case_id"], result["trial"])
        if key not in expected or key in seen:
            raise ValueError(f"Unexpected or duplicate result: {key}")
        seen.add(key)

        if result["status"] != "completed":
            raise ValueError(f"Evaluation failed: {key}")

        score = result["eval_score"]
        if (
            type(score) not in (int, float)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError(f"Invalid score: {key}")

        model = result.get("returned_model")
        if not isinstance(model, str) or not model:
            raise ValueError(f"Missing returned model: {key}")

        models.add(model)
        grouped[key[0]].append(float(score))

    missing = expected - seen
    if missing:
        raise ValueError(f"Missing {len(missing)} evaluation result(s).")
    if len(models) != 1:
        raise ValueError("Run contains multiple returned judge models.")

    return grouped, models


def compare(
    baseline: dict[str, Any], candidate: dict[str, Any], allowed_drop: float = 0.05
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "gate_version": GATE_VERSION,
        "baseline_run_id": baseline["run_id"],
        "candidate_run_id": candidate["run_id"],
        "allowed_absolute_drop": allowed_drop,
        "aggregation": "mean score per case across trials",
        "decision": "INCONCLUSIVE",
        "reasons": [],
        "cases": [],
    }

    try:
        if not math.isfinite(allowed_drop) or not 0 <= allowed_drop <= 1:
            raise ValueError("Allowed drop must be finite and between 0 and 1.")
        if baseline["run_id"] == candidate["run_id"]:
            raise ValueError("Choose two different run IDs.")

        for field in COMPATIBILITY_FIELDS:
            if field not in baseline["config"] or field not in candidate["config"]:
                raise ValueError(f"Missing configuration field: {field}")
            if baseline["config"][field] != candidate["config"][field]:
                raise ValueError(f"Incompatible configuration: {field}")

        baseline_contract = case_contract(baseline["dataset"])
        candidate_contract = case_contract(candidate["dataset"])
        if baseline_contract != candidate_contract:
            raise ValueError(
                "Case IDs, questions, or references differ. "
                "Use a shared evaluation contract."
            )

        baseline_scores, baseline_models = validate_results(
            baseline, baseline_contract
        )
        candidate_scores, candidate_models = validate_results(
            candidate, candidate_contract
        )
        if baseline_models != candidate_models:
            raise ValueError("Returned judge models differ.")

        baseline_answers = {
            c["case_id"]: c["candidate_answer"] for c in baseline["dataset"]["cases"]
        }
        candidate_answers = {
            c["case_id"]: c["candidate_answer"] for c in candidate["dataset"]["cases"]
        }
        changed_answers = [
            case_id
            for case_id in baseline_contract
            if baseline_answers[case_id] != candidate_answers[case_id]
        ]
        report["changed_answer_case_ids"] = sorted(changed_answers)
        report["comparison_kind"] = (
            "changed_saved_answers" if changed_answers else "judge_repeatability"
        )

        for case_id in sorted(baseline_contract):
            old_scores = baseline_scores[case_id]
            new_scores = candidate_scores[case_id]
            old_mean = math.fsum(old_scores) / len(old_scores)
            new_mean = math.fsum(new_scores) / len(new_scores)
            drop = old_mean - new_mean

            report["cases"].append(
                {
                    "case_id": case_id,
                    "baseline_mean": round(old_mean, 6),
                    "candidate_mean": round(new_mean, 6),
                    "absolute_drop": round(drop, 6),
                    "baseline_score_range": round(
                        max(old_scores) - min(old_scores), 6
                    ),
                    "candidate_score_range": round(
                        max(new_scores) - min(new_scores), 6
                    ),
                    # Tiny tolerance avoids float artifacts at the boundary.
                    "regressed": drop > allowed_drop + 1e-12,
                }
            )

        regressions = [c["case_id"] for c in report["cases"] if c["regressed"]]
        report["decision"] = "BLOCK" if regressions else "PASS"
        report["reasons"] = (
            [f"Allowed drop exceeded: {case_id}" for case_id in regressions]
            if regressions
            else ["No case exceeded the allowed score drop."]
        )
    except (ValueError, KeyError, TypeError) as exc:
        report["reasons"] = [str(exc)]

    return report


def load_run(
    connection: psycopg.Connection[Any], run_id: uuid.UUID
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT config, dataset_snapshot
        FROM ledger_eval_runs WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Run not found: {run_id}")

    config, dataset = row
    rows = connection.execute(
        """
        SELECT case_id, trial, status, eval_score,
               result->>'returned_model'
        FROM ledger_eval_results
        WHERE run_id = %s
        ORDER BY case_id, trial
        """,
        (run_id,),
    ).fetchall()

    return {
        "run_id": str(run_id),
        "config": config,
        "dataset": dataset,
        "results": [
            {
                "case_id": case_id,
                "trial": trial,
                "status": status,
                "eval_score": score,
                "returned_model": model,
            }
            for case_id, trial, status, score, model in rows
        ],
    }


class GateTests(unittest.TestCase):
    def run_fixture(self, run_id: str, scores: dict[str, float]) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "config": {
                "rubric_version": "v1",
                "rubric_sha256": "rubric-hash",
                "evaluator_source_sha256": "code-hash",
                "requested_model": "judge-model",
                "temperature": 0,
                "pass_threshold": 0.75,
                "repeats": 1,
            },
            "dataset": {
                "cases": [
                    {
                        "case_id": case_id,
                        "question": f"Question {case_id}",
                        "reference": f"Reference {case_id}",
                        "candidate_answer": "Saved answer",
                    }
                    for case_id in scores
                ]
            },
            "results": [
                {
                    "case_id": case_id,
                    "trial": 1,
                    "status": "completed",
                    "eval_score": score,
                    "returned_model": "judge-model",
                }
                for case_id, score in scores.items()
            ],
        }

    def test_unchanged_passes(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = self.run_fixture("b", {"one": 0.9})
        self.assertEqual(compare(a, b)["decision"], "PASS")

    def test_exact_boundary_passes(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = self.run_fixture("b", {"one": 0.85})
        self.assertEqual(compare(a, b)["decision"], "PASS")

    def test_one_regression_blocks_despite_other_improvement(self) -> None:
        a = self.run_fixture("a", {"one": 0.9, "two": 0.5})
        b = self.run_fixture("b", {"one": 0.79, "two": 1.0})
        self.assertEqual(compare(a, b)["decision"], "BLOCK")

    def test_missing_result_is_inconclusive(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = self.run_fixture("b", {"one": 0.9})
        b["results"] = []
        self.assertEqual(compare(a, b)["decision"], "INCONCLUSIVE")

    def test_error_is_inconclusive(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = self.run_fixture("b", {"one": 0.9})
        b["results"][0]["status"] = "error"
        self.assertEqual(compare(a, b)["decision"], "INCONCLUSIVE")

    def test_changed_rubric_is_inconclusive(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = copy.deepcopy(a)
        b["run_id"] = "b"
        b["config"]["rubric_sha256"] = "different"
        self.assertEqual(compare(a, b)["decision"], "INCONCLUSIVE")

    def test_changed_answer_is_allowed(self) -> None:
        a = self.run_fixture("a", {"one": 0.9})
        b = self.run_fixture("b", {"one": 0.79})
        b["dataset"]["cases"][0]["candidate_answer"] = "Worse answer"
        report = compare(a, b)
        self.assertEqual(report["decision"], "BLOCK")
        self.assertEqual(report["comparison_kind"], "changed_saved_answers")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")
    runner = commands.add_parser("compare")
    runner.add_argument("--baseline", required=True, type=uuid.UUID)
    runner.add_argument("--candidate", required=True, type=uuid.UUID)
    runner.add_argument("--allowed-drop", type=float, default=0.05)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(GateTests)
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if outcome.wasSuccessful() else 1)

    try:
        with connect() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            baseline = load_run(connection, args.baseline)
            candidate = load_run(connection, args.candidate)
        report = compare(baseline, candidate, args.allowed_drop)
    except Exception as exc:  # noqa: BLE001 - the gate must always decide
        report = {
            "gate_version": GATE_VERSION,
            "baseline_run_id": str(args.baseline),
            "candidate_run_id": str(args.candidate),
            "decision": "INCONCLUSIVE",
            "reasons": [f"{type(exc).__name__}: {exc}"],
            "cases": [],
        }

    report["compared_at"] = datetime.now(UTC).isoformat()
    output = Path("results/day6")
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    print(f"Decision: {report['decision']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    for case in report["cases"]:
        print(
            f"{case['case_id']}: "
            f"{case['baseline_mean']} -> {case['candidate_mean']} "
            f"drop={case['absolute_drop']} regressed={case['regressed']}"
        )
    print(f"Report: {path}")
    raise SystemExit({"PASS": 0, "BLOCK": 1, "INCONCLUSIVE": 2}[report["decision"]])


if __name__ == "__main__":
    main()
