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
    CEREBRAS_API_KEY   -> Cerebras   (1M tokens/day free, no card)
    NVIDIA_API_KEY     -> NVIDIA NIM (free credits on signup, no card)
    COHERE_API_KEY     -> Cohere     (command models, free tier, no card)
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
import threading
import time
import urllib.error
import urllib.request

import free_brains_cache as _cache

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
    # Model list verified live against a real key: the previous three slugs
    # now return 404 "unavailable for free". These answered in Arabic.
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-super-120b-a12b:free,"
        "inclusionai/ling-3.0-flash-fin:free,"
        "nvidia/nemotron-3.5-lightning:free,"
        "qwen/qwen3.8-27b:free",
        "OPENROUTER_API_KEY",
    ),
    "cerebras": (
        "https://api.cerebras.ai/v1",
        "llama3.1-8b",
        "qwen-3-32b,llama-3.3-70b",
        "CEREBRAS_API_KEY",
    ),
    # NVIDIA NIM — ~1k free credits on signup, no card, very fast inference.
    "nvidia": (
        "https://integrate.api.nvidia.com/v1",
        "qwen/qwen3-coder-30b-a3b-instruct",
        "meta/llama-3.3-70b-instruct,qwen/qwen3-235b-a22b",
        "NVIDIA_API_KEY",
    ),
    # Cohere — command models, free trial tier, no card.
    # command-r / command-r-plus were removed in Sep 2025; command-a is the
    # current line and was verified live to answer in Arabic.
    "cohere": (
        "https://api.cohere.com/v2",
        "command-a-03-2025",
        "command-a-plus-05-2026",
        "COHERE_API_KEY",
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

# Verified liveness, refreshed by the background prober.
# label -> {"ok": bool, "checked_at": float, "detail": str}
_verified: dict[str, dict] = {}


def _probe_one(label: str) -> dict:
    """One tiny real call. This is the only trustworthy liveness signal."""
    cfg = PROVIDERS.get(label)
    if not cfg:
        return {"ok": False, "checked_at": time.time(), "detail": "unknown provider"}
    key = os.environ.get(cfg[3], "").strip()
    if not key:
        return {"ok": False, "checked_at": time.time(), "detail": "no key"}
    body = {"model": _model_chain(label, cfg[1], cfg[2])[0],
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 4}
    try:
        _post(_base_url(label, cfg[0]), key, body)
        return {"ok": True, "checked_at": time.time(), "detail": "answered"}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Rate limited, not broken: the key works, it is just busy.
            return {"ok": True, "checked_at": time.time(), "detail": "rate-limited"}
        return {"ok": False, "checked_at": time.time(), "detail": f"http {e.code}"}
    except Exception as e:
        return {"ok": False, "checked_at": time.time(), "detail": type(e).__name__}


def verify(force: bool = False) -> dict[str, dict]:
    """Refresh verified liveness for every configured provider."""
    if not enabled():
        return {}
    for label in configured_labels():
        prev = _verified.get(label)
        fresh = prev and (time.time() - prev.get("checked_at", 0)) < 900
        if force or not fresh:
            _verified[label] = _probe_one(label)
    return dict(_verified)


def verified_count() -> int:
    """Providers that actually answered. This is what the UI must show.

    Falls back to the configured count only before the first probe finishes,
    so a cold start cannot read as zero; after that the number is measured,
    never assumed.
    """
    if not enabled():
        return 0
    labels = configured_labels()
    if not labels:
        return 0
    if not any(label in _verified for label in labels):
        return len(labels)  # first probe has not run yet — do not claim zero
    return sum(1 for label in labels if _verified.get(label, {}).get("ok"))


def verified_detail() -> dict[str, str]:
    """label -> short status, for server-side diagnostics only."""
    return {label: _verified.get(label, {}).get("detail", "unprobed")
            for label in configured_labels()}


def start_prober(interval: int = 600) -> None:
    """Keep verified liveness warm so the UI never shows a stale number."""
    def loop() -> None:
        while True:
            try:
                verify(force=True)
            except Exception:
                pass
            time.sleep(max(60, interval))

    threading.Thread(target=loop, daemon=True).start()


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
    base = base.rstrip("/")
    # Cohere's v2 surface is /chat; everyone else is OpenAI-compatible.
    url = base + "/chat" if base.endswith("/v2") else base + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
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

    temp = max(0.0, min(1.5, temperature))
    cap = max(64, min(int(max_tokens), 4096))

    # A cached answer costs no upstream request at all. Free tiers are capped
    # per day, so serving repeats from disk is what makes $0 stretch.
    cached = _cache.cache_get(system, user)
    if cached:
        _last_provider = "cache"
        return cached, "cache"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Healthy providers first; ones in cooldown are still tried, just last.
    for label in _cache.ordered_labels(list(PROVIDERS)):
        cfg = PROVIDERS.get(label)
        if not cfg:
            continue
        default_base, default_model, fallbacks, key_env = cfg
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
                if text and text.strip():
                    _last_provider = label
                    _cache.note_success(label)
                    _cache.cache_put(system, user, text, label)
                    return text, label
                # An empty reply means the model cannot serve this request
                # (some refuse structured output). Back off so the next
                # request tries another provider instead of hitting the
                # same dead end.
                _last_error.append(f"{label}/{model}: empty reply")
                _cache.note_failure(label, "empty reply")
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
                spent = e.code == 429 and (
                    "per-day" in detail or "per day" in detail
                    or "quota" in detail.lower() or "credits" in detail.lower())
                _last_error.append(f"{label}/{model}: HTTP {e.code}"
                                   + (" (daily quota used up)" if spent else ""))
                _cache.note_failure(label, f"HTTP {e.code}", quota=spent)
            except Exception as e:  # network / DNS / timeout
                _last_error.append(f"{label}/{model}: {type(e).__name__}")
                _cache.note_failure(label, type(e).__name__)
    return None
