"""Require an explicit estimated-spend approval before rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ledger.pipeline.container_binding import validate_reference
from ledger.pipeline.golden_set import load_dataset
from ledger.pipeline.provenance import clean_commit, require_tracked

VERSION = "ledger-spend-plan-v1"
POLICY_FILE = Path("evaluation-budget.json")
PLAN_LIFETIME = timedelta(hours=1)
MILLION = Decimal(1000000)


def money(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("Money and price values must be decimal strings.")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal money value.") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Money values must be finite and nonnegative.")
    return result


def positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    return hash_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def role_estimate(settings: object, logical_calls: int) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("Each usage role needs a settings object.")
    model = settings.get("model")
    if (
        not isinstance(model, str)
        or not model.strip()
        or "REPLACE" in model
    ):
        raise ValueError("Provide the actual requested model for each role.")

    input_price = money(settings.get("input_usd_per_million"))
    output_price = money(settings.get("output_usd_per_million"))
    input_tokens = positive_integer(
        settings.get("planned_input_tokens_per_call"), "Input tokens"
    )
    output_tokens = positive_integer(
        settings.get("planned_output_tokens_per_call"), "Output tokens"
    )
    attempts = positive_integer(
        settings.get("planned_attempts_per_call"), "Planned attempts"
    )

    planned_attempts = logical_calls * attempts
    estimate = (
        Decimal(planned_attempts)
        * (
            Decimal(input_tokens) * input_price
            + Decimal(output_tokens) * output_price
        )
        / MILLION
    )
    return {
        "requested_model": model,
        "logical_calls": logical_calls,
        "planned_attempts": planned_attempts,
        "planned_input_tokens_per_attempt": input_tokens,
        "planned_output_tokens_per_attempt": output_tokens,
        "estimated_usd": str(estimate),
    }


def calculate(
    policy: dict[str, Any], case_count: int, repeats: int
) -> dict[str, Any]:
    positive_integer(case_count, "Case count")
    positive_integer(repeats, "Repeats")

    if policy.get("version") != "ledger-spend-policy-v1":
        raise ValueError("Unsupported spending policy.")
    if policy.get("currency") != "USD":
        raise ValueError("This planner currently supports USD only.")

    source = policy.get("pricing_source")
    if (
        not isinstance(source, str)
        or not source.strip()
        or "REPLACE" in source
    ):
        raise ValueError("Record your verified pricing source and date.")

    budget = money(policy.get("budget_usd"))
    application = role_estimate(policy.get("application"), case_count)
    judge = role_estimate(policy.get("judge"), case_count * repeats)
    total = Decimal(application["estimated_usd"]) + Decimal(
        judge["estimated_usd"]
    )

    return {
        "currency": "USD",
        "pricing_source": source,
        "budget_usd": str(budget),
        "application": application,
        "judge": judge,
        "estimated_total_usd": str(total),
        "within_planned_budget": total <= budget,
        "hard_billing_cap": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    commit = clean_commit()
    require_tracked(POLICY_FILE)
    require_tracked("runtime-config.json")
    require_tracked("ledger/pipeline/spend_plan.py")
    validate_reference(args.image)

    policy_bytes = POLICY_FILE.read_bytes()
    policy = json.loads(policy_bytes)
    runtime = json.loads(
        Path("runtime-config.json").read_text(encoding="utf-8")
    )
    if policy.get("application", {}).get("model") != runtime.get("app_model"):
        raise ValueError(
            "Application pricing model differs from runtime-config.json."
        )

    source, source_hash = load_dataset()
    case_count = sum(
        case["case_id"].endswith("-good") for case in source["cases"]
    )

    for name in ("allowed_drop", "quality_floor"):
        value = getattr(args, name)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be finite and between 0 and 1.")

    if not args.app_version.strip() or not args.reviewed_by.strip():
        raise ValueError("Application version and reviewer cannot be empty.")

    return {
        "source_commit": commit,
        "image_reference": args.image,
        "baseline_run_id": str(args.baseline),
        "source_dataset_sha256": source_hash,
        "spend_policy_sha256": hash_bytes(policy_bytes),
        "runtime_config_sha256": hash_bytes(
            Path("runtime-config.json").read_bytes()
        ),
        "case_count": case_count,
        "execution": {
            "app_version": args.app_version,
            "reviewed_by": args.reviewed_by,
            "repeats": args.repeats,
            "allowed_drop": args.allowed_drop,
            "quality_floor": args.quality_floor,
        },
        "cost_plan": calculate(policy, case_count, args.repeats),
    }


def validate_plan(
    plan: dict[str, Any], current_payload: dict[str, Any], now: datetime
) -> None:
    if plan.get("version") != VERSION:
        raise ValueError("Unsupported spend plan.")

    try:
        created = datetime.fromisoformat(plan["created_at"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Plan timestamp is invalid.") from None
    if created.tzinfo is None:
        raise ValueError("Plan timestamp needs a timezone.")
    if created > now or now - created > PLAN_LIFETIME:
        raise ValueError("Plan is expired or its timestamp is in the future.")

    payload = plan.get("payload")
    if plan.get("payload_sha256") != canonical_hash(payload):
        raise ValueError("Plan content and hash disagree.")
    if payload != current_payload:
        raise ValueError(
            "Source, policy, image, dataset, or execution parameters changed. "
            "Create a new plan."
        )
    if not current_payload["cost_plan"]["within_planned_budget"]:
        raise ValueError("Estimated spend exceeds the configured budget.")


def create_plan(args: argparse.Namespace) -> int:
    payload = build_payload(args)
    plan = {
        "version": VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "payload": payload,
        "payload_sha256": canonical_hash(payload),
    }
    directory = Path("results/day16")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.json"
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    costs = payload["cost_plan"]
    print(f"Application estimate USD: {costs['application']['estimated_usd']}")
    print(f"Judge estimate USD: {costs['judge']['estimated_usd']}")
    print(f"Total estimate USD: {costs['estimated_total_usd']}")
    print(f"Budget USD: {costs['budget_usd']}")
    print(f"Within planned budget: {costs['within_planned_budget']}")
    print(f"Plan: {path}")
    return 0 if costs["within_planned_budget"] else 1


def execute_plan(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    payload = plan["payload"]
    execution = payload["execution"]

    reconstructed = argparse.Namespace(
        image=payload["image_reference"],
        baseline=uuid.UUID(payload["baseline_run_id"]),
        app_version=execution["app_version"],
        reviewed_by=execution["reviewed_by"],
        repeats=execution["repeats"],
        allowed_drop=execution["allowed_drop"],
        quality_floor=execution["quality_floor"],
    )
    if reconstructed.repeats not in range(1, 6):
        raise ValueError("Plan has an unsupported repeat count.")

    current = build_payload(reconstructed)
    validate_plan(plan, current, datetime.now(UTC))

    print("Spend plan accepted. Starting preflight.", flush=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ledger.pipeline.preflight",
            "run",
            "--image",
            reconstructed.image,
            "--baseline",
            str(reconstructed.baseline),
            "--app-version",
            reconstructed.app_version,
            "--reviewed-by",
            reconstructed.reviewed_by,
            "--repeats",
            str(reconstructed.repeats),
            "--allowed-drop",
            str(reconstructed.allowed_drop),
            "--quality-floor",
            str(reconstructed.quality_floor),
        ]
    )
    return completed.returncode if completed.returncode in (0, 1, 2, 3) else 3


class SpendTests(unittest.TestCase):
    def policy(self) -> dict[str, Any]:
        role = {
            "model": "test-model",
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
            "planned_input_tokens_per_call": 100,
            "planned_output_tokens_per_call": 50,
            "planned_attempts_per_call": 1,
        }
        return {
            "version": "ledger-spend-policy-v1",
            "currency": "USD",
            "pricing_source": "Synthetic test prices; not provider rates",
            "budget_usd": "1",
            "application": dict(role),
            "judge": dict(role),
        }

    def test_exact_cost(self) -> None:
        result = calculate(self.policy(), 6, 1)
        self.assertEqual(Decimal(result["estimated_total_usd"]), Decimal("0.0024"))

    def test_repeats_increase_judge_only(self) -> None:
        result = calculate(self.policy(), 6, 3)
        self.assertEqual(result["application"]["logical_calls"], 6)
        self.assertEqual(result["judge"]["logical_calls"], 18)

    def test_attempt_allowance(self) -> None:
        policy = self.policy()
        policy["judge"]["planned_attempts_per_call"] = 3
        result = calculate(policy, 6, 1)
        self.assertEqual(result["judge"]["planned_attempts"], 18)

    def test_unknown_price_rejected(self) -> None:
        policy = self.policy()
        policy["judge"]["input_usd_per_million"] = None
        with self.assertRaises(ValueError):
            calculate(policy, 6, 1)

    def test_over_budget(self) -> None:
        policy = self.policy()
        policy["budget_usd"] = "0.001"
        self.assertFalse(calculate(policy, 6, 1)["within_planned_budget"])

    def test_expired_plan(self) -> None:
        now = datetime.now(UTC)
        payload = {"cost_plan": {"within_planned_budget": True}}
        plan = {
            "version": VERSION,
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "payload": payload,
            "payload_sha256": canonical_hash(payload),
        }
        with self.assertRaises(ValueError):
            validate_plan(plan, payload, now)

    def test_changed_payload(self) -> None:
        now = datetime.now(UTC)
        payload = {"cost_plan": {"within_planned_budget": True}}
        plan = {
            "version": VERSION,
            "created_at": now.isoformat(),
            "payload": payload,
            "payload_sha256": canonical_hash(payload),
        }
        with self.assertRaises(ValueError):
            validate_plan(plan, {"changed": True}, now)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("test")

    planner = commands.add_parser("plan")
    planner.add_argument("--image", required=True)
    planner.add_argument("--baseline", required=True, type=uuid.UUID)
    planner.add_argument("--app-version", required=True)
    planner.add_argument("--reviewed-by", required=True)
    planner.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    planner.add_argument("--allowed-drop", type=float, default=0.05)
    planner.add_argument("--quality-floor", type=float, default=0.75)

    runner = commands.add_parser("run")
    runner.add_argument("--plan", required=True)
    runner.add_argument("--approve-spend", action="store_true")
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SpendTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.command == "run" and not args.approve_spend:
        parser.error("Execution requires explicit --approve-spend.")

    try:
        return create_plan(args) if args.command == "plan" else execute_plan(args)
    except ValueError as exc:
        print(f"Spend gate rejected: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(
            f"Spend gate could not complete ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
