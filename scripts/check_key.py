"""Check whether a key is accepted, before running the judge.

    python scripts/check_key.py            # checks whichever key is in .env
    python scripts/check_key.py --groq     # force one provider

Prints the HTTP status and never prints the key. Exits 0 if the key works,
1 if it does not. Costs one request, or zero if the key's shape is already wrong.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ledger.judges import _key_provider_warning, _mask, load_dotenv

BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
}
PROBE_MODEL = {
    "openrouter": "openai/gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "groq": "openai/gpt-oss-120b",
}


def check(provider: str, key: str) -> int:
    warning = _key_provider_warning(key, provider)
    if warning:
        print(f"FAIL  {warning}")
        print("      Correct the variable name in .env, or get a key from the right provider.")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("FAIL  the 'openai' package is not installed.")
        print("      Run: pip install -r requirements.txt")
        return 1

    # Use the SDK rather than urllib: Groq's edge rejects non-browser clients
    # with a Cloudflare 403 before the request ever reaches the API.
    client = OpenAI(api_key=key, base_url=BASE_URLS[provider])

    try:
        client.chat.completions.create(
            model=PROBE_MODEL[provider],
            messages=[{"role": "user", "content": "Reply with the single word OK."}],
            max_tokens=32,
        )
        print(f"OK    {provider} accepted key {_mask(key)}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report anything
        status = getattr(exc, "status_code", None)
        text = str(exc)
        suffix = f" (HTTP {status})" if status else ""
        print(f"FAIL  {provider} rejected key {_mask(key)}{suffix}")
        print(f"      {text[:200].strip()}")
        if status in (401, 403):
            print("      The key is invalid, revoked, or blocked for this model.")
        elif status == 402 or "insufficient_quota" in text or "no credit" in text.lower():
            # OpenRouter reports a zero balance as 402; OpenAI uses 429 with an
            # "insufficient_quota" error type. Same cause, different status.
            print("      The key is valid but the account has no credit.")
        elif status == 429:
            print("      Rate limited. Retry shortly, or check your account quota.")
        elif status == 404:
            print("      The key works, but this account cannot use the probe model.")
        else:
            print("      Provider unreachable or request rejected. Retry shortly.")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a key works before judging.")
    parser.add_argument("--openai", action="store_true", help="Check as an OpenAI key.")
    parser.add_argument("--openrouter", action="store_true", help="Check as an OpenRouter key.")
    parser.add_argument("--groq", action="store_true", help="Check as a Groq key.")
    args = parser.parse_args(argv)

    load_dotenv()

    keys = {
        "openai": os.environ.get("OPENAI_API_KEY"),
        "openrouter": os.environ.get("OPENROUTER_API_KEY"),
        "groq": os.environ.get("GROQ_API_KEY"),
    }

    forced = [name for name in keys if getattr(args, name, False)]
    if forced:
        provider = forced[0]
    else:
        provider = next((name for name, value in keys.items() if value), "")

    if not provider:
        print("No key found in .env or the environment.")
        return 1

    key = keys[provider]
    if not key:
        print(f"No {provider.upper()}_API_KEY set. Add it to .env.")
        return 1

    return check(provider, key)


if __name__ == "__main__":
    sys.exit(main())
