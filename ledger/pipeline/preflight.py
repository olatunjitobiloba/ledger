"""Check evaluation readiness before spending model calls.

    python -m ledger.pipeline.preflight test
    python -m ledger.pipeline.preflight check --image registry/image@sha256:<digest> ...
    python -m ledger.pipeline.preflight run --image registry/image@sha256:<digest> ...

The preflight runs inside the pinned evaluation image and writes only local
logs and a summary report.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.container_binding import container_command, inspect_image
from ledger.pipeline.provenance import clean_commit

VERSION = "ledger-preflight-v1"
TABLE_PRIVILEGES = {
    "ledger_eval_runs": ("SELECT", "INSERT"),
    "ledger_eval_results": ("SELECT", "INSERT"),
    "ledger_application_outputs": ("SELECT", "INSERT"),
    "ledger_injection_findings": ("SELECT", "INSERT"),
    "ledger_eval_costs": ("SELECT", "INSERT", "UPDATE"),
}


def validate_baseline(
    dataset: object,
    source_cases: list[dict[str, Any]],
    rows: list[tuple[Any, ...]],
    repeats: int,
) -> dict[str, int]:
    if not isinstance(dataset, dict):
        raise ValueError("Baseline dataset snapshot is invalid.")

    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Baseline has no dataset cases.")

    expected = {case["case_id"]: case for case in source_cases}
    actual = {case["case_id"]: case for case in cases}

    if (
        not expected
        or len(actual) != len(cases)
        or set(actual) != set(expected)
    ):
        raise ValueError(
            "Baseline cases differ from the current starter application set."
        )

    for case_id, case in actual.items():
        for field in ("question", "reference", "scenario_id"):
            if case.get(field) != expected[case_id].get(field):
                raise ValueError(f"Baseline case contract changed: {case_id}/{field}")

    wanted = {
        (case_id, trial)
        for case_id in expected
        for trial in range(1, repeats + 1)
    }
    observed = set()

    for case_id, trial, status, score, passed in rows:
        key = (case_id, trial)
        if key in observed:
            raise ValueError("Baseline contains duplicate evaluation keys.")
        observed.add(key)
        if (
            status != "completed"
            or type(score) not in (int, float)
            or not math.isfinite(score)
            or not 0 <= score <= 1
            or type(passed) is not bool
        ):
            raise ValueError(
                f"Baseline evaluation is incomplete or invalid: {case_id}/{trial}"
            )

    if observed != wanted:
        raise ValueError(
            "Baseline evaluation coverage does not match the requested repeats."
        )

    return {
        "case_count": len(expected),
        "evaluation_count": len(rows),
        "repeats": repeats,
    }


def inside_preflight(args: argparse.Namespace) -> None:
    from ledger.pipeline.evaluation_runs import connect
    from ledger.pipeline.golden_set import load_dataset
    from ledger.pipeline.runtime_binding import build_binding

    runtime = build_binding()
    source, _ = load_dataset()
    selected = [
        case for case in source["cases"] if case["case_id"].endswith("-good")
    ]

    results = Path("results")
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryFile(dir=results) as temporary:
        temporary.write(b"ledger-preflight")
        temporary.flush()

    with connect() as connection, connection.transaction():
        connection.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )

        for table, privileges in TABLE_PRIVILEGES.items():
            exists = connection.execute(
                "SELECT to_regclass(%s)", (table,)
            ).fetchone()[0]
            if exists is None:
                raise ValueError(
                    f"Missing table: {table}. Initialize the evaluation "
                    "database before running the rehearsal."
                )

            for privilege in privileges:
                permitted = connection.execute(
                    "SELECT has_table_privilege(current_user, %s, %s)",
                    (table, privilege),
                ).fetchone()[0]
                if not permitted:
                    raise ValueError(f"Missing {privilege} privilege on {table}.")

        row = connection.execute(
            """
                SELECT dataset_snapshot
                FROM ledger_eval_runs WHERE run_id = %s
                """,
            (args.baseline,),
        ).fetchone()
        if row is None:
            raise ValueError("Baseline run does not exist.")

        rows = connection.execute(
            """
                SELECT case_id, trial, status, eval_score, passed
                FROM ledger_eval_results
                WHERE run_id = %s
                ORDER BY case_id, trial
                """,
            (args.baseline,),
        ).fetchall()

        coverage = validate_baseline(row[0], selected, rows, args.repeats)

    print(
        json.dumps(
            {
                "status": "PASS",
                "runtime_fingerprint": runtime["fingerprint"],
                "baseline_coverage": coverage,
                "database_reachable_from_container": True,
                "table_privileges_checked": True,
                "artifact_storage_writable": True,
            }
        )
    )


def execute(args: argparse.Namespace) -> int:
    directory = Path("results/day15") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    report: dict[str, Any] = {
        "version": VERSION,
        "started_at": datetime.now(UTC).isoformat(),
        "baseline_run_id": str(args.baseline),
        "status": "FAILED",
        "rehearsal_started": False,
        "reasons": [],
    }
    exit_code = 3

    try:
        for name in ("GROQ_API_KEY", "DATABASE_URL"):
            if not os.getenv(name):
                raise ValueError(f"Set {name} before starting.")

        commit = clean_commit()
        binding = inspect_image(args.image)
        report["source_commit"] = commit
        report["execution_container"] = binding

        completed = subprocess.run(
            container_command(
                binding,
                ["-m", "ledger.pipeline.preflight", "inside", "--baseline", str(args.baseline),
                 "--repeats", str(args.repeats)],
            ),
            text=True,
            capture_output=True,
        )
        (directory / "preflight.stdout.log").write_text(
            completed.stdout, encoding="utf-8"
        )
        (directory / "preflight.stderr.log").write_text(
            completed.stderr, encoding="utf-8"
        )

        if completed.returncode:
            raise ValueError("Container preflight failed. Inspect its local logs.")

        evidence = json.loads(completed.stdout)
        if evidence.get("status") != "PASS":
            raise ValueError("Preflight did not return valid passing evidence.")
        if clean_commit() != commit:
            raise ValueError("Source changed during preflight.")

        report["status"] = "PASS"
        report["evidence"] = evidence
        exit_code = 0

        if args.command == "run":
            report["rehearsal_started"] = True
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ledger.pipeline.orchestration",
                    "run",
                    "--image",
                    args.image,
                    "--baseline",
                    str(args.baseline),
                    "--app-version",
                    args.app_version,
                    "--reviewed-by",
                    args.reviewed_by,
                    "--repeats",
                    str(args.repeats),
                    "--allowed-drop",
                    str(args.allowed_drop),
                    "--quality-floor",
                    str(args.quality_floor),
                ]
            )
            exit_code = completed.returncode
            report["rehearsal_exit_code"] = exit_code
            if exit_code not in (0, 1, 2, 3):
                raise ValueError("Rehearsal terminated unexpectedly.")

    except ValueError as exc:
        report["status"] = "FAILED"
        report["reasons"] = [str(exc)]
        exit_code = 3
    except Exception as exc:
        report["status"] = "FAILED"
        report["reasons"] = [
            (f"Preflight/rehearsal could not complete ({type(exc).__name__}). "
            "Check Docker, registry access, dependencies, and database setup.")
        ]
        exit_code = 3

    report["finished_at"] = datetime.now(UTC).isoformat()
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Preflight status: {report['status']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Preflight report: {path}")
    return exit_code


class PreflightTests(unittest.TestCase):
    def fixtures(self) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[Any, ...]]]:
        case = {
            "case_id": "one-good",
            "question": "Question",
            "reference": "Reference",
            "scenario_id": "one",
        }
        return (
            {"cases": [dict(case)]},
            [case],
            [("one-good", 1, "completed", 0.9, True)],
        )

    def test_complete_baseline(self) -> None:
        result = validate_baseline(*self.fixtures(), 1)
        self.assertEqual(result["evaluation_count"], 1)

    def test_missing_trial(self) -> None:
        with self.assertRaises(ValueError):
            validate_baseline(*self.fixtures(), 2)

    def test_changed_reference(self) -> None:
        dataset, source, rows = self.fixtures()
        dataset["cases"][0]["reference"] = "Changed"
        with self.assertRaises(ValueError):
            validate_baseline(dataset, source, rows, 1)

    def test_failed_evaluation(self) -> None:
        dataset, source, _ = self.fixtures()
        with self.assertRaises(ValueError):
            validate_baseline(
                dataset,
                source,
                [("one-good", 1, "error", None, None)],
                1,
            )

    def test_nonfinite_score(self) -> None:
        dataset, source, _ = self.fixtures()
        with self.assertRaises(ValueError):
            validate_baseline(
                dataset,
                source,
                [("one-good", 1, "completed", float("nan"), True)],
                1,
            )

    def test_poor_baseline_is_not_a_readiness_failure(self) -> None:
        dataset, source, _ = self.fixtures()
        validate_baseline(
            dataset,
            source,
            [("one-good", 1, "completed", 0.4, False)],
            1,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    inside = commands.add_parser("inside")
    inside.add_argument("--baseline", required=True, type=uuid.UUID)
    inside.add_argument("--repeats", type=int, choices=range(1, 6), default=1)

    for name in ("check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--image", required=True)
        command.add_argument("--baseline", required=True, type=uuid.UUID)
        command.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
        if name == "run":
            command.add_argument("--app-version", required=True)
            command.add_argument("--reviewed-by", required=True)
            command.add_argument("--allowed-drop", type=float, default=0.05)
            command.add_argument("--quality-floor", type=float, default=0.75)

    args = parser.parse_args()
    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PreflightTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.command == "inside":
        try:
            inside_preflight(args)
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"Container preflight failed ({type(exc).__name__}).", file=sys.stderr)
            return 3

    if args.command == "run":
        for name in ("allowed_drop", "quality_floor"):
            value = getattr(args, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                parser.error(
                    f"--{name.replace('_', '-')} must be finite and between 0 and 1."
                )

    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
