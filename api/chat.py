"""دالة الاستضافة: محادثة Fenix بذاكرة كاملة (يُمرر سجل الرسائل من العميل)."""
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
    if not message:
        return (
            400,
            {**CORS, "Content-Type": "application/json; charset=utf-8"},
            '{"error": "اكتب رسالتك أولاً"}',
        )
    if not isinstance(history, list):
        history = []
    # حدود أمان: آخر 40 رسالة كحد أقصى للسجل
    history = history[-40:]

    try:
        reply = gemini_chat(history, message)
        body = json.dumps({"reply": reply}, ensure_ascii=False)
        return (200, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
    except Exception as e:
        body = json.dumps({"error": f"تعذر الاتصال: {e}"}, ensure_ascii=False)
        return (502, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
