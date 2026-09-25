"""Fenix tool registry and safe dispatch layer.

Tools are explicit capabilities, not hidden side effects. Every tool declares an
input schema, an output schema, a safety boundary and an availability state.
The registry keeps the chat path honest: unavailable tools fail with a clear
status instead of returning fabricated success.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_API_DIR = str(Path(__file__).resolve().parent)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)
from dataclasses import dataclass
from typing import Any, Callable

import json
import os
import urllib.parse
import urllib.request

import memory as memory_store
import research as research_engine
import sandbox
import store


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    safety: tuple[str, ...]
    requires_auth: bool = True
    available: Callable[[], bool] = lambda: False


class ToolError(Exception):
    def __init__(self, message: str, code: str = "tool_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _nonempty(value: Any, field: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        raise ToolError(f"{field} is required", "invalid_input")
    if len(text) > limit:
        raise ToolError(f"{field} is too long", "invalid_input")
    return text


def _project(token: str, project_id: str) -> dict:
    project = store.get_project(token, project_id)
    if not project:
        raise ToolError("Project not found", "not_found", 404)
    return project


def _dispatch_research(token: str | None, args: dict[str, Any]) -> dict[str, Any]:
    query = _nonempty(args.get("query"), "query", 1000)
    if not research_engine.research_is_configured():
        raise ToolError("Web research is not configured; add SERPER_API_KEY on the server", "unavailable", 503)
    # The key is never accepted from a client and is never returned.
    result = research_engine.run_research(query, tier=args.get("tier", "flash"), gemini_key=os.environ.get("GEMINI_API_KEY", ""))
    return {"query": query, "answer": result["answer"], "sources": result["sources"], "status": "completed"}


def _dispatch_memory(token: str | None, args: dict[str, Any]) -> dict[str, Any]:
    if not token or not store.get_user(token):
        raise ToolError("Sign in first", "auth_required", 401)
    operation = str(args.get("operation") or "retrieve").lower()
    if operation == "retrieve":
        entries = memory_store.list_memory(token, args.get("category"))
        return {"entries": entries, "status": "completed"}
    if operation == "create":
        entry = memory_store.add_entry(token, args.get("category"), args.get("text"), "user")
        return {"entry": entry, "status": "completed"}
    if operation == "update":
        ok = memory_store.update_entry(token, str(args.get("id") or ""), args.get("text"), args.get("category"))
        if not ok:
            raise ToolError("Memory entry not found", "not_found", 404)
        return {"ok": True, "status": "completed"}
    if operation == "delete":
        ok = memory_store.delete_entry(token, str(args.get("id") or ""))
        if not ok:
            raise ToolError("Memory entry not found", "not_found", 404)
        return {"ok": True, "status": "completed"}
    if operation == "export":
        return {"memory": memory_store.export_memory(token), "status": "completed"}
    raise ToolError("operation must be retrieve, create, update, delete, or export", "invalid_input")


def _dispatch_file(token: str | None, args: dict[str, Any]) -> dict[str, Any]:
    if not token or not store.get_user(token):
        raise ToolError("Sign in first", "auth_required", 401)
    project_id = _nonempty(args.get("projectId"), "projectId", 120)
    project = _project(token, project_id)
    operation = str(args.get("operation") or "inspect").lower()
    files = project.get("files", {})
    if operation == "list":
        return {"files": [{"path": p, "bytes": len(v.encode())} for p, v in files.items()], "status": "completed"}
    path = _nonempty(args.get("path"), "path", 200)
    if operation == "read":
        if path not in files:
            raise ToolError("File not found", "not_found", 404)
        return {"path": path, "content": files[path], "status": "completed"}
    if operation == "write":
        content = str(args.get("content") or "")
        if len(content.encode()) > store.MAX_FILE_BYTES:
            raise ToolError("File exceeds the 200 KB project limit", "limit_exceeded")
        changed = store.save_files(token, project_id, [{"path": path, "content": content}])["changed"]
        return {"path": path, "changed": bool(changed), "status": "completed"}
    if operation == "delete":
        store.delete_file(token, project_id, path)
        return {"path": path, "status": "completed"}
    raise ToolError("operation must be list, read, write, or delete", "invalid_input")


def _dispatch_execution(token: str | None, args: dict[str, Any]) -> dict[str, Any]:
    if not sandbox.configured():
        raise ToolError(
            "Code execution is unavailable until an isolated sandbox runtime is configured",
            "unavailable", 503,
        )
    language = str(args.get("language") or "").strip().lower()
    code = _nonempty(args.get("code"), "code", sandbox.MAX_CODE_BYTES)
    try:
        result = sandbox.execute(
            language, code, stdin=str(args.get("stdin") or ""),
            timeout_ms=args.get("timeoutMs"),
        )
    except ValueError as exc:
        raise ToolError(str(exc), "invalid_input", 400) from exc
    except RuntimeError as exc:
        raise ToolError(str(exc), "sandbox_unavailable", 502) from exc
    return result


def _dispatch_image(token: str | None, args: dict[str, Any]) -> dict[str, Any]:
    """Image generation via Pollinations (server-side key only).

    A key is free at enter.pollinations.ai. Set POLLINATIONS_API_KEY in the
    server environment. Without a key this fails honestly with setup
    instructions — it never pretends an image was generated.
    """
    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if not api_key:
        raise ToolError(
            "Image generation needs a (free) API key: get one at enter.pollinations.ai"
            " and add POLLINATIONS_API_KEY in Settings → Environment",
            "unavailable", 503,
        )
    prompt = _nonempty(args.get("prompt"), "prompt", 600)
    try:
        width = max(256, min(1024, int(args.get("width") or 768)))
        height = max(256, min(1024, int(args.get("height") or 768)))
    except (TypeError, ValueError):
        width = height = 768
    url = ("https://gen.pollinations.ai/image/"
           + urllib.parse.quote(prompt + ", detailed, no text")
           + f"?model=flux&width={width}&height={height}&nologo=true&seed={int(time.time()) % 100000}")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "FenixAI/1.0", "Authorization": "Bearer " + api_key,
        })
        with urllib.request.urlopen(req, timeout=120) as r:
            img = r.read()
        if len(img) < 1000:
            raise RuntimeError("empty image")
    except Exception as exc:
        raise ToolError("Image generation failed — try again in a moment", "provider_failed", 502) from exc
    name = f"fenix-img-{int(time.time())}.jpg"
    try:
        Path("/tmp", name).write_bytes(img)
    except Exception as exc:
        raise ToolError("Could not store the generated image", "storage_failed", 500) from exc
    return {"status": "completed", "url": f"/audio/{name}", "width": width, "height": height}


TOOLS: dict[str, tuple[ToolSpec, Callable[[str | None, dict[str, Any]], dict[str, Any]]]] = {
    "web_research": (ToolSpec(
        "web_research", "Search the web and return grounded, numbered sources.",
        {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
        {"type": "object", "required": ["answer", "sources"]},
        ("server-side search key", "no client secrets", "no fabricated sources"),
        requires_auth=False, available=research_engine.research_is_configured,
    ), _dispatch_research),
    "memory": (ToolSpec(
        "memory", "Explicitly retrieve or change user-controlled persistent memory.",
        {"type": "object", "required": ["operation"], "properties": {"operation": {"enum": ["retrieve", "create", "update", "delete", "export"]}, "id": {"type": "string"}, "category": {"type": "string"}, "text": {"type": "string"}}},
        {"type": "object", "required": ["status"]},
        ("explicit user action", "never store secrets", "user can view/export/delete"),
        available=lambda: True,
    ), _dispatch_memory),
    "files": (ToolSpec(
        "files", "Inspect or change files inside a user-owned Fenix project.",
        {"type": "object", "required": ["projectId", "operation"], "properties": {"projectId": {"type": "string"}, "operation": {"enum": ["list", "read", "write", "delete"]}, "path": {"type": "string"}, "content": {"type": "string"}}},
        {"type": "object", "required": ["status"]},
        ("authenticated owner only", "200 KB per file", "no host filesystem paths"),
        available=lambda: True,
    ), _dispatch_file),
    "code_execution": (ToolSpec(
        "code_execution", "Run code in a configured isolated sandbox.",
        {"type": "object", "required": ["language", "code"], "properties": {"language": {"enum": ["python", "javascript"]}, "code": {"type": "string"}, "timeoutMs": {"type": "integer", "maximum": 10000}}},
        {"type": "object", "required": ["status", "exitCode", "stdout", "stderr"]},
        ("isolated container/VM provider", "no host secrets", "no unrestricted filesystem/network"),
        available=sandbox.configured,
    ), _dispatch_execution),
    "image_generation": (ToolSpec(
        "image_generation", "Generate an image from a text prompt.",
        {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}}},
        {"type": "object", "required": ["status", "url"]},
        ("server-side POLLINATIONS_API_KEY (free at enter.pollinations.ai)", "no client secrets", "never claim generation without a URL"),
        available=lambda: bool(os.environ.get("POLLINATIONS_API_KEY", "").strip()),
    ), _dispatch_image),
    "system_utility": (ToolSpec(
        "system_utility", "Inspect capability health without exposing secrets.",
        {"type": "object", "properties": {}}, {"type": "object", "required": ["status"]},
        ("read-only status only",), requires_auth=False, available=lambda: True,
    ), lambda _token, _args: {"status": "completed", "tools": list(TOOLS)}),
}


def tool_catalog() -> list[dict[str, Any]]:
    return [{"name": s.name, "description": s.description, "inputSchema": s.input_schema,
             "outputSchema": s.output_schema, "safety": list(s.safety),
             "requiresAuth": s.requires_auth, "available": bool(s.available())}
            for s, _ in TOOLS.values()]


def dispatch(name: str, args: dict[str, Any] | None, token: str | None) -> dict[str, Any]:
    key = str(name or "").strip().lower()
    if key not in TOOLS:
        raise ToolError(f"Unknown tool: {key}", "unknown_tool", 404)
    spec, handler = TOOLS[key]
    if spec.requires_auth and (not token or not store.get_user(token)):
        raise ToolError("Sign in first", "auth_required", 401)
    started = time.perf_counter()
    try:
        result = handler(token, args or {})
        result.setdefault("tool", key)
        result.setdefault("latencyMs", round((time.perf_counter() - started) * 1000, 2))
        return result
    except ToolError:
        raise
    except ValueError as exc:
        raise ToolError(str(exc), "invalid_input", 400) from exc
    except Exception as exc:
        raise ToolError(f"Tool failed: {type(exc).__name__}", "tool_failed", 502) from exc
