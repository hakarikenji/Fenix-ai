"""Shared helpers for Fenix AI — chat (multimodal), enhance, prompt library."""
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL_CHAINS = {
    "pro": ["gemini-3.6-pro", "gemini-3.5-pro", "gemini-3.6-flash"],
    "flash": ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
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
You are "Fenix AI" — a brilliant, multimodal AI assistant.
You combine Claude's depth of thought, ChatGPT's dynamism, and Gemini's analytical power.

Your rules:
1. Personality: confident, witty, quick, and deeply human — never robotic or templated.
2. Accuracy: never invent facts — if unsure, say so plainly.
3. Formatting: use clean Markdown when it helps (headings, lists, tables, code blocks).
4. Language: always answer in the language the user writes in.
5. Smart brevity: answer fully but without filler — unnecessary detail is your enemy.
6. Multimodal: when the user shares images or documents, analyze them microscopically before answering; ground every claim in what is actually visible or written.
{style_hint}
"""

STYLE_HINTS = {
    "concise": "7. Style: keep answers tight and scannable — lead with the answer, then minimal supporting detail.",
    "detailed": "7. Style: give thorough, well-structured answers with examples, context and step-by-step detail where useful.",
}

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
) -> str:
    """Multimodal chat with full memory: history + new message/attachments."""
    system = FENIX_SYSTEM_INSTRUCTION.replace(
        "{style_hint}", STYLE_HINTS.get(style, STYLE_HINTS["concise"])
    )
    return _generate(system, _chat_contents(history, message, attachments), 0.7, tier)


def gemini_enhance(contents: str, tier: str = "flash") -> str:
    """Enhance a user prompt with the engineer persona (single-shot, no memory)."""
    return _generate(ENHANCER_SYSTEM_INSTRUCTION, contents, 0.3, tier)
