"""Fenix Core — Step 1: build a clean fine-tuning dataset from real chat data.

Sources (in priority order):
  .data/projects/*/chats/*.json   — Coder-mode conversations (rich, technical)
  .data/users/*/chats/*.json      — normal chat history (if the store keeps it)
  web export file (optional)      — pass --export path/to/chats-export.json

What it does (the cleaning pipeline):
  1. Collect (user, assistant) pairs with enough substance.
  2. Normalize whitespace, strip UI noise ("stopped by you", connection errors).
  3. Drop pairs that are broken/too short/too long or contain API error text.
  4. Scrub PII: emails → [EMAIL], long numbers/keys → [NUM], bearer tokens → [TOKEN].
  5. Deduplicate (exact + near-dup on normalized text).
  6. Split 95/5 into train/val (deterministic seed → repeatable).

Output: training/data/train.jsonl, training/data/val.jsonl
Format: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
"""
import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(__file__).resolve().parent / "data"

NOISE_MARKERS = (
    "connection failed", "stopped by you", "server unreachable",
    "not linked to a server", "api key", "401", "403", "429",
)
MIN_USER_CHARS, MIN_ASSISTANT_CHARS = 8, 15
MAX_PAIR_CHARS = 12000
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TOKEN_RE = re.compile(r"(?:sk-|Bearer\s+)[A-Za-z0-9_\-\.]{16,}")
LONGNUM_RE = re.compile(r"\b\d{9,}\b")
WS_RE = re.compile(r"[ \t]+")


def clean_text(t: str) -> str:
    t = WS_RE.sub(" ", (t or "").replace("\r", "")).strip()
    t = EMAIL_RE.sub("[EMAIL]", t)
    t = TOKEN_RE.sub("[TOKEN]", t)
    t = LONGNUM_RE.sub("[NUM]", t)
    return t


def is_noise(t: str) -> bool:
    low = (t or "").lower()
    return any(m in low for m in NOISE_MARKERS)


def dedup_key(user: str, assistant: str) -> str:
    norm = re.sub(r"\W+", "", (user + "|" + assistant).lower())[:4000]
    return hashlib.sha1(norm.encode()).hexdigest()


def iter_history_files():
    data = ROOT / ".data"
    if data.exists():
        yield from data.rglob("chats/*.json")
        yield from data.rglob("chats.json")
    export = ROOT / "web" / "chats-export.json"
    if export.exists():
        yield export


def pairs_from_doc(doc) -> list[tuple[str, str]]:
    """Accepts a list of chats or a single chat dict; returns cleaned pairs."""
    chats = doc if isinstance(doc, list) else [doc]
    out = []
    for chat in chats:
        msgs = (chat or {}).get("messages") or []
        user_txt, parts = None, []
        for m in msgs:
            role, content = m.get("role"), str(m.get("content") or "").strip()
            if role == "user":
                if user_txt is not None and parts:
                    out.append((user_txt, "\n".join(parts)))
                user_txt, parts = content, []
            elif role == "assistant" and user_txt is not None:
                if content:
                    parts.append(content)
        if user_txt is not None and parts:
            out.append((user_txt, "\n".join(parts)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", help="optional path to a chats export JSON")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    raw: list[tuple[str, str]] = []
    files = list(iter_history_files())
    if args.export:
        files.append(Path(args.export))
    for f in files:
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  skip {f}: {e}")
            continue
        got = pairs_from_doc(doc)
        raw.extend(got)
        print(f"  {f}: {len(got)} pairs")

    # Clean + filter
    seen, samples = set(), []
    dropped = {"noise": 0, "short": 0, "long": 0, "dup": 0}
    for user, assistant in raw:
        user, assistant = clean_text(user), clean_text(assistant)
        if is_noise(user) or is_noise(assistant):
            dropped["noise"] += 1
            continue
        if len(user) < MIN_USER_CHARS or len(assistant) < MIN_ASSISTANT_CHARS:
            dropped["short"] += 1
            continue
        if len(user) + len(assistant) > MAX_PAIR_CHARS:
            dropped["long"] += 1
            continue
        key = dedup_key(user, assistant)
        if key in seen:
            dropped["dup"] += 1
            continue
        seen.add(key)
        samples.append({
            "messages": [
                {"role": "system", "content": "You are Fenix, an AI assistant built by Hakari. Your engine is the model behind this deployment."},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ]
        })

    random.Random(args.seed).shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_frac)) if samples else 0
    val, train = samples[:n_val], samples[n_val:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("val.jsonl", val)):
        path = OUT_DIR / name
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"✓ {path} — {len(rows)} samples")

    print(f"\nSummary: {len(samples)} clean pairs "
          f"(dropped: {dropped['noise']} noise, {dropped['short']} short, "
          f"{dropped['long']} long, {dropped['dup']} duplicates)")
    if len(samples) < 50:
        print("\n⚠️ Fewer than 50 pairs. Quality beats quantity: keep chatting with "
              "Fenix (especially Coder mode) and re-run this, or pass --export with "
              "a bigger chat history. Training on <50 pairs will mostly teach style, not knowledge.")


if __name__ == "__main__":
    sys.exit(main())
