"""
Fenix Research — web search + page extraction with honest degradation.

Pipeline: question → need? → search → fetch top pages → extract → synthesize
→ return answer + sources.

Search providers, tried in order — all free:
  1. SearXNG public instances (JSON API, no key). Configure your own instance
     with SEARXNG_BASE_URL for full control (recommended for production).
  2. Serper (only if SERPER_API_KEY is set — free 2500-credit trial).
  3. DuckDuckGo Lite (keyless HTML, last-resort fallback).

research_is_configured() is always True because at least one keyless provider
exists; individual failures degrade to the next provider honestly.
"""
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.request

SERPER_API_KEY = ""  # populated from env at import time below (see load_config)
SEARXNG_BASE_URL = ""  # optional: your own SearXNG instance (e.g. https://myspace.hf.space)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_FETCH_BYTES = 400_000
FETCH_TIMEOUT = 12

# Free public SearXNG instances with JSON enabled (community-maintained).
# Order matters: private/self-hosted first if configured, then public ones.
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.inetol.net",
    "https://baresearch.org",
    "https://search.hbubli.cc",
    "https://searx.tiekoetter.com",
    "https://priv.au",
    "https://opnxng.com",
]

RESEARCH_SYSTEM = """You are Fenix's research synthesizer. You receive a user
question and real snippets/pages fetched from the web. Write a direct, useful
answer grounded ONLY in the provided material. Rules:
1. Never invent facts, numbers or sources — if the material is insufficient, say exactly what is missing.
2. Cite inline as [1], [2] matching the numbered sources.
3. Distinguish clearly: current web findings vs general model knowledge. If you add background knowledge, mark that sentence with (general knowledge).
4. Be concise: lead with the answer, then key details. Reply in the user's language."""


def load_config() -> None:
    """Read server-side config from env (called from server.py at startup)."""
    global SERPER_API_KEY, SEARXNG_BASE_URL
    import os

    SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
    SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "").rstrip("/")


def research_is_configured() -> bool:
    """Always true: SearXNG/DDG fallbacks need no key."""
    return True


def _get(url: str, timeout: int = 12, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json,text/html",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(MAX_FETCH_BYTES).decode("utf-8", errors="ignore")


def _post_json(url: str, body: dict, key_header: dict | None = None, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(key_header or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _searxng_search(query: str, num: int) -> list[dict]:
    """Search via SearXNG JSON API across configured instances.
    Your own instance (SEARXNG_BASE_URL) is tried first, then public ones."""
    instances = ([SEARXNG_BASE_URL] if SEARXNG_BASE_URL else []) + SEARXNG_INSTANCES
    last_err = None
    for base in instances[:6]:  # cap: don't crawl forever
        try:
            raw = _get(f"{base}/search?q={urllib.parse.quote(query)}&format=json&language=en")
            data = json.loads(raw)
            out = []
            for item in (data.get("results") or [])[:num]:
                link = str(item.get("url") or "").strip()
                if not link:
                    continue
                out.append({
                    "title": str(item.get("title") or "")[:200],
                    "link": link,
                    "snippet": str(item.get("content") or "")[:400],
                })
            if out:
                return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"all SearXNG instances failed (last: {last_err})")


def _ddg_lite_search(query: str, num: int) -> list[dict]:
    """Keyless last-resort: DuckDuckGo Lite HTML results."""
    body = urllib.parse.urlencode({"q": query}).encode()
    req = urllib.request.Request(
        "https://lite.duckduckgo.com/lite/", data=body,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        html = resp.read(MAX_FETCH_BYTES).decode("utf-8", "ignore")
    out, seen = [], set()
    for url, title in re.findall(r'<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        if "duckduckgo.com" in url:
            continue
        title = re.sub(r"<[^>]+>", "", title).strip()
        if not title or url in seen:
            continue
        seen.add(url)
        out.append({"title": title[:200], "link": url, "snippet": ""})
        if len(out) >= num:
            break
    if not out:
        raise RuntimeError("ddg lite returned no results")
    return out


def search_web(query: str, num: int = 6) -> list[dict]:
    """Search the web through the free provider chain:
    SearXNG → Serper (if key set) → DuckDuckGo Lite.
    Returns [{title, link, snippet}]. Raises on total failure."""
    errors = []

    # 1) SearXNG (free, no key)
    try:
        results = _searxng_search(query, num)
    except Exception as e:  # noqa: BLE001
        errors.append(f"searxng: {e}")
        results = []
    if results:
        return _validate_results(results, num)

    # 2) Serper (only when a key is configured)
    if SERPER_API_KEY:
        try:
            results = _serper_search(query, num)
        except Exception as e:  # noqa: BLE001
            errors.append(f"serper: {e}")
            results = []
        if results:
            return _validate_results(results, num)

    # 3) DuckDuckGo Lite (keyless fallback)
    try:
        results = _ddg_lite_search(query, num)
    except Exception as e:  # noqa: BLE001
        errors.append(f"ddg: {e}")
        raise RuntimeError("No search results for this query (" + "; ".join(errors) + ")")
    return _validate_results(results, num)


def _validate_results(results: list[dict], num: int) -> list[dict]:
    """Enforce SSRF-safe public URLs and dedupe."""
    out, seen = [], set()
    for r in results[: num * 2]:
        link = str(r.get("link") or "").strip()
        if not link or link in seen:
            continue
        try:
            link = _public_http_url(link)
        except ValueError:
            continue
        seen.add(link)
        out.append({"title": (r.get("title") or "")[:200], "link": link,
                    "snippet": (r.get("snippet") or "")[:400]})
        if len(out) >= num:
            break
    return out


def _serper_search(query: str, num: int) -> list[dict]:
    """Search via Serper (requires SERPER_API_KEY). Returns raw results."""
    data = _post_json(
        "https://google.serper.dev/search",
        {"q": query, "num": max(3, min(num, 10))},
        {"X-API-KEY": SERPER_API_KEY},
    )
    return [{
        "title": str(item.get("title") or "")[:200],
        "link": str(item.get("link") or "").strip(),
        "snippet": str(item.get("snippet") or "")[:400],
    } for item in data.get("organic", [])[:num]]


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
    """Heuristic: does this question likely need current web info?
    Bilingual (English + Arabic) cues — any hit triggers live search."""
    m = (message or "").lower()
    cues = (
        # English
        "latest", "news", "today", "current", "2024", "2025", "2026",
        "price of", "who won", "release date", "update on", "recent",
        "stock", "weather", "score", "version of", "how much is", "as of",
        "search", "google", "look up", "web", "online", "find out",
        # Arabic (and transliterations users actually type)
        "ابحث", "ابحث", "بحث", "ابحاث", "جوجل", "انترنت", "إنترنت",
        "اخبار", "أخبار", "خبر", "اليوم", "حاليا", "الان", "الآن",
        "احدث", "أحدث", "جديد", "سعر", "اسعار", "أسعار", "نتيجة", "نتائج",
        "في الويب", "عن الويب", "مين", "من هو", "ماهو", "ما هو",
    )
    return any(c in m for c in cues)


def _plan_queries(message: str) -> list[str]:
    """Turn the question into 2–3 complementary search queries.
    The first is the question itself; the second strips question words and
    targets the core nouns; the third adds the current year for freshness."""
    base = " ".join(message.split())[:180]
    clean = re.sub(r"^(who|what|when|where|why|how|is|are|was|were|do|does|did|can|tell me about)\s+", "",
                   base, flags=re.I).strip(" ?؟.")
    year = time.strftime("%Y")
    queries = [base]
    if clean and clean.lower() != base.lower():
        queries.append(clean)
    if not any(y in base for y in (year, str(int(year) - 1))):
        queries.append(f"{clean or base} {year}")
    # Dedupe, keep order, cap at 3.
    seen, out = set(), []
    for q in queries:
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:3]


def _rank_sources(results: list[dict]) -> list[dict]:
    """Simple source ranking: domain diversity first, then snippet richness."""
    def score(r: dict) -> float:
        s = len(r.get("snippet") or "") / 400.0
        title_bonus = 0.5 if r.get("title") else 0.0
        return s + title_bonus
    seen_domains: dict[str, int] = {}
    ranked = sorted(results, key=score, reverse=True)
    out = []
    for r in ranked:
        try:
            host = urllib.parse.urlsplit(r["link"]).hostname or ""
        except Exception:
            host = ""
        if host and seen_domains.get(host, 0) >= 2:
            continue  # max 2 results per domain for diversity
        seen_domains[host] = seen_domains.get(host, 0) + 1
        out.append(r)
    return out


def run_research(message: str, tier: str = "flash", gemini_key: str | None = None) -> dict:
    """Full pipeline. Returns {answer, sources, note}. Raises ValueError with a
    friendly message when research is not configured, and RuntimeError on failure."""
    if not research_is_configured():
        raise ValueError("not_configured")

    # Query planning: several complementary queries, merged and deduped.
    merged: list[dict] = []
    seen_links = set()
    for q in _plan_queries(message):
        try:
            for r in search_web(q, num=5):
                if r["link"] not in seen_links:
                    seen_links.add(r["link"])
                    merged.append(r)
        except Exception:
            continue  # one failing query must not kill the run
    results = _rank_sources(merged)[:8]
    if not results:
        raise RuntimeError("No search results for this query")

    # Deeper retrieval: fetch up to 4 top pages (snippets already cover the rest).
    corpus = []
    for i, r in enumerate(results, 1):
        corpus.append(f"[{i}] {r['title']}\n{r['link']}\n{r['snippet']}")
    for i, r in enumerate(results[:4], 1):
        try:
            corpus.append(f"[{i}] page content: {fetch_page_text(r['link'], max_chars=8000)}")
        except Exception:
            pass  # a blocked page is fine — snippets already cover it
    material = "\n\n".join(corpus)[:16000]

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
