# ledger

LLM evaluation harness. Day 2: the judge prompt and scoring loop.

## What this is

`judge.py` scores a `(prompt, response)` pair with GPT-4o-mini as the judge and
returns a plain dict:

```python
{"score": 0.85, "reasoning": "one sentence", "flags": ["incomplete"]}
```

It is a standalone module on purpose. No Postgres, no SDK wrapper, no project
imports. Call it from anywhere; swap it out later without touching callers.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then put your real key in .env
```

`.env` is gitignored. Do not paste keys into chat, issues, or commits.

## Run it

```bash
python judge.py              # live, needs OPENAI_API_KEY in the environment
python judge.py --mock       # offline dry run, no key, no network
python judge.py --repeat 3   # score-drift check at temperature=0
python -m unittest test_judge  # 16 tests, no network
```

Exit codes: `0` judge discriminated, `1` discrimination check failed, `2` setup
problem (missing key or missing dependency).

## Reading the output

Every run ends with a discrimination check, and that check is the point:

```
--- discrimination check ---
mean high=0.91  mean low=0.10  gap=0.81
flags on bad answer(s): ['hallucination']
PASS: judge discriminates.
```

Test case 2 is deliberately wrong. If the judge does not score it low, the run
exits non-zero and the scoring criteria need rewriting. A judge that returns
0.9+ for everything is not measuring anything.

## Design notes

**`response_format={"type": "json_object"}`** removes the "parse free text"
problem. The judge returns JSON, so it lands in Postgres as columns instead of
requiring regex scraping.

**`temperature=0`** minimizes variance but does not guarantee byte-identical
output, because the provider backend has its own nondeterminism. `--repeat`
tells you the actual drift on your account instead of assuming it.

**Graceful failure beats crashing.** `_parse_judge_payload` converts every
malformed judge output into `score: None` plus a `judge_error` flag. A broken
judge should cost you one data point, not the pipeline.

**Lazy client.** `_get_client()` builds the OpenAI client on first call, so
importing `judge` never requires the package or the env var. Tests and Day 4's
database wiring import this module without credentials.

**`--mock` scores nothing.** It exists to verify wiring and the parse path with
no key and no network. Never treat its numbers as evaluations.

## Layout

| File | Purpose |
| --- | --- |
| `judge.py` | Judge prompt, `judge_output()`, parse path, test harness |
| `test_judge.py` | Unit tests for the parse and discrimination logic |
| `requirements.txt` | `openai` |
| `.env.example` | Key template. Copy to `.env` |

## Not here yet

Postgres persistence is Day 4. `flags` is deliberately categorical so it can
become a chart dimension later.