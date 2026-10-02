"""Unit tests for the judge parse path. No network, no API key, stdlib only.

    python -m unittest test_judge -v

These cover the part that must not break: a judge returning garbage must
degrade into a flagged result, never an exception that kills the pipeline.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from judge import (
    _parse_judge_payload,
    check_discrimination,
    judge_output_mock,
    run_cases,
    TEST_CASES,
)


def quiet(fn, *args):
    """Run a harness function with its reporting output suppressed."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


class TestParseJudgePayload(unittest.TestCase):
    def test_valid_payload_parses(self):
        result = _parse_judge_payload(
            '{"score": 0.85, "reasoning": "solid", "flags": ["incomplete"]}'
        )
        self.assertEqual(result["score"], 0.85)
        self.assertEqual(result["reasoning"], "solid")
        self.assertEqual(result["flags"], ["incomplete"])

    def test_score_is_coerced_to_float(self):
        result = _parse_judge_payload('{"score": "0.5", "reasoning": "ok", "flags": []}')
        self.assertIsInstance(result["score"], float)
        self.assertEqual(result["score"], 0.5)

    def test_missing_reasoning_and_flags_default(self):
        result = _parse_judge_payload('{"score": 0.9}')
        self.assertEqual(result["score"], 0.9)
        self.assertEqual(result["reasoning"], "")
        self.assertEqual(result["flags"], [])

    def test_malformed_json_fails_gracefully(self):
        result = _parse_judge_payload('{"score": 0.9, oops')
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])

    def test_empty_content_fails_gracefully(self):
        for payload in ("", None):
            result = _parse_judge_payload(payload)
            self.assertIsNone(result["score"])
            self.assertIn("judge_error", result["flags"])

    def test_non_dict_top_level_fails_gracefully(self):
        result = _parse_judge_payload("[0.9, 1.0]")
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])

    def test_missing_score_fails_gracefully(self):
        result = _parse_judge_payload('{"reasoning": "forgot the score"}')
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])

    def test_null_score_fails_gracefully(self):
        result = _parse_judge_payload('{"score": null}')
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])

    def test_out_of_range_score_fails_gracefully(self):
        result = _parse_judge_payload('{"score": 1.4}')
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])

    def test_prose_wrapped_json_still_parses(self):
        # The model may ignore "return ONLY JSON". Recover rather than crash.
        result = _parse_judge_payload(
            'Sure! Here is my evaluation:\n{"score": 0.7, "reasoning": "ok", "flags": []}\nHope that helps!'
        )
        self.assertIsNone(result["score"])
        self.assertIn("judge_error", result["flags"])


class TestFlagCoercion(unittest.TestCase):
    def test_string_flags_become_list(self):
        result = _parse_judge_payload(
            '{"score": 0.4, "reasoning": "x", "flags": "hallucination"}'
        )
        self.assertEqual(result["flags"], ["hallucination"])

    def test_flag_entries_are_stringified(self):
        result = _parse_judge_payload(
            '{"score": 0.4, "reasoning": "x", "flags": [1, null]}'
        )
        self.assertEqual(result["flags"], ["1", "None"])


class TestHarness(unittest.TestCase):
    def test_mock_scores_every_case_without_erroring(self):
        results = quiet(run_cases, judge_output_mock, TEST_CASES)
        self.assertEqual(len(results), len(TEST_CASES))
        for entry in results:
            self.assertIsNotNone(entry["outcome"]["score"])
            self.assertNotIn("judge_error", entry["outcome"]["flags"])

    def test_discrimination_check_passes_on_discriminating_judge(self):
        results = quiet(run_cases, judge_output_mock, TEST_CASES)
        self.assertTrue(quiet(check_discrimination, results))

    def test_discrimination_check_fails_when_judge_is_flat(self):
        def flat_judge(prompt, response):
            return {"score": 0.95, "reasoning": "everything is fine", "flags": []}

        results = quiet(run_cases, flat_judge, TEST_CASES)
        self.assertFalse(quiet(check_discrimination, results))

    def test_discrimination_check_fails_when_all_cases_error(self):
        def broken_judge(prompt, response):
            return {"score": None, "reasoning": "boom", "flags": ["judge_error"]}

        results = quiet(run_cases, broken_judge, TEST_CASES)
        self.assertFalse(quiet(check_discrimination, results))


if __name__ == "__main__":
    unittest.main(verbosity=2)