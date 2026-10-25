"""Recovery drill: restore and reconcile a package from a clean checkout.

Proves that a Day 23 reconciliation package can be restored and re-verified
without reusing evidence left on the original runner. The drill refuses to run
when the target report or historical policy already exists, makes no model
calls, and performs no database writes.

python -m ledger.pipeline.recovery_drill test
python -m ledger.pipeline.recovery_drill drill --package PATH.zip
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ledger.pipeline.evidence_bundle import (
    read_archive_from_bytes,
    sha256,
)
from ledger.pipeline.policy_portability import (
    inspect_evidence,
    read_package,
    validate_policy,
)
from ledger.pipeline.reservation_reconciliation import CHILD_EXIT_CODES

VERSION = "ledger-recovery-drill-v1"
COST_EXIT_CODES = CHILD_EXIT_CODES
ACTIVE_POLICY = Path("evaluation-budget.json")


def now() -> str:
    return datetime.now(UTC).isoformat()


def file_hash_or_none(path: Path) -> str | None:
    return sha256(path.read_bytes()) if path.exists() else None


def require_absent(report_path: Path, policy_path: Path) -> None:
    for path in (report_path, policy_path):
        if path.exists() or path.is_symlink():
            raise ValueError(
                f"Drill requires absent evidence: {path}. "
                "Use a fresh checkout; do not delete original evidence."
            )


def require_unchanged(before: str | None, after: str | None) -> None:
    if before != after:
        raise ValueError("Active pricing policy changed during the drill.")


def find_reconciliation_report(stdout: str) -> Path:
    paths = [
        line[len("Report: ") :]
        for line in stdout.splitlines()
        if line.startswith("Report: ")
    ]
    if len(paths) != 1:
        raise ValueError("Expected exactly one Day 21 report path.")

    supplied = Path(paths[0])
    resolved = supplied.resolve()
    root = Path("results/day21").resolve()
    if (
        supplied.is_absolute()
        or not resolved.is_relative_to(root)
        or resolved.name != "report.json"
        or not resolved.is_file()
    ):
        raise ValueError("Unexpected Day 21 report location.")
    return supplied


def validate_reconciliation(
    report: dict[str, Any], returncode: int, reservation: uuid.UUID
) -> str:
    if report.get("version") != "ledger-reservation-reconciliation-v1":
        raise ValueError("Unsupported Day 21 report.")
    if report.get("reservation_id") != str(reservation):
        raise ValueError("Reconciliation reservation differs from the package.")

    status = report.get("status")
    if status not in COST_EXIT_CODES or COST_EXIT_CODES[status] != returncode:
        raise ValueError("Reconciliation status and exit code disagree.")

    if report.get("association_verified") is not True:
        raise ValueError("Restored evidence did not pass association checks.")

    return status


def run_logged(command: list[str], directory: Path, label: str) -> tuple[int, Path]:
    stdout_path = directory / f"{label}.stdout.log"
    stderr_path = directory / f"{label}.stderr.log"
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        completed = subprocess.run(
            command,
            stdout=stdout,
            stderr=stderr,
            text=True,
            check=False,
        )
    return completed.returncode, stdout_path


def drill(args: argparse.Namespace) -> int:
    directory = Path("results/day24") / str(uuid.uuid4())
    directory.mkdir(parents=True)

    summary: dict[str, Any] = {
        "version": VERSION,
        "started_at": now(),
        "drill_status": "FAILED",
        "cost_status": None,
        "initial_evidence_absent": False,
        "restoration_verified": False,
        "association_verified": False,
        "reconciliation_completed": False,
        "active_policy_unchanged": False,
        "database_restore_tested": False,
        "reasons": [],
    }
    before = None
    baseline_captured = False

    try:
        before = file_hash_or_none(ACTIVE_POLICY)
        baseline_captured = True
        summary["active_policy_sha256_before"] = before

        # Snapshot the package so the inspected and restored bytes are identical.
        package_raw = Path(args.package).read_bytes()
        package_path = directory / "package.zip"
        package_path.write_bytes(package_raw)
        summary["package_sha256"] = sha256(package_raw)

        files, manifest = read_package(package_path)
        plan, inner_manifest, reservation = inspect_evidence(files["evidence.zip"])
        policy_hash = validate_policy(plan, files["pricing-policy.json"])

        if (
            manifest.get("reservation_id") != str(reservation)
            or manifest.get("plan_sha256") != inner_manifest["plan_sha256"]
            or manifest.get("pricing_policy_sha256") != policy_hash
        ):
            raise ValueError("Package identities disagree.")

        report_path = Path(inner_manifest["rehearsal_report"])
        policy_path = Path("results/day23") / str(reservation) / "pricing-policy.json"
        require_absent(report_path, policy_path)

        summary.update(
            {
                "reservation_id": str(reservation),
                "initial_evidence_absent": True,
                "pricing_policy_sha256": policy_hash,
            }
        )

        code, _ = run_logged(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.policy_portability",
                "restore",
                "--package",
                str(package_path),
            ],
            directory,
            "restore",
        )
        if code != 0:
            raise ValueError("Day 23 restoration failed. Inspect restore.stderr.log.")

        _inner_manifest, _plan_bytes, rehearsal_bytes = read_archive_from_bytes(
            files["evidence.zip"]
        )
        if report_path.read_bytes() != rehearsal_bytes:
            raise ValueError("Restored rehearsal report bytes differ.")
        if policy_path.read_bytes() != files["pricing-policy.json"]:
            raise ValueError("Restored historical policy bytes differ.")
        summary["restoration_verified"] = True

        code, stdout_path = run_logged(
            [
                sys.executable,
                "-m",
                "ledger.pipeline.reservation_reconciliation",
                "reconcile",
                "--reservation",
                str(reservation),
            ],
            directory,
            "reconcile",
        )
        reconciliation_path = find_reconciliation_report(
            stdout_path.read_text(encoding="utf-8")
        )
        raw = reconciliation_path.read_bytes()
        reconciliation = json.loads(raw)
        status = validate_reconciliation(reconciliation, code, reservation)

        summary.update(
            {
                "association_verified": True,
                "cost_status": status,
                "reconciliation_completed": status in {"RECONCILED_RECORDS", "PARTIAL"},
                "reconciliation_report": str(reconciliation_path),
                "reconciliation_report_sha256": sha256(raw),
                "reconciliation": reconciliation,
            }
        )

        if status == "INCONCLUSIVE":
            raise ValueError(
                "Association passed, but cost reconciliation was inconclusive."
            )

        summary["drill_status"] = "PASSED"
        if status == "PARTIAL":
            summary["reasons"].append(
                "Recovery worked; saved cost evidence remains partial."
            )

    except ValueError as exc:
        summary["reasons"].append(str(exc))
    except Exception as exc:  # noqa: BLE001
        summary["reasons"].append(
            f"Drill could not complete ({type(exc).__name__}). "
            "Inspect local logs, package, database access, and script setup."
        )
    finally:
        if baseline_captured:
            try:
                after = file_hash_or_none(ACTIVE_POLICY)
                summary["active_policy_sha256_after"] = after
                require_unchanged(before, after)
                summary["active_policy_unchanged"] = True
            except Exception as exc:  # noqa: BLE001
                summary["drill_status"] = "FAILED"
                summary["reasons"].append(
                    f"Active policy preservation check failed: {exc}"
                )

    summary["finished_at"] = now()
    destination = directory / "report.json"
    destination.write_text(
        json.dumps(summary, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print(f"Drill: {summary['drill_status']}")
    print(f"Cost status: {summary['cost_status']}")
    for reason in summary["reasons"]:
        print(f"- {reason}")
    print(f"Report: {destination}")
    return 0 if summary["drill_status"] == "PASSED" else 3


class RecoveryDrillTests(unittest.TestCase):
    def report(self, status: str) -> tuple[dict[str, Any], uuid.UUID]:
        reservation = uuid.uuid4()
        report = {
            "version": "ledger-reservation-reconciliation-v1",
            "reservation_id": str(reservation),
            "association_verified": True,
            "status": status,
        }
        return report, reservation

    def test_complete_reconciliation(self) -> None:
        report, reservation = self.report("RECONCILED_RECORDS")
        self.assertEqual(
            validate_reconciliation(report, 0, reservation),
            "RECONCILED_RECORDS",
        )

    def test_partial_reconciliation(self) -> None:
        report, reservation = self.report("PARTIAL")
        self.assertEqual(validate_reconciliation(report, 2, reservation), "PARTIAL")

    def test_wrong_reservation_rejected(self) -> None:
        report, _ = self.report("PARTIAL")
        with self.assertRaises(ValueError):
            validate_reconciliation(report, 2, uuid.uuid4())

    def test_unverified_association_rejected(self) -> None:
        report, reservation = self.report("PARTIAL")
        report["association_verified"] = False
        with self.assertRaises(ValueError):
            validate_reconciliation(report, 2, reservation)

    def test_wrong_exit_code_rejected(self) -> None:
        report, reservation = self.report("RECONCILED_RECORDS")
        with self.assertRaises(ValueError):
            validate_reconciliation(report, 3, reservation)

    def test_policy_change_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_unchanged("a" * 64, "b" * 64)

    def test_existing_evidence_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            policy = Path(directory) / "policy.json"
            report.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                require_absent(report, policy)

    def test_absent_evidence_accepted(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            require_absent(
                Path(directory) / "report.json",
                Path(directory) / "policy.json",
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    command = commands.add_parser("drill")
    command.add_argument("--package", required=True)
    args = parser.parse_args(argv)

    if args.command == "test":
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryDrillTests)
        )
        return 0 if result.wasSuccessful() else 1

    return drill(args)


if __name__ == "__main__":
    raise SystemExit(main())
