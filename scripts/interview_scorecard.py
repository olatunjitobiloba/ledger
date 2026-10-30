"""Interview evidence scorecard.

Records and scores qualitative customer discovery interviews against predefined
thresholds: >=8 interviews, >=4 cost surprises, and >=2 committed pilots.

Usage:
    python scripts/interview_scorecard.py add --alias "P1" --role "ML lead" \
        --surprise-evidence "Eval run cost 3x estimate, Sept" \
        --pilot committed --next-step "Share sample config by Nov 10"

    python scripts/interview_scorecard.py score
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_FILE = Path("results/day30/interviews.jsonl")
MIN_INTERVIEWS, MIN_SURPRISES, MIN_PILOTS = 8, 4, 2
PILOT_LEVELS = ("none", "interested", "committed")


def load(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            rows = []
            for r in reader:
                had_surprise = str(r.get("had_cost_surprise", "")).strip().lower() in {"yes", "y", "true", "1"}
                agreed_pilot = str(r.get("agreed_to_pilot", "")).strip().lower() in {"yes", "y", "true", "1"}
                rows.append({
                    "alias": r.get("name", ""),
                    "role": "Interviewee",
                    "date": date.today().isoformat(),
                    "cost_surprise_evidence": "had cost surprise" if had_surprise else "",
                    "pilot": "committed" if agreed_pilot else "none",
                    "next_step": "pilot agreed" if agreed_pilot else "",
                })
            return rows

    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def add_interview(
    path: Path | str,
    alias: str,
    role: str,
    surprise_evidence: str = "",
    pilot: str = "none",
    next_step: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    alias, role = alias.strip(), role.strip()
    surprise_evidence, next_step = surprise_evidence.strip(), next_step.strip()
    if not alias or not role:
        raise ValueError("alias and role are required")
    if pilot not in PILOT_LEVELS:
        raise ValueError(f"pilot must be one of {PILOT_LEVELS}")
    if pilot == "committed" and not next_step:
        raise ValueError("committed pilot needs --next-step (who does what, by when)")
    if any(r.get("alias", "").lower() == alias.lower() for r in load(path)):
        raise ValueError(f"alias already recorded: {alias}")
    row = {
        "alias": alias,
        "role": role,
        "date": (today or date.today()).isoformat(),
        "cost_surprise_evidence": surprise_evidence,
        "pilot": pilot,
        "next_step": next_step,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    interviews = len(rows)
    surprises = sum(1 for r in rows if r.get("cost_surprise_evidence"))
    pilots = sum(1 for r in rows if r.get("pilot") == "committed")
    met = surprises >= MIN_SURPRISES and pilots >= MIN_PILOTS
    if interviews < MIN_INTERVIEWS:
        verdict, code = "CONTINUE", 2
    elif met:
        verdict, code = "GO", 0
    else:
        verdict, code = "NO_GO", 3
    return {
        "interviews": interviews,
        "cost_surprises": surprises,
        "committed_pilots": pilots,
        "verdict": verdict,
        "exit_code": code,
    }


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Backwards compatibility: if called with no subcommand or a file path directly
    if not argv:
        argv = ["score"]
    elif argv[0] not in ("add", "score", "-h", "--help"):
        argv = ["score", "--file", argv[0]]

    p = argparse.ArgumentParser(description="Interview evidence scorecard")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Record a customer discovery interview")
    a.add_argument("--file", default=str(DEFAULT_FILE), help="Target JSONL file")
    a.add_argument("--alias", required=True, help="Participant alias (not real name)")
    a.add_argument("--role", required=True, help="Participant role / title")
    a.add_argument("--surprise-evidence", default="", help="Factual historical cost surprise evidence")
    a.add_argument("--pilot", default="none", choices=PILOT_LEVELS, help="Pilot commitment level")
    a.add_argument("--next-step", default="", help="Specific agreed next step with owner and deadline")

    s = sub.add_parser("score", help="Score recorded interviews against validation thresholds")
    s.add_argument("--file", default=str(DEFAULT_FILE), help="Source JSONL/CSV file")

    args = p.parse_args(argv)

    try:
        if args.cmd == "add":
            add_interview(
                args.file,
                args.alias,
                args.role,
                args.surprise_evidence,
                args.pilot,
                args.next_step,
            )
            print("recorded")
            return 0
        result = score(load(args.file))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
