"""Check whether a key is accepted, before running the judge.

    python check_key.py            # checks whichever key is in .env
    python check_key.py --openai   # force one provider

Prints the HTTP status and never prints the key. Exits 0 if the key works,
1 if it does not. Costs one request, or zero if the key's shape is already wrong.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from judge import _key_provider_warning, _mask, load_dotenv

ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}
PROBE_MODEL = {
    "openrouter": "openai/gpt-4o-mini",
    "openai": "gpt-4o-mini",
}


def check(provider: str, key: str) -> int:
    warning = _key_provider_warning(key, provider)
    if warning:
        print(f"FAIL  {warning}")
        print("      Correct the variable name in .env, or get a key from the right provider.")
        return 1

    body = json.dumps(
        {
            "model": PROBE_MODEL[provider],
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
    ).encode()

    request = urllib.request.Request(
        ENDPOINTS[provider],
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )

    try:
        response = urllib.request.urlopen(request, timeout=30)
        print(f"OK    {provider} accepted key {_mask(key)} (HTTP {response.status})")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"FAIL  {provider} rejected key {_mask(key)} (HTTP {exc.code})")
        detail = exc.read().decode(errors="replace")[:200].strip()
        print(f"      {detail}")
        if exc.code in (401, 403):
            print("      The key is invalid or revoked. Generate a new one.")
        elif exc.code == 402:
            print("      The key is valid but the account has no credit.")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary, report anything
        print(f"FAIL  {provider} unreachable: {type(exc).__name__}: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a key works before judging.")
    parser.add_argument("--openai", action="store_true", help="Check as an OpenAI key.")
    parser.add_argument("--openrouter", action="store_true", help="Check as an OpenRouter key.")
    args = parser.parse_args(argv)

    load_dotenv()

    openai_key = os.environ.get("OPENAI_API_KEY")
    router_key = os.environ.get("OPENROUTER_API_KEY")

    if args.openai or (not args.openrouter and not router_key and openai_key):
        provider, key = "openai", openai_key
    elif args.openrouter or router_key:
        provider, key = "openrouter", router_key
    else:
        print("No key found in .env or the environment.")
        return 1

    if not key:
        print(f"No {provider.upper()}_API_KEY set. Add it to .env.")
        return 1

    return check(provider, key)


if __name__ == "__main__":
    sys.exit(main())