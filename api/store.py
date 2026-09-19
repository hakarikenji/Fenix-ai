"""
Fenix AI — lightweight account store (JSON file backend).

Server-side persistence is a bonus for web users; the APK keeps working fully
offline with its embedded brain. Accounts are keyed by email, passwords are
salted PBKDF2 hashes — plaintext is never stored.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time

DATA_DIR = os.environ.get("FENIX_DATA_DIR", ".data")
ACCOUNTS_PATH = os.path.join(DATA_DIR, "accounts.json")
PROJECTS_PATH = os.path.join(DATA_DIR, "projects.json")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ITERS = 120_000

_lock = threading.Lock()


def _ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _read(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERS)
    return dk.hex()


def new_salt() -> str:
    return secrets.token_bytes(16).hex()


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def signup(email: str, password: str, name: str | None = None) -> dict:
    """Create an account → {token, user}. Raises ValueError with a friendly message."""
    email = (email or "").strip().lower()
    if not valid_email(email):
        raise ValueError("Enter a valid email address")
    if len(password or "") < 6:
        raise ValueError("Password must be at least 6 characters")
    with _lock:
        accounts = _read(ACCOUNTS_PATH, {})
        if email in accounts:
            raise ValueError("This email is already registered — try signing in")
        salt = new_salt()
        accounts[email] = {
            "name": (name or "").strip() or email.split("@")[0],
            "salt": salt,
            "hash": _hash_password(password, salt),
            "created": time.time(),
        }
        _write(ACCOUNTS_PATH, accounts)
    return signin(email, password)


def signin(email: str, password: str) -> dict:
    """Authenticate → {token, user}. Raises ValueError with a friendly message."""
    email = (email or "").strip().lower()
    with _lock:
        accounts = _read(ACCOUNTS_PATH, {})
        acc = accounts.get(email)
        if not acc or _hash_password(password or "", acc["salt"]) != acc["hash"]:
            raise ValueError("Wrong email or password")
        token = secrets.token_urlsafe(32)
        tokens = _read(_tokens_path(), {})
        tokens[token] = {"email": email, "created": time.time()}
        _write(_tokens_path(), tokens)
    return {"token": token, "user": {"email": email, "name": acc.get("name", email)}}


def _tokens_path() -> str:
    return os.path.join(DATA_DIR, "tokens.json")


def get_user(token: str) -> dict | None:
    """Resolve a bearer token → {email, name} or None."""
    if not token:
        return None
    tokens = _read(_tokens_path(), {})
    info = tokens.get(token)
    if not info:
        return None
    email = info["email"]
    acc = _read(ACCOUNTS_PATH, {}).get(email, {})
    return {"email": email, "name": acc.get("name", email)}


def bearer_token() -> str | None:
    """Read the OAuth2 bearer token from a Flask request, if present."""
    try:
        from flask import request

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
    except Exception:
        pass
    return None


# ============================ Projects ============================

MAX_FILE_BYTES = 200_000
MAX_FILES = 40


def _user_key(token_or_email: str) -> str:
    """Resolve a bearer token to its owner's email; fall back to a raw email."""
    user = get_user(token_or_email or "")
    if user:
        return user["email"]
    return (token_or_email or "").strip().lower()


def list_projects(token: str) -> list[dict]:
    """Projects owned by this account, newest first."""
    email = _user_key(token)
    with _lock:
        projects = _read(PROJECTS_PATH, {})
    return [
        {"id": p["id"], "name": p["name"], "stack": p.get("stack", ""),
         "description": p.get("description", ""), "updated": p.get("updated", 0),
         "files": len(p.get("files", {}))}
        for p in reversed(list(projects.get(email, {}).values()))
    ]


def create_project(token: str, name: str, stack: str = "", description: str = "") -> dict:
    email = _user_key(token)
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Project name is required")
    pid = secrets.token_urlsafe(8)
    now = time.time()
    with _lock:
        projects = _read(PROJECTS_PATH, {})
        projects.setdefault(email, {})[pid] = {
            "id": pid, "name": name,
            "stack": (stack or "").strip()[:120],
            "description": (description or "").strip()[:4000],
            "files": {}, "created": now, "updated": now,
        }
        _write(PROJECTS_PATH, projects)
    return {"id": pid, "name": name}


def get_project(token: str, project_id: str) -> dict | None:
    email = _user_key(token)
    with _lock:
        projects = _read(PROJECTS_PATH, {})
    return projects.get(email, {}).get(project_id)


def delete_project(token: str, project_id: str) -> None:
    email = _user_key(token)
    with _lock:
        projects = _read(PROJECTS_PATH, {})
        if project_id in projects.get(email, {}):
            del projects[email][project_id]
            _write(PROJECTS_PATH, projects)


def save_files(token: str, project_id: str, files: list[dict]) -> dict:
    """Upsert files [{path, content}] (path ≤ 200 chars, content ≤ 200KB each)."""
    email = _user_key(token)
    now = time.time()
    with _lock:
        projects = _read(PROJECTS_PATH, {})
        proj = projects.get(email, {}).get(project_id)
        if not proj:
            raise ValueError("Project not found")
        changed = 0
        for f in files or []:
            path = str(f.get("path") or "").strip()[:200]
            content = str(f.get("content") or "")
            if not path or len(content.encode()) > MAX_FILE_BYTES:
                continue
            if content != proj["files"].get(path):
                proj["files"][path] = content
                changed += 1
        proj["updated"] = now
        _write(PROJECTS_PATH, projects)
    return {"ok": True, "changed": changed}


def delete_file(token: str, project_id: str, path: str) -> None:
    email = _user_key(token)
    with _lock:
        projects = _read(PROJECTS_PATH, {})
        proj = projects.get(email, {}).get(project_id)
        if proj and path in proj["files"]:
            del proj["files"][path]
            proj["updated"] = time.time()
            _write(PROJECTS_PATH, projects)


def project_context(proj: dict, max_chars: int = 24_000) -> str:
    """Render a project description + all files into a Coder system-prompt block."""
    lines = [f"Project: {proj['name']}"]
    if proj.get("stack"):
        lines.append(f"Tech stack: {proj['stack']}")
    if proj.get("description"):
        lines.append(f"Description: {proj['description']}")
    if proj.get("files"):
        lines.append("")
        lines.append("Current files:")
        for path, content in proj["files"].items():
            entry = f"--- {path} ---\n{content}"
            if sum(len(l) + 1 for l in lines) + len(entry) > max_chars:
                break
            lines.append(entry)
    return "\n".join(lines)
