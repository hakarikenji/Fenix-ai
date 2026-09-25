"""Fenix sandbox adapter.

Code execution is intentionally delegated to a separately isolated runtime. This
module never runs model-generated code in the Flask process or passes server
credentials to the browser. Providers can implement the small contract below:

POST {SANDBOX_URL}/execute
Authorization: Bearer {SANDBOX_API_KEY}  # server-side only
{
  "language": "python|javascript",
  "code": "...",
  "stdin": "...",
  "timeoutMs": 5000
}

Expected response:
{
  "status": "completed|failed|timeout",
  "stdout": "...",
  "stderr": "...",
  "exitCode": 0,
  "durationMs": 12
}

The provider is responsible for container/VM isolation, filesystem and network
policy, CPU/memory limits, and killing timed-out processes. Fenix only validates
and forwards the result.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

MAX_CODE_BYTES = 100_000
MAX_INPUT_BYTES = 20_000
MAX_OUTPUT_CHARS = 20_000
MAX_TIMEOUT_MS = 10_000
LANGUAGES = ("python", "javascript")


@dataclass(frozen=True)
class SandboxConfig:
    url: str
    api_key: str
    timeout_ms: int


def configured() -> bool:
    return bool(os.environ.get("SANDBOX_URL", "").strip())


def _config() -> SandboxConfig:
    url = os.environ.get("SANDBOX_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SANDBOX_URL is not configured")
    try:
        timeout = int(os.environ.get("SANDBOX_TIMEOUT_MS", "5000"))
    except ValueError:
        timeout = 5000
    return SandboxConfig(url, os.environ.get("SANDBOX_API_KEY", "").strip(),
                         max(250, min(timeout, MAX_TIMEOUT_MS)))


def _text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def execute(language: str, code: str, *, stdin: str = "", timeout_ms: int | None = None) -> dict[str, Any]:
    """Execute in the configured remote sandbox and return a bounded result.

    Raises RuntimeError for configuration/provider failures. Callers convert
    these to honest tool errors; a failed execution is never reported as a pass.
    """
    language = str(language or "").strip().lower()
    code = str(code or "")
    stdin = str(stdin or "")
    if language not in LANGUAGES:
        raise ValueError("language must be python or javascript")
    if not code.strip():
        raise ValueError("code is required")
    if len(code.encode()) > MAX_CODE_BYTES:
        raise ValueError("code exceeds the 100 KB limit")
    if len(stdin.encode()) > MAX_INPUT_BYTES:
        raise ValueError("stdin exceeds the 20 KB limit")

    config = _config()
    requested = int(timeout_ms or config.timeout_ms)
    requested = max(250, min(requested, MAX_TIMEOUT_MS, config.timeout_ms))
    payload = {
        "language": language,
        "code": code,
        "stdin": stdin[:MAX_INPUT_BYTES],
        "timeoutMs": requested,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = "Bearer " + config.api_key
    request = urllib.request.Request(
        config.url + "/execute", data=json.dumps(payload).encode(), headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=(requested / 1000) + 2) as response:
            raw = response.read(MAX_OUTPUT_CHARS * 4).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"sandbox returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("sandbox unavailable or timed out") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("sandbox returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("sandbox returned an invalid result")

    status = str(data.get("status") or "completed").lower()
    if status not in {"completed", "failed", "timeout"}:
        status = "failed"
    try:
        exit_code = int(data.get("exitCode", 1 if status != "completed" else 0))
    except (TypeError, ValueError):
        exit_code = 1 if status != "completed" else 0
    return {
        "status": status,
        "language": language,
        "stdout": _text(data.get("stdout"), MAX_OUTPUT_CHARS),
        "stderr": _text(data.get("stderr"), MAX_OUTPUT_CHARS),
        "exitCode": exit_code,
        "durationMs": max(0, int(data.get("durationMs") or 0)),
        "sandboxed": True,
    }
