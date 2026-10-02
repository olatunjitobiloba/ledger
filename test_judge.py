"""Unit tests for the judge parse path. No network, no API key, stdlib only.

    python -m unittest test_judge -v

These cover the part that must not break: a judge returning garbage must
degrade into a flagged result, never an exception that kills the pipeline.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from judge import (
    _key_provider_warning,
    _mask,
    _parse_judge_payload,
    check_discrimination,
    judge_output_mock,
    load_dotenv,
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


class TestKeyDiagnostics(unittest.TestCase):
    """A key from the wrong provider costs a confusing 401, so catch it early."""

    def test_mask_never_reveals_the_whole_secret(self):
        secret = "sk-or-v1-abcdefghijklmnop"
        masked = _mask(secret)
        self.assertNotIn("efghijklmnop", masked)
        self.assertTrue(masked.startswith("sk-or-"))
        self.assertTrue(masked.endswith("op"))

    def test_mask_hides_short_values_entirely(self):
        self.assertEqual(_mask("short"), "***")

    def test_openai_style_key_flagged_when_used_as_openrouter(self):
        warning = _key_provider_warning("sk-abc123def456ghi789", "openrouter")
        self.assertIsNotNone(warning)
        self.assertIn("sk-or-v1-", warning)

    def test_openrouter_style_key_flagged_when_used_as_openai(self):
        warning = _key_provider_warning("sk-or-v1-abcdef", "openai")
        self.assertIsNotNone(warning)
        self.assertIn("OPENROUTER_API_KEY", warning)

    def test_matching_provider_produces_no_warning(self):
        self.assertIsNone(_key_provider_warning("sk-or-v1-abcdef", "openrouter"))
        self.assertIsNone(_key_provider_warning("sk-abc123def456", "openai"))


class TestLoadDotenv(unittest.TestCase):
    """The .env path is how a key avoids ever appearing in chat, so it matters."""

    def setUp(self):
        self.saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def _write(self, body):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".env", delete=False, encoding="utf-8"
        )
        handle.write(body)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_reads_pairs_and_skips_comments_and_blanks(self):
        path = self._write(
            "# a comment\n\nJUDGE_TEST_KEY=abc123\nJUDGE_TEST_OTHER = spaced \n"
        )
        load_dotenv(path)
        self.assertEqual(os.environ["JUDGE_TEST_KEY"], "abc123")
        self.assertEqual(os.environ["JUDGE_TEST_OTHER"], "spaced")

    def test_strips_surrounding_quotes(self):
        path = self._write('JUDGE_TEST_Q="quoted-value"\n')
        load_dotenv(path)
        self.assertEqual(os.environ["JUDGE_TEST_Q"], "quoted-value")

    def test_preserves_equals_inside_value(self):
        path = self._write("JUDGE_TEST_B64=abc=def==\n")
        load_dotenv(path)
        self.assertEqual(os.environ["JUDGE_TEST_B64"], "abc=def==")

    def test_existing_env_var_wins_over_file(self):
        os.environ["JUDGE_TEST_KEY"] = "from-shell"
        path = self._write("JUDGE_TEST_KEY=from-file\n")
        load_dotenv(path)
        self.assertEqual(os.environ["JUDGE_TEST_KEY"], "from-shell")

    def test_missing_file_is_not_an_error(self):
        load_dotenv("definitely-not-a-real-file-9182.env")

    def test_bare_openrouter_key_is_inferred(self):
        path = self._write("sk-or-v1-abcdef0123456789\n")
        load_dotenv(path)
        self.assertEqual(os.environ["OPENROUTER_API_KEY"], "sk-or-v1-abcdef0123456789")

    def test_bare_openai_key_is_inferred_with_a_warning(self):
        path = self._write("sk-abcdef0123456789\n")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            load_dotenv(path)
        self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-abcdef0123456789")
        self.assertIn("no variable name", err.getvalue())

    def test_bare_key_does_not_clobber_explicit_variable(self):
        os.environ["OPENROUTER_API_KEY"] = "already-set"
        path = self._write("sk-or-v1-abcdef0123456789\n")
        load_dotenv(path)
        self.assertEqual(os.environ["OPENROUTER_API_KEY"], "already-set")

    def test_unrecognised_bare_line_is_ignored(self):
        path = self._write("just some prose here\n")
        with contextlib.redirect_stderr(io.StringIO()):
            load_dotenv(path)
        self.assertNotIn("just some prose here", os.environ.values())


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