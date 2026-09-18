"""
Fenix Studio — خادم التطوير
يقدم واجهة الويب ويستضيف /api/* بنفس منطق دوال الإنتاج في api/
(المفتاح يبقى مخفياً في الخادم ولا يظهر في التطبيق إطلاقاً).

التشغيل:  python server.py
"""
import json
import os
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

# استيراد الأدوات المشتركة من مجلد api/
sys.path.insert(0, str(Path(__file__).parent / "api"))
from common import gemini_enhance, load_prompts  # noqa: E402

app = Flask(__name__, static_folder="web", static_url_path="")


@app.after_request
def add_cors(response):
    """السماح للتطبيق المثبّت (APK/Capacitor) بنداء الخادم من نطاق مختلف."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def api_preflight(_any):
    return Response(status=204)


@app.route("/api/enhance", methods=["POST"])
def api_enhance():
    """تحويل أمر المستخدم البسيط إلى Enhanced Prompt عبر Gemini."""
    data = request.get_json(silent=True) or {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return jsonify({"error": "أدخل نصاً أولاً"}), 400
    try:
        return jsonify({"result": gemini_enhance(f'أمر المستخدم:\n"""\n{user_text}\n"""')})
    except Exception as e:
        return jsonify({"error": f"فشل الاتصال بـ Gemini: {e}"}), 502


@app.route("/api/library", methods=["GET"])
def api_library():
    """إرجاع قائمة برومبتات المكتبة (بدون القوالب الكاملة)."""
    return jsonify(
        [
            {"id": key, "title": item["title"], "description": item["description"]}
            for key, item in load_prompts().items()
        ]
    )


@app.route("/api/library/<prompt_id>", methods=["POST"])
def api_library_apply(prompt_id: str):
    """تعبئة قالب مكتبة بنص المستخدم ثم تحسينه عبر Gemini."""
    prompts = load_prompts()
    if prompt_id not in prompts:
        return jsonify({"error": "البرومبت غير موجود"}), 404

    data = request.get_json(silent=True) or {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return jsonify({"error": "أدخل نصاً أولاً"}), 400

    filled = prompts[prompt_id]["template"].replace("{user_input}", user_text)
    try:
        return jsonify({"result": gemini_enhance(filled), "filled_prompt": filled})
    except Exception as e:
        return jsonify({"error": f"فشل الاتصال بـ Gemini: {e}"}), 502


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/sw.js")
def service_worker():
    response = send_from_directory("web", "sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/manifest.json")
def manifest():
    return send_from_directory("web", "manifest.json", mimetype="application/manifest+json")


@app.route("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"🔥 Fenix Studio يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
