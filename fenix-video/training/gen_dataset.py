# توليد بيانات تدريب لعقل Fenix Video — يسأل العقل الحي (fenix-core على Modal)
# أو Gemini الاحتياطي، ويحفظ الأمثلة بصيغة messages (JSONL) جاهزة للتدريب.
# كل مثال يُتحقق منه بـ parse_script() — فقط الأمثلة الصالحة 100% مع مخطط /api/video/script تبقى.
#
#   python fenix-video/training/gen_dataset.py            # 30 مثال من العقل الحي
#   python fenix-video/training/gen_dataset.py --gemini   # من Gemini (لما Modal معطّل)
#
# الناتج: fenix-video/training/data.jsonl
import argparse
import importlib.util
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# استيراد brain.py بنفس طريقة server.py — بدون تعبئة sys.path
_here = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("fenix_video_brain", _here.parent / "api" / "brain.py")
brain_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brain_mod)

BRAIN_URL = os.environ.get("FENIX_BRAIN_URL", "https://yasinnait30--fenix-brain.modal.run").rstrip("/")
USE_GEMINI = False  # --gemini: ولّد البيانات من Gemini الاحتياطي بدل العقل الحي

# (الأسلوب البصري، اللغة، الفكرة) — خليط سينمائي متعدد اللغات كما هو جمهور Fenix العالمي
PROMPTS = [
    ("cinematic, moody, neon", "Darija/Arabic", "مطاردة ليلية على الكورنيش فالدار البيضاء"),
    ("cinematic, golden hour", "Darija/Arabic", "صعود فنان من الحومة للمسرح"),
    ("dark, rainy, neon-noir", "Arabic", "محقق يتبع أدلة في مدينة مطرة"),
    ("uplifting, sunrise, drone", "Arabic", "رحلة صباحية في جبال الأطلس"),
    ("high-energy, street, handheld", "Darija/Arabic", "ليلة مباراة والشوارع مشتعلة"),
    ("cinematic, moody, neon", "English", "a heist crew walks into a midnight casino"),
    ("warm, nostalgic, 35mm film", "English", "the last summer before everything changed"),
    ("epic, orchestral, aerial", "English", "a lone climber conquers a frozen peak"),
    ("fast-paced, glitchy, cyberpunk", "English", "a courier races through a neon megacity"),
    ("documentary, natural light", "French", "un matin au marché de Marseille"),
    ("cinematic, moody, neon", "French", "une course-poursuite sur le périphérique parisien"),
    ("dreamy, pastel, slow-motion", "Spanish", "un verano infinito en la costa"),
    ("gritty, urban, high-contrast", "Spanish", "el último boxeador del barrio"),
    ("anime-inspired, vivid, dynamic", "Japanese", "放課後の屋上での決闘"),
    ("cinematic, neon, rain", "Japanese", "雨の夜、信号待ちの女豹"),
    ("moody, snowy, minimalist", "Russian", "ночная поездка по заснеженному городу"),
    ("cinematic, golden hour", "Portuguese", "o último fôlego antes da final"),
    ("luxurious, sleek, product-ad", "English", "launch night of the Fenix flagship phone"),
    ("cozy, warm, lo-fi vibes", "English", "3am coding session that becomes a breakthrough"),
    ("gritty, documentary style", "Darija/Arabic", "الحرفة اليدوية في سوق المدينة القديمة"),
    ("surreal, dreamlike, floating", "Arabic", "حالم يطير فوق مدينته النائمة"),
    ("tense, thriller, handheld", "English", "she finds the hidden door behind the bookshelf"),
    ("playful, colorful, whip-pans", "English", "a street-food cook becomes a legend"),
    ("cinematic, desaturated, rain", "Darija/Arabic", "وداع في محطة القطار تحت المطر"),
    ("bold, graphic, kinetic type", "Arabic", "إعلان إطلاق شركة Fenix في العالم"),
    ("serene, misty, slow push-in", "English", "dawn over a quiet fishing harbor"),
    ("explosive, action, crash-zoom", "English", "the underground race nobody was supposed to see"),
    ("intimate, close-up, candlelight", "Spanish", "la carta que nunca envió"),
    ("futuristic, clean, macro", "English", "the robot learns what rain is"),
    ("cinematic, moody, neon", "Darija/Arabic", "الفينيق ينهض من الرماد فوق المدينة"),
]


def ask(prompt_tuple):
    style, language, topic = prompt_tuple
    system = brain_mod.script_system(language, style, topic)
    user = f"Write the video script JSON for: {topic}."
    if USE_GEMINI:
        text = brain_mod._gemini_call(system, user, 0.95, 2500)
    else:
        body = json.dumps({
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.95, "max_tokens": 2500,
        }).encode()
        req = urllib.request.Request(BRAIN_URL + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
        text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    if len(text) < 200:
        raise RuntimeError(f"short answer for {topic}")
    brain_mod.parse_script(text)  # يرفع خطأ إذا الرد مش مخطط صالح — فقط الصالح يُحفظ
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": text},
    ]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
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
        print(f"  ✗ {pt[2]}: {last}")
        return None

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(ask_retry, picks):
            if res is not None:
                rows.append(res)
                print(f"  ✓ {len(rows)}/{len(picks)}")

    out = _here / "data.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"✅ {len(rows)} examples → {out}")
    if len(rows) < 12:
        print("⚠️ أمثلة قليلة — أعد التشغيل لاحقاً لزيادة العدد (30+ أفضل للتدريب)")


if __name__ == "__main__":
    main()
