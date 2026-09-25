"""Fenix — free always-on brain layer (no GPU, no hosting, $0).

Why this exists
---------------
The private LoRA brains are trained once and then served from a GPU host
(Modal today). Those hosts cost money and can be disabled, so the app falls
back to Gemini. This module adds a *second* brain layer that is free and
always available: public OpenAI-compatible inference providers with a free
tier. They answer in Fenix's voice, follow the same system instructions, and
the UI is told exactly which provider answered (never faked).

Chain (all optional, zero-config — no key means silently skipped):
    GROQ_API_KEY       -> Groq       (fastest free tier, OpenAI-compatible)
    OPENROUTER_API_KEY -> OpenRouter (many ":free" models incl. Qwen)
    CEREBRAS_API_KEY   -> Cerebras   (fast free tier)
    DEEPSEEK_API_KEY   -> DeepSeek   (OpenAI-compatible secondary brain)

Groq free tier, verified against Groq docs in Sept 2026:
    * free models: openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b,
      qwen/qwen3.6-27b
    * llama-3.1-8b and llama-3.3-70b became ENTERPRISE-ONLY on 16 Aug 2026,
      so they are only used if you set GROQ_MODEL yourself
    * limits: 30 req/min, 1000 req/day, 8k tok/min, 200k tok/day

If a provider rejects the model (400/403/404) or the quota is hit (429), the
next model and then the next provider are tried. Nothing raises, nothing
leaks secrets. Set FREE_BRAINS=off to disable the layer. The server keeps the
provider label internally for diagnostics while the public product identity
remains Fenix Core.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT = float(os.environ.get("FREE_BRAINS_TIMEOUT", "45"))

# label: (default base url, default model, built-in fallback models, key env var)
PROVIDERS: dict[str, tuple[str, str, str, str]] = {
    # Qwen first: Arabic quality matters for Fenix.
    "groq": (
        "https://api.groq.com/openai/v1",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.6-27b",
        "GROQ_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "qwen/qwen3-32b:free",
        "meta-llama/llama-3.3-70b-instruct:free,deepseek/deepseek-chat-v3-0324:free",
        "OPENROUTER_API_KEY",
    ),
    "cerebras": (
        "https://api.cerebras.ai/v1",
        "llama3.1-8b",
        "qwen-3-32b,llama-3.3-70b",
        "CEREBRAS_API_KEY",
    ),
    "deepseek": (
        "https://api.deepseek.com/v1",
        "deepseek-chat",
        "deepseek-reasoner",
        "DEEPSEEK_API_KEY",
    ),
}

_last_error: list[str] = []
_last_provider: str = ""


def enabled() -> bool:
    return os.environ.get("FREE_BRAINS", "").strip().lower() not in ("off", "none", "0", "false")


def _base_url(label: str, default: str) -> str:
    return (os.environ.get(f"{label.upper()}_BASE_URL", default) or default).strip().rstrip("/")


def _model_chain(label: str, default: str, fallbacks: str) -> list[str]:
    env = label.upper()
    primary = os.environ.get(f"{env}_MODEL", default).strip() or default
    raw_fb = os.environ.get(f"{env}_MODEL_FALLBACKS")
    chain = [primary]
    for m in (raw_fb if raw_fb is not None else fallbacks).split(","):
        m = m.strip()
        if m and m not in chain:
            chain.append(m)
    return chain


def configured_labels() -> list[str]:
    """Internal diagnostic labels — for server-side logs only, never for the client."""
    if not enabled():
        return []
    return [label for label, cfg in PROVIDERS.items() if os.environ.get(cfg[3], "").strip()]


def configured_count() -> int:
    """How many free brain providers are ready. Public-facing APIs report only
    this number — provider names stay server-side so every brain presents as
    Fenix Core LoRA to the user."""
    return len(configured_labels())


def active_models() -> dict[str, str]:
    """label -> model that will be tried first (no secrets involved)."""
    return {
        label: _model_chain(label, cfg[1], cfg[2])[0]
        for label, cfg in PROVIDERS.items()
        if os.environ.get(cfg[3], "").strip()
    }


def last_errors() -> list[str]:
    return list(_last_error)


def last_provider() -> str:
    """Internal provider label for diagnostics; never exposed as a brand in chat."""
    return _last_provider


def _post(base: str, key: str, body: dict, extra_headers: dict | None = None) -> str:
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=headers
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode("utf-8", "ignore")
    out = json.loads(raw)
    return ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()


def free_brain_reply(
    system: str,
    user: str,
    temperature: float = 0.6,
    max_tokens: int = 1600,
) -> tuple[str, str] | None:
    """Try every configured free provider and its fallback models in order.

    Returns (text, label) for the provider that actually answered, or None so
    the caller continues to Gemini. Never raises.
    """
    _last_error.clear()
    global _last_provider
    _last_provider = ""
    if not enabled() or not user.strip():
        return None

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    temp = max(0.0, min(1.5, temperature))
    cap = max(64, min(int(max_tokens), 4096))

    for label, (default_base, default_model, fallbacks, key_env) in PROVIDERS.items():
        key = os.environ.get(key_env, "").strip()
        if not key:
            continue
        base = _base_url(label, default_base)
        extra = ({"HTTP-Referer": "https://fenix.ai", "X-Title": "Fenix AI"}
                 if label == "openrouter" else None)
        for model in _model_chain(label, default_model, fallbacks):
            body = {"model": model, "messages": messages, "temperature": temp, "max_tokens": cap}
            try:
                text = _post(base, key, body, extra)
                if text:
                    _last_provider = label
                    return text, label
                _last_error.append(f"{label}/{model}: empty reply")
            except urllib.error.HTTPError as e:
                _last_error.append(f"{label}/{model}: HTTP {e.code}")
            except Exception as e:  # network / DNS / timeout
                _last_error.append(f"{label}/{model}: {type(e).__name__}")
    return None
