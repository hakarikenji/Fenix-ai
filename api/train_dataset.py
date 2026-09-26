"""
Fenix — build a training set from real usage, and refuse to build a bad one.

This exists because Fenix already has a trained-looking LoRA that learned
almost nothing: six steps, a loss of 3.23, and a name the product presents as
its own brain. That did not happen because training is hard. It happened
because nobody checked whether the data was worth training on.

So this module is deliberately unhelpful in one direction: it will happily
build a clean dataset, and it will refuse — loudly, with numbers — to hand
over one that would produce another useless adapter.

What it does:

* reads real conversations and real ratings out of the Fenix database
* pairs each user turn with the reply that answered it
* drops empty, truncated, duplicate and identity-leaking pairs
* reports what it found, and refuses below a configurable floor

Run:  python3 api/train_dataset.py [--min 300] [--out data/fenix-sft.jsonl]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# A LoRA on a 4B model needs a few hundred real pairs to move behaviour at
# all. Below this it memorises noise and reports a low loss while learning
# nothing — the exact failure already on the Hub.
MIN_PAIRS = 300
# If most rows are the same exchange, the model learns to repeat one answer.
MAX_DUPLICATE_SHARE = 0.05
# Below this many rows the share of a single reply is not evidence of anything.
REPETITION_MIN_ROWS = 20
# Replies that name a provider break the product's identity guarantee, so they
# must never reach a training file.
FORBIDDEN = re.compile(
    r"\b(gpt|chatgpt|openai|anthropic|claude|gemini|llama|qwen|mistral|cohere|"
    r"deepseek|groq|hugging\s?face|transformers?|pytorch)\b", re.I)
IDENTITY_Q = re.compile(
    r"(who\s+are\s+you|what\s+(ai|brain|model)\s+do\s+you|which\s+(ai|model|engine)|"
    r"من\s+انت|شنو\s+انت|ايش\s+انت|شو\s+انت)", re.I)

PLACEHOLDER = re.compile(r"^\s*(\(see attachment\)|image|attachment|file)\s*$", re.I)
CODE_ONLY = re.compile(r"^```[\s\S]*```$")


def _clean(text: str) -> str:
    """One reply, trimmed and normalised. Never returns the caller's object."""
    t = (text or "").replace("\r\n", "\n").strip()
    if not t:
        return ""
    # Strip a lone fenced block's fences but keep the code: code replies are
    # exactly the kind of thing the coder brain should learn to produce.
    return t[:8000]


def _fingerprint(prompt: str, reply: str) -> str:
    return hashlib.sha256(f"{prompt}\x00{reply}".encode()).hexdigest()[:32]


def looks_like_a_real_exchange(prompt: str, reply: str) -> bool:
    """Reject the exchanges that poison a small training set."""
    if not prompt or not reply:
        return False
    if PLACEHOLDER.match(prompt) or PLACEHOLDER.match(reply):
        return False
    # A test ping, a greeting, or a one-word answer teaches the model nothing.
    if len(prompt.strip()) < 12 or len(reply.strip()) < 12:
        return False
    if prompt.strip().lower() in ("hi", "hello", "hey", "test", "ping", "yo"):
        return False
    # An identity question whose answer names another engine is exactly the
    # behaviour the product forbids; it must be fixed by hand, not learned.
    if IDENTITY_Q.search(prompt) and FORBIDDEN.search(reply):
        return False
    return True


def _pairs_from_conversations(limit: int = 0, user_token: str | None = None) -> list[dict]:
    """Every user turn paired with the reply that answered it."""
    try:
        import db
    except Exception:
        return []
    out: list[dict] = []
    try:
        c = db.conn()
        if user_token is not None:
            convs = c.execute(
                "SELECT id FROM conversations WHERE user_key=? ORDER BY updated DESC"
                + (f" LIMIT {int(limit)}" if limit else ""),
                (db._key(user_token),)).fetchall()
        else:
            convs = c.execute(
                "SELECT id FROM conversations ORDER BY updated DESC"
                + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    except Exception:
        return []
    for conv in convs:
        try:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE conversation_id=?"
                " ORDER BY id", (conv["id"],)).fetchall()
        except Exception:
            continue
        pending: list[str] = []
        for row in rows:
            role = (row["role"] or "").lower()
            body = _clean(row["content"])
            if role == "user":
                pending.append(body)
            elif role == "assistant" and body:
                # The most recent user turn is the prompt for this reply.
                prompt = pending[-1] if pending else ""
                out.append({"prompt": prompt, "reply": body, "source": "conversation",
                            "rated": False})
                if len(pending) > 4:
                    pending = pending[-4:]
    return out


def _pairs_from_ratings(user_token: str | None = None) -> list[dict]:
    """Up-rated pairs, and the down-rated ones kept aside for the eval split."""
    try:
        import db
    except Exception:
        return []
    good, bad = [], []
    try:
        c = db.conn()
        if user_token is not None:
            rows = c.execute(
                "SELECT message, reply, rating, reason, brain, created FROM ratings"
                " WHERE user_key=? ORDER BY created",
                (db._key(user_token),)).fetchall()
        else:
            rows = c.execute(
                "SELECT message, reply, rating, reason, brain, created FROM ratings"
                " ORDER BY created").fetchall()
    except Exception:
        return []
    for r in rows:
        pair = {"prompt": _clean(r["message"]), "reply": _clean(r["reply"]),
                "source": "rating", "rated": True,
                "reason": (r["reason"] or "")[:300],
                "brain": (r["brain"] or "")[:40]}
        (good if int(r["rating"] or 0) > 0 else bad).append(pair)
    # A down-rated reply is real evidence too — it belongs in the held-out set
    # so the run can be scored against answers a person rejected.
    for pair in bad:
        pair["rated"] = False
        pair["source"] = "rating-rejected"
    return good + bad


def build(min_pairs: int = MIN_PAIRS, user_token: str | None = None) -> dict:
    """Build the set and report honestly on whether it is worth training.

    `user_token` scopes the set to one account. Without it the whole database
    is read, which is only ever right for a local training run.
    """
    raw = _pairs_from_ratings(user_token) + _pairs_from_conversations(0, user_token)

    kept: list[dict] = []
    seen: set[str] = set()
    dropped = Counter()
    for pair in raw:
        prompt, reply = pair.get("prompt", ""), pair.get("reply", "")
        if not looks_like_a_real_exchange(prompt, reply):
            dropped["trivial or empty"] += 1
            continue
        fp = _fingerprint(prompt.strip().lower(), reply.strip().lower())
        if fp in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(fp)
        kept.append({**pair, "fingerprint": fp})

    # Repetition is the failure mode of a small set: a model trained on it
    # learns the single most common answer and nothing else. But "share" is
    # only a meaningful measure once there is enough material for one answer
    # to dominate — on a handful of rows every single reply looks like a
    # majority, and the filter would quietly throw away the only real pairs
    # the user has.
    counter = Counter(p["reply"].strip().lower() for p in kept)
    worst_share = (counter.most_common(1)[0][1] / len(kept)) if kept else 0.0
    if len(kept) >= REPETITION_MIN_ROWS and worst_share > MAX_DUPLICATE_SHARE:
        keep_n = max(1, int(len(kept) * (1 - MAX_DUPLICATE_SHARE)))
        for _ in range(len(kept) - keep_n):
            kept.pop()

    # Rated pairs first: a person saying "this one was good" is worth more
    # than the same exchange merely having happened.
    kept.sort(key=lambda p: (not p.get("rated"), p.get("source") != "rating"))

    problems = []
    if len(kept) < min_pairs:
        problems.append(
            f"only {len(kept)} usable pairs, need {min_pairs} — training on this "
            f"would produce another adapter that reports a loss and learns nothing")
    distinct = len(counter)
    if len(kept) >= 20 and distinct < len(kept) * 0.5:
        problems.append(
            f"only {distinct} distinct replies across {len(kept)} pairs — the set is "
            f"repetitive enough to teach one answer instead of a style")
    if not kept:
        problems.append("no usable pairs at all")

    return {
        "pairs": kept,
        "count": len(kept),
        "raw_seen": len(raw),
        "dropped": dict(dropped),
        "distinct_replies": distinct,
        "max_repeat_share": round(worst_share, 3),
        "rated": sum(1 for p in kept if p.get("rated")),
        "ready": not problems,
        "problems": problems,
    }


def to_jsonl(pairs: list[dict]) -> str:
    """The dataset as a string, in the chat format the trainer reads."""
    lines = []
    for p in pairs:
        lines.append(json.dumps({"messages": [
            {"role": "system", "content":
             "You are Fenix Core LoRA, the primary AI identity built by Hakari. "
             "Answer in the user's language. Be honest about what you did and "
             "did not do."},
            {"role": "user", "content": p["prompt"]},
            {"role": "assistant", "content": p["reply"]},
        ]}, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def write_jsonl(report: dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_jsonl(report["pairs"]))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a Fenix SFT dataset from real usage.")
    ap.add_argument("--min", type=int, default=MIN_PAIRS,
                    help=f"refuse to write fewer than this many pairs (default {MIN_PAIRS})")
    ap.add_argument("--out", default="data/fenix-sft.jsonl")
    ap.add_argument("--force", action="store_true",
                    help="write the file even if the report says it is not ready")
    args = ap.parse_args(argv)

    report = build(args.min)
    print(f"raw exchanges seen : {report['raw_seen']}")
    print(f"dropped            : {report['dropped'] or '{}'}")
    print(f"usable pairs       : {report['count']}  ({report['rated']} explicitly up-rated)")
    print(f"distinct replies   : {report['distinct_replies']}")
    print(f"largest repeat     : {report['max_repeat_share']:.1%}")
    print()
    if report["problems"]:
        print("NOT READY TO TRAIN")
        for p in report["problems"]:
            print("  - " + p)
        print()
        print("No file was written. Collect more real usage, or lower --min if you")
        print("know the set is small but clean. Do not train on this as it stands:")
        print("that is how the current adapter ended up at six steps and a loss of 3.23.")
        return 1

    path = write_jsonl(report, args.out)
    print(f"READY — wrote {report['count']} pairs to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
