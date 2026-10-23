"""Bind evidence to a digest-pinned container runtime.

    python -m ledger.pipeline.container_binding test
    python -m ledger.pipeline.container_binding generate --image registry/image@sha256:<digest>
    python -m ledger.pipeline.container_binding check --image registry/image@sha256:<digest> ...

The source checkout is mounted read-only and results are mounted read-write.
The image contains dependencies; it is not the deployable application image.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.execution_context import context_from_environment
from ledger.pipeline.provenance import clean_commit

VERSION = "ledger-container-binding-v1"
EXIT_CODES = {"READY": 0, "BLOCK": 1, "REVIEW": 2, "INCONCLUSIVE": 3}


def validate_reference(reference: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", reference):
        raise ValueError("Provide a registry image pinned by SHA-256 digest.")


def inspect_image(reference: str) -> dict[str, Any]:
    validate_reference(reference)
    subprocess.run(["docker", "pull", reference], check=True)
    raw = subprocess.check_output(["docker", "image", "inspect", reference], text=True)
    details = json.loads(raw)
    if len(details) != 1:
        raise ValueError("Expected exactly one resolved image.")
    image = details[0]
    return {
        "version": VERSION,
        "image_reference": reference,
        "image_id": image["Id"],
        "platform": {
            "os": image["Os"],
            "architecture": image["Architecture"],
            "variant": image.get("Variant", ""),
        },
        "scope": "dependency runtime with separately mounted Git source",
    }


def validate_binding(stored: object, expected: dict[str, Any]) -> None:
    if not isinstance(stored, dict) or stored.get("version") != VERSION:
        raise ValueError("Candidate has no supported container binding.")
    for key in ("image_reference", "image_id", "platform"):
        if stored.get(key) != expected[key]:
            raise ValueError(f"Container binding mismatch: {key}")


def container_command(
    binding: dict[str, Any], script_args: list[str], generation: bool = False
) -> list[str]:
    root = Path.cwd().resolve()
    results = root / "results"
    results.mkdir(exist_ok=True)

    environment = ["GROQ_API_KEY"] if generation else ["DATABASE_URL"]
    for name in environment:
        if not os.getenv(name):
            raise ValueError(f"Set {name} before running this command.")

    command = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--mount",
        f"type=bind,src={root},dst=/workspace,readonly",
        "--mount",
        f"type=bind,src={results},dst=/workspace/results",
        "--workdir",
        "/workspace",
    ]
    for name in environment:
        command.extend(["--env", name])
    command.extend([binding["image_id"], "python", *script_args])
    return command


def run_container(
    binding: dict[str, Any], script_args: list[str], generation: bool = False
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        container_command(binding, script_args, generation),
        text=True,
        capture_output=True,
    )
    print(completed.stdout, end="")
    if completed.returncode not in EXIT_CODES.values():
        raise ValueError("Container process failed unexpectedly.")
    return completed


def generation_artifact(stdout: str) -> Path:
    paths = [
        line.removeprefix("Generation artifact: ")
        for line in stdout.splitlines()
        if line.startswith("Generation artifact: ")
    ]
    if len(paths) != 1:
        raise ValueError("Could not identify the generated artifact.")
    relative = Path(paths[0])
    expected_parent = Path("results/day7")
    if (
        relative.is_absolute()
        or relative.parent != expected_parent
        or relative.suffix != ".json"
    ):
        raise ValueError("Unexpected generation artifact path.")
    path = relative.resolve()
    if path.parent != (Path.cwd() / expected_parent).resolve():
        raise ValueError("Generation artifact escaped its expected directory.")
    return path


def check_report(stdout: str) -> Path:
    lines = [
        line.removeprefix("Report: ")
        for line in stdout.splitlines()
        if line.startswith("Report: ")
    ]
    if len(lines) != 1:
        raise ValueError("Underlying check did not identify one report.")
    relative = Path(lines[0])
    expected_parent = Path("results/day12")
    if relative.is_absolute() or relative.parent != expected_parent:
        raise ValueError("Unexpected underlying report path.")
    path = relative.resolve()
    if path.parent != (Path.cwd() / expected_parent).resolve():
        raise ValueError("Underlying report escaped its expected directory.")
    return path


def generate(args: argparse.Namespace) -> None:
    execution_context = context_from_environment()
    commit = clean_commit()
    binding = inspect_image(args.image)
    completed = run_container(
        binding,
        [
            "ledger/pipeline/runtime_binding.py",
            "generate",
            "--app-version",
            args.app_version,
            "--reviewed-by",
            args.reviewed_by,
        ],
        generation=True,
    )
    if completed.returncode:
        raise ValueError(
            "Generation failed; no container binding was attached. "
            "Do not evaluate the incomplete/unbound artifact."
        )
    if clean_commit() != commit:
        raise ValueError("Source changed during generation; discard this run.")

    path = generation_artifact(completed.stdout)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    provenance = manifest.get("application_provenance", {})
    if (
        not manifest.get("generation_complete")
        or provenance.get("commit_sha") != commit
        or not manifest.get("runtime_binding")
    ):
        raise ValueError("Generation did not produce expected bound evidence.")

    manifest["container_binding"] = binding
    manifest["execution_context"] = execution_context
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
    print(f"Container-bound artifact: {path}")


def check(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "decision": "INCONCLUSIVE",
        "reasons": [],
        "baseline_run_id": str(args.baseline),
        "candidate_run_id": str(args.candidate),
        "expected_commit": args.expected_commit,
        "container_binding_version": VERSION,
    }
    try:
        if clean_commit() != args.expected_commit:
            raise ValueError("Checkout does not match the expected clean commit.")

        binding = inspect_image(args.image)
        with connect() as connection:
            row = connection.execute(
                "SELECT config FROM ledger_eval_runs WHERE run_id = %s",
                (args.candidate,),
            ).fetchone()
        if row is None:
            raise ValueError("Candidate run does not exist.")
        validate_binding(row[0].get("container_binding"), binding)

        completed = run_container(
            binding,
            [
                "ledger/pipeline/runtime_binding.py",
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
        )
        path = check_report(completed.stdout)
        underlying = json.loads(path.read_text(encoding="utf-8"))
        decision = underlying.get("decision")
        if decision not in EXIT_CODES or EXIT_CODES[decision] != completed.returncode:
            raise ValueError("Underlying decision and exit status disagree.")

        report.update(underlying)
        report.update(
            {
                "container_binding_version": VERSION,
                "container_verified": True,
                "container_binding": binding,
            }
        )
    except ValueError as exc:
        report["reasons"] = [str(exc)]
    except Exception as exc:
        report["reasons"] = [
            (
                f"Check could not complete ({type(exc).__name__}). "
                "Verify Docker, registry access, database, and repository."
            )
        ]

    report["checked_at"] = datetime.now(UTC).isoformat()
    directory = Path("results/day13")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Decision: {report['decision']}")
    print(f"Report: {path}")
    return EXIT_CODES[report["decision"]]


class ContainerTests(unittest.TestCase):
    def binding(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "image_reference": "registry.example/ledger@sha256:" + "a" * 64,
            "image_id": "sha256:" + "b" * 64,
            "platform": {
                "os": "linux",
                "architecture": "amd64",
                "variant": "",
            },
        }

    def test_digest_reference(self) -> None:
        validate_reference(self.binding()["image_reference"])

    def test_mutable_tag_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_reference("registry.example/ledger:latest")

    def test_matching_binding(self) -> None:
        validate_binding(self.binding(), self.binding())

    def test_missing_binding(self) -> None:
        with self.assertRaises(ValueError):
            validate_binding(None, self.binding())

    def test_changed_image_rejected(self) -> None:
        changed = self.binding()
        changed["image_id"] = "sha256:" + "c" * 64
        with self.assertRaises(ValueError):
            validate_binding(self.binding(), changed)

    def test_changed_platform_rejected(self) -> None:
        changed = self.binding()
        changed["platform"] = {"os": "linux", "architecture": "arm64"}
        with self.assertRaises(ValueError):
            validate_binding(self.binding(), changed)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    generator = commands.add_parser("generate")
    generator.add_argument("--image", required=True)
    generator.add_argument("--app-version", required=True)
    generator.add_argument("--reviewed-by", required=True)

    checker = commands.add_parser("check")
    checker.add_argument("--image", required=True)
    checker.add_argument("--baseline", required=True, type=uuid.UUID)
    checker.add_argument("--candidate", required=True, type=uuid.UUID)
    checker.add_argument("--expected-commit", required=True)
    checker.add_argument("--allowed-drop", type=float, default=0.05)
    checker.add_argument("--quality-floor", type=float, default=0.75)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContainerTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.command == "check":
        return check(args)
    try:
        generate(args)
        return 0
    except Exception as exc:
        print(f"Generation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
