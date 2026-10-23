"""Estimate Groq judge cost from provider-reported token usage.

    python -m ledger.pipeline.costs test
    python -m ledger.pipeline.costs backfill

Estimates only. Actual billing, retries that were never returned, and historical
price changes are out of scope. Unknown is stored as NULL, never zero.
"""

from __future__ import annotations

import argparse
import unittest
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from ledger.pipeline.evaluation_runs import connect

PRICE_VERSION = "groq-published-2026-10-22-v1"
PRICE_SOURCE = "https://console.groq.com/docs/models"
MILLION = Decimal(1000000)

# Observation date is not a claim about historical effective dates.
PRICES: dict[str, dict[str, str]] = {
    "openai/gpt-oss-20b": {
        "input_per_million": "0.075",
        "output_per_million": "0.30",
    },
    "openai/gpt-oss-120b": {
        "input_per_million": "0.15",
        "output_per_million": "0.60",
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_eval_costs (
    run_id UUID NOT NULL,
    case_id TEXT NOT NULL,
    trial INTEGER NOT NULL,
    pricing_version TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'groq',
    usage_role TEXT NOT NULL DEFAULT 'judge',
    currency TEXT NOT NULL DEFAULT 'USD',
    returned_model TEXT,
    input_tokens BIGINT,
    output_tokens BIGINT,
    usage_source TEXT NOT NULL,
    cost_status TEXT NOT NULL CHECK (cost_status IN ('estimated', 'unknown')),
    unknown_reason TEXT,
    estimated_cost_usd NUMERIC(24, 12),
    actual_cost_usd NUMERIC(24, 12),
    actual_cost_source TEXT,
    pricing_snapshot JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, case_id, trial, pricing_version),
    FOREIGN KEY (run_id, case_id, trial)
        REFERENCES ledger_eval_results(run_id, case_id, trial)
        ON DELETE CASCADE,
    CHECK (
        (cost_status = 'estimated'
            AND estimated_cost_usd IS NOT NULL
            AND estimated_cost_usd >= 0
            AND unknown_reason IS NULL)
        OR
        (cost_status = 'unknown'
            AND estimated_cost_usd IS NULL
            AND unknown_reason IS NOT NULL)
    ),
    CHECK (
        (actual_cost_usd IS NULL AND actual_cost_source IS NULL)
        OR
        (actual_cost_usd IS NOT NULL
            AND actual_cost_usd >= 0
            AND actual_cost_source IS NOT NULL)
    )
);
"""


def valid_tokens(value: object) -> bool:
    # Reject booleans, floats, negative numbers, and missing values.
    return type(value) is int and 0 <= value <= 9223372036854775807


def calculate_cost(result: dict[str, Any]) -> dict[str, Any]:
    model = result.get("returned_model")
    if not isinstance(model, str) or not model.strip():
        model = None

    input_tokens = result.get("judge_prompt_tokens")
    output_tokens = result.get("judge_completion_tokens")
    rates = PRICES.get(model) if model else None

    snapshot: dict[str, Any] = {
        "pricing_version": PRICE_VERSION,
        "source": PRICE_SOURCE,
        "observed_on": "2026-10-22",
        "rates": rates,
        "currency": "USD",
        "basis": "standard published token rates",
    }

    cost: dict[str, Any] = {
        "returned_model": model,
        "input_tokens": input_tokens if valid_tokens(input_tokens) else None,
        "output_tokens": output_tokens if valid_tokens(output_tokens) else None,
        "usage_source": "groq_response_usage",
        "cost_status": "unknown",
        "unknown_reason": None,
        "estimated_cost_usd": None,
        "pricing_snapshot": snapshot,
    }

    if model is None:
        cost["unknown_reason"] = "missing_returned_model"
    elif rates is None:
        cost["unknown_reason"] = "unmapped_model_price"
    elif not valid_tokens(input_tokens) or not valid_tokens(output_tokens):
        cost["unknown_reason"] = "missing_or_invalid_token_usage"
    else:
        assert isinstance(input_tokens, int)
        assert isinstance(output_tokens, int)
        cost["estimated_cost_usd"] = (
            Decimal(input_tokens) * Decimal(rates["input_per_million"])
            + Decimal(output_tokens) * Decimal(rates["output_per_million"])
        ) / MILLION
        cost["cost_status"] = "estimated"

    return cost


def backfill() -> None:
    inserted = 0
    with connect() as connection, connection.transaction():
        connection.execute(SCHEMA)

    with connect() as connection, connection.transaction(), connection.cursor(
        name="cost_backfill"
    ) as cursor:
        # Stream existing results rather than loading the entire table.
        cursor.execute(
            """
            SELECT r.run_id, r.case_id, r.trial, r.result
            FROM ledger_eval_results r
            WHERE NOT EXISTS (
                SELECT 1 FROM ledger_eval_costs c
                WHERE c.run_id = r.run_id
                  AND c.case_id = r.case_id
                  AND c.trial = r.trial
                  AND c.pricing_version = %s
            )
            """,
            (PRICE_VERSION,),
        )

        for run_id, case_id, trial, result in cursor:
            cost = calculate_cost(result)
            written = connection.execute(
                """
                INSERT INTO ledger_eval_costs (
                    run_id, case_id, trial, pricing_version,
                    returned_model, input_tokens, output_tokens,
                    usage_source, cost_status, unknown_reason,
                    estimated_cost_usd, pricing_snapshot
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    run_id, case_id, trial, pricing_version
                ) DO NOTHING
                """,
                (
                    run_id,
                    case_id,
                    trial,
                    PRICE_VERSION,
                    cost["returned_model"],
                    cost["input_tokens"],
                    cost["output_tokens"],
                    cost["usage_source"],
                    cost["cost_status"],
                    cost["unknown_reason"],
                    cost["estimated_cost_usd"],
                    Jsonb(cost["pricing_snapshot"]),
                ),
            )
            inserted += written.rowcount

    print(f"Saved {inserted} cost records under {PRICE_VERSION}.")
    print("Actual costs remain NULL; no billing data was supplied.")


class CostTests(unittest.TestCase):
    def result(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "returned_model": "openai/gpt-oss-20b",
            "judge_prompt_tokens": 1000,
            "judge_completion_tokens": 500,
        }
        data.update(overrides)
        return data

    def test_known_cost(self) -> None:
        cost = calculate_cost(self.result())
        self.assertEqual(cost["cost_status"], "estimated")
        self.assertEqual(cost["estimated_cost_usd"], Decimal("0.000225"))

    def test_zero_is_valid(self) -> None:
        cost = calculate_cost(
            self.result(judge_prompt_tokens=0, judge_completion_tokens=0)
        )
        self.assertEqual(cost["estimated_cost_usd"], Decimal(0))

    def test_missing_usage_is_not_zero(self) -> None:
        cost = calculate_cost(self.result(judge_prompt_tokens=None))
        self.assertIsNone(cost["estimated_cost_usd"])
        self.assertEqual(cost["cost_status"], "unknown")

    def test_unknown_model(self) -> None:
        cost = calculate_cost(self.result(returned_model="unmapped-model"))
        self.assertEqual(cost["unknown_reason"], "unmapped_model_price")

    def test_invalid_counts(self) -> None:
        for value in (-1, True, 1.5, "100"):
            with self.subTest(value=value):
                cost = calculate_cost(self.result(judge_completion_tokens=value))
                self.assertEqual(cost["cost_status"], "unknown")

    def test_error_response_can_still_have_usage(self) -> None:
        cost = calculate_cost(self.result(status="error"))
        self.assertEqual(cost["cost_status"], "estimated")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["test", "backfill"])
    args = parser.parse_args()

    if args.command == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CostTests)
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
        if not outcome.wasSuccessful():
            raise SystemExit(1)
    else:
        backfill()


if __name__ == "__main__":
    main()
