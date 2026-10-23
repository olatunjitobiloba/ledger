"""Portable reconciliation package primitives.

Packages a reservation evidence bundle together with the historical pricing
policy that produced its spend plan, so a reviewer can restore and re-verify
the estimate outside the active repository policy.

python -m ledger.pipeline.policy_portability test
python -m ledger.pipeline.policy_portability export --reservation RESERVATION_UUID --output PATH.zip
python -m ledger.pipeline.policy_portability restore --package PATH.zip
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from typing import Any

from ledger.pipeline.evidence_bundle import (
    MAX_ARCHIVE_BYTES,
    MAX_MEMBER_BYTES,
    publish_no_overwrite,
    read_archive,
    sha256,
)
from ledger.pipeline.spend_plan import VERSION as PLAN_VERSION
from ledger.pipeline.spend_plan import calculate, canonical_hash

VERSION = "ledger-reconciliation-package-v1"
MEMBERS = {"manifest.json", "evidence.zip", "pricing-policy.json"}
PACKAGE_LIMIT = MAX_ARCHIVE_BYTES + MAX_MEMBER_BYTES + 1024 * 1024


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def validate_policy(plan: dict[str, Any], policy_raw: bytes) -> str:
    if plan.get("version") != PLAN_VERSION:
        raise ValueError("Unsupported spend plan.")

    payload = plan.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Invalid spend-plan payload.")
    if plan.get("payload_sha256") != canonical_hash(payload):
        raise ValueError("Spend-plan payload hash differs.")

    if sha256(policy_raw) != payload["spend_policy_sha256"]:
        raise ValueError("Pricing policy does not match the spend plan.")

    policy = json.loads(policy_raw)
    recalculated = calculate(
        policy,
        payload["case_count"],
        payload["execution"]["repeats"],
    )
    if recalculated != payload["cost_plan"]:
        raise ValueError("Pricing policy does not reproduce the saved estimate.")

    return payload["spend_policy_sha256"]


def inspect_evidence(raw: bytes) -> tuple[dict[str, Any], dict[str, Any], uuid.UUID]:
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Inner evidence archive is too large.")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "evidence.zip"
        path.write_bytes(raw)
        manifest, plan_bytes, _rehearsal_bytes = read_archive(path)

    plan = json.loads(plan_bytes)
    if canonical_hash(plan) != manifest.get("plan_sha256"):
        raise ValueError("Inner plan and evidence manifest disagree.")

    reservation = uuid.UUID(manifest["reservation_id"])
    return plan, manifest, reservation


def read_package(path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    path = Path(path)
    if path.stat().st_size > PACKAGE_LIMIT:
        raise ValueError("Package exceeds the allowed size.")

    limits = {
        "manifest.json": MAX_MEMBER_BYTES,
        "evidence.zip": MAX_ARCHIVE_BYTES,
        "pricing-policy.json": MAX_MEMBER_BYTES,
    }
    with zipfile.ZipFile(path, "r") as archive:
        entries = archive.infolist()
        if (
            len(entries) != len(MEMBERS)
            or {entry.filename for entry in entries} != MEMBERS
        ):
            raise ValueError("Package has missing or unexpected members.")

        files: dict[str, bytes] = {}
        for entry in entries:
            if entry.is_dir() or entry.flag_bits & 1:
                raise ValueError("Directories/encrypted members are unsupported.")
            limit = limits[entry.filename]
            if entry.file_size > limit:
                raise ValueError("Package member is too large.")
            with archive.open(entry) as stream:
                raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("Expanded package member is too large.")
            files[entry.filename] = raw

    manifest = json.loads(files["manifest.json"])
    if manifest.get("version") != VERSION:
        raise ValueError("Unsupported reconciliation package.")

    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != {
        "evidence.zip",
        "pricing-policy.json",
    }:
        raise ValueError("Invalid package manifest.")

    for name, digest in expected.items():
        if sha256(files[name]) != digest:
            raise ValueError(f"Package hash mismatch: {name}")

    return files, manifest


def export_package(args: argparse.Namespace) -> int:
    policy_raw = Path(args.policy).read_bytes()
    if len(policy_raw) > MAX_MEMBER_BYTES:
        raise ValueError("Pricing policy is too large.")

    with tempfile.TemporaryDirectory() as directory:
        evidence_path = Path(directory) / "evidence.zip"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.evidence_bundle",
                "export",
                "--reservation",
                str(args.reservation),
                "--output",
                str(evidence_path),
            ],
            check=True,
        )
        evidence_raw = evidence_path.read_bytes()

    plan, inner_manifest, reservation = inspect_evidence(evidence_raw)
    if reservation != args.reservation:
        raise ValueError("Evidence belongs to a different reservation.")
    policy_hash = validate_policy(plan, policy_raw)

    manifest = {
        "version": VERSION,
        "reservation_id": str(reservation),
        "plan_sha256": inner_manifest["plan_sha256"],
        "pricing_policy_sha256": policy_hash,
        "files": {
            "evidence.zip": sha256(evidence_raw),
            "pricing-policy.json": sha256(policy_raw),
        },
        "signed": False,
    }

    with tempfile.TemporaryDirectory() as directory:
        package_path = Path(directory) / "package.zip"
        with zipfile.ZipFile(
            package_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("manifest.json", json_bytes(manifest))
            archive.writestr("evidence.zip", evidence_raw)
            archive.writestr("pricing-policy.json", policy_raw)
        package_raw = package_path.read_bytes()

    if len(package_raw) > PACKAGE_LIMIT:
        raise ValueError("Generated package is too large.")

    result = publish_no_overwrite(Path(args.output), package_raw)
    print(f"Package: {args.output}")
    print(f"Publication: {result}")
    print(f"Package SHA-256: {sha256(package_raw)}")
    return 0


def restore_package(args: argparse.Namespace) -> int:
    files, manifest = read_package(args.package)
    plan, inner_manifest, reservation = inspect_evidence(files["evidence.zip"])
    policy_hash = validate_policy(plan, files["pricing-policy.json"])

    if (
        manifest.get("reservation_id") != str(reservation)
        or manifest.get("plan_sha256") != inner_manifest["plan_sha256"]
        or manifest.get("pricing_policy_sha256") != policy_hash
    ):
        raise ValueError("Outer and inner package identities disagree.")

    # The evidence bundle verifies the plan, report, and candidate against PostgreSQL.
    with tempfile.TemporaryDirectory() as directory:
        evidence_path = Path(directory) / "evidence.zip"
        evidence_path.write_bytes(files["evidence.zip"])
        subprocess.run(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.evidence_bundle",
                "restore",
                "--bundle",
                str(evidence_path),
            ],
            check=True,
        )

    policy_path = (
        Path("results/day23") / str(reservation) / "pricing-policy.json"
    )
    result = publish_no_overwrite(policy_path, files["pricing-policy.json"])

    print(f"Reservation: {reservation}")
    print(f"Historical policy: {policy_path}")
    print(f"Policy publication: {result}")
    print("Active repository policy and database unchanged.")
    return 0


class PolicyPortabilityTests(unittest.TestCase):
    def fixtures(self) -> tuple[dict[str, Any], bytes]:
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
        raw = json_bytes(policy)
        payload = {
            "spend_policy_sha256": sha256(raw),
            "case_count": 6,
            "execution": {"repeats": 1},
            "cost_plan": calculate(policy, 6, 1),
        }
        plan = {
            "version": PLAN_VERSION,
            "payload": payload,
            "payload_sha256": canonical_hash(payload),
        }
        return plan, raw

    def test_exact_policy(self) -> None:
        plan, raw = self.fixtures()
        self.assertEqual(validate_policy(plan, raw), sha256(raw))

    def test_changed_policy_rejected(self) -> None:
        plan, raw = self.fixtures()
        with self.assertRaises(ValueError):
            validate_policy(plan, raw + b"\n")

    def test_changed_estimate_rejected(self) -> None:
        plan, raw = self.fixtures()
        plan["payload"]["cost_plan"]["estimated_total_usd"] = "999"
        plan["payload_sha256"] = canonical_hash(plan["payload"])
        with self.assertRaises(ValueError):
            validate_policy(plan, raw)

    def test_changed_payload_hash_rejected(self) -> None:
        plan, raw = self.fixtures()
        plan["payload_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_policy(plan, raw)

    def test_unknown_plan_version_rejected(self) -> None:
        plan, raw = self.fixtures()
        plan["version"] = "unknown"
        with self.assertRaises(ValueError):
            validate_policy(plan, raw)

    def test_unexpected_package_member_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../outside.txt", "unexpected")
            with self.assertRaises(ValueError):
                read_package(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    exporter = commands.add_parser("export")
    exporter.add_argument("--reservation", required=True, type=uuid.UUID)
    exporter.add_argument("--policy", default="evaluation-budget.json")
    exporter.add_argument("--output", required=True)

    restorer = commands.add_parser("restore")
    restorer.add_argument("--package", required=True)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            PolicyPortabilityTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    try:
        return (
            export_package(args)
            if args.command == "export"
            else restore_package(args)
        )
    except ValueError as exc:
        print(f"Package operation rejected: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(
            f"Package operation could not complete ({type(exc).__name__}). "
            "Check evidence, historical policy, database access, and files.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
