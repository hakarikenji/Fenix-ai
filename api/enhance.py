"""دالة الاستضافة: تحسين أمر المستخدم عبر Gemini."""
import json

from common import gemini_enhance

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def handler(request):
    if request.method == "OPTIONS":
        return (204, CORS, "")
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return (400, {**CORS, "Content-Type": "application/json; charset=utf-8"}, '{"error": "أدخل نصاً أولاً"}')
    try:
        result = gemini_enhance(f'أمر المستخدم:\n"""\n{user_text}\n"""')
        body = json.dumps({"result": result}, ensure_ascii=False)
        return (200, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
    except Exception as e:
        body = json.dumps({"error": f"فشل الاتصال بـ Gemini: {e}"}, ensure_ascii=False)
        return (502, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
