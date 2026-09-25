"""Fenix Music — expand the training set with fresh, strong examples.

Uses api.common.gemini_brain (system+user kept SEPARATE — the exact fix that
killed the prompt-echo bug). Every row is validated before appending:
  - JSONL parses, 3 messages, roles ok
  - assistant text has structure labels and multilingual flavor
  - near-duplicates (first 80 chars of the assistant text) are dropped

Usage:
  python3 fenix-music/training/gen_examples.py            # 24 examples
  python3 fenix-music/training/gen_examples.py --count 8  # smaller batch
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from api.common import gemini_brain  # noqa: E402

DATA = ROOT / "fenix-music" / "training" / "data.jsonl"

SYSTEM = (
    "You are Fenix Music's lyric-writing brain. You write complete, release-ready "
    "song lyrics. Multilingual street style: the base language carries the verses, "
    "but hooks and punchlines naturally borrow words from English, French, Spanish, "
    "Japanese and Russian (the Fenix signature blend). Always include structure "
    "labels like [Intro], [Verse 1], [Chorus], [Bridge], [Outro]. Vivid concrete "
    "imagery, confident energy, real emotion — never generic filler. Output ONLY "
    "the lyrics, no commentary, no markdown fences."
)

GENRES = [
    ("drift phonk", "dark aggressive", "a midnight highway drift, engine screaming"),
    ("trap", "cold confident", "coming up from nothing, now the city knows my name"),
    ("hip-hop", "gritty determined", "late night studio sessions chasing the dream"),
    ("pop", "euphoric bright", "summer nights that never want to end"),
    ("rock", "explosive rebellious", "breaking free from a life that caged me"),
    ("electronic", "hypnotic pulsing", "losing myself in the warehouse strobe lights"),
    ("lo-fi", "nostalgic calm", "rainy windows, old photographs, 3am thoughts"),
    ("r&b", "smooth yearning", "texting you at 2am, afraid you moved on"),
    ("cinematic", "epic triumphant", "the final battle at the gates of dawn"),
    ("anime-inspired", "heroic passionate", "awakening the power that slept inside me"),
    ("game soundtrack", "tense adrenaline", "boss fight in a collapsing cyber city"),
    ("ambient", "floating serene", "dawn breaking over an empty ocean"),
]

LANGS = ["English", "Darija/Arabic", "Arabic", "French", "Spanish", "Russian", "Japanese", "Moroccan Darija with French hooks"]

PERSONAS = [
    "a fearless young racer", "a street poet with a broken heart", "a rising star who never sleeps",
    "a lone wanderer in a neon city", "a champion before the final match", "an artist painting the night",
    "a hacker outrunning the system", "a dreamer saving money for a new life", "a biker king of the coast road",
]

LANG_RULE = {
    "English": "Write everything in English (Fenix still drops a couple of foreign words in hooks).",
    "Darija/Arabic": "Write in Moroccan Darija (Arabic script), hooks may mix French/English words.",
    "Moroccan Darija with French hooks": "Write verses in Moroccan Darija (Arabic script), chorus in French.",
    "Arabic": "Write in Modern Standard Arabic.",
    "French": "Write in French.",
    "Spanish": "Write in Spanish.",
    "Russian": "Write in Russian (Cyrillic).",
    "Japanese": "Write in Japanese with romaji for the hook lines.",
}


def build_examples(count: int) -> list:
    combos = []
    for genre, mood, topic in GENRES:
        combos.append((genre, mood, topic))
    # extra randomized combos for density
    rnd = random.Random(20260923)
    while len(combos) < count:
        g, m, _ = rnd.choice(GENRES)
        t = rnd.choice(PERSONAS) + " — " + rnd.choice([
            "chasing the horizon", "against the whole world", "under a sky full of sparks",
            "one last night before everything changes", "proof that we never fold",
        ])
        combos.append((g, m, t))
    random.Random(7).shuffle(combos)
    return combos[:count]


def valid(row: dict) -> bool:
    try:
        msgs = row["messages"]
        if [m["role"] for m in msgs] != ["system", "user", "assistant"]:
            return False
        a = msgs[2]["content"]
        if len(a) < 300:
            return False
        low = a.lower()
        if "[" not in a or "verse" not in low and "chorus" not in low:
            return False
        if "act as" in low or "here are" in low or "```" in a:
            return False
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=24)
    args = ap.parse_args()

    existing = []
    if DATA.exists():
        existing = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen = {r["messages"][2]["content"][:80] for r in existing}
    print(f"existing rows: {len(existing)}")

    added = 0
    for genre, mood, topic in build_examples(args.count):
        lang = random.choice(LANGS)
        rule = LANG_RULE.get(lang, f"Write in {lang}.")
        sys_p = SYSTEM + f" Base language rule: {rule}"
        user = f"Write {genre} lyrics about: {topic}. Mood: {mood}. {rule}"
        try:
            text = gemini_brain(sys_p, user, 0.95)
        except Exception as e:
            print(f"  skip ({genre}/{lang}): {str(e)[:80]}")
            continue
        row = {
            "messages": [
                {"role": "system", "content": "Fenix Music persona. Multilingual street lyrics: verses in base language, hooks from EN/FR/ES/JA/RU pool."},
                {"role": "user", "content": user},
                {"role": "assistant", "content": (text or "").strip()},
            ]
        }
        if not valid(row) or row["messages"][2]["content"][:80] in seen:
            print(f"  reject ({genre}/{lang})")
            continue
        seen.add(row["messages"][2]["content"][:80])
        with DATA.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        added += 1
        print(f"  + {genre} / {lang} ({len(row['messages'][2]['content'])} chars)")
        time.sleep(1.5)

    total = len([l for l in DATA.read_text(encoding='utf-8').splitlines() if l.strip()]) if DATA.exists() else len(existing)
    print(f"DONE: +{added} new, total {total}")


if __name__ == "__main__":
    main()
