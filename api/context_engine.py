"""Unified, provenance-labelled context construction for Fenix Core."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_API_DIR = str(Path(__file__).resolve().parent)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

import evolution as evolution_store
import memory as memory_store
import store

MAX_CONTEXT_CHARS = 28_000


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def build_context(
    token: str | None,
    message: str,
    history: list[dict[str, Any]] | None = None,
    project: dict[str, Any] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    research: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return labelled context plus a compact system hint.

    This layer is intentionally provider-neutral. It does not decide which tool
    to call; it makes the evidence supplied to the model explicit and auditable.
    """
    sections: list[dict[str, Any]] = []
    if message:
        sections.append({"label": "USER_INPUT", "content": _clip(message, 3000)})
    if history:
        for item in history[-12:]:
            content = _clip(item.get("content", ""), 1200)
            if content and content != "(see attachment)":
                sections.append({"label": "CONVERSATION", "role": item.get("role", "user"), "content": content})
    if token and store.get_user(token):
        memory = memory_store.memory_block(token, 3000)
        if memory:
            sections.append({"label": "MEMORY", "content": memory})
        evolution = evolution_store.evolution_block(token, 1600)
        if evolution:
            sections.append({"label": "EVOLUTION", "content": evolution})
    if project:
        sections.append({"label": "PROJECT_CONTEXT", "content": _clip(store.project_context(project), 9000)})
    for result in tool_results or []:
        sections.append({"label": "TOOL_RESULT", "tool": result.get("tool", "unknown"),
                         "content": _clip(str(result), 4000)})
    if research:
        sections.append({"label": "WEB_RESEARCH", "content": _clip(research.get("answer", ""), 5000),
                         "sources": research.get("sources", [])})
    if execution:
        sections.append({"label": "EXECUTION_RESULT", "content": _clip(str(execution), 4000)})
    for item in files or []:
        sections.append({"label": "FILE", "content": _clip(str(item), 2500)})

    hint_parts = [
        "Use source labels exactly: USER_INPUT, CONVERSATION, MEMORY, EVOLUTION, PROJECT_CONTEXT, "
        "WEB_RESEARCH, FILE, EXECUTION_RESULT, TOOL_RESULT.",
        "Only claim an action happened when its labelled result proves it. "
        "Never invent sources, memory, files, or execution output.",
    ]
    for section in sections:
        hint_parts.append(f"[{section['label']}]\n{section['content']}")
    hint = "\n\n".join(hint_parts)
    if len(hint) > MAX_CONTEXT_CHARS:
        hint = hint[:MAX_CONTEXT_CHARS] + "\n[context truncated by Fenix safety limit]"
    return {"sections": sections, "system_hint": hint, "truncated": len(hint) > MAX_CONTEXT_CHARS}
