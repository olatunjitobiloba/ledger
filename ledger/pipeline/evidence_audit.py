"""Evidence audit: finished reservations without recoverable evidence.

Compares the reservation ledger, Day 23 packages, and the coverage recorded in a
Day 25 backup manifest. Read-only: no model calls, database writes, or restores.

python -m ledger.pipeline.evidence_audit test
python -m ledger.pipeline.evidence_audit audit \
    --backup PATH.dump --packages DIRECTORY
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

from ledger.pipeline.database_recovery import (
    DRILL_VERSION,
    metadata_path,
    verify_backup,
)
from ledger.pipeline.evaluation_runs import connect
from ledger.pipeline.evidence_bundle import sha256
from ledger.pipeline.policy_portability import (
    inspect_evidence,
    read_package,
    validate_policy,
)

VERSION = "ledger-evidence-audit-v1"
KEYS = (
    "reservation_id",
    "candidate_run_id",
    "plan_sha256",
    "rehearsal_report_sha256",
)
EXIT_CODES = {"OK": 0, "ATTENTION": 2, "ERROR": 3}

FINISHED_QUERY = """
    SELECT reservation_id::text, candidate_run_id::text,
           plan_sha256, rehearsal_report_sha256
    FROM ledger_spend_reservations
    WHERE state = 'FINISHED' AND candidate_run_id IS NOT NULL
    ORDER BY reservation_id
"""

UNRESOLVED_QUERY = """
    SELECT reservation_id::text, state
    FROM ledger_spend_reservations
    WHERE state IN ('RUNNING', 'UNKNOWN')
    ORDER BY reservation_id
"""


def now() -> datetime:
    return datetime.now(UTC)


def entry_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(entry.get(key) for key in KEYS)


def canonical_uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid.")  # noqa: TRY004
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{label} is invalid.") from exc
    if str(parsed) != value:
        raise ValueError(f"{label} is not canonical.")
    return value


def require_hash(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} is invalid.")
    return value


def load_ledger() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    try:
        with connect() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            finished = connection.execute(FINISHED_QUERY).fetchall()
            unresolved = connection.execute(UNRESOLVED_QUERY).fetchall()
    except psycopg.errors.UndefinedTable as exc:
        raise ValueError(
            "ledger_spend_reservations is missing; initialize the "
            "spend-reservation schema before auditing."
        ) from exc

    return (
        [dict(zip(KEYS, row, strict=True)) for row in finished],
        [{"reservation_id": row[0], "state": row[1]} for row in unresolved],
    )


def scan_packages(
    directory: str | Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"Package directory does not exist: {root}")

    entries: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for path in sorted(root.glob("*.zip")):
        try:
            if path.is_symlink():
                raise ValueError("Package path is a symlink.")
            files, manifest = read_package(path)
            plan, inner, _reservation = inspect_evidence(files["evidence.zip"])
            policy_hash = validate_policy(plan, files["pricing-policy.json"])

            reservation_id = canonical_uuid(
                inner.get("reservation_id"), "Reservation ID"
            )
            candidate_run_id = canonical_uuid(
                inner.get("candidate_run_id"), "Candidate run ID"
            )
            plan_sha256 = require_hash(inner.get("plan_sha256"), "Plan hash")
            report_sha256 = require_hash(
                inner.get("rehearsal_sha256"), "Rehearsal report hash"
            )

            if (
                manifest.get("reservation_id") != reservation_id
                or manifest.get("plan_sha256") != plan_sha256
                or manifest.get("pricing_policy_sha256") != policy_hash
            ):
                raise ValueError("Outer and inner package identities disagree.")

            entries.append(
                {
                    "reservation_id": reservation_id,
                    "candidate_run_id": candidate_run_id,
                    "plan_sha256": plan_sha256,
                    "rehearsal_report_sha256": report_sha256,
                    "package": path.name,
                    "package_sha256": sha256(path.read_bytes()),
                }
            )
        except Exception as exc:  # noqa: BLE001
            rejected.append(
                {
                    "package": path.name,
                    "reason": (
                        str(exc)
                        if isinstance(exc, ValueError)
                        else f"Unreadable package ({type(exc).__name__})."
                    ),
                }
            )
    return entries, rejected


def find_gaps(
    finished: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    backup_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    packaged = {entry_key(entry) for entry in packages}
    backed = {entry_key(entry) for entry in backup_entries}
    gaps = []
    for entry in finished:
        key = entry_key(entry)
        problems = []
        if key not in packaged:
            problems.append("no verified package matches the ledger")
        if key not in backed:
            problems.append("not covered by the supplied backup")
        if problems:
            gaps.append(
                {
                    "reservation_id": entry["reservation_id"],
                    "problems": problems,
                }
            )
    return gaps


def load_drill_reports(directory: str | Path) -> list[dict[str, Any]]:
    reports = []
    for path in sorted(Path(directory).glob("*/report.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(report, dict) and report.get("version") == DRILL_VERSION:
            reports.append(report)
    return reports


def report_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def latest_passed_drill(reports: list[dict[str, Any]]) -> datetime | None:
    times = []
    for report in reports:
        if report.get("status") != "PASSED":
            continue
        finished = report_time(report.get("finished_at"))
        if finished is not None:
            times.append(finished)
    return max(times) if times else None


def drill_is_fresh(
    latest: datetime | None, current: datetime, max_age_days: int
) -> bool:
    if latest is None:
        return False
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current - latest <= timedelta(days=max_age_days)


def audit(args: argparse.Namespace) -> int:
    directory = Path("results/day27") / str(uuid.uuid4())
    directory.mkdir(parents=True)
    summary: dict[str, Any] = {
        "version": VERSION,
        "started_at": now().isoformat(),
        "status": "ERROR",
        "reasons": [],
        "database_modified": False,
        "model_calls_made": False,
    }

    try:
        dump = Path(args.backup)
        if dump.is_symlink() or not dump.is_file():
            raise ValueError("Backup dump is missing or unsupported.")
        metadata = json.loads(
            metadata_path(dump).read_text(encoding="utf-8")
        )
        verify_backup(dump, metadata)

        coverage = metadata.get("coverage")
        if not isinstance(coverage, dict) or coverage.get("table_available") is not True:
            raise ValueError(
                "Backup manifest has no usable coverage. Take a new backup."
            )
        backup_entries = coverage.get("finished_reservations")
        if not isinstance(backup_entries, list) or not all(
            isinstance(entry, dict)
            and all(isinstance(entry.get(key), str) for key in KEYS)
            for entry in backup_entries
        ):
            raise ValueError("Backup coverage is invalid.")

        finished, unresolved = load_ledger()
        packages, rejected = scan_packages(args.packages)
        gaps = find_gaps(finished, packages, backup_entries)
        latest = latest_passed_drill(load_drill_reports(args.drill_dir))
        fresh = drill_is_fresh(latest, now(), args.max_drill_age_days)

        if gaps:
            summary["reasons"].append(
                f"{len(gaps)} finished reservation(s) have recovery gaps."
            )
        if not fresh:
            summary["reasons"].append(
                "No passing database drill within "
                f"{args.max_drill_age_days} days in {args.drill_dir}."
            )

        summary.update(
            {
                "status": "ATTENTION" if summary["reasons"] else "OK",
                "finished_reservations": len(finished),
                "verified_packages": len(packages),
                "backup_coverage_count": len(backup_entries),
                "gaps": gaps,
                "unresolved_reservations": unresolved,
                "rejected_packages": rejected,
                "latest_passed_drill": latest.isoformat() if latest else None,
                "drill_fresh": fresh,
                "backup_dump_sha256": metadata["dump_sha256"],
            }
        )
    except Exception as exc:  # noqa: BLE001
        summary["reasons"].append(
            str(exc)
            if isinstance(exc, ValueError)
            else f"Audit could not complete ({type(exc).__name__}). "
            "Check database access, paths, and the backup manifest."
        )

    summary["finished_at"] = now().isoformat()
    report_path = directory / "report.json"
    report_path.write_text(
        json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8"
    )

    print(f"Audit: {summary['status']}")
    print(f"Finished reservations: {summary.get('finished_reservations')}")
    for gap in summary.get("gaps", []):
        print(f"- {gap['reservation_id']}: {'; '.join(gap['problems'])}")
    for item in summary.get("unresolved_reservations", []):
        print(f"- unresolved {item['reservation_id']} ({item['state']})")
    for item in summary.get("rejected_packages", []):
        print(f"- rejected {item['package']}: {item['reason']}")
    for reason in summary["reasons"]:
        print(f"* {reason}")
    print(f"Report: {report_path}")
    return EXIT_CODES[summary["status"]]


class EvidenceAuditTests(unittest.TestCase):
    def entry(self, name: str = "r1", report: str = "h") -> dict[str, str]:
        return {
            "reservation_id": name,
            "candidate_run_id": "c",
            "plan_sha256": "p",
            "rehearsal_report_sha256": report,
        }

    def test_no_gaps(self) -> None:
        entry = self.entry()
        self.assertEqual(find_gaps([entry], [entry], [entry]), [])

    def test_missing_package(self) -> None:
        entry = self.entry()
        gaps = find_gaps([entry], [], [entry])
        self.assertEqual(len(gaps), 1)
        self.assertIn("package", gaps[0]["problems"][0])

    def test_missing_backup(self) -> None:
        entry = self.entry()
        gaps = find_gaps([entry], [entry], [])
        self.assertIn("backup", gaps[0]["problems"][0])

    def test_changed_report_hash_is_a_gap(self) -> None:
        gaps = find_gaps(
            [self.entry()], [self.entry(report="other")], [self.entry()]
        )
        self.assertEqual(len(gaps), 1)

    def test_fresh_drill(self) -> None:
        current = datetime(2026, 10, 27, tzinfo=UTC)
        latest = current - timedelta(days=3)
        self.assertTrue(drill_is_fresh(latest, current, 7))

    def test_stale_drill(self) -> None:
        current = datetime(2026, 10, 27, tzinfo=UTC)
        latest = current - timedelta(days=30)
        self.assertFalse(drill_is_fresh(latest, current, 7))

    def test_no_drill(self) -> None:
        self.assertFalse(drill_is_fresh(None, now(), 7))

    def test_failed_drills_ignored(self) -> None:
        reports = [
            {"status": "FAILED", "finished_at": "2026-10-26T00:00:00+00:00"},
            {"status": "PASSED", "finished_at": "2026-10-20T00:00:00+00:00"},
        ]
        self.assertEqual(
            latest_passed_drill(reports),
            datetime(2026, 10, 20, tzinfo=UTC),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    command = commands.add_parser("audit")
    command.add_argument("--backup", required=True)
    command.add_argument("--packages", required=True)
    command.add_argument("--drill-dir", default="results/day25")
    command.add_argument("--max-drill-age-days", type=int, default=30)
    args = parser.parse_args(argv)

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            EvidenceAuditTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.max_drill_age_days < 0:
        print("--max-drill-age-days must not be negative.", file=sys.stderr)
        return EXIT_CODES["ERROR"]
    return audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
