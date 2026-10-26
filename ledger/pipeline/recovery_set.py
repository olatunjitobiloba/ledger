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
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from ledger.pipeline.database_recovery import verify_backup
from ledger.pipeline.evidence_bundle import canonical_plan_bytes, sha256
from ledger.pipeline.policy_portability import (
    inspect_evidence,
    json_bytes,
    read_package,
    validate_policy,
)
from ledger.pipeline.recovery_drill import file_hash_or_none
from ledger.pipeline.spend_plan import VERSION as PLAN_VERSION
from ledger.pipeline.spend_plan import calculate, canonical_hash

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
    dump_path = directory / "database.dump"
    metadata_path = directory / "database.dump.json"
    package_path = directory / "evidence.zip"
    for path in (metadata_path, package_path):
        if path.is_symlink():
            raise ValueError(f"Recovery input must not be a symlink: {path.name}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    verify_backup(dump_path, metadata)

    files, manifest = read_package(package_path)
    plan, inner_manifest, reservation = inspect_evidence(files["evidence.zip"])
    policy_hash = validate_policy(plan, files["pricing-policy.json"])

    if (
        manifest.get("reservation_id") != str(reservation)
        or manifest.get("plan_sha256") != inner_manifest["plan_sha256"]
        or manifest.get("pricing_policy_sha256") != policy_hash
    ):
        raise ValueError("Enclosed package identities disagree.")

    return {
        "source_database": metadata["source_database"],
        "reservation_id": str(reservation),
        "plan_sha256": inner_manifest["plan_sha256"],
        "pricing_policy_sha256": policy_hash,
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
    sources = {
        "database.dump": Path(args.backup),
        "database.dump.json": Path(str(args.backup) + ".json"),
        "evidence.zip": Path(args.package),
    }
    for name, source in sources.items():
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Missing or unsupported recovery input: {source}")

    # Refuse to merge into or overwrite an existing recovery set.
    destination.mkdir(parents=True, exist_ok=False)
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
            (directory / "database-recovery.stdout.log").open("w") as stdout,
            (directory / "database-recovery.stderr.log").open("w") as stderr,
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ledger.pipeline.database_recovery",
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
                check=False,
            )

        summary["database_recovery_exit_code"] = completed.returncode
        if completed.returncode != 0:
            raise ValueError(
                "Database recovery drill failed. "
                "Inspect its captured output and recovery report."
            )
        summary["status"] = "PASSED"

    except Exception as exc:  # noqa: BLE001
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

    def backup_fixture(self, directory: Path) -> Path:
        dump = directory / "backup.dump"
        dump.write_bytes(b"postgresql-custom-dump")
        write_json(
            Path(str(dump) + ".json"),
            {
                "version": "ledger-database-backup-v1",
                "created_at": now(),
                "source_database": "ledger",
                "dump_sha256": file_hash(dump),
                "format": "postgresql-custom",
                "ownership_and_permissions_preserved": False,
                "signed": False,
            },
        )
        return dump

    def package_fixture(self, directory: Path) -> tuple[Path, uuid.UUID]:
        reservation = uuid.uuid4()
        role = {
            "model": "test-model",
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
            "planned_input_tokens_per_call": 100,
            "planned_output_tokens_per_call": 50,
            "planned_attempts_per_call": 1,
        }
        policy = {
            "version": "ledger-spend-policy-v1",
            "currency": "USD",
            "pricing_source": "Synthetic test prices",
            "budget_usd": "1",
            "application": dict(role),
            "judge": dict(role),
        }
        policy_raw = json_bytes(policy)
        payload = {
            "spend_policy_sha256": sha256(policy_raw),
            "case_count": 6,
            "execution": {"repeats": 1},
            "cost_plan": calculate(policy, 6, 1),
        }
        plan = {
            "version": PLAN_VERSION,
            "payload": payload,
            "payload_sha256": canonical_hash(payload),
        }
        plan_raw = canonical_plan_bytes(plan)
        rehearsal_raw = b'{"rehearsal":true}'
        evidence_manifest = {
            "version": "ledger-evidence-bundle-v1",
            "reservation_id": str(reservation),
            "plan_sha256": sha256(plan_raw),
            "rehearsal_sha256": sha256(rehearsal_raw),
            "signed": False,
        }
        evidence_path = directory / "inner-evidence.zip"
        with zipfile.ZipFile(evidence_path, "w") as archive:
            archive.writestr("manifest.json", json_bytes(evidence_manifest))
            archive.writestr("plan.json", plan_raw)
            archive.writestr("rehearsal.json", rehearsal_raw)
        evidence_raw = evidence_path.read_bytes()

        package_manifest = {
            "version": "ledger-reconciliation-package-v1",
            "reservation_id": str(reservation),
            "plan_sha256": sha256(plan_raw),
            "pricing_policy_sha256": sha256(policy_raw),
            "files": {
                "evidence.zip": sha256(evidence_raw),
                "pricing-policy.json": sha256(policy_raw),
            },
            "signed": False,
        }
        package_path = directory / "package.zip"
        with zipfile.ZipFile(package_path, "w") as archive:
            archive.writestr("manifest.json", json_bytes(package_manifest))
            archive.writestr("evidence.zip", evidence_raw)
            archive.writestr("pricing-policy.json", policy_raw)
        return package_path, reservation

    def create_fixture(self, root: Path) -> tuple[Path, uuid.UUID]:
        dump = self.backup_fixture(root)
        package, reservation = self.package_fixture(root)
        output = root / "recovery-set"
        code = create_set(
            SimpleNamespace(
                backup=str(dump), package=str(package), output=str(output)
            )
        )
        self.assertEqual(code, 0)
        return output, reservation

    def test_create_and_verify_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, reservation = self.create_fixture(Path(temporary))
            manifest = verify_set(output)
            self.assertEqual(set(manifest["files"]), FILES)
            self.assertEqual(
                manifest["identity"]["reservation_id"], str(reservation)
            )
            self.assertEqual(
                manifest["identity"]["source_database"], "ledger"
            )
            self.assertEqual(len(manifest["identity"]["plan_sha256"]), 64)
            self.assertEqual(
                len(manifest["identity"]["pricing_policy_sha256"]), 64
            )

    def test_tampered_dump_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.create_fixture(Path(temporary))
            (output / "database.dump").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify_set(output)

    def test_identity_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.create_fixture(Path(temporary))
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            manifest["identity"]["reservation_id"] = str(uuid.uuid4())
            write_json(output / "manifest.json", manifest)
            with self.assertRaises(ValueError):
                verify_set(output)

    def test_missing_source_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "recovery-set"
            with self.assertRaises(ValueError):
                create_set(
                    SimpleNamespace(
                        backup=str(root / "missing.dump"),
                        package=str(root / "missing.zip"),
                        output=str(output),
                    )
                )
            self.assertFalse(output.exists())

    def test_existing_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dump = self.backup_fixture(root)
            package, _ = self.package_fixture(root)
            output = root / "recovery-set"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                create_set(
                    SimpleNamespace(
                        backup=str(dump),
                        package=str(package),
                        output=str(output),
                    )
                )

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
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaises(ValueError),
        ):
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
    except Exception as exc:  # noqa: BLE001
        print(
            str(exc) if isinstance(exc, ValueError)
            else f"Operation failed ({type(exc).__name__}). Check private files.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())