"""Bind release evidence to the exact Git commit.

    python -m ledger.pipeline.provenance test
    python -m ledger.pipeline.provenance generate --prompt-file prompts/candidate.txt
    python -m ledger.pipeline.provenance check --baseline <UUID> --candidate <UUID>

Generation requires a clean repository. Checks reject candidate evidence whose
generation-time provenance does not match the expected commit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.evaluation_runs import connect

PROVENANCE_VERSION = "ledger-git-provenance-v1"
EXIT_CODES = {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def repository_root() -> Path:
    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    if Path.cwd().resolve() != root:
        raise ValueError("Run ledger.pipeline.provenance from the repository root.")
    return root


def clean_commit() -> str:
    repository_root()
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError(
            "Repository has tracked changes or untracked files. "
            "Review and commit them before generating evidence."
        )
    return git("rev-parse", "HEAD")


def require_tracked(path: str) -> None:
    root = repository_root()
    relative = Path(path).resolve().relative_to(root)
    git("ls-files", "--error-unmatch", "--", relative.as_posix())


def output_path(stdout: str, prefix: str, directory: str) -> Path:
    lines = [
        line[len(prefix) :] for line in stdout.splitlines() if line.startswith(prefix)
    ]
    if len(lines) != 1:
        raise ValueError("Could not identify exactly one output artifact.")

    path = Path(lines[0]).resolve()
    if path.parent != Path(directory).resolve() or not path.is_file():
        raise ValueError("Unexpected artifact location.")
    return path


def validate_provenance(provenance: object, expected_commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected_commit):
        raise ValueError("Expected commit must be a full lowercase Git SHA.")
    if not isinstance(provenance, dict):
        raise ValueError("Candidate has no generation-time provenance.")
    if provenance.get("version") != PROVENANCE_VERSION:
        raise ValueError("Unsupported provenance version.")
    if provenance.get("repository_clean") is not True:
        raise ValueError("Candidate was not recorded from a clean repository.")
    if provenance.get("commit_sha") != expected_commit:
        raise ValueError("Candidate evidence belongs to a different commit.")


def generate(args: argparse.Namespace) -> None:
    before = clean_commit()
    for path in (
        "ledger/pipeline/prompt_evaluation.py",
        "judge.py",
        "ledger/pipeline/provenance.py",
        args.prompt_file,
    ):
        require_tracked(path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.pipeline.prompt_evaluation",
            "generate",
            "--prompt-file",
            args.prompt_file,
            "--app-version",
            args.app_version,
            "--reviewed-by",
            args.reviewed_by,
            "--app-model",
            args.app_model,
        ],
        text=True,
        capture_output=True,
    )
    print(completed.stdout, end="")
    if completed.returncode:
        raise ValueError(
            "Generation failed. Inspect its saved artifact; "
            "no valid commit provenance was attached."
        )

    path = output_path(completed.stdout, "Generation artifact: ", "results/day7")
    after = clean_commit()
    if before != after:
        raise ValueError(
            "Repository commit changed during generation. "
            "Discard this run and generate again."
        )

    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("generation_complete"):
        raise ValueError("Generation artifact is incomplete.")

    manifest["application_provenance"] = {
        "version": PROVENANCE_VERSION,
        "commit_sha": before,
        "repository_clean": True,
        "captured_at": datetime.now(UTC).isoformat(),
        "scope": "clean local Git repository snapshot",
    }

    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)

    print(f"Bound generation to commit: {before}")
    print(f"Evaluate this artifact: {path}")


def check(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "decision": "INCONCLUSIVE",
        "baseline_run_id": str(args.baseline),
        "candidate_run_id": str(args.candidate),
        "expected_commit": args.expected_commit,
        "provenance_version": PROVENANCE_VERSION,
        "reasons": [],
    }

    try:
        repository_root()
        if git("rev-parse", "HEAD") != args.expected_commit:
            raise ValueError(
                "Checked-out repository does not match the expected commit."
            )

        with connect() as connection:
            row = connection.execute(
                """
                SELECT config
                FROM ledger_eval_runs WHERE run_id = %s
                """,
                (args.candidate,),
            ).fetchone()

        if row is None:
            raise ValueError("Candidate run does not exist.")

        provenance = row[0].get("application_provenance")
        validate_provenance(provenance, args.expected_commit)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.release_policy",
                "check",
                "--baseline",
                str(args.baseline),
                "--candidate",
                str(args.candidate),
                "--allowed-drop",
                str(args.allowed_drop),
                "--quality-floor",
                str(args.quality_floor),
            ],
            text=True,
            capture_output=True,
        )
        path = output_path(completed.stdout, "Report: ", "results/day9")
        underlying = json.loads(path.read_text(encoding="utf-8"))
        expected_exit = EXIT_CODES.get(underlying.get("decision"))
        if expected_exit is None or completed.returncode != expected_exit:
            raise ValueError("Release-check output and exit status disagree.")

        report.update(underlying)
        report.update(
            {
                "expected_commit": args.expected_commit,
                "application_provenance": provenance,
                "provenance_verified": True,
                "provenance_version": PROVENANCE_VERSION,
            }
        )
    except ValueError as exc:
        report["reasons"] = [str(exc)]
    except Exception as exc:
        report["reasons"] = [
            (
                f"Check could not complete ({type(exc).__name__}). "
                "Verify repository, database, and run configuration."
            )
        ]

    report["checked_at"] = datetime.now(UTC).isoformat()
    output = Path("results/day11")
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    print(f"Decision: {report['decision']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    print(f"Report: {path}")
    return EXIT_CODES[report["decision"]]


class ProvenanceTests(unittest.TestCase):
    def provenance(self) -> dict[str, Any]:
        return {
            "version": PROVENANCE_VERSION,
            "commit_sha": "a" * 40,
            "repository_clean": True,
        }

    def test_matching_commit(self) -> None:
        validate_provenance(self.provenance(), "a" * 40)

    def test_wrong_commit(self) -> None:
        with self.assertRaises(ValueError):
            validate_provenance(self.provenance(), "b" * 40)

    def test_missing_provenance(self) -> None:
        with self.assertRaises(ValueError):
            validate_provenance(None, "a" * 40)

    def test_dirty_repository_attestation(self) -> None:
        provenance = self.provenance()
        provenance["repository_clean"] = False
        with self.assertRaises(ValueError):
            validate_provenance(provenance, "a" * 40)

    def test_abbreviated_sha_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_provenance(self.provenance(), "abcdef0")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    generator = commands.add_parser("generate")
    generator.add_argument("--prompt-file", required=True)
    generator.add_argument("--app-version", required=True)
    generator.add_argument("--reviewed-by", required=True)
    generator.add_argument("--app-model", default="openai/gpt-oss-20b")

    checker = commands.add_parser("check")
    checker.add_argument("--baseline", required=True, type=uuid.UUID)
    checker.add_argument("--candidate", required=True, type=uuid.UUID)
    checker.add_argument("--expected-commit", required=True)
    checker.add_argument("--allowed-drop", type=float, default=0.05)
    checker.add_argument("--quality-floor", type=float, default=0.75)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProvenanceTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.command == "check":
        return check(args)

    try:
        generate(args)
        return 0
    except Exception as exc:
        print(
            f"Generation wrapper failed ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
