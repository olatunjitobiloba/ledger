"""Bind release evidence to runtime configuration.

    python -m ledger.pipeline.runtime_binding test
    python -m ledger.pipeline.runtime_binding generate --app-version candidate-v3 --reviewed-by "Tobi"
    python -m ledger.pipeline.runtime_binding check --baseline <UUID> --candidate <UUID>

This fingerprints tracked configuration, inputs, dependencies, and Python
version before allowing a commit-bound release check to run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.golden_set import load_dataset
from ledger.pipeline.provenance import clean_commit, output_path, require_tracked

BINDING_VERSION = "ledger-runtime-binding-v1"
CONFIG_FILE = Path("runtime-config.json")
CRITICAL_PACKAGES = ("groq", "pydantic", "psycopg", "psycopg-binary")
EXIT_CODES = {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def file_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_binding() -> dict[str, Any]:
    for path in (CONFIG_FILE, "requirements.txt", "ledger/pipeline/runtime_binding.py"):
        require_tracked(str(path))

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    expected_keys = {
        "version",
        "app_model",
        "prompt_file",
        "temperature",
        "max_completion_tokens",
    }
    if set(config) != expected_keys:
        raise ValueError("Runtime configuration has missing or unknown keys.")
    if config["version"] != "ledger-runtime-v1":
        raise ValueError("Unsupported runtime configuration version.")
    if (
        type(config["temperature"]) not in (int, float)
        or config["temperature"] != 0
        or type(config["max_completion_tokens"]) is not int
        or config["max_completion_tokens"] != 2048
    ):
        raise ValueError(
            "Prompt evaluation currently supports temperature=0 and token limit=2048."
        )
    if not isinstance(config["app_model"], str) or not config["app_model"].strip():
        raise ValueError("Application model must be a nonempty string.")
    if not isinstance(config["prompt_file"], str):
        raise ValueError("Prompt path must be a string.")

    require_tracked(config["prompt_file"])
    prompt = Path(config["prompt_file"]).read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("Application prompt is empty.")

    _, dataset_hash = load_dataset()
    payload = {
        "version": BINDING_VERSION,
        "runtime_config": config,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "source_dataset_sha256": dataset_hash,
        "requirements_sha256": file_digest("requirements.txt"),
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "critical_packages": {
            name: importlib.metadata.version(name) for name in CRITICAL_PACKAGES
        },
    }
    return {"fingerprint": digest(payload), "payload": payload}


def validate_binding(stored: object, expected: dict[str, Any]) -> None:
    if not isinstance(stored, dict) or not isinstance(
        stored.get("payload"), dict
    ):
        raise ValueError("Candidate has no valid runtime binding.")
    if stored["payload"].get("version") != BINDING_VERSION:
        raise ValueError("Unsupported runtime binding version.")
    if stored.get("fingerprint") != digest(stored["payload"]):
        raise ValueError("Stored runtime fingerprint is inconsistent.")
    if stored["fingerprint"] != expected["fingerprint"]:
        raise ValueError(
            "Runtime differs: inspect configuration, prompt, dataset, "
            "Python version, requirements, and critical packages."
        )


def validate_metadata(metadata: dict[str, Any], binding: dict[str, Any]) -> None:
    payload = binding["payload"]
    config = payload["runtime_config"]
    expected = {
        "application_model": config["app_model"],
        "application_prompt_sha256": payload["prompt_sha256"],
        "source_dataset_sha256": payload["source_dataset_sha256"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"Application metadata disagrees with binding: {key}")


def generate(args: argparse.Namespace) -> None:
    commit = clean_commit()
    before = build_binding()
    config = before["payload"]["runtime_config"]

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.pipeline.provenance",
            "generate",
            "--prompt-file",
            config["prompt_file"],
            "--app-model",
            config["app_model"],
            "--app-version",
            args.app_version,
            "--reviewed-by",
            args.reviewed_by,
        ],
        text=True,
        capture_output=True,
    )
    print(completed.stdout, end="")
    if completed.returncode:
        raise ValueError(
            "Commit-bound generation failed; no runtime binding was attached."
        )

    path = output_path(
        completed.stdout, "Generation artifact: ", "results/day7"
    )
    if clean_commit() != commit:
        raise ValueError("Commit changed during generation.")
    after = build_binding()
    validate_binding(before, after)

    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_metadata(
        {
            "application_model": manifest["requested_app_model"],
            "application_prompt_sha256": manifest["prompt_sha256"],
            "source_dataset_sha256": manifest["source_dataset_sha256"],
        },
        before,
    )

    manifest["runtime_binding"] = before
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
    print(f"Runtime fingerprint: {before['fingerprint']}")
    print(f"Evaluate this artifact: {path}")


def check(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "decision": "INCONCLUSIVE",
        "reasons": [],
        "baseline_run_id": str(args.baseline),
        "candidate_run_id": str(args.candidate),
        "expected_commit": args.expected_commit,
        "runtime_binding_version": BINDING_VERSION,
    }
    try:
        if clean_commit() != args.expected_commit:
            raise ValueError("Checkout differs from the expected clean commit.")
        expected = build_binding()

        with connect() as connection:
            row = connection.execute(
                "SELECT config FROM ledger_eval_runs WHERE run_id = %s",
                (args.candidate,),
            ).fetchone()
        if row is None:
            raise ValueError("Candidate run not found.")

        run_config = row[0]
        validate_binding(run_config.get("runtime_binding"), expected)
        validate_metadata(
            {
                "application_model": run_config.get("application_model"),
                "application_prompt_sha256": run_config.get(
                    "application_prompt_sha256"
                ),
                "source_dataset_sha256": run_config.get(
                    "source_dataset_sha256"
                ),
            },
            expected,
        )

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.provenance",
                "check",
                "--baseline",
                str(args.baseline),
                "--candidate",
                str(args.candidate),
                "--expected-commit",
                args.expected_commit,
                "--allowed-drop",
                str(args.allowed_drop),
                "--quality-floor",
                str(args.quality_floor),
            ],
            text=True,
            capture_output=True,
        )
        path = output_path(completed.stdout, "Report: ", "results/day11")
        underlying = json.loads(path.read_text(encoding="utf-8"))
        decision = underlying.get("decision")
        if (
            decision not in EXIT_CODES
            or completed.returncode != EXIT_CODES[decision]
        ):
            raise ValueError("Underlying check produced inconsistent output.")

        report.update(underlying)
        report.update(
            {
                "runtime_binding_version": BINDING_VERSION,
                "runtime_verified": True,
                "runtime_fingerprint": expected["fingerprint"],
            }
        )
    except ValueError as exc:
        report["reasons"] = [str(exc)]
    except Exception as exc:
        report["reasons"] = [
            (f"Check could not complete ({type(exc).__name__}). "
            "Verify dependencies, repository, and database setup.")
        ]

    report["checked_at"] = datetime.now(UTC).isoformat()
    directory = Path("results/day12")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.json"
    path.write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"Decision: {report['decision']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Report: {path}")
    return EXIT_CODES[report["decision"]]


class BindingTests(unittest.TestCase):
    def binding(self, model: str = "model-a") -> dict[str, Any]:
        payload = {
            "version": BINDING_VERSION,
            "runtime_config": {"app_model": model},
            "prompt_sha256": "prompt",
            "source_dataset_sha256": "dataset",
        }
        return {"payload": payload, "fingerprint": digest(payload)}

    def test_matching_binding(self) -> None:
        validate_binding(self.binding(), self.binding())

    def test_changed_model(self) -> None:
        with self.assertRaises(ValueError):
            validate_binding(self.binding(), self.binding("model-b"))

    def test_missing_binding(self) -> None:
        with self.assertRaises(ValueError):
            validate_binding(None, self.binding())

    def test_tampered_payload(self) -> None:
        stored = self.binding()
        stored["payload"]["prompt_sha256"] = "changed"
        with self.assertRaises(ValueError):
            validate_binding(stored, self.binding())

    def test_changed_dataset(self) -> None:
        changed = self.binding()
        changed["payload"]["source_dataset_sha256"] = "new-dataset"
        changed["fingerprint"] = digest(changed["payload"])
        with self.assertRaises(ValueError):
            validate_binding(self.binding(), changed)

    def test_metadata_disagreement(self) -> None:
        with self.assertRaises(ValueError):
            validate_metadata(
                {
                    "application_model": "wrong-model",
                    "application_prompt_sha256": "prompt",
                    "source_dataset_sha256": "dataset",
                },
                self.binding(),
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    generator = commands.add_parser("generate")
    generator.add_argument("--app-version", required=True)
    generator.add_argument("--reviewed-by", required=True)

    checker = commands.add_parser("check")
    checker.add_argument("--baseline", required=True, type=uuid.UUID)
    checker.add_argument("--candidate", required=True, type=uuid.UUID)
    checker.add_argument("--expected-commit", required=True)
    checker.add_argument("--allowed-drop", type=float, default=0.05)
    checker.add_argument("--quality-floor", type=float, default=0.75)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(BindingTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.command == "check":
        return check(args)
    try:
        generate(args)
        return 0
    except Exception as exc:
        print(
            f"Generation failed ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
