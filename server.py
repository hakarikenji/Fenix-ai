"""
Fenix — خادم التطبيق
يقدم واجهة الويب ويستضيف /api/* بنفس منطق دوال الإنتاج في api/
(المفتاح يبقى مخفياً في الخادم ولا يظهر في التطبيق إطلاقاً).

التشغيل:  python server.py
"""
import json
import os
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

# استيراد الأدوات المشتركة من مجلد api/
sys.path.insert(0, str(Path(__file__).parent / "api"))
from common import (  # noqa: E402
    EMBEDDED_MODEL_CHAINS,
    KEY,
    gemini_chat,
    gemini_coder,
    gemini_enhance,
    load_prompts,
)
import store  # noqa: E402
import memory as memory_store  # noqa: E402
import evolution as evolution_store  # noqa: E402
import research as research_engine  # noqa: E402
import urllib.request

research_engine.load_config()  # read SERPER_API_KEY from the server environment

import urllib.request

app = Flask(__name__, static_folder="web", static_url_path="")

# ===================== Fenix Core — custom brain routing =====================
# When CUSTOM_LLM_BASE_URL is set, Fenix answers from the fine-tuned open-weight
# model (OpenAI-compatible endpoint, e.g. Ollama/llama.cpp/vLLM). ANY failure —
# connection, timeout, bad response, empty text — falls back to Gemini
# automatically, and the reply is tagged with the brain that actually produced
# it so the UI never lies about who answered.
CUSTOM_LLM_BASE_URL = os.environ.get("CUSTOM_LLM_BASE_URL", "").rstrip("/")
CUSTOM_LLM_MODEL = os.environ.get("CUSTOM_LLM_MODEL", "fenix-core")
CUSTOM_LLM_TIMEOUT = float(os.environ.get("CUSTOM_LLM_TIMEOUT", "120"))
# Optional shared secret for YOUR brain (Bearer token sent on every call).
# The brain server validates it; Gemini is untouched and keeps its own key.
CUSTOM_LLM_API_KEY = os.environ.get("CUSTOM_LLM_API_KEY", "")


def custom_brain_reply(message: str, history: list, attachments: list, style: str, hints: str) -> str | None:
    """Try the custom brain; return None on ANY failure (caller falls back)."""
    if not CUSTOM_LLM_BASE_URL:
        return None
    msgs = [{"role": "system", "content":
             ("You are Fenix, an AI assistant built by Hakari. "
              "Answer in the user's language. Be honest about what you did and did not do.")
             + ("\n" + hints if hints else "")}]
    for m in history[-20:]:
        role = "user" if m.get("role") == "user" else "assistant"
        txt = str(m.get("content") or "").strip()
        if txt and txt != "(see attachment)":
            msgs.append({"role": role, "content": txt})
    if message:
        msgs.append({"role": "user", "content": message})
    try:
        body = json.dumps({"model": CUSTOM_LLM_MODEL, "messages": msgs,
                           "temperature": 0.6, "max_tokens": 2048}).encode()
        headers = {"Content-Type": "application/json"}
        if CUSTOM_LLM_API_KEY:
            headers["Authorization"] = "Bearer " + CUSTOM_LLM_API_KEY
        req = urllib.request.Request(CUSTOM_LLM_BASE_URL + "/chat/completions", data=body,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=CUSTOM_LLM_TIMEOUT) as r:
            out = json.load(r)
        text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        return text or None
    except Exception:
        return None  # honest fallback — the app never shows a half-dead answer


def _brain_tag() -> str:
    return CUSTOM_LLM_MODEL if CUSTOM_LLM_BASE_URL else "gemini"


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


def _sse(data: dict) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """Streaming chat: Server-Sent Events with real token-by-token output from
    Gemini (streamGenerateContent with alt=sse), falling back through the model
    chain. Events: {t:'delta', v:text} | {t:'done'} | {t:'error', v:message}.
    The client can abort the HTTP request to stop generation at any moment."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    attachments = data.get("attachments") or []
    tier = data.get("model") if data.get("model") in ("pro", "flash") else "flash"
    style = data.get("style") if data.get("style") in ("concise", "detailed") else "concise"
    if not message and not attachments:
        return jsonify({"error": "Type a message first"}), 400
    history = history[-40:] if isinstance(history, list) else []

    try:
        token = store.bearer_token()
        user = store.get_user(token)
        hints = ""
        if user:
            hints = memory_store.memory_block(token) + evolution_store.evolution_block(token)
        pid = data.get("projectId")
        if pid:
            if not user:
                return jsonify({"error": "Sign in to work on projects"}), 401
            proj = store.get_project(token, pid)
            if not proj:
                return jsonify({"error": "Project not found"}), 404
            if data.get("save") and data.get("files"):
                store.save_files(token, pid, data["files"])
                proj = store.get_project(token, pid) or proj
            from common import gemini_coder_system, coder_contents  # noqa
            system = gemini_coder_system(
                style, hints, store.project_context(proj))
            contents = coder_contents(history, message, attachments)
            temperature, chain = 0.25, EMBEDDED_MODEL_CHAINS["pro"]
        else:
            from common import gemini_chat_system, chat_contents
            system = gemini_chat_system(style, hints)
            contents = chat_contents(history, message, attachments)
            temperature, chain = 0.7, EMBEDDED_MODEL_CHAINS.get(tier, EMBEDDED_MODEL_CHAINS["flash"])
    except Exception as e:
        return jsonify({"error": f"Connection failed: {e}"}), 502

    @stream_with_context
    def gen():
        body = json.dumps({
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": temperature},
        }).encode()
        last_err = None
        for model in chain:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={KEY}"
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            try:
                got_any = False
                with urllib.request.urlopen(req, timeout=180) as up:
                    for raw in up:
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            chunk = json.loads(line[5:].strip())
                        except Exception:
                            continue
                        parts = (chunk.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts)
                        if text:
                            got_any = True
                            yield _sse({"t": "delta", "v": text})
                if got_any:
                    yield _sse({"t": "done"})
                    return
                last_err = RuntimeError("Empty response from " + model)
            except Exception as e:
                last_err = e
                # Only fall through when nothing was streamed yet.
                if got_any:
                    yield _sse({"t": "done"})
                    return
        yield _sse({"t": "error", "v": str(last_err) or "All models unavailable"})

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Multimodal Fenix chat with full memory: history + new turn → model reply."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    attachments = data.get("attachments") or []
    tier = data.get("model") if data.get("model") in ("pro", "flash") else "flash"
    style = data.get("style") if data.get("style") in ("concise", "detailed") else "concise"
    if not message and not attachments:
        return jsonify({"error": "Type a message first"}), 400
    if not isinstance(history, list):
        history = []
    history = history[-40:]
    try:
        token = store.bearer_token()
        user = store.get_user(token)
        # Signed-in users get their memory + evolution in the system prompt.
        hints = ""
        if user:
            hints = memory_store.memory_block(token) + evolution_store.evolution_block(token)

        # Coder mode: the chat belongs to a project → ultra code-builder persona
        # with the full project context injected into the system instruction.
        pid = data.get("projectId")
        if pid:
            if not user:
                return jsonify({"error": "Sign in to work on projects"}), 401
            proj = store.get_project(token, pid)
            if not proj:
                return jsonify({"error": "Project not found"}), 404
            if data.get("save") and data.get("files"):
                store.save_files(token, pid, data["files"])
                proj = store.get_project(token, pid) or proj
            reply = gemini_coder(
                history, message, attachments, tier, style,
                project_context=store.project_context(proj),
                memory_hint=hints,
            )
            # Evolution: evidence-based observation (only a real repeated signal).
            if user and any(c in message.lower() for c in ("test", "verify", "build", "error", "fix")):
                evolution_store.observe(
                    token, "work_style",
                    "Wants explicit verification after code changes",
                    "Report verification status honestly; label code as Proposed until the user confirms it runs",
                    "User mentions testing/verification in project chats",
                )
            return jsonify({"reply": reply, "brain": "gemini-coder"})

        # Fenix Core: try the private fine-tuned brain first (if configured).
        core = custom_brain_reply(message, history, attachments, style, hints)
        if core:
            return jsonify({"reply": core, "brain": CUSTOM_LLM_MODEL})

        # Fenix Research: auto web search for time-sensitive questions
        # (only when SERPER_API_KEY is configured server-side; never faked).
        res = research_engine.maybe_research(message, gemini_key=KEY, tier=tier)
        if res:
            return jsonify({"reply": res["answer"], "sources": res["sources"], "note": res["note"], "brain": "gemini-research"})

        return jsonify({
            "reply": gemini_chat(history, message, attachments, tier, style, memory_hint=hints),
            "brain": "gemini",
        })
    except Exception as e:
        return jsonify({"error": f"Connection failed: {e}"}), 502


@app.route("/api/enhance", methods=["POST"])
def api_enhance():
    """تحويل أمر المستخدم البسيط إلى Enhanced Prompt عبر Gemini."""
    data = request.get_json(silent=True) or {}
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return jsonify({"error": "Enter some text first"}), 400
    try:
        return jsonify({"result": gemini_enhance(f'User prompt:\n"""\n{user_text}\n"""')})
    except Exception as e:
        return jsonify({"error": f"Gemini connection failed: {e}"}), 502


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
        return jsonify({"error": "Enter some text first"}), 400

    filled = prompts[prompt_id]["template"].replace("{user_input}", user_text)
    try:
        return jsonify({"result": gemini_enhance(filled), "filled_prompt": filled})
    except Exception as e:
        return jsonify({"error": f"Gemini connection failed: {e}"}), 502


@app.route("/api/embedded-config", methods=["GET"])
def api_embedded_config():
    """تكوين وضع التطبيق المدمج: سلسلة النماذج + هل المفتاح متاح على الخادم.
    ملاحظة: المفتاح نفسه لا يُرسل أبداً — العميل يستدعي /api/* على الخادم فقط."""
    return jsonify({
        "embedded": bool(KEY),
        "chains": EMBEDDED_MODEL_CHAINS,
        "research": research_engine.research_is_configured(),
        "brain": _brain_tag(),
        "custom_brain": bool(CUSTOM_LLM_BASE_URL),
    })


# ===================== Fenix Memory (user-controlled) =====================

def _require_user():
    token = store.bearer_token()
    user = store.get_user(token)
    return (token, user) if user else (None, None)


@app.route("/api/memory", methods=["GET"])
def api_memory_list():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    return jsonify(memory_store.list_memory(token, request.args.get("category")))


@app.route("/api/memory", methods=["POST"])
def api_memory_add():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(memory_store.add_entry(
            token, data.get("category"), data.get("text"),
            data.get("source", "user"),
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/memory/<entry_id>", methods=["POST", "DELETE"])
def api_memory_entry(entry_id):
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    if request.method == "DELETE":
        if not memory_store.delete_entry(token, entry_id):
            return jsonify({"error": "Entry not found"}), 404
        return Response(status=204)
    data = request.get_json(silent=True) or {}
    if not memory_store.update_entry(token, entry_id, data.get("text"), data.get("category")):
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/memory/clear", methods=["POST"])
def api_memory_clear():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    data = request.get_json(silent=True) or {}
    deleted = memory_store.clear_category(token, data.get("category"))
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/memory/export", methods=["GET"])
def api_memory_export():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    return jsonify(memory_store.export_memory(token))


# ===================== Fenix Evolution =====================

@app.route("/api/evolution", methods=["GET"])
def api_evolution_profile():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    return jsonify(evolution_store.profile(token))


@app.route("/api/evolution/observe", methods=["POST"])
def api_evolution_observe():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    data = request.get_json(silent=True) or {}
    entry = evolution_store.observe(
        token, data.get("dimension"), data.get("observation"),
        data.get("change"), data.get("reason"),
    )
    if entry is None:
        return jsonify({"ok": False, "note": "Evolution disabled or empty observation"})
    return jsonify({"ok": True, "entry": entry})


@app.route("/api/evolution/toggle", methods=["POST"])
def api_evolution_toggle():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    data = request.get_json(silent=True) or {}
    return jsonify(evolution_store.set_enabled(token, bool(data.get("enabled", True))))


@app.route("/api/evolution/insight/<insight_id>", methods=["POST", "DELETE"])
def api_evolution_insight(insight_id):
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    if request.method == "DELETE":
        if not evolution_store.delete_insight(token, insight_id):
            return jsonify({"error": "Insight not found"}), 404
        return Response(status=204)
    data = request.get_json(silent=True) or {}
    if not evolution_store.update_insight(token, insight_id, data.get("change"), data.get("observation")):
        return jsonify({"error": "Insight not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/evolution/clear", methods=["POST"])
def api_evolution_clear():
    token, user = _require_user()
    if not user:
        return jsonify({"error": "Sign in first"}), 401
    return jsonify({"ok": True, "deleted": evolution_store.clear_all(token)})


# ===================== Accounts & Projects (email sign-in) =====================

def _auth_body(fn):
    """Wrap a handler: pass (token, data); on ValueError return 400 JSON."""
    def wrapper():
        data = request.get_json(silent=True) or {}
        try:
            return fn(store.bearer_token(), data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route("/api/auth/signup", methods=["POST"])
@_auth_body
def api_signup(token, data):
    """Create account {email, password, name?} → {token, user}."""
    return jsonify(store.signup(
        data.get("email"), data.get("password"), data.get("name"),
    ))


@app.route("/api/auth/signin", methods=["POST"])
@_auth_body
def api_signin(token, data):
    """Authenticate {email, password} → {token, user}."""
    return jsonify(store.signin(data.get("email"), data.get("password")))


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    user = store.get_user(store.bearer_token())
    if not user:
        return jsonify({"error": "Not signed in"}), 401
    return jsonify({"user": user})


@app.route("/api/projects", methods=["GET", "POST"])
def api_projects():
    token = store.bearer_token()
    if not store.get_user(token):
        return jsonify({"error": "Sign in first"}), 401
    if request.method == "GET":
        return jsonify(store.list_projects(token))
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(store.create_project(
            token, data.get("name"), data.get("stack"), data.get("description"),
        ))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/projects/<pid>", methods=["GET", "DELETE"])
def api_project(pid):
    token = store.bearer_token()
    if not store.get_user(token):
        return jsonify({"error": "Sign in first"}), 401
    if request.method == "DELETE":
        store.delete_project(token, pid)
        return Response(status=204)
    proj = store.get_project(token, pid)
    if not proj:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(proj)


@app.route("/api/projects/<pid>/files", methods=["POST"])
def api_project_files(pid):
    """Upsert project files: Authorization: Bearer + {files:[{path, content}]} → {ok, changed}."""
    token = store.bearer_token()
    if not store.get_user(token):
        return jsonify({"error": "Sign in first"}), 401
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(store.save_files(token, pid, data.get("files")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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
    print(f"🔥 Fenix running on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
