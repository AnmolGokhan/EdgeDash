"""Single door to any language model — steering rule 15.

Public API:
    complete_json(prompt, schema, *, max_retries=1) -> dict

No other module may import an LLM SDK. All provider logic lives here.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Raised when the LLM cannot produce a valid response after all retries."""


# ---------------------------------------------------------------------------
# Rate limiter (shared across all calls in a process)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Enforces a minimum gap between calls and a rolling per-minute cap.

    Both limits are respected simultaneously:
    - min_interval_s  : minimum seconds between any two calls (default 1.0)
    - max_per_minute  : rolling 60-second window cap (from config)
    """

    def __init__(self, min_interval_s: float = 1.0, max_per_minute: int = 15) -> None:
        self._min_interval = min_interval_s
        self._max_per_minute = max_per_minute
        self._last_call: float = 0.0
        self._window: deque[float] = deque()  # timestamps of recent calls

    def wait(self) -> None:
        now = time.monotonic()

        # Enforce minimum interval between calls.
        gap = now - self._last_call
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
            now = time.monotonic()

        # Enforce rolling per-minute cap.
        cutoff = now - 60.0
        while self._window and self._window[0] < cutoff:
            self._window.popleft()

        if len(self._window) >= self._max_per_minute:
            oldest = self._window[0]
            sleep_for = (oldest + 60.0) - now + 0.05  # small buffer
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()

        self._window.append(now)
        self._last_call = now


# Module-level limiter; reconfigured by _get_limiter() on first use.
_limiter: _RateLimiter | None = None


def _get_limiter(max_per_minute: int) -> _RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _RateLimiter(min_interval_s=1.0, max_per_minute=max_per_minute)
    return _limiter


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, model: str) -> str:
    """Send prompt to Gemini and return raw response text."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LLMError(
            "GEMINI_API_KEY is not set. "
            "Add it to edgedash/.env as: GEMINI_API_KEY=your_key_here"
        )

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise LLMError(
            "google-genai is required for the Gemini provider: "
            "pip install google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return response.text


def _call_ollama(prompt: str, model: str) -> str:
    """Send prompt to a local Ollama instance and return raw response text."""
    try:
        import requests as _requests
    except ImportError as exc:
        raise LLMError("requests is required for the Ollama provider") from exc

    url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    try:
        resp = _requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc


# Registry: provider_name -> callable(prompt, model) -> raw_text
_PROVIDERS: dict[str, Any] = {
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}


def _call_provider(provider: str, model: str, prompt: str) -> str:
    """Dispatch to the correct provider, with 429/quota backoff."""
    if provider not in _PROVIDERS:
        raise LLMError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported: {sorted(_PROVIDERS)}"
        )
    fn = _PROVIDERS[provider]

    backoff = 1.0
    for attempt in range(3):
        try:
            return fn(prompt, model)
        except Exception as exc:
            msg = str(exc).lower()
            is_quota = "429" in msg or "quota" in msg or "rate" in msg
            if is_quota and attempt < 2:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise LLMError(f"Provider '{provider}' error: {exc}") from exc

    raise LLMError(f"Provider '{provider}' exhausted retries")


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip markdown fences and surrounding prose; return the JSON substring."""
    # Try to pull content from a code fence first.
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()

    # Find the outermost JSON object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

    return text.strip()


def _validate(data: Any, schema: dict) -> None:
    """Minimal schema validation: check required keys and basic types.

    Raises ValueError with a clear message on the first failure found.
    We intentionally avoid jsonschema to stay stdlib-first; this covers
    the structural checks our scorer needs (required fields, no extras).
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")

    required = schema.get("required", list(schema.get("properties", {}).keys()))
    properties = schema.get("properties", {})

    for key in required:
        if key not in data:
            raise ValueError(f"Missing required key: '{key}'")

    for key, spec in properties.items():
        if key not in data:
            continue
        value = data[key]
        expected_type = spec.get("type")
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]

        if value is None:
            if "null" in allowed_types:
                continue
            raise ValueError(f"Key '{key}' cannot be null")

        if "string" in allowed_types and isinstance(value, str):
            continue
        if "integer" in allowed_types and isinstance(value, int) and not isinstance(value, bool):
            continue
        if "number" in allowed_types and isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        if "boolean" in allowed_types and isinstance(value, bool):
            continue
        if "array" in allowed_types and isinstance(value, list):
            continue
        if "object" in allowed_types and isinstance(value, dict):
            continue

        allowed_label = ", ".join(str(item) for item in allowed_types)
        raise ValueError(
            f"Key '{key}' must be one of: {allowed_label}, got {type(value).__name__}"
        )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def complete_json(
    prompt: str,
    schema: dict,
    *,
    max_retries: int = 1,
) -> dict:
    """Send prompt to the configured LLM and return a validated JSON dict.

    Args:
        prompt:      The full prompt text to send.
        schema:      A minimal JSON-Schema-style dict describing expected keys
                     and types.  Used for validation before returning.
        max_retries: Number of times to retry on parse/validation failure
                     (default 1 per steering rule 17).

    Returns:
        A dict matching the schema.

    Raises:
        LLMError: If the response cannot be parsed and validated after all
                  retries, or if the provider itself fails.
    """
    # Import config lazily to avoid circular imports; llm.py is imported
    # by agents, which are imported by orchestrator, which imports config.
    from edgedash.config import load_config
    cfg = load_config()

    limiter = _get_limiter(cfg.llm_requests_per_minute)

    current_prompt = prompt
    last_error: str = ""

    for attempt in range(max_retries + 1):
        limiter.wait()

        raw = _call_provider(cfg.llm_provider, cfg.llm_model, current_prompt)

        # Strip fences / prose and parse.
        try:
            cleaned = _extract_json(raw)
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = f"JSON parse error: {exc}"
        else:
            # Validate against schema.
            try:
                _validate(data, schema)
                return data
            except ValueError as exc:
                last_error = f"Schema validation error: {exc}"

        # If we have retries left, append the error to the prompt.
        if attempt < max_retries:
            current_prompt = (
                f"{prompt}\n\n"
                f"Your previous response was invalid: {last_error}\n"
                "Reply with JSON only. No prose, no markdown fences. "
                "Your entire reply must be a single valid JSON object."
            )

    raise LLMError(
        f"LLM failed to produce a valid response after {max_retries + 1} "
        f"attempt(s). Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# CLI check: python -m edgedash.llm --check
# ---------------------------------------------------------------------------

def _run_check() -> None:
    """Send one trivial prompt and report provider, model, and outcome."""
    from edgedash.config import load_config

    # Load .env before checking config.
    _load_dotenv()

    cfg = load_config()
    print(f"  Provider : {cfg.llm_provider}")
    print(f"  Model    : {cfg.llm_model}")
    print(f"  RPM cap  : {cfg.llm_requests_per_minute}")
    print()

    schema = {"properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    test_prompt = 'Reply with exactly: {"ok": true}'

    try:
        result = complete_json(test_prompt, schema)
        print(f"  ✓ Connection OK — response: {result}")
    except LLMError as exc:
        print(f"  ✗ FAILED — {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _run_check()
    else:
        print("Usage: python -m edgedash.llm --check")
        raise SystemExit(1)
