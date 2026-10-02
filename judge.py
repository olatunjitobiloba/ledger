"""LLM-as-judge scoring loop.

Standalone and swappable: this module has no dependency on Postgres, on any
SDK wrapper, or on any project-specific import. It takes two strings and
returns a dict. Anything that can call a Python function can call this.

Usage:
    python judge.py                 # live run, requires OPENAI_API_KEY
    python judge.py --mock          # offline dry run, no key, no network
    python judge.py --repeat 2      # consistency check at temperature=0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

JUDGE_MODEL = "gpt-4o-mini"

JUDGE_SYSTEM_PROMPT = """You are an evaluation judge for AI system outputs.
Score the RESPONSE against the PROMPT on a 0.0-1.0 scale.

Scoring criteria:
- Correctness: Does the response accurately address the prompt?
- Completeness: Does it cover what was asked, nothing missing?
- Coherence: Is it well-structured and logically sound?

Return ONLY valid JSON, no other text, using exactly these keys:
{
  "score": 0.0,
  "reasoning": "one sentence explaining the score",
  "flags": []
}

"flags" must be a JSON array of strings drawn from this vocabulary:
hallucination, incorrect, incomplete, off_topic, incoherent.
Use an empty array when there are no issues. Never add keys, never add prose
outside the JSON object, and never leave a trailing comma.

Score bands:
0.9-1.0: Excellent, no issues
0.7-0.89: Good, minor issues
0.4-0.69: Mediocre, noticeable problems
0.0-0.39: Poor, major issues or wrong
"""

JUDGE_USER_TEMPLATE = """PROMPT:
{prompt}

RESPONSE:
{response}

Evaluate the RESPONSE above."""


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a local .env file into os.environ.

    Exists so an API key can live on disk instead of in a shell command or a
    chat transcript. Existing environment variables win, so a real env var is
    never clobbered by the file.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip("'\"")
        if name and name not in os.environ:
            os.environ[name] = value


def _get_client() -> Any:
    """Build the OpenAI client lazily.

    Lazy so that importing this module never requires the dependency or the
    environment variable to be present. Tests and Postgres wiring can import
    judge without a configured key.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise RuntimeError(
            "The 'openai' package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")

    if not api_key:
        router_key = os.environ.get("OPENROUTER_API_KEY")
        if router_key:
            # OpenRouter speaks the same chat.completions dialect, so the same
            # client works with a different base URL and no other changes.
            api_key = router_key
            base_url = base_url or "https://openrouter.ai/api/v1"

    if not api_key:
        raise RuntimeError(
            "No API key found. Copy .env.example to .env, put your key in it, "
            "and run again. Never paste a key into chat."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _parse_judge_payload(content: str | None) -> dict[str, Any]:
    """Turn raw judge output into a validated result dict.

    A judge that fails gracefully is worth more than one that kills the
    pipeline, so every failure mode lands here and returns a flagged result
    instead of raising.
    """
    if not content:
        return {
            "score": None,
            "reasoning": "judge_parse_error: empty content",
            "flags": ["judge_error"],
        }

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        return {
            "score": None,
            "reasoning": f"judge_parse_error: {exc}",
            "flags": ["judge_error"],
        }

    if not isinstance(result, dict):
        return {
            "score": None,
            "reasoning": "judge_parse_error: top level was not a JSON object",
            "flags": ["judge_error"],
        }

    try:
        score = float(result["score"])
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "score": None,
            "reasoning": f"judge_parse_error: bad score field ({exc})",
            "flags": ["judge_error"],
        }

    if not 0.0 <= score <= 1.0:
        return {
            "score": None,
            "reasoning": f"judge_parse_error: score {score} out of range 0.0-1.0",
            "flags": ["judge_error"],
        }

    flags = result.get("flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]

    return {
        "score": score,
        "reasoning": str(result.get("reasoning", "")),
        "flags": [str(f) for f in flags],
    }


def _api_error_types() -> tuple[type[BaseException], ...]:
    """Base classes for provider-side failures, or empty if openai is absent.

    An empty tuple is a valid except clause that matches nothing, so this
    stays correct whether or not the package is installed.
    """
    try:
        from openai import OpenAIError
    except ImportError:
        return ()
    return (OpenAIError,)


def judge_output(prompt: str, response: str) -> dict[str, Any]:
    """Score a prompt/response pair with GPT-4o-mini as the judge.

    Returns a dict with keys: score (float or None), reasoning (str), flags
    (list[str]). Never raises on malformed judge output; sets score to None
    and adds the 'judge_error' flag instead.
    """
    client = _get_client()
    completion = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": JUDGE_USER_TEMPLATE.format(
                    prompt=prompt, response=response
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    return _parse_judge_payload(completion.choices[0].message.content)


def judge_output_mock(prompt: str, response: str) -> dict[str, Any]:
    """Offline stand-in for judge_output, for exercising the harness.

    This scores nothing. It exists so the CLI wiring, the parse path, the
    graceful-failure path, and the reporting can be verified without a key
    or a network call. Never use it to produce real evaluation numbers.
    """
    del prompt  # a real judge reads the prompt; this one only reads keywords
    lowered = response.lower()

    if "weather" in lowered:
        return {
            "score": 0.1,
            "reasoning": "mock: response contradicts the source material.",
            "flags": ["hallucination"],
        }
    if "set of rules" in lowered:
        return {
            "score": 0.95,
            "reasoning": "mock: accurate and correctly scoped.",
            "flags": [],
        }
    if len(response.split()) < 4:
        return {
            "score": 0.45,
            "reasoning": "mock: too thin to be complete.",
            "flags": ["incomplete"],
        }
    return {
        "score": 0.9,
        "reasoning": "mock: plausible answer.",
        "flags": [],
    }


TEST_CASES: list[dict[str, Any]] = [
    {
        "prompt": "What is the capital of France?",
        "response": "The capital of France is Paris.",
        "expect": "high",
    },
    {
        "prompt": "Summarize: The stock market fell 2% today due to inflation fears.",
        "response": "Stocks dropped because of weather conditions.",
        "expect": "low",
    },
    {
        "prompt": "List 3 benefits of exercise.",
        "response": "Exercise improves cardiovascular health, mood, and sleep quality.",
        "expect": "high",
    },
    {
        "prompt": "What's 15% of 200?",
        "response": "15% of 200 is 30.",
        "expect": "high",
    },
    {
        "prompt": "Explain what an API is in one sentence.",
        "response": "An API is a set of rules that lets different software talk to each other.",
        "expect": "high",
    },
]


def run_cases(judge_fn: Any, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run each case once through judge_fn and collect results."""
    results = []
    for index, case in enumerate(cases, start=1):
        outcome = judge_fn(case["prompt"], case["response"])
        results.append({"index": index, "case": case, "outcome": outcome})
        print(f"Test {index}: score={outcome['score']}, flags={outcome['flags']}")
        print(f"  reasoning: {outcome['reasoning']}")
    return results


def check_discrimination(results: list[dict[str, Any]]) -> bool:
    """Verify the judge separates the deliberately bad answer from the good ones.

    This is the check that matters. A judge that rates everything 0.9+ is not
    measuring anything, and you cannot tell the difference without a known-bad
    case in the set.
    """
    scored = [r for r in results if r["outcome"]["score"] is not None]
    if not scored:
        print("\nFAIL: every case errored, nothing to compare.")
        return False

    lows = [r["outcome"]["score"] for r in scored if r["case"]["expect"] == "low"]
    highs = [r["outcome"]["score"] for r in scored if r["case"]["expect"] == "high"]
    errored = len(results) - len(scored)

    print("\n--- discrimination check ---")
    print(f"judge errors: {errored}/{len(results)}")
    if lows:
        print(f"expected-low  scores: {lows}")
    if highs:
        print(f"expected-high scores: {highs}")

    if not lows or not highs:
        print("FAIL: need at least one low and one high case to compare.")
        return False

    mean_high = sum(highs) / len(highs)
    mean_low = sum(lows) / len(lows)
    print(f"mean high={mean_high:.2f}  mean low={mean_low:.2f}  gap={mean_high - mean_low:.2f}")

    if mean_low >= 0.5:
        print("FAIL: the known-bad answer was not scored low. Rewrite the criteria before Day 3.")
        return False
    if mean_high <= mean_low:
        print("FAIL: no separation between good and bad.")
        return False

    flagged = [f for r in scored if r["case"]["expect"] == "low" for f in r["outcome"]["flags"]]
    print(f"flags on bad answer(s): {flagged or 'none'}")
    print("PASS: judge discriminates.")
    return True


def check_consistency(judge_fn: Any, cases: list[dict[str, Any]], repeat: int) -> bool:
    """Run the same cases `repeat` times and report score drift."""
    print(f"\n--- consistency check ({repeat} passes) ---")
    stable = True
    for index, case in enumerate(cases, start=1):
        seen = [judge_fn(case["prompt"], case["response"])["score"] for _ in range(repeat)]
        drift = max(seen) - min(seen) if None not in seen else None
        verdict = "stable" if drift == 0 else f"drift={drift:.2f}"
        if drift != 0:
            stable = False
        print(f"Test {index}: scores={seen} -> {verdict}")
    return stable


def main(argv: list[str] | None = None) -> int:
    global JUDGE_MODEL
    parser = argparse.ArgumentParser(description="Judge a set of prompt/response pairs.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Offline dry run. Verifies wiring only; scores are not real.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run the set N times to check score stability at temperature=0.",
    )
    parser.add_argument(
        "--model",
        default=JUDGE_MODEL,
        help=f"Judge model id (default: {JUDGE_MODEL}).",
    )
    args = parser.parse_args(argv)

    JUDGE_MODEL = args.model

    load_dotenv()

    judge_fn = judge_output_mock if args.mock else judge_output
    if args.mock:
        print("MOCK MODE: wiring and parsing only. Scores below are not real evals.\n")
    else:
        print(f"Live mode: model={JUDGE_MODEL}, temperature=0\n")

    try:
        results = run_cases(judge_fn, TEST_CASES)
    except RuntimeError as exc:
        # Missing dependency or missing key. That is a setup problem, not a
        # bug, so report it as one line instead of a traceback.
        print(f"\nSetup problem: {exc}", file=sys.stderr)
        return 2
    except _api_error_types() as exc:
        # Auth, rate limit, or transport failure. Report the cause and stop;
        # there is nothing meaningful to score.
        print(f"\nJudge API call failed: {exc}", file=sys.stderr)
        return 3

    ok = check_discrimination(results)

    if args.repeat > 1:
        ok = check_consistency(judge_fn, TEST_CASES, args.repeat) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())