"""Outreach funnel tracker.

Tracks customer discovery outreach events in an append-only JSONL log, calculates
funnel drop-offs, flags overdue 5-day follow-ups, and cross-references booked
interviews against the interview scorecard (results/day30/interviews.jsonl).

Usage:
    python scripts/outreach_tracker.py add --alias "P1" --status contacted --channel linkedin
    python scripts/outreach_tracker.py summary
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

OUTREACH = Path("results/day31/outreach.jsonl")
INTERVIEWS = Path("results/day30/interviews.jsonl")
STATUSES = ("contacted", "replied", "booked", "interviewed", "declined", "no_response")
FOLLOW_UP_DAYS = 5


def load(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def add_event(
    path: Path | str,
    alias: str,
    status: str,
    channel: str = "",
    note: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    alias = alias.strip()
    if not alias:
        raise ValueError("alias is required")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    known = {r["alias"].lower() for r in load(path)}
    seen = alias.lower() in known
    if not seen and status != "contacted":
        raise ValueError("first event for an alias must be 'contacted'")
    if seen and status == "contacted":
        raise ValueError("already contacted; log replied or no_response instead")
    row = {
        "alias": alias,
        "status": status,
        "channel": channel.strip(),
        "note": note.strip(),
        "date": (today or date.today()).isoformat(),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def summarize(
    rows: list[dict[str, Any]],
    interview_aliases: Sequence[str] = (),
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    current: dict[str, dict[str, Any]] = {}
    for r in rows:  # later events overwrite earlier ones
        current[r["alias"].lower()] = r
    counts = {s: 0 for s in STATUSES}
    for r in current.values():
        counts[r["status"]] += 1
    follow_up_due = sorted(
        r["alias"]
        for r in current.values()
        if r["status"] == "contacted"
        and (today - date.fromisoformat(r["date"])).days >= FOLLOW_UP_DAYS
    )
    logged = {a.lower() for a in interview_aliases}
    claimed = {k for k, r in current.items() if r["status"] == "interviewed"}
    missing = sorted(claimed - logged)  # "interviewed" but absent from Day 30
    needs_attention = bool(follow_up_due or missing)
    return {
        "people_contacted": len(current),
        "counts": counts,
        "follow_up_due": follow_up_due,
        "interviewed_missing_from_day30": missing,
        "exit_code": 2 if needs_attention else 0,
    }


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Backwards compatibility / ease of use: default to summary if no args or if given file path
    if not argv:
        argv = ["summary"]
    elif argv[0] not in ("add", "summary", "-h", "--help"):
        argv = ["summary", "--file", argv[0]]

    p = argparse.ArgumentParser(description="Outreach funnel tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Record an outreach event for a contact alias")
    a.add_argument("--file", default=str(OUTREACH), help="Target outreach JSONL file")
    a.add_argument("--alias", required=True, help="Contact alias")
    a.add_argument("--status", required=True, choices=STATUSES, help="Event status")
    a.add_argument("--channel", default="", help="Channel used (e.g. linkedin, email, twitter)")
    a.add_argument("--note", default="", help="Optional context or notes")

    s = sub.add_parser("summary", help="Summarize outreach funnel and pending actions")
    s.add_argument("--file", default=str(OUTREACH), help="Source outreach JSONL file")
    s.add_argument("--interviews", default=str(INTERVIEWS), help="Source interviews JSONL file")

    args = p.parse_args(argv)

    try:
        if args.cmd == "add":
            add_event(args.file, args.alias, args.status, args.channel, args.note)
            print("recorded")
            return 0
        aliases = [r["alias"] for r in load(args.interviews)]
        result = summarize(load(args.file), aliases)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

