"""Offline tests for the Day 2 strict-rubric judge.

No network: a fake client returns canned completions so the score
normalization, the correctness guard, and the failure path stay pinned.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from judge_groq import CASES, JudgeAssessment, evaluate


def _content(correctness: int, relevance: int, completeness: int) -> str:
    return json.dumps(
        {
            "correctness": correctness,
            "relevance": relevance,
            "completeness": completeness,
            "reason": "test",
            "evidence": "test",
        }
    )


class FakeClient:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **_kwargs):
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        choice = SimpleNamespace(
            message=SimpleNamespace(content=self.content),
            finish_reason=self.finish_reason,
        )
        return SimpleNamespace(
            id="resp_test", model="fake-model", usage=usage, choices=[choice]
        )


class TestEvaluate(unittest.TestCase):
    def test_perfect_dimensions_pass(self):
        record = evaluate(FakeClient(_content(4, 4, 4)), CASES[0])
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["eval_score"], 1.0)
        self.assertTrue(record["passed"])
        self.assertTrue(record["matches_human_label"])

    def test_incorrect_answer_cannot_pass_on_other_dimensions(self):
        # 0.5*0 + 0.25*4 + 0.25*4 = 0.5, and correctness < 3 blocks the pass.
        record = evaluate(FakeClient(_content(0, 4, 4)), CASES[2])
        self.assertEqual(record["eval_score"], 0.5)
        self.assertFalse(record["passed"])
        self.assertTrue(record["matches_human_label"])

    def test_malformed_judge_output_is_recorded_not_raised(self):
        record = evaluate(FakeClient("not json"), CASES[0])
        self.assertEqual(record["status"], "error")
        self.assertIsNone(record["eval_score"])
        self.assertIsNone(record["passed"])
        self.assertEqual(record["error_type"], "ValidationError")

    def test_truncated_response_is_recorded_not_raised(self):
        record = evaluate(FakeClient(_content(4, 4, 4), "length"), CASES[0])
        self.assertEqual(record["status"], "error")
        self.assertIn("Incomplete judge response", record["error"])

    def test_record_carries_usage_and_latency(self):
        record = evaluate(FakeClient(_content(4, 4, 4)), CASES[0])
        self.assertEqual(record["judge_total_tokens"], 15)
        self.assertGreaterEqual(record["judge_latency_ms"], 0)


class TestSchema(unittest.TestCase):
    def test_schema_is_strict_and_forbids_extra_keys(self):
        schema = JudgeAssessment.model_json_schema()
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(
            set(schema["required"]),
            {"correctness", "relevance", "completeness", "reason", "evidence"},
        )


if __name__ == "__main__":
    unittest.main()
