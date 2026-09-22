"""
Fenix Video — خادم التطبيق (نفس كور Fenix)
يقدم استوديو الويب + واجهة /api/* : سيناريو، صور مشاهد، حالة الخدمة.

التشغيل:  python server.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).parent / "api"))
import brain as brain_mod  # noqa: E402

app = Flask(__name__, static_folder="web", static_url_path="")


@app.after_request
def add_cors(response):
    """السماح لتطبيق APK/Capacitor بنداء الخادم من نطاق مختلف."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def api_preflight(_any):
    return Response(status=204)


# ===================== Scenario =====================

@app.route("/api/script", methods=["POST"])
def api_script():
    """فكرة → سيناريو مشاهد JSON: {topic, language, style} → {title, scenes, brain}."""
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()[:400]
    language = (data.get("language") or "العربية").strip()[:30]
    style = (data.get("style") or "cinematic, moody, neon").strip()[:80]
    try:
        temperature = float(data.get("temperature") or 0.9)
    except (TypeError, ValueError):
        temperature = 0.9
    try:
        script = brain_mod.write_script(language, style, topic, temperature)
    except Exception as e:
        return jsonify({"error": str(e)}), 503
    return jsonify({**script, "brain": brain_mod.VIDEO_BRAIN_MODEL if brain_mod.VIDEO_BRAIN_URL
                    else ("fenix-core" if brain_mod.CORE_BRAIN_URL else "gemini")})


@app.route("/api/scene-image")
def api_scene_image():
    """صورة مشهد مجانية بدون مفتاح (Pollinations) — بروكسي حتى يشتغل من أي جهاز."""
    prompt = request.args.get("prompt", "").strip()[:600]
    if not prompt:
        return jsonify({"error": "prompt مطلوب"}), 400
    w = min(1024, max(512, int(request.args.get("w", 768))))
    h = min(1024, max(512, int(request.args.get("h", 768))))
    url = ("https://image.pollinations.ai/prompt/"
           + urllib.parse.quote(prompt + ", cinematic film still, no text")
           + f"?width={w}&height={h}&nologo=true&seed={request.args.get('seed', '7')}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FenixVideo/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            img = r.read()
        if len(img) < 1000:
            raise RuntimeError("empty image")
        return Response(img, mimetype="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        return jsonify({"error": f"فشل توليد الصورة: {e}"}), 502


@app.route("/api/config", methods=["GET"])
def api_config():
    """حالة السلسلة كاملة (بدون أي أسرار)."""
    return jsonify({
        "brain": (brain_mod.VIDEO_BRAIN_MODEL if brain_mod.VIDEO_BRAIN_URL
                  else ("fenix-core" if brain_mod.CORE_BRAIN_URL else "gemini")),
        "gemini": bool(brain_mod.KEY),
        "brains": {
            "video_brain": bool(brain_mod.VIDEO_BRAIN_URL),
            "core_brain": bool(brain_mod.CORE_BRAIN_URL),
            "gemini": bool(brain_mod.KEY),
        },
        "free_images": True,
    })


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"🎬 Fenix Video running on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
