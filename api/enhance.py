"""دالة الاستضافة: تحسين أمر المستخدم عبر Gemini."""
import json

from common import gemini_enhance


def handler(request):
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return (400, {"Content-Type": "application/json; charset=utf-8"}, '{"error": "أدخل نصاً أولاً"}')
    try:
        result = gemini_enhance(f'أمر المستخدم:\n"""\n{user_text}\n"""')
        body = json.dumps({"result": result}, ensure_ascii=False)
        return (200, {"Content-Type": "application/json; charset=utf-8"}, body)
    except Exception as e:
        body = json.dumps({"error": f"فشل الاتصال بـ Gemini: {e}"}, ensure_ascii=False)
        return (502, {"Content-Type": "application/json; charset=utf-8"}, body)
