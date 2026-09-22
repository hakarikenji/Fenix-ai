# 🎵 Fenix Music — استوديو الموسيقى بالذكاء الاصطناعي

**Fenix** — شركة العنقاء 🦅: تطبيقات عالمية حديثة، مجانية بالكامل. كل تطبيق مستقل تماماً
ولكل تطبيق **عقله الخاص بمجاله** (LoRA مدرّب) يعمل بجانب العقل الرئيسي **Fenix Core**.

تطبيق Fenix Music: توليد **فونك وأغانٍ كاملة بالكلمات** بعدة لغات (عربي · English · Français · Español · 日本語 · Русский) — بعقل موسيقى خاص + مولّد صوت GPU.

## ماذا يفعل

| الميزة | الشرح |
|---|---|
| ✍️ كلمات أصلية | فونك/راب/أي نوع — بنية كاملة (Intro/Verse/Chorus/Bridge/Outro) بالعربية أو الإنجليزية |
| 🎚️ برومبت صوتي احترافي | يحوّل فكرتك لوصف موسيقي دense يفهمه مولّد الصوت |
| 🎧 توليد موسيقى حقيقي | MusicGen على Modal GPU — WAV جاهز للتشغيل والتحميل والمشاركة |
| 💬 محادثة موسيقية | مذيع راديو آلي يفهم ذوقك ويساعدك تختار النمط |
| 🧠 عقل خاص (اختياري) | درّب عقلك بنفس رحلة Fenix Core — الخادم يستخدمه أولاً ويرجع لـ Gemini تلقائياً |

## البنية (نفس كور Fenix)

```
fenix-music/
├── server.py            # خادم Flask: /api/lyrics /api/audio-prompt /api/chat /api/generate
├── api/brain.py         # كلمات + برومبت + شخصية المذيع (Gemini)
├── web/index.html       # الاستوديو (PWA جاهز للتغليف بـ Capacitor كـ APK)
├── generator/worker.py  # Modal MusicGen GPU worker
├── training/README.md   # رحلة تدريب عقل الموسيقى (نفس Fenix Core)
└── requirements.txt
```

## التشغيل

```bash
pip install -r requirements.txt
python server.py          # يعمل على PORT (افتراضي 8000)
```

متغيرات البيئة:

| المتغير | الوظيفة | مطلوب؟ |
|---|---|---|
| `GEMINI_API_KEY` | العقل المؤقت (كلمات/محادثة) | قبل تدريب عقلك |
| `GEMINI_MODEL_CHAIN` | سلسلة نماذج احتياطية عبر الفواصل (الافتراضي `gemini-3.5-flash,gemini-3.6-flash,gemini-2.5-flash`) — إذا أُرهقت/حُذف نموذج ينتقل للذي بعده تلقائياً | لا |
| `MUSIC_GEN_URL` | رابط عامل التوليد على Modal | للتوليد الفعلي |
| `MUSIC_BRAIN_URL` | رابط العقل المدرّب (متوافق OpenAI) | لا — **موصول افتراضياً** بعقل Fenix Core على Modal؛ ضع `off` لتعطيله أو ضع رابط عقل الموسيقى بعد تدريبه |
| `MUSIC_BRAIN_MODEL` | اسم الموديل عند العقل | لا (افتراضي `fenix-core`) |
| `MUSIC_GEN_API_KEY` / `MUSIC_BRAIN_API_KEY` | حماية Bearer بين الخادم والعقول | اختياري |

## خطوات الإطلاق الكاملة

1. **الخادم**: انشر `fenix-music/` (Freebuff deploy أو أي استضافة Python)
2. **المولّد**: `modal deploy fenix-music/generator/worker.py` ← ثم ضع الرابط في `MUSIC_GEN_URL`
3. **العقل الخاص** (لاحقاً): درّبه بنفس نوتبوك Fenix Core → Hugging Face → Modal ← ضع الرابط في `MUSIC_BRAIN_URL`

جزء من منظومة **Fenix** 🦅 — كل تطبيق مستقل بعقله الخاص، والكل يرتبط بعقل Fenix Core:
**Fenix AI** (المساعد الشخصي) · **Fenix Music** (عقل الموسيقى) · قادم: مولّد الفيديو 🎬 ومنشئ التطبيقات 🛠️
