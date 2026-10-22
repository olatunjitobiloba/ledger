"""Day 14: rehearse the complete containerized evaluation pipeline.

    python day14.py test
    python day14.py run --image registry/image@sha256:<digest> ...

All evidence-producing steps run inside the pinned Day 13 runtime image.
Step output is written to local logs instead of the summary report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day11 import clean_commit
from day13 import container_command, generation_artifact, inspect_image, validate_binding


VERSION = "ledger-rehearsal-v1"
EXIT_CODES = {
    "READY": 0,
    "BLOCK": 1,
    "REVIEW": 2,
    "INCONCLUSIVE": 3,
}


def parse_report_path(stdout: str, directory: str) -> Path:
    lines = [
        line.removeprefix("Report: ")
        for line in stdout.splitlines()
        if line.startswith("Report: ")
    ]
    if len(lines) != 1:
        raise ValueError("Expected exactly one report path.")

    relative = Path(lines[0])
    if relative.is_absolute() or relative.parent != Path(directory):
        raise ValueError("Unexpected report location.")

    resolved = relative.resolve()
    if resolved.parent != Path(directory).resolve():
        raise ValueError("Report path escaped its expected directory.")
    if not resolved.is_file():
        raise ValueError("Report file does not exist.")
    return resolved


def validate_decision(report: object, returncode: int) -> str:
    if not isinstance(report, dict):
        raise ValueError("Release report must be an object.")
    decision = report.get("decision")
    if decision not in EXIT_CODES:
        raise ValueError("Unknown release decision.")
    if EXIT_CODES[decision] != returncode:
        raise ValueError("Release decision and exit code disagree.")
    return decision


def judge_command(
    binding: dict[str, Any], artifact: str, repeats: int
) -> list[str]:
    command = container_command(
        binding,
        [
            "day7.py",
            "evaluate",
            "--artifact",
            artifact,
            "--repeats",
            str(repeats),
        ],
        generation=True,
    )

    image_position = command.index(binding["image_id"])
    command[image_position:image_position] = ["--env", "DATABASE_URL"]
    return command


def run_step(
    report: dict[str, Any],
    directory: Path,
    name: str,
    command: list[str],
) -> int:
    started = time.perf_counter()
    record = {
        "name": name,
        "status": "running",
        "exit_code": None,
        "duration_seconds": None,
        "stdout_log": str(directory / f"{name}.stdout.log"),
        "stderr_log": str(directory / f"{name}.stderr.log"),
    }
    report["steps"].append(record)
    print(f"Running: {name}", flush=True)

    try:
        with (
            Path(record["stdout_log"]).open("w", encoding="utf-8") as stdout,
            Path(record["stderr_log"]).open("w", encoding="utf-8") as stderr,
        ):
            completed = subprocess.run(
                command,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
        record["exit_code"] = completed.returncode
        record["status"] = (
            "completed" if completed.returncode == 0 else "nonzero_exit"
        )
        return completed.returncode
    except Exception:
        record["status"] = "execution_error"
        raise
    finally:
        record["duration_seconds"] = round(time.perf_counter() - started, 3)


def require_success(code: int, name: str) -> None:
    if code != 0:
        raise ValueError(
            f"{name} failed with exit code {code}; inspect its local logs."
        )


def read_stdout(directory: Path, name: str) -> str:
    return (directory / f"{name}.stdout.log").read_text(encoding="utf-8")


def rehearsal(args: argparse.Namespace) -> int:
    rehearsal_id = str(uuid.uuid4())
    directory = Path("results/day14") / rehearsal_id
    directory.mkdir(parents=True)

    report: dict[str, Any] = {
        "version": VERSION,
        "rehearsal_id": rehearsal_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "baseline_run_id": str(args.baseline),
        "candidate_run_id": None,
        "decision": "INCONCLUSIVE",
        "reasons": [],
        "steps": [],
        "release_report": None,
        "deployment_performed": False,
    }

    try:
        for name in ("GROQ_API_KEY", "DATABASE_URL"):
            if not os.getenv(name):
                raise ValueError(f"Set {name} before starting.")

        commit = clean_commit()
        binding = inspect_image(args.image)
        report["source_commit"] = commit
        report["execution_container"] = binding
        report["repeats"] = args.repeats
        report["allowed_drop"] = args.allowed_drop
        report["quality_floor"] = args.quality_floor

        code = run_step(
            report,
            directory,
            "generation",
            [
                sys.executable,
                "day13.py",
                "generate",
                "--image",
                args.image,
                "--app-version",
                args.app_version,
                "--reviewed-by",
                args.reviewed_by,
            ],
        )
        require_success(code, "Generation")

        artifact = generation_artifact(read_stdout(directory, "generation"))
        manifest_bytes = artifact.read_bytes()
        manifest = json.loads(manifest_bytes)
        candidate_id = uuid.UUID(manifest["run_id"])
        validate_binding(manifest.get("container_binding"), binding)

        report["candidate_run_id"] = str(candidate_id)
        report["generation_artifact"] = str(artifact.relative_to(Path.cwd()))
        report["generation_artifact_sha256"] = hashlib.sha256(
            manifest_bytes
        ).hexdigest()

        code = run_step(
            report,
            directory,
            "evaluation",
            judge_command(
                binding,
                report["generation_artifact"],
                args.repeats,
            ),
        )
        require_success(code, "Evaluation")

        code = run_step(
            report,
            directory,
            "security_scan",
            container_command(
                binding,
                ["day8.py", "scan-run", "--run-id", str(candidate_id)],
            ),
        )
        require_success(code, "Security scan")

        code = run_step(
            report,
            directory,
            "cost_backfill",
            container_command(binding, ["day5.py", "backfill"]),
        )
        require_success(code, "Cost backfill")

        if clean_commit() != commit:
            raise ValueError("Source changed before the release check.")

        code = run_step(
            report,
            directory,
            "release_check",
            [
                sys.executable,
                "day13.py",
                "check",
                "--image",
                args.image,
                "--baseline",
                str(args.baseline),
                "--candidate",
                str(candidate_id),
                "--expected-commit",
                commit,
                "--allowed-drop",
                str(args.allowed_drop),
                "--quality-floor",
                str(args.quality_floor),
            ],
        )
        release_path = parse_report_path(
            read_stdout(directory, "release_check"), "results/day13"
        )
        release = json.loads(release_path.read_text(encoding="utf-8"))
        decision = validate_decision(release, code)

        if clean_commit() != commit:
            raise ValueError("Source changed before the rehearsal completed.")

        report["decision"] = decision
        report["reasons"] = release.get("reasons", [])
        report["release_report"] = str(release_path.relative_to(Path.cwd()))
        report["release_report_sha256"] = hashlib.sha256(
            release_path.read_bytes()
        ).hexdigest()

    except ValueError as exc:
        report["decision"] = "INCONCLUSIVE"
        report["reasons"] = [str(exc)]
    except Exception as exc:
        report["decision"] = "INCONCLUSIVE"
        report["reasons"] = [
            f"Rehearsal could not complete ({type(exc).__name__}). "
            "Inspect local step logs and environment setup."
        ]

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = directory / "report.json"
    path.write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"\nDecision: {report['decision']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Report: {path}")
    return EXIT_CODES[report["decision"]]


class RehearsalTests(unittest.TestCase):
    def test_ready_exit(self) -> None:
        self.assertEqual(validate_decision({"decision": "READY"}, 0), "READY")

    def test_review_is_not_success(self) -> None:
        self.assertEqual(validate_decision({"decision": "REVIEW"}, 2), "REVIEW")

    def test_inconsistent_exit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_decision({"decision": "BLOCK"}, 0)

    def test_unknown_decision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_decision({"decision": "APPROVED"}, 0)

    def test_failed_step_stops_pipeline(self) -> None:
        with self.assertRaises(ValueError):
            require_success(1, "Evaluation")

    def test_judge_receives_both_secret_names(self) -> None:
        from unittest.mock import patch

        binding = {"image_id": "sha256:" + "a" * 64}
        with patch(
            "day14.container_command",
            return_value=[
                "docker",
                "run",
                "--env",
                "GROQ_API_KEY",
                binding["image_id"],
                "python",
                "day7.py",
            ],
        ):
            command = judge_command(binding, "results/day7/example.json", 1)
        image_position = command.index(binding["image_id"])
        self.assertEqual(
            command[image_position - 2 : image_position],
            ["--env", "DATABASE_URL"],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    runner = commands.add_parser("run")
    runner.add_argument("--image", required=True)
    runner.add_argument("--baseline", required=True, type=uuid.UUID)
    runner.add_argument("--app-version", required=True)
    runner.add_argument("--reviewed-by", required=True)
    runner.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    runner.add_argument("--allowed-drop", type=float, default=0.05)
    runner.add_argument("--quality-floor", type=float, default=0.75)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(RehearsalTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    for name in ("allowed_drop", "quality_floor"):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1.")

    return rehearsal(args)


if __name__ == "__main__":
    raise SystemExit(main())
