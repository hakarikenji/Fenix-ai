"""
Fenix Research — web search + page extraction with honest degradation.

Pipeline: question → need? → search → fetch top pages → extract → synthesize
→ return answer + sources.

Configuration (server-side only, never exposed to the client):
  SERPER_API_KEY — api.serper.dev search API (https://serper.dev, free tier)

If SERPER_API_KEY is missing, research_is_configured() returns False and the
/UI shows a clear "not configured" state instead of faking results.
"""
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request

SERPER_API_KEY = ""  # populated from env at import time below (see load_config)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_FETCH_BYTES = 400_000
FETCH_TIMEOUT = 12

RESEARCH_SYSTEM = """You are Fenix's research synthesizer. You receive a user
question and real snippets/pages fetched from the web. Write a direct, useful
answer grounded ONLY in the provided material. Rules:
1. Never invent facts, numbers or sources — if the material is insufficient, say exactly what is missing.
2. Cite inline as [1], [2] matching the numbered sources.
3. Distinguish clearly: current web findings vs general model knowledge. If you add background knowledge, mark that sentence with (general knowledge).
4. Be concise: lead with the answer, then key details. Reply in the user's language."""


def load_config() -> None:
    """Read server-side config from env (called from server.py at startup)."""
    global SERPER_API_KEY
    import os

    SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")


def research_is_configured() -> bool:
    return bool(SERPER_API_KEY)


def _post_json(url: str, body: dict, key_header: dict | None = None, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(key_header or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def search_web(query: str, num: int = 6) -> list[dict]:
    """Search via Serper. Returns [{title, link, snippet}]. Raises on failure."""
    data = _post_json(
        "https://google.serper.dev/search",
        {"q": query, "num": max(3, min(num, 10))},
        {"X-API-KEY": SERPER_API_KEY},
    )
    out = []
    seen = set()
    for item in data.get("organic", [])[:num]:
        link = str(item.get("link") or "").strip()
        if not link or link in seen:
            continue
        try:
            link = _public_http_url(link)
        except ValueError:
            continue
        seen.add(link)
        out.append({
            "title": str(item.get("title") or "")[:200],
            "link": link,
            "snippet": str(item.get("snippet") or "")[:400],
        })
    return out


def _public_http_url(url: str) -> str:
    """Reject non-HTTP and private/local targets to reduce SSRF exposure."""
    parsed = urllib.parse.urlsplit(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("research URL must be public HTTP(S)")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("research URL host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("research URL points to a non-public network")
    return urllib.parse.urlunsplit(parsed)


def fetch_page_text(url: str, max_chars: int = 6000) -> str:
    """Fetch a validated public page and strip it to readable text."""
    safe_url = _public_http_url(url)
    req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0 (Fenix research)"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        raw = resp.read(MAX_FETCH_BYTES).decode("utf-8", errors="ignore")
    raw = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()[:max_chars]


def decide_research_needed(message: str) -> bool:
    """Heuristic: does this question likely need current web info?"""
    m = (message or "").lower()
    cues = (
        "latest", "news", "today", "current", "2025", "2026", "price of",
        "who won", "release date", "update on", "recent", "stock", "weather",
        "score", "version of", "how much is", "as of",
    )
    return any(c in m for c in cues)


def run_research(message: str, tier: str = "flash", gemini_key: str | None = None) -> dict:
    """Full pipeline. Returns {answer, sources, note}. Raises ValueError with a
    friendly message when research is not configured, and RuntimeError on failure."""
    if not research_is_configured():
        raise ValueError("not_configured")
    results = search_web(message, num=6)
    if not results:
        raise RuntimeError("No search results for this query")
    # Light retrieval: fetch the top 2 pages when possible.
    corpus = []
    for i, r in enumerate(results, 1):
        corpus.append(f"[{i}] {r['title']}\n{r['link']}\n{r['snippet']}")
    for i, r in enumerate(results[:2], 1):
        try:
            corpus.append(f"[{i}] page content: {fetch_page_text(r['link'])}")
        except Exception:
            pass  # a blocked page is fine — snippets already cover it
    material = "\n\n".join(corpus)[:14000]

    # Synthesize with Gemini (server-side key)
    key = gemini_key or ""
    if not key:
        raise RuntimeError("AI key missing for synthesis")
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": f"User question: {message}\n\nWeb material:\n{material}"}
        ]}],
        "systemInstruction": {"parts": [{"text": RESEARCH_SYSTEM}]},
        "generationConfig": {"temperature": 0.3},
    }
    chain = ["gemini-3.5-flash", "gemini-flash-lite-latest"] if tier != "pro" else [
        "gemini-3.1-pro-preview", "gemini-pro-latest", "gemini-3.5-flash"]
    answer, last_err = None, None
    for model in chain:
        try:
            data = _post_json(f"{GEMINI_API_URL}/models/{model}:generateContent?key={key}", body)
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                answer = text
                break
        except Exception as e:
            last_err = e
    if not answer:
        raise RuntimeError(f"Synthesis failed: {last_err}")
    return {"answer": answer, "sources": results, "note": "Live web research"}


def maybe_research(message: str, gemini_key: str | None = None, tier: str = "flash") -> dict | None:
    """Auto-trigger research for time-sensitive questions. Returns None when
    research is off/not needed so the normal chat path handles the message."""
    if not research_is_configured():
        return None
    if not decide_research_needed(message):
        return None
    try:
        return run_research(message, tier=tier, gemini_key=gemini_key)
    except Exception:
        return None  # fail-soft: normal chat proceeds without fake sources
