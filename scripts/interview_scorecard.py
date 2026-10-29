import csv
import sys

PROCEED_IF_PILOTS = 2        # adjust thresholds before first interview
PROCEED_IF_SURPRISES = 4     # before the interviews, not after
MIN_INTERVIEWS = 8

FIELDS = [
    "name",
    "runs_evals",
    "monthly_spend_usd",
    "had_cost_surprise",
    "current_workaround",
    "agreed_to_pilot",
    "would_pay_usd",
]


def yes(value):
    return str(value).strip().lower() in {"yes", "y", "true", "1"}


def main(path):
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    qualified = [r for r in rows if yes(r["runs_evals"])]
    surprised = [r for r in qualified if yes(r["had_cost_surprise"])]
    pilots = [r for r in qualified if yes(r["agreed_to_pilot"])]
    paying = [r for r in pilots if float(r["would_pay_usd"] or 0) > 0]

    print(f"Interviews: {len(rows)} | run evals: {len(qualified)}")
    print(f"Cost surprise: {len(surprised)}")
    print(f"Agreed to pilot: {len(pilots)} | named a price: {len(paying)}")

    if len(rows) < MIN_INTERVIEWS:
        print("NOT ENOUGH DATA: keep interviewing.")
    elif len(pilots) >= PROCEED_IF_PILOTS and len(surprised) >= PROCEED_IF_SURPRISES:
        print("PROCEED: run a paid pilot with the pilot-takers.")
    else:
        print("STOP OR PIVOT: the problem or the buyer is wrong.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "interviews.csv")
