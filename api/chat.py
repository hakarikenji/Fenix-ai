"""Hosting function: multimodal Fenix chat with full memory (client sends history)."""
import json

from common import CORS, gemini_chat


def handler(request):
    if request.method == "OPTIONS":
        return (204, CORS, "")
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}

    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    attachments = data.get("attachments") or []
    tier = data.get("model") if data.get("model") in ("pro", "flash") else "flash"
    style = data.get("style") if data.get("style") in ("concise", "detailed") else "concise"
    if not message and not attachments:
        return (
            400,
            {**CORS, "Content-Type": "application/json; charset=utf-8"},
            '{"error": "Type a message first"}',
        )
    if not isinstance(history, list):
        history = []
    # Safety bound: last 40 messages of history
    history = history[-40:]

    try:
        reply = gemini_chat(history, message, attachments, tier, style)
        body = json.dumps({"reply": reply}, ensure_ascii=False)
        return (200, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
    except Exception as e:
        body = json.dumps({"error": f"Connection failed: {e}"}, ensure_ascii=False)
        return (502, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
