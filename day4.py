"""Day 4: persist golden-set evaluations in PostgreSQL.

    python day4.py init-db
    python day4.py run --reviewed-by "Tobi" --repeats 1
    python day4.py run --reviewed-by "Tobi" --repeats 1 --run-id <UUID>

Results are written one row at a time. Reusing a run id skips rows that are
already saved and refuses to continue if the dataset, evaluator, or config
changed. This is resumable, not an exactly-once API caller: a crash between the
judge call and the INSERT can repeat one paid call on resume.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg
from groq import Groq
from psycopg.types.json import Jsonb

import judge_groq as judge
from day3 import load_dataset

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_eval_runs (
    run_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    config_sha256 TEXT NOT NULL,
    config JSONB NOT NULL,
    reviewed_by TEXT NOT NULL,
    dataset_snapshot JSONB NOT NULL,
    rubric_snapshot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_eval_results (
    run_id UUID NOT NULL
        REFERENCES ledger_eval_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    trial INTEGER NOT NULL CHECK (trial > 0),
    status TEXT NOT NULL CHECK (status IN ('completed', 'error')),
    eval_score DOUBLE PRECISION,
    expected_pass BOOLEAN NOT NULL,
    passed BOOLEAN,
    judge_latency_ms DOUBLE PRECISION NOT NULL,
    result JSONB NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, case_id, trial),
    CHECK (
        (status = 'completed'
            AND eval_score IS NOT NULL
            AND eval_score BETWEEN 0 AND 1
            AND passed IS NOT NULL)
        OR
        (status = 'error'
            AND eval_score IS NULL
            AND passed IS NULL)
    )
);
"""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def database_url() -> str:
    """Accept DATABASE_URL, or fall back to the app's LEDGER_DATABASE_URL."""
    url = os.getenv("DATABASE_URL") or os.getenv("LEDGER_DATABASE_URL")
    if not url:
        raise SystemExit(
            "Set DATABASE_URL (or LEDGER_DATABASE_URL) before running. "
            "Add ?sslmode=require for a hosted database without a CA file."
        )
    url = url.replace("postgresql+psycopg://", "postgresql://")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def connect() -> psycopg.Connection[Any]:
    url = database_url()
    if "sslmode=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        print(
            "Warning: remote DATABASE_URL has no sslmode. Append ?sslmode=require "
            "(or verify-full with sslrootcert) before relying on this connection.",
            file=sys.stderr,
        )
    return psycopg.connect(url, autocommit=True, connect_timeout=10)


def initialize_database() -> None:
    with connect() as connection, connection.transaction():
        connection.execute(SCHEMA)
    print("Created ledger_eval_runs and ledger_eval_results.")


def build_config(
    dataset: dict[str, Any], dataset_hash: str, repeats: int
) -> dict[str, Any]:
    return {
        "dataset_version": dataset["dataset_version"],
        "dataset_sha256": dataset_hash,
        "rubric_version": judge.RUBRIC_VERSION,
        "rubric_sha256": digest(judge.RUBRIC.encode()),
        # Captures changes to score weights and other evaluator code.
        "evaluator_source_sha256": digest(Path(judge.__file__).read_bytes()),
        "requested_model": judge.MODEL,
        "temperature": 0,
        "pass_threshold": judge.PASS_THRESHOLD,
        "repeats": repeats,
        "case_count": len(dataset["cases"]),
    }


def print_summary(connection: psycopg.Connection[Any], run_id: uuid.UUID) -> int:
    row = connection.execute(
        """
        SELECT
            count(*) AS saved,
            count(*) FILTER (WHERE status = 'completed') AS completed,
            count(*) FILTER (WHERE status = 'error') AS errors,
            count(*) FILTER (
                WHERE status = 'completed'
                  AND passed = TRUE AND expected_pass = FALSE
            ) AS false_passes,
            count(*) FILTER (
                WHERE status = 'completed'
                  AND passed = FALSE AND expected_pass = TRUE
            ) AS false_fails
        FROM ledger_eval_results
        WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()

    if row is None:
        raise SystemExit("Could not read the result summary.")

    saved, completed, errors, false_passes, false_fails = row
    print(
        f"\nSaved={saved}, completed={completed}, errors={errors}, "
        f"false_passes={false_passes}, false_fails={false_fails}"
    )
    return int(errors)


def run_evaluations(args: argparse.Namespace) -> None:
    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("Set GROQ_API_KEY before running.")
    if not args.reviewed_by.strip():
        raise SystemExit("Provide the name of the actual dataset reviewer.")

    dataset, dataset_hash = load_dataset()
    judge.DATASET_VERSION = dataset["dataset_version"]
    config = build_config(dataset, dataset_hash, args.repeats)
    config_hash = digest(json.dumps(config, sort_keys=True).encode())
    run_id: uuid.UUID = args.run_id or uuid.uuid4()

    print(f"Run ID: {run_id}", flush=True)
    print("Keep this ID if you need to resume an interrupted run.")

    client = Groq(timeout=30.0, max_retries=2)

    with connect() as connection:
        # Prevent two runner processes from operating on the same run.
        lock_key = int.from_bytes(
            hashlib.sha256(run_id.bytes).digest()[:8],
            byteorder="big",
            signed=True,
        )
        locked_row = connection.execute(
            "SELECT pg_try_advisory_lock(%s)", (lock_key,)
        ).fetchone()
        if not locked_row or not locked_row[0]:
            raise SystemExit("Another process is already executing this run.")

        connection.execute(
            """
            INSERT INTO ledger_eval_runs (
                run_id, config_sha256, config, reviewed_by,
                dataset_snapshot, rubric_snapshot
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                run_id,
                config_hash,
                Jsonb(config),
                args.reviewed_by,
                Jsonb(dataset),
                judge.RUBRIC,
            ),
        )

        existing = connection.execute(
            """
            SELECT config_sha256, reviewed_by
            FROM ledger_eval_runs WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()

        if existing != (config_hash, args.reviewed_by):
            raise SystemExit(
                "Run configuration or reviewer changed. Start a new run "
                "instead of mixing results."
            )

        for trial in range(1, args.repeats + 1):
            for case in dataset["cases"]:
                saved = connection.execute(
                    """
                    SELECT 1 FROM ledger_eval_results
                    WHERE run_id = %s AND case_id = %s AND trial = %s
                    """,
                    (run_id, case["case_id"], trial),
                ).fetchone()

                if saved:
                    print(f"Skip saved: trial={trial} {case['case_id']}")
                    continue

                result = judge.evaluate(client, case)
                result["trial"] = trial
                result["scenario_id"] = case["scenario_id"]

                # Persist immediately, before evaluating the next case.
                connection.execute(
                    """
                    INSERT INTO ledger_eval_results (
                        run_id, case_id, trial, status, eval_score,
                        expected_pass, passed, judge_latency_ms, result
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        case["case_id"],
                        trial,
                        result["status"],
                        result["eval_score"],
                        result["expected_pass"],
                        result["passed"],
                        result["judge_latency_ms"],
                        Jsonb(result),
                    ),
                )

                print(
                    f"Saved: trial={trial} {case['case_id']} "
                    f"status={result['status']} score={result['eval_score']}",
                    flush=True,
                )

        errors = print_summary(connection, run_id)

    if errors:
        raise SystemExit(
            "Run contains evaluation errors. Inspect them, fix the cause, "
            "and start a new run. Saved errors are not overwritten."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")

    runner = commands.add_parser("run")
    runner.add_argument("--reviewed-by", required=True)
    runner.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    runner.add_argument("--run-id", type=uuid.UUID)

    args = parser.parse_args()
    if args.command == "init-db":
        initialize_database()
    else:
        run_evaluations(args)


if __name__ == "__main__":
    main()
