# -*- coding: utf-8 -*-
"""groq_brain_test.py — prove Groq answers through the Fenix brain chain.

Usage (no server needed; it uses Flask's test client):
    python groq_brain_test.py

Usage against a running preview/server:
    python groq_brain_test.py --url http://127.0.0.1:8000

Exit codes:
    0  Groq answered (real Groq API, real key)
    1  The chain answered, but not from Groq
    2  BLOCKED — GROQ_API_KEY is not available in this environment

The key is never printed.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api"))
os.chdir(ROOT)

PROMPT = "من جاوبني؟ جاوب بكلمة واحدة فقط."


def direct_groq_ping() -> tuple[str, str]:
    """Call Groq's OpenAI-compatible endpoint directly (bypasses Fenix)."""
    import free_brains

    key = os.environ.get("GROQ_API_KEY", "").strip()
    models = free_brains._model_chain("groq", *free_brains.PROVIDERS["groq"][1:3])
    base = free_brains._base_url("groq", free_brains.PROVIDERS["groq"][0])
    last = ""
    for model in models:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Say OK"}],
                           "max_tokens": 16}).encode()
        req = urllib.request.Request(
            base + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode("utf-8", "ignore"))
            text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
            if text:
                return model, text
            last = f"{model}: empty reply"
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code}"
        except Exception as e:
            last = f"{model}: {type(e).__name__}"
    return "", last


def through_chain(url: str | None) -> tuple[int, dict]:
    if url:
        req = urllib.request.Request(
            url.rstrip("/") + "/api/chat",
            data=json.dumps({"message": PROMPT, "history": []}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode("utf-8", "ignore"))
    import server  # noqa: E402

    client = server.app.test_client()
    resp = client.post("/api/chat", json={"message": PROMPT, "history": []})
    return resp.status_code, resp.get_json() or {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="base URL of a running Fenix server")
    args = ap.parse_args()

    if not os.environ.get("GROQ_API_KEY", "").strip():
        print("BLOCKED: GROQ_API_KEY is not set in this environment.")
        print("Add it in Settings -> Environment (name: GROQ_API_KEY), then re-run:")
        print("    python groq_brain_test.py")
        return 2

    import free_brains  # noqa: E402

    print("free-brain providers :", free_brains.configured_labels())
    print("groq model chain     :", free_brains._model_chain("groq", *free_brains.PROVIDERS["groq"][1:3]))

    model, direct = direct_groq_ping()
    print(f"direct groq call     : model={model or '-'} reply={direct!r}")

    status, data = through_chain(args.url)
    brain = data.get("brain")
    engine = data.get("engine")
    reply = (data.get("reply") or "").strip()
    print(f"Fenix /api/chat      : HTTP {status} brain={brain} engine={engine} reply={reply[:240]!r}")
    if free_brains.last_errors():
        print("layer errors         :", "; ".join(free_brains.last_errors()[:5]))

    if reply and (brain == "groq" or (brain == "fenix-core" and engine == "groq")):
        print("\nRESULT: GROQ_LIVE_OK — Fenix Core answered through the Groq provider.")
        return 0
    print(f"\nRESULT: NOT_GROQ — the chain answered from: brain={brain} engine={engine}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
