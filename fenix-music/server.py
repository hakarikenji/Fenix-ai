"""
Fenix Music — خادم التطبيق (نفس كور Fenix)
يقدم استوديو الويب + واجهة /api/* : كلمات، برومبت صوتي، توليد موسيقى (Modal)، محادثة.

التشغيل:  python server.py
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).parent / "api"))
from brain import KEY, audio_prompt_system, chat_reply, lyric_system  # noqa: E402

app = Flask(__name__, static_folder="web", static_url_path="")

# ===================== Fenix Brains (private, default) =====================
# سلسلة العقول: عقل الموسيقى المدرّب أولاً → عقل Fenix Core → Gemini كاحتياط أخير.
# أي فشل في حلقة ينتقل للتي بعده بصمت. ضع القيمة "off" لتعطيل أي حلقة.
FENIX_CORE_BRAIN_URL = "https://yasinnait30--fenix-brain.modal.run"
FENIX_MUSIC_BRAIN_URL = "https://yasinnait30--fenix-music-brain.modal.run"


def _brain(url_env: str, default: str) -> str:
    raw = os.environ.get(url_env, default).strip()
    return "" if raw.lower() in ("off", "none", "disabled") else raw.rstrip("/")


MUSIC_BRAIN_URL = _brain("MUSIC_BRAIN_URL", FENIX_MUSIC_BRAIN_URL)      # عقل الموسيقى المدرّب
CORE_BRAIN_URL = _brain("CORE_BRAIN_URL", FENIX_CORE_BRAIN_URL)          # عقل الكور
MUSIC_BRAIN_MODEL = os.environ.get("MUSIC_BRAIN_MODEL", "fenix-music")
MUSIC_BRAIN_TIMEOUT = float(os.environ.get("MUSIC_BRAIN_TIMEOUT", "300"))
MUSIC_BRAIN_API_KEY = os.environ.get("MUSIC_BRAIN_API_KEY", "")


def music_brain_reply(system: str, user: str, temperature: float) -> str | None:
    """جرّب سلسلة العقول المدرّبة بالترتيب؛ None = فشل الكل (النادِ يرجع لـ Gemini)."""
    body = json.dumps({
        "model": MUSIC_BRAIN_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature, "max_tokens": 2048,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if MUSIC_BRAIN_API_KEY:
        headers["Authorization"] = "Bearer " + MUSIC_BRAIN_API_KEY
    for base_url in (MUSIC_BRAIN_URL, CORE_BRAIN_URL):
        if not base_url:
            continue
        try:
            req = urllib.request.Request(base_url + "/chat/completions",
                                         data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=MUSIC_BRAIN_TIMEOUT) as r:
                out = json.load(r)
            text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
            if text:
                return text
        except Exception:
            continue
    return None


def _brain_tag() -> str:
    if MUSIC_BRAIN_URL:
        return MUSIC_BRAIN_MODEL
    if CORE_BRAIN_URL:
        return "fenix-core"
    return "gemini"


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


# ===================== Generation =====================

@app.route("/api/lyrics", methods=["POST"])
def api_lyrics():
    """كلمات أغنية أصلية: {genre, mood, language, topic} → {lyrics, brain}."""
    data = request.get_json(silent=True) or {}
    genre = (data.get("genre") or "phonk").strip()[:40]
    mood = (data.get("mood") or "dark aggressive").strip()[:60]
    language = (data.get("language") or "Arabic").strip()[:20]
    topic = (data.get("topic") or "").strip()[:300]
    system = lyric_system(genre, mood, language, topic)
    user = f"Write {genre} lyrics about: {topic or 'your best idea'}."
    text = music_brain_reply(system, user, 0.95)  # private brain first
    if not text:
        if not KEY:
            return jsonify({"error": "No music brain configured"}), 502
        try:
            from brain import _gen
            text = _gen(system, user, 0.95)
        except Exception as e:
            return jsonify({"error": f"Brain connection failed: {e}"}), 502
    return jsonify({"lyrics": text, "brain": _brain_tag()})


@app.route("/api/audio-prompt", methods=["POST"])
def api_audio_prompt():
    """برومبت صوتي احترافي من وصف المستخدم: → {prompt, brain}."""
    data = request.get_json(silent=True) or {}
    genre = (data.get("genre") or "phonk").strip()[:40]
    mood = (data.get("mood") or "dark aggressive").strip()[:60]
    try:
        bpm = int(data.get("bpm") or 140)
    except (TypeError, ValueError):
        bpm = 140
    bpm = max(60, min(200, bpm))
    try:
        duration = int(data.get("duration") or 20)
    except (TypeError, ValueError):
        duration = 20
    duration = max(5, min(30, duration))
    system = audio_prompt_system(genre, mood, bpm, duration)
    user = f"Describe a {genre} beat, mood: {mood}, {bpm} BPM, {duration}s."
    text = music_brain_reply(system, user, 0.9)
    if not text:
        if not KEY:
            return jsonify({"error": "No music brain configured"}), 502
        try:
            from brain import _gen
            text = _gen(system, user, 0.9)
        except Exception as e:
            return jsonify({"error": f"Brain connection failed: {e}"}), 502
    return jsonify({"prompt": text, "brain": _brain_tag()})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """محادثة مذيع الموسيقى: {message, history} → {reply, brain}."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    if not message:
        return jsonify({"error": "Type a message first"}), 400
    if not isinstance(history, list):
        history = []
    system = ("You are Fenix Music, the AI music studio built by Hakari. Warm radio-host "
              "personality, tasteful producer knowledge. Answer in the user's language.")
    reply = music_brain_reply(system, message, 0.8)
    if not reply:
        if not KEY:
            return jsonify({"error": "No music brain configured"}), 502
        try:
            reply = chat_reply(history[-20:], message)
        except Exception as e:
            return jsonify({"error": f"Brain connection failed: {e}"}), 502
    return jsonify({"reply": reply, "brain": _brain_tag()})


# ===================== Music generation (Modal MusicGen worker) =====================

def _hf_musicgen(prompt: str) -> bytes | None:
    """البديل المجاني: MusicGen عبر Hugging Face Inference API (يحتاج HF_TOKEN مجاني)."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        return None
    body = json.dumps({"inputs": prompt}).encode()
    req = urllib.request.Request(
        "https://api-inference.huggingface.co/models/facebook/musicgen-small",
        data=body, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=600) as r:
        audio = r.read()
    return audio if len(audio) > 1000 else None


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """توليد الموسيقى: {prompt, duration, seed?} → {url}. WAV bytes من أقرب مولّد:
    1) Modal GPU worker (MUSIC_GEN_URL)  2) Hugging Face MusicGen المجاني (HF_TOKEN)."""
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()[:800]
    if not prompt:
        return jsonify({"error": "Prompt is empty"}), 400
    try:
        duration = int(data.get("duration") or 20)
    except (TypeError, ValueError):
        duration = 20
    duration = max(5, min(30, duration))
    worker_url = os.environ.get("MUSIC_GEN_URL", "").rstrip("/")
    t0 = time.time()
    try:
        audio = None
        if worker_url:
            body = json.dumps({"prompt": prompt, "duration": duration,
                               "seed": data.get("seed")}).encode()
            headers = {"Content-Type": "application/json"}
            token = os.environ.get("MUSIC_GEN_API_KEY", "")
            if token:
                headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(worker_url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as r:
                audio = r.read()
            if len(audio) < 1000:
                audio = None
        if audio is None:
            audio = _hf_musicgen(prompt)  # البديل المجاني
        if audio is None:
            return jsonify({"error": "No generator available: set MUSIC_GEN_URL (Modal) or HF_TOKEN (free)"}), 503
        out = Path("/tmp") / f"fenix-music-{int(time.time())}.wav"
        out.write_bytes(audio)
        return jsonify({"url": f"/audio/{out.name}", "seconds": round(time.time() - t0, 1)})
    except Exception as e:
        return jsonify({"error": f"Generation failed: {e}"}), 502


@app.route("/audio/<path:name>")
def serve_audio(name):
    return send_from_directory("/tmp", name, mimetype="audio/wav")


@app.route("/api/models")
def api_models():
    """Диагностика: какие модели доступны этому ключу Gemini (без секретов)."""
    from brain import API, MODEL_CHAIN
    if not KEY:
        return jsonify({"error": "GEMINI_API_KEY not set"}), 503
    try:
        with urllib.request.urlopen(f"{API}?key={KEY}", timeout=30) as r:
            out = json.load(r)
        names = [m.get("name", "").split("/")[-1]
                 for m in out.get("models", [])
                 if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        return jsonify({"available": names, "chain": MODEL_CHAIN})
    except Exception as e:
        return jsonify({"error": str(e), "chain": MODEL_CHAIN}), 502


@app.route("/api/config", methods=["GET"])
def api_config():
    """تكوين الواجهة: هل الخادم كامل التجهيز؟ (بدون أي أسرار)."""
    return jsonify({
        "brain": _brain_tag(),
        "custom_brain": bool(MUSIC_BRAIN_URL),
        "generator": bool(os.environ.get("MUSIC_GEN_URL")),
        "gemini": bool(KEY),
    })


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"🎵 Fenix Music running on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
