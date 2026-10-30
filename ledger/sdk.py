"""Tiny non-blocking Python SDK for Ledger ingestion."""

from __future__ import annotations

import asyncio
import copy
import re
import uuid
from typing import Any


class Ledger:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        timeout: float = 0.25,
        *,
        capture_prompt: bool = False,
        redact_patterns: list[str] | None = None,
    ):
        self.endpoint, self.api_key, self.timeout = (
            endpoint.rstrip("/"),
            api_key,
            timeout,
        )
        self.capture_prompt, self.redact_patterns = (
            capture_prompt,
            redact_patterns or [],
        )

    async def ingest(self, traces: list[dict[str, Any]]) -> None:
        """Schedule delivery and return immediately; never blocks the host LLM call."""
        sanitized = copy.deepcopy(traces)
        for trace in sanitized:
            trace_model = trace.get("model")
            for span in trace.get("spans", []):
                # Ensure model is always populated on llm_call spans before ingest
                if span.get("span_type", span.get("type", "llm_call")) == "llm_call":
                    if not span.get("model"):
                        span["model"] = trace_model or "gpt-4o-mini"
                if not self.capture_prompt:
                    span.pop("prompt", None)
                    span.pop("response", None)
                else:
                    for field in ("prompt", "response"):
                        if field in span and span[field] is not None:
                            for pattern in self.redact_patterns:
                                try:
                                    span[field] = re.sub(
                                        pattern, "[REDACTED]", str(span[field])
                                    )
                                except re.error:
                                    # SDK telemetry must never affect the host request.
                                    continue
        asyncio.create_task(self._send(sanitized))

    async def _send(self, traces: list[dict[str, Any]]) -> None:
        try:
            import urllib.request

            payload = __import__("json").dumps({"traces": traces}).encode()
            request = urllib.request.Request(
                self.endpoint + "/v1/ingest",
                data=payload,
                method="POST",
                headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            )
            await asyncio.wait_for(
                asyncio.to_thread(
                    urllib.request.urlopen, request, timeout=self.timeout
                ),
                self.timeout,
            )
        except Exception:
            pass  # Observability must never break or delay the host application.

    @staticmethod
    def span(**values: Any) -> dict[str, Any]:
        values.setdefault("span_id", str(uuid.uuid4()))
        values.setdefault("span_type", "llm_call")
        if values.get("span_type") == "llm_call" and not values.get("model"):
            values["model"] = "gpt-4o-mini"
        return values
