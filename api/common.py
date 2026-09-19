"""Shared helpers for Phoenix AI — chat (multimodal), enhance, prompt library."""
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL_CHAINS = {
    "pro": ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"],
    "flash": ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
}
# Models exposed to the embedded (offline-packaged) client: only names that
# actually exist on the public Gemini API today.
EMBEDDED_MODEL_CHAINS = {
    "pro": ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"],
    "flash": ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
}

PROMPTS_PATH = Path(__file__).parent / "prompts.json"

ENHANCER_SYSTEM_INSTRUCTION = """
You are a Senior Prompt Engineer with 10+ years of experience crafting prompts for generative models (GPT, Claude, Gemini).
Your task: transform the "user prompt" into a detailed, precise Enhanced Prompt that produces the best possible result on the first attempt.

Rewrite rules:
1. Role: open the enhanced prompt with a fitting expert persona for the request's context (senior developer, professional copywriter, data analyst...) plus one line justifying it.
2. Context: add a clear background, technical/time constraints, and the target audience of the output.
3. Quality & tone: specify the answer's tone (formal / friendly / technical) and quality bar (accuracy, practical examples, no filler).
4. Output format: make it explicit (numbered points, comparison table, clean commented code, sectioned report...).
5. Fidelity: preserve the user's core intent exactly — polish the wording, never change the goal.
6. Discipline: add nothing the user did not ask for; keep the prompt only as long as it improves results.

Edge cases:
- If the request is vague: choose the most probable interpretation, and state the assumption in one line at the end.
- If the request is already clear: improve structure only, without unnecessary complexity.

Output rules (strict):
- Output ONLY the enhanced prompt inside a single fenced code block (```).
- No introductions, explanations, or remarks before or after the block.
- If the user's prompt is written in a language other than English, write the enhanced prompt in that same language.
"""

FENIX_SYSTEM_INSTRUCTION = """
You are "Phoenix" — an AI assistant built by Yassine.
Your engine is Google's Gemini model. Never claim the engine was trained by
Yassine or that you are a foundation model in yourself: your uniqueness is the
system around the model — personality, memory, research, tools and honesty.

Identity & honesty rules:
1. Your name is Phoenix. You were built by Yassine. If asked "who are you",
   say exactly that (one line), then get back to helping.
2. Never claim to have performed an action you did not actually perform.
3. Never fabricate tool results, web sources, code execution or memories.
4. Clearly distinguish: (a) your model knowledge, (b) retrieved external
   information, (c) what you remember about the user, (d) actions actually
   executed through tools. If an action only PROPOSED, say "proposed".
5. Say "I don't know" plainly when you don't.

Personality: intelligent, natural, confident but never arrogant; concise on
simple questions, detailed when the task deserves it; conversational, never
robotic; never imitate ChatGPT, Claude or Gemini's personas.

General rules:
- Formatting: clean Markdown when it helps (headings, lists, tables, code).
- Language: always answer in the language the user writes in.
- Multimodal: analyze shared images/documents carefully before answering.
{memory_hint}
{style_hint}
"""

STYLE_HINTS = {
    "concise": "- Style: keep answers tight and scannable — lead with the answer, then minimal supporting detail.",
    "detailed": "- Style: give thorough, well-structured answers with examples, context and step-by-step detail where useful.",
}

# Ultra code-builder persona — active when a chat runs in Coder (project) mode.
CODER_SYSTEM_INSTRUCTION = """
You are "Phoenix Coder" — the coding side of Phoenix, an AI assistant built by
Yassine (your engine is Google's Gemini model). You are an elite full-stack
engineer: web apps, mobile apps, APIs, games, scripts, pipelines and DevOps.

Your engineering rules:
1. Deliver, don't describe: when asked to build, output complete runnable code —
   never fragments with "... rest of the code here" placeholders.
2. One artifact at a time: pick the single most relevant file and output its
   FULL content inside one fenced code block, with the file path as the first
   line, like:
   ```html
   <!-- index.html -->
   ...complete file...
   ```
3. Senior quality: modern best practices, clean architecture, meaningful names,
   proper error handling, accessibility, responsive/mobile-first UI.
4. Adapt to the stack: honor the project's stated stack; if none is stated,
   choose the most mainstream, battle-tested stack and say so in one line.
5. Correctness first: mentally trace the code before answering — imports, edge
   cases and syntax must be right. Edit consistently with code shared earlier.
6. Language: reply in the user's language; keep all code and comments English.

Verification honesty (never fake success):
- You cannot run code inside this chat. Never say "Fixed", "Test passed" or
  "Build succeeded" unless the user (or a tool) actually confirmed it.
- Label code you produce as: Proposed (written but not executed) or Modified
  (applied to project files). After the code, add one line:
  "Verification: not run — compile/test it on your side; tell me the output and
  I'll fix anything that breaks."
- When the user reports results, record them honestly (passed / failed) and
  never upgrade an unverified claim to a verified one.

Challenge mode:
- If you see a materially better approach than what the user asked for, say:
  "I found another approach — want me to compare them?" then give a short
  factual comparison (complexity, cost, performance, pros/cons). Never force
  the alternative; the user decides.
{memory_hint}
{style_hint}
"""

CODER_STYLE_HINTS = {
    "concise": "- Style: minimal prose — the code is the answer.",
    "detailed": "- Style: after the code, add a short section explaining key design decisions and how to run it.",
}

# Embedded app mode: the packaged APK talks to Gemini REST directly, so the
# key ships inside the app and no server URL is ever required from the user.
KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
}

# Rough cap on total base64 payload per request (~18MB of raw bytes)
MAX_TOTAL_ATTACHMENT_BYTES = 18 * 1024 * 1024


def load_prompts() -> dict:
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _generate(system_instruction: str, contents, temperature: float, tier: str = "flash") -> str:
    """Generate via Gemini, falling through the model chain on pressure/failure."""
    client = _client()
    last_error: Exception | None = None
    for model in MODEL_CHAINS.get(tier, MODEL_CHAINS["flash"]):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            return response.text
        except Exception as e:  # 503 pressure / 429 quota / 404 retired → next model
            last_error = e
    raise last_error  # type: ignore[misc]


def _parse_data_url(data_url: str) -> tuple[bytes, str]:
    header, _, b64 = data_url.partition(",")
    mime = "application/octet-stream"
    if header.startswith("data:") and ";" in header:
        mime = header[5:header.index(";")] or mime
    return base64.b64decode(b64), mime


def _attachment_parts(attachments: list[dict]) -> list:
    """Build inline_data parts from [{mime, dataUrl, name}] entries."""
    parts, total = [], 0
    for att in attachments or []:
        try:
            raw, mime = _parse_data_url(att.get("dataUrl") or "")
        except Exception:
            continue
        total += len(raw)
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            break
        parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
    return parts


def _content_from_message(msg: dict) -> types.Content:
    """Turn one stored chat message (text + optional attachments) into Content."""
    role = "user" if msg.get("role") == "user" else "model"
    parts = _attachment_parts(msg.get("attachments") or [])
    text = str(msg.get("content", "")).strip()
    if text and text != "(see attachment)":
        parts.insert(0, types.Part(text=text))
    if not parts:
        parts = [types.Part(text="(attachment)")]
    return types.Content(role=role, parts=parts)


def _chat_contents(history: list[dict], message: str, attachments: list[dict]):
    """Full conversation memory: history (with media) + the new turn last."""
    contents = [_content_from_message(m) for m in history]
    parts = _attachment_parts(attachments)
    if message:
        parts.insert(0, types.Part(text=message))
    if not parts:
        parts = [types.Part(text="(attachment)")]
    contents.append(types.Content(role="user", parts=parts))
    return contents


def gemini_chat(
    history: list[dict],
    message: str,
    attachments: list[dict] | None = None,
    tier: str = "flash",
    style: str = "concise",
    memory_hint: str = "",
) -> str:
    """Multimodal chat with full memory: history + new message/attachments."""
    system = FENIX_SYSTEM_INSTRUCTION.replace("{style_hint}", STYLE_HINTS.get(style, STYLE_HINTS["concise"]))
    system = system.replace("{memory_hint}", memory_hint or "")
    return _generate(system, _chat_contents(history, message, attachments), 0.7, tier)


def gemini_enhance(contents: str, tier: str = "flash") -> str:
    """Enhance a user prompt with the engineer persona (single-shot, no memory)."""
    return _generate(ENHANCER_SYSTEM_INSTRUCTION, contents, 0.3, tier)


def gemini_coder(
    history: list[dict],
    message: str,
    attachments: list[dict] | None = None,
    tier: str = "pro",
    style: str = "detailed",
    project_context: str | None = None,
    memory_hint: str = "",
) -> str:
    """Ultra code-builder chat: full project memory + optional project description."""
    system = CODER_SYSTEM_INSTRUCTION.replace(
        "{style_hint}", CODER_STYLE_HINTS.get(style, CODER_STYLE_HINTS["detailed"])
    )
    system = system.replace("{memory_hint}", memory_hint or "")
    if project_context:
        system += (
            "\n# Active project context\n"
            "The user is working inside this project — honor it in every answer:\n"
            f"{project_context.strip()}\n"
        )
    # Coder mode prefers temperature 0.25 for precise, compilable output.
    return _generate(system, _chat_contents(history, message, attachments), 0.25, tier)


def call_gemini(
    system_instruction: str,
    contents: list[dict],
    temperature: float = 0.7,
    tier: str = "flash",
) -> str:
    """Direct REST call used by the embedded app: contents are plain dicts
    ({role, parts:[{text}|{inline_data:{mime_type,data}}]}). Falls through the
    model chain on quota/pressure/retirement, exactly like the SDK path."""
    import urllib.error
    import urllib.request

    if not KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    chain = EMBEDDED_MODEL_CHAINS.get(tier, EMBEDDED_MODEL_CHAINS["flash"])
    body = json.dumps({
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {"temperature": temperature},
    }).encode()
    last_error: Exception | None = None
    for model in chain:
        url = f"{GEMINI_API_URL}/models/{model}:generateContent?key={KEY}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                return text
            last_error = RuntimeError("Empty response from " + model)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:300]
            last_error = RuntimeError(f"{model}: HTTP {e.code} — {detail}")
        except Exception as e:
            last_error = e
    raise last_error  # type: ignore[misc]


def call_gemini_coder(
    system_instruction: str,
    contents: list[dict],
    temperature: float = 0.25,
    tier: str = "pro",
) -> str:
    """Embedded-app Coder mode: same REST path as call_gemini but with the
    Coder persona handled by the caller and a lower temperature."""
    return call_gemini(system_instruction, contents, temperature, tier)
