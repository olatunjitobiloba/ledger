import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


HISTORY = Path("results/day28/audit-history.jsonl")
EXIT_CODES = {"OK": 0, "ATTENTION": 2, "ERROR": 3}


def now():
    return datetime.now(timezone.utc).isoformat()


def find_report(stdout):
    paths = [
        line[len("Report: "):]
        for line in stdout.splitlines()
        if line.startswith("Report: ")
    ]
    if len(paths) != 1:
        raise ValueError("Day 27 did not identify exactly one report.")

    supplied = Path(paths[0])
    resolved = supplied.resolve()
    root = Path("results/day27").resolve()
    if (
        supplied.is_absolute()
        or not resolved.is_relative_to(root)
        or resolved.name != "report.json"
        or not resolved.is_file()
    ):
        raise ValueError("Unexpected Day 27 report location.")
    return supplied


def summarize(report, report_path, returncode):
    if report.get("version") != "ledger-evidence-audit-v1":
        raise ValueError("Unsupported Day 27 report.")
    status = report.get("status")
    if status not in EXIT_CODES or EXIT_CODES[status] != returncode:
        raise ValueError("Day 27 status and exit code disagree.")

    return {
        "checked_at": now(),
        "status": status,
        "finished_reservations": report.get("finished_reservations"),
        "gap_ids": sorted(
            g["reservation_id"] for g in report.get("gaps", [])
        ),
        "unresolved_ids": sorted(
            u["reservation_id"]
            for u in report.get("unresolved_reservations", [])
        ),
        "rejected_packages": len(report.get("rejected_packages", [])),
        "drill_fresh": report.get("drill_fresh"),
        "audit_report": str(report_path),
        "reasons": report.get("reasons", []),
    }


def failure_entry(reason):
    return {
        "checked_at": now(),
        "status": "ERROR",
        "finished_reservations": None,
        "gap_ids": [],
        "unresolved_ids": [],
        "rejected_packages": 0,
        "drill_fresh": None,
        "audit_report": None,
        "reasons": [reason],
    }


def compare(previous, current):
    before = set(previous["gap_ids"]) if previous else set()
    after = set(current["gap_ids"])
    return {
        "new_gaps": sorted(after - before),
        "cleared_gaps": sorted(before - after),
    }


def consecutive_non_ok(history):
    count = 0
    for entry in reversed(history):
        if entry.get("status") == "OK":
            break
        count += 1
    return count


def read_history(path):
    entries = []
    if not Path(path).exists():
        return entries
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue  # Skip a damaged line; never rewrite history.
    return entries


def append_history(path, entry):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(args):
    history = read_history(HISTORY)
    previous = history[-1] if history else None

    command = [
        sys.executable, "day27.py", "audit",
        "--backup", args.backup,
        "--packages", args.packages,
        "--drill-dir", args.drill_dir,
        "--max-drill-age-days", str(args.max_drill_age_days),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)

    try:
        path = find_report(completed.stdout)
        report = json.loads(path.read_text(encoding="utf-8"))
        entry = summarize(report, path, completed.returncode)
    except Exception as exc:
        entry = failure_entry(
            str(exc) if isinstance(exc, ValueError)
            else f"Wrapper failed ({type(exc).__name__})."
        )

    changes = compare(previous, entry)
    append_history(HISTORY, entry)
    streak = consecutive_non_ok(read_history(HISTORY))

    print(f"Scheduled audit: {entry['status']}")
    if changes["new_gaps"]:
        print(f"New gaps since last run: {', '.join(changes['new_gaps'])}")
    if changes["cleared_gaps"]:
        print(f"Cleared: {', '.join(changes['cleared_gaps'])}")
    if streak >= args.escalate_after:
        print(
            f"ESCALATE: {streak} consecutive runs were not OK. "
            "Fix the cause; do not raise the threshold."
        )
    print(f"History: {HISTORY}")
    return EXIT_CODES[entry["status"]]


class ScheduledAuditTests(unittest.TestCase):
    def report(self, status="OK"):
        return {
            "version": "ledger-evidence-audit-v1",
            "status": status,
            "finished_reservations": 2,
            "gaps": [{"reservation_id": "r1", "problems": []}],
            "drill_fresh": True,
        }

    def test_summarize(self):
        entry = summarize(self.report(), Path("x"), 0)
        self.assertEqual(entry["gap_ids"], ["r1"])

    def test_status_exit_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            summarize(self.report("OK"), Path("x"), 2)

    def test_find_report_needs_exactly_one(self):
        with self.assertRaises(ValueError):
            find_report("no report here")

    def test_find_report_rejects_outside_root(self):
        with self.assertRaises(ValueError):
            find_report("Report: /tmp/report.json")

    def test_compare_new_and_cleared(self):
        previous = {"gap_ids": ["a", "b"]}
        current = {"gap_ids": ["b", "c"]}
        self.assertEqual(
            compare(previous, current),
            {"new_gaps": ["c"], "cleared_gaps": ["a"]},
        )

    def test_first_run_gaps_are_new(self):
        self.assertEqual(
            compare(None, {"gap_ids": ["a"]})["new_gaps"], ["a"]
        )

    def test_consecutive_non_ok(self):
        history = [
            {"status": "ATTENTION"}, {"status": "OK"},
            {"status": "ATTENTION"}, {"status": "ERROR"},
        ]
        self.assertEqual(consecutive_non_ok(history), 2)

    def test_history_skips_damaged_line_and_appends(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.jsonl"
            path.write_text('{"status": "OK"}\nnot json\n')
            append_history(path, {"status": "ATTENTION"})
            statuses = [e["status"] for e in read_history(path)]
            self.assertEqual(statuses, ["OK", "ATTENTION"])


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    command = commands.add_parser("run")
    command.add_argument("--backup", required=True)
    command.add_argument("--packages", required=True)
    command.add_argument("--drill-dir", default="results/day25")
    command.add_argument("--max-drill-age-days", type=int, default=30)
    command.add_argument("--escalate-after", type=int, default=3)
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            ScheduledAuditTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())