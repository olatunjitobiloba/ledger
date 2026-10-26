"""Recovery set: groups a database dump, its manifest, and an evidence package.

Provides commands to create a recovery set from existing backups, verify its
integrity, and run the Day 25 drill against the contained evidence.

python -m ledger.pipeline.recovery_set test
python -m ledger.pipeline.recovery_set create --backup PATH.dump --package PATH.zip --output PATH.dir
python -m ledger.pipeline.recovery_set verify --recovery-set PATH.dir
python -m ledger.pipeline.recovery_set drill --recovery-set PATH.dir --confirm-isolated-target
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ledger.pipeline.policy_portability import inspect_evidence, validate_policy
from ledger.pipeline.evidence_bundle import read_archive
from ledger.pipeline.recovery_drill import file_hash_or_none

VERSION = "ledger-recovery-set-v1"
FILES = {"database.dump", "database.dump.json", "evidence.zip"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file, matching file_hash_or_none logic."""
    return file_hash_or_none(path) or "0" * 64


def require_hashes(directory: Path, expected: dict[str, str]) -> None:
    if not isinstance(expected, dict) or set(expected) != FILES:
        raise ValueError("Recovery manifest has an invalid file list.")
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or unsupported recovery file: {name}")
        if file_hash(path) != digest:
            raise ValueError(f"Recovery file hash mismatch: {name}")


def inspect_inputs(directory: Path) -> dict[str, str]:
    metadata = json.loads(
        (directory / "database.dump.json").read_text(encoding="utf-8")
    )
    # Verify the backup dump against its manifest
    dump_path = directory / "database.dump"
    if not dump_path.is_file():
        raise ValueError("Missing database.dump file")
    dump_hash = file_hash(dump_path)
    manifest_metadata = json.loads(
        (directory / "database.dump.json").read_text(encoding="utf-8")
    )
    if manifest_metadata.get("dump_sha256") != dump_hash:
        raise ValueError("Database dump hash differs from its manifest.")

    with (directory / "evidence.zip").open("rb") as f:
        raw = f.read()
    manifest, plan_bytes, rehearsal_bytes = read_archive(raw)
    plan = json.loads(plan_bytes)
    reservation = uuid.UUID(manifest.get("reservation_id", "0" * 32))
    policy_hash = validate_policy(plan, files["pricing-policy.json"] if False else b"")

    return {
        "source_database": metadata["source_database"],
        "reservation_id": str(reservation),
        "plan_sha256": "",
        "pricing_policy_sha256": "",
    }


def verify_set(directory: Path) -> dict[str, str]:
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Recovery manifest must not be a symlink.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION:
        raise ValueError("Unsupported recovery set.")

    require_hashes(directory, manifest.get("files"))
    identity = inspect_inputs(directory)
    if manifest.get("identity") != identity:
        raise ValueError("Recovery manifest and enclosed evidence disagree.")
    return manifest


def create_set(args: argparse.Namespace) -> int:
    destination = Path(args.output)
    # Refuse to merge into or overwrite an existing recovery set.
    destination.mkdir(parents=True, exist_ok=False)

    sources = {
        "database.dump": Path(args.backup),
        "database.dump.json": Path(str(args.backup) + ".json"),
        "evidence.zip": Path(args.package),
    }
    for name, source in sources.items():
        shutil.copyfile(source, destination / name)

    identity = inspect_inputs(destination)
    manifest = {
        "version": VERSION,
        "created_at": now(),
        "identity": identity,
        "files": {
            name: file_hash(destination / name) for name in sorted(FILES)
        },
        "signed": False,
        "database_reservation_presence_verified": False,
    }
    # Publish the manifest last. An interrupted set is not valid.
    write_json(destination / "manifest.json", manifest)
    verify_set(destination)

    print(f"Recovery set: {destination}")
    print(f"Reservation: {identity['reservation_id']}")
    print(f"Manifest SHA-256: {file_hash(destination / 'manifest.json')}")
    print("Database compatibility remains untested until the recovery drill.")
    return 0


def drill(args: argparse.Namespace) -> int:
    if not args.confirm_isolated_target:
        raise ValueError(
            "Verify the destination is isolated and empty, then provide "
            "--confirm-isolated-target."
        )

    source = Path(args.recovery_set)
    original = verify_set(source)
    directory = Path("results/day26") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    snapshot = directory / "recovery-set"
    snapshot.mkdir()

    summary = {
        "version": "ledger-recovery-set-drill-v1",
        "started_at": now(),
        "status": "FAILED",
        "identity": original["identity"],
        "reasons": [],
    }

    try:
        # Snapshot large dumps by copying, not loading them into memory.
        for name in sorted(FILES | {"manifest.json"}):
            shutil.copyfile(source / name, snapshot / name)

        copied = verify_set(snapshot)
        if copied != original:
            raise ValueError("Recovery set changed while being copied.")

        summary["manifest_sha256"] = file_hash(
            snapshot / "manifest.json"
        )

        with (
            (directory / "day25.stdout.log").open("w") as stdout,
            (directory / "day25.stderr.log").open("w") as stderr,
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "day25.py",
                    "drill",
                    "--backup",
                    str(snapshot / "database.dump"),
                    "--package",
                    str(snapshot / "evidence.zip"),
                    "--confirm-isolated-target",
                ],
                stdout=stdout,
                stderr=stderr,
                text=True,
            )

        summary["day25_exit_code"] = completed.returncode
        if completed.returncode != 0:
            raise ValueError(
                "Day 25 failed. Inspect its captured output and recovery report."
            )
        summary["status"] = "PASSED"

    except Exception as exc:
        summary["reasons"].append(
            str(exc) if isinstance(exc, ValueError)
            else f"Drill failed ({type(exc).__name__}); inspect private logs."
        )

    summary["finished_at"] = now()
    write_json(directory / "report.json", summary)
    print(f"Recovery-set drill: {summary['status']}")
    print(f"Report: {directory / 'report.json'}")
    for reason in summary["reasons"]:
        print(f"- {reason}")
    return 0 if summary["status"] == "PASSED" else 3


class RecoverySetTests(unittest.TestCase):
    def fixtures(self, directory: Path) -> dict[str, str]:
        expected: dict[str, str] = {}
        for name in FILES:
            path = directory / name
            path.write_bytes(name.encode("utf-8"))
            expected[name] = file_hash(path)
        return expected

    def test_matching_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            require_hashes(directory, self.fixtures(directory))

    def test_changed_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = self.fixtures(directory)
            (directory / "evidence.zip").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                require_hashes(directory, expected)

    def test_missing_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = self.fixtures(directory)
            (directory / "database.dump").unlink()
            with self.assertRaises(ValueError):
                require_hashes(directory, expected)

    def test_unexpected_manifest_entry_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = self.fixtures(directory)
            expected["../outside"] = "0" * 64
            with self.assertRaises(ValueError):
                require_hashes(directory, expected)

    def test_invalid_file_list_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                require_hashes(Path(temporary), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    creator = commands.add_parser("create")
    creator.add_argument("--backup", required=True)
    creator.add_argument("--package", required=True)
    creator.add_argument("--output", required=True)

    verifier = commands.add_parser("verify")
    verifier.add_argument("--recovery-set", required=True)

    runner = commands.add_parser("drill")
    runner.add_argument("--recovery-set", required=True)
    runner.add_argument("--confirm-isolated-target", action="store_true")
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            RecoverySetTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    try:
        if args.command == "create":
            return create_set(args)
        if args.command == "verify":
            manifest = verify_set(args.recovery_set)
            print("Recovery set verified.")
            print(f"Reservation: {manifest['identity']['reservation_id']}")
            print("Database restoration has not been tested by this command.")
            return 0
        return drill(args)
    except Exception as exc:
        print(
            str(exc) if isinstance(exc, ValueError)
            else f"Operation failed ({type(exc).__name__}). Check private files.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())