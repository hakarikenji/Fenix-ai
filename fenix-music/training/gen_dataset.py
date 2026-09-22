# توليد بيانات تدريب لعقل Fenix Music — يسأل العقل الحي (fenix-core على Modal)
# ويحفظ الأمثلة بصيغة messages (JSONL) جاهزة للتدريب.
#
#   python fenix-music/training/gen_dataset.py            # 24 مثال
#   python fenix-music/training/gen_dataset.py --n 40
#
# الناتج: fenix-music/training/data.jsonl
import argparse
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
import brain as brain_mod  # نفس التعليمات اللي يستخدمها الخادم حرفياً
from brain import lyric_system

BRAIN_URL = os.environ.get("FENIX_BRAIN_URL", "https://yasinnait30--fenix-brain.modal.run").rstrip("/")
USE_GEMINI = False  # --gemini: ولّد البيانات من Gemini الاحتياطي بدل العقل الحي

# (النوع، المزاج، اللغة الأساسية، الفكرة) — خليط شوارع متعدد اللغات كما هي الأغاني الحقيقية
PROMPTS = [
    ("drift phonk", "dark aggressive", "Darija/Arabic", "ليل الدار البيضاء والسرعة على الكورنيش"),
    ("phonk", "energetic", "Darija/Arabic", "صعود من الحومة للقمة"),
    ("drift phonk", "dark aggressive", "Arabic", "مطاردة ليلية في المدينة"),
    ("rap", "confident", "Darija/Arabic", "الكلام يقتل بس الأعمال ت spoken"),
    ("trap", "dark aggressive", "Arabic", "أرقام وحلم كبير"),
    ("phonk", "sad emotional", "Darija/Arabic", "فراق صاحب الطفولة"),
    ("drift phonk", "energetic", "Darija/Arabic", "طنجة والليل والهكي"),
    ("rap", "aggressive", "Arabic", "رد على الكفى والغِيظ"),
    ("phonk", "dark aggressive", "Darija/Arabic", "شبح المدينة بعد منتصف الليل"),
    ("trap", "chill nostalgic", "Arabic", "ذكريات الصيف والحومة"),
    ("drift phonk", "epic cinematic", "Darija/Arabic", "سباق نهائي تحت المطر"),
    ("phonk", "energetic", "English", "midnight highway run"),
    ("rap", "confident", "English", "from nothing to something"),
    ("trap", "dark aggressive", "English", "shadows in the club"),
    ("drift phonk", "epic cinematic", "English", "touge battle at dawn"),
    ("phonk", "sad emotional", "English", "empty apartment after she left"),
    ("rap", "aggressive", "French", "la nuit sur le périph"),
    ("drift phonk", "dark aggressive", "French", "course dans les rues de Paris"),
    ("phonk", "energetic", "Darija/Arabic", "الباص لي كيدور فالليل"),
    ("trap", "confident", "Darija/Arabic", "الفن كيغير الحياة"),
    ("rap", "sad emotional", "Arabic", "القلم والورقة علاج"),
    ("drift phonk", "energetic", "Arabic", "أضواء المدينة في المرايا"),
    ("phonk", "dark aggressive", "Darija/Arabic", "الذئب وحيد يجري"),
    ("trap", "energetic", "Darija/Arabic", "من السوق للستوديو"),
]


def ask(prompt_tuple):
    genre, mood, language, topic = prompt_tuple
    system = lyric_system(genre, mood, language, topic)
    user = f"Write {genre} lyrics about: {topic}."
    if USE_GEMINI:
        text = brain_mod._gen(system, user, 1.0, 900)
    else:
        body = json.dumps({
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 1.0, "max_tokens": 900,
        }).encode()
        req = urllib.request.Request(BRAIN_URL + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
        text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    if len(text) < 120:
        raise RuntimeError(f"short answer for {topic}")
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": text},
    ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--gemini", action="store_true",
                    help="ولّد من Gemini الاحتياطي (إذا عقل Modal معطّل)")
    args = ap.parse_args()
    global USE_GEMINI
    USE_GEMINI = args.gemini

    picks = [PROMPTS[i % len(PROMPTS)] for i in range(args.n)]
    print(f"🎬 generating {len(picks)} examples ({'Gemini' if USE_GEMINI else BRAIN_URL})…")

    def ask_retry(pt):  # محاولتان لكل مثال قبل الاستسلام
        last = None
        for _ in range(2):
            try:
                return ask(pt)
            except Exception as e:  # noqa: BLE001
                last = e
        print(f"  ✗ {pt[3]}: {last}")
        return None

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(ask_retry, picks):
            if res is not None:
                rows.append(res)
                print(f"  ✓ {len(rows)}/{len(picks)}")

    out = Path(__file__).parent / "data.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"✅ {len(rows)} examples → {out}")
    if len(rows) < 12:
        print("⚠️ أمثلة قليلة — أعد التشغيل لاحقاً لزيادة العدد (30+ أفضل للتدريب)")


if __name__ == "__main__":
    main()
