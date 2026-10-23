"""Generate application answers, evaluate them, keep usage separate.

    python -m ledger.pipeline.prompt_evaluation generate --prompt-file prompts/baseline.txt \
        --app-version baseline-v1 --reviewed-by "Tobi"
    python -m ledger.pipeline.prompt_evaluation evaluate --artifact results/day7/<run>.json --repeats 1

Application outputs are frozen into a local artifact before judging, so judge
reruns never regenerate answers. Judge usage is written to ledger_eval_results;
application usage lives in ledger_application_outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groq import Groq
from psycopg.types.json import Jsonb

import judge_groq as judge
from ledger.pipeline.evaluation_runs import SCHEMA, build_config, connect, print_summary
from ledger.pipeline.golden_set import load_dataset

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_application_outputs (
    run_id UUID NOT NULL REFERENCES ledger_eval_runs(run_id),
    case_id TEXT NOT NULL,
    app_version TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    returned_model TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    answer TEXT NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    usage JSONB NOT NULL,
    response_id TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id)
);
"""


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def generate(args: argparse.Namespace) -> None:
    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("Set GROQ_API_KEY.")
    if not args.reviewed_by.strip() or not args.app_version.strip():
        raise SystemExit("Provide a reviewer and application version.")

    source, source_hash = load_dataset()
    selected = [
        case for case in source["cases"] if case["case_id"].endswith("-good")
    ]
    if not selected:
        raise SystemExit("No starter '-good' cases found.")

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if not prompt.strip():
        raise SystemExit("Application prompt is empty.")

    run_id = str(uuid.uuid4())
    path = Path("results/day7") / f"{run_id}.json"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "reviewed_by": args.reviewed_by,
        "source_dataset_sha256": source_hash,
        "app_version": args.app_version,
        "requested_app_model": args.app_model,
        "app_temperature": 0,
        "app_reasoning_effort": "low",
        "prompt_sha256": sha(prompt.encode()),
        "prompt_snapshot": prompt,
        "generation_complete": False,
        "outputs": [],
        "dataset": {
            "dataset_version": "ledger-app-starter-v1",
            "cases": [],
        },
    }
    save_json(path, manifest)
    print(f"Generation artifact: {path}", flush=True)

    # No automatic generation retries: preserve failed attempts explicitly.
    client = Groq(timeout=60.0, max_retries=0)

    for source_case in selected:
        started = time.perf_counter()
        output: dict[str, Any] = {"case_id": source_case["case_id"], "status": "error"}
        try:
            response = client.chat.completions.create(
                model=args.app_model,
                temperature=0,
                max_completion_tokens=2048,
                reasoning_effort="low",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": source_case["question"]},
                ],
            )
            output.update(
                {
                    "response_id": response.id,
                    "returned_model": response.model,
                    "usage": (response.usage.model_dump() if response.usage else {}),
                    "finish_reason": response.choices[0].finish_reason,
                }
            )

            answer = response.choices[0].message.content or ""
            if response.choices[0].finish_reason != "stop" or not answer.strip():
                raise ValueError("Application response is incomplete or empty.")

            output.update({"status": "completed", "answer": answer})
            manifest["dataset"]["cases"].append(
                {
                    "case_id": source_case["case_id"],
                    "scenario_id": source_case["scenario_id"],
                    "question": source_case["question"],
                    "reference": source_case["reference"],
                    "candidate_answer": answer,
                    # A desired quality expectation, not a human label asserting
                    # that the newly generated answer is correct.
                    "expected_pass": True,
                    "label_reason": "Desired application quality expectation.",
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep failed attempts explicit
            output["error"] = f"{type(exc).__name__}: {exc}"

        output["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        manifest["outputs"].append(output)
        save_json(path, manifest)
        print(f"{output['case_id']}: {output['status']}", flush=True)

        if output["status"] == "error":
            raise SystemExit(
                f"Generation failed; details saved to {path}. "
                "Fix the cause and start a new generation."
            )

    manifest["generation_complete"] = True
    save_json(path, manifest)
    print(f"\nReady to evaluate: {path}")


def evaluate(args: argparse.Namespace) -> None:
    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("Set GROQ_API_KEY.")

    raw = Path(args.artifact).read_bytes()
    manifest: dict[str, Any] = json.loads(raw)
    if not manifest.get("generation_complete"):
        raise SystemExit("Generation is incomplete; evaluation refused.")

    dataset = manifest["dataset"]
    cases = dataset["cases"]
    outputs = manifest["outputs"]
    if (
        not cases
        or len(cases) != len(outputs)
        or any(o["status"] != "completed" for o in outputs)
        or {c["case_id"] for c in cases} != {o["case_id"] for o in outputs}
        or len({c["case_id"] for c in cases}) != len(cases)
    ):
        raise SystemExit("Invalid or inconsistent generation artifact.")

    run_id = uuid.UUID(manifest["run_id"])
    judge.DATASET_VERSION = dataset["dataset_version"]
    dataset_hash = sha(json.dumps(dataset, sort_keys=True).encode())
    config = build_config(dataset, dataset_hash, args.repeats)
    config.update(
        {
            "application_provenance": manifest.get("application_provenance"),
            "source_dataset_sha256": manifest["source_dataset_sha256"],
            "runtime_binding": manifest.get("runtime_binding"),
            "container_binding": manifest.get("container_binding"),
            "execution_context": manifest.get("execution_context"),
            "application_version": manifest["app_version"],
            "application_model": manifest["requested_app_model"],
            "application_reasoning_effort": manifest.get(
                "app_reasoning_effort", "low"
            ),
            "application_prompt_sha256": manifest["prompt_sha256"],
            "generation_artifact_sha256": sha(raw),
            "expected_pass_semantics": "desired_quality_not_human_label",
        }
    )
    config_hash = sha(json.dumps(config, sort_keys=True).encode())
    reviewer = manifest["reviewed_by"]
    client = Groq(timeout=30.0, max_retries=2)

    connection = connect()
    try:
        with connection.transaction():
            connection.execute(SCHEMA)
            connection.execute(APP_SCHEMA)

        lock_key = int.from_bytes(
            hashlib.sha256(run_id.bytes).digest()[:8], "big", signed=True
        )
        locked_row = connection.execute(
            "SELECT pg_try_advisory_lock(%s)", (lock_key,)
        ).fetchone()
        if locked_row is None or not locked_row[0]:
            raise SystemExit("Another process is evaluating this run.")

        with connection.transaction():
            connection.execute(
                """
                INSERT INTO ledger_eval_runs (
                    run_id, config_sha256, config, reviewed_by,
                    dataset_snapshot, rubric_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    run_id,
                    config_hash,
                    Jsonb(config),
                    reviewer,
                    Jsonb(dataset),
                    judge.RUBRIC,
                ),
            )
            existing_row = connection.execute(
                "SELECT config_sha256 FROM ledger_eval_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if existing_row is None or existing_row[0] != config_hash:
                raise SystemExit(
                    "Artifact or evaluator configuration changed. "
                    "Generate a new run instead."
                )

            for output in outputs:
                connection.execute(
                    """
                    INSERT INTO ledger_application_outputs (
                        run_id, case_id, app_version, requested_model,
                        returned_model, prompt_sha256, answer,
                        latency_ms, usage, response_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, case_id) DO NOTHING
                    """,
                    (
                        run_id,
                        output["case_id"],
                        manifest["app_version"],
                        manifest["requested_app_model"],
                        output["returned_model"],
                        manifest["prompt_sha256"],
                        output["answer"],
                        output["latency_ms"],
                        Jsonb(output["usage"]),
                        output["response_id"],
                    ),
                )

        for trial in range(1, args.repeats + 1):
            for case in cases:
                saved = connection.execute(
                    """
                    SELECT 1 FROM ledger_eval_results
                    WHERE run_id = %s AND case_id = %s AND trial = %s
                    """,
                    (run_id, case["case_id"], trial),
                ).fetchone()
                if saved:
                    print(f"Skip saved: {case['case_id']} trial={trial}")
                    continue

                result = judge.evaluate(client, case)
                result["trial"] = trial
                result["scenario_id"] = case["scenario_id"]
                result.pop("matches_human_label", None)
                result["meets_quality_expectation"] = (
                    result["passed"] if result["status"] == "completed" else None
                )

                connection.execute(
                    """
                    INSERT INTO ledger_eval_results (
                        run_id, case_id, trial, status, eval_score,
                        expected_pass, passed, judge_latency_ms, result
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        case["case_id"],
                        trial,
                        result["status"],
                        result["eval_score"],
                        True,
                        result["passed"],
                        result["judge_latency_ms"],
                        Jsonb(result),
                    ),
                )
                print(
                    f"Saved {case['case_id']} trial={trial}: "
                    f"{result['status']} score={result['eval_score']}",
                    flush=True,
                )

        errors = print_summary(connection, run_id)
    finally:
        connection.close()

    print(f"Run ID: {run_id}")
    print(
        "For these runs, 'false_fails' in the inherited summary means "
        "unmet desired quality, not a verified judge mistake."
    )
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    generator = commands.add_parser("generate")
    generator.add_argument("--prompt-file", required=True)
    generator.add_argument("--app-version", required=True)
    generator.add_argument("--reviewed-by", required=True)
    generator.add_argument("--app-model", default="openai/gpt-oss-20b")

    evaluator = commands.add_parser("evaluate")
    evaluator.add_argument("--artifact", required=True)
    evaluator.add_argument("--repeats", type=int, choices=range(1, 6), default=1)

    args = parser.parse_args()
    if args.command == "generate":
        generate(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
