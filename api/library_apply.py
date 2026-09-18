"""دالة الاستضافة: تشغيل قالب مكتبة محدد على نص المستخدم عبر Gemini."""
import json

from common import gemini_enhance, load_prompts

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def handler(request, prompt_id: str):
    if request.method == "OPTIONS":
        return (204, CORS, "")
    prompts = load_prompts()
    if prompt_id not in prompts:
        return (404, {**CORS, "Content-Type": "application/json; charset=utf-8"}, '{"error": "البرومبت غير موجود"}')

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return (400, {**CORS, "Content-Type": "application/json; charset=utf-8"}, '{"error": "أدخل نصاً أولاً"}')

    filled = prompts[prompt_id]["template"].replace("{user_input}", user_text)
    try:
        result = gemini_enhance(filled)
        body = json.dumps({"result": result, "filled_prompt": filled}, ensure_ascii=False)
        return (200, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
    except Exception as e:
        body = json.dumps({"error": f"فشل الاتصال بـ Gemini: {e}"}, ensure_ascii=False)
        return (502, {**CORS, "Content-Type": "application/json; charset=utf-8"}, body)
