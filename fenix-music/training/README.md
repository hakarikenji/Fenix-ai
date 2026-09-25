# Fenix Music — عقل الموسيقى المدرَّب 🧠🎵

> **حالة حالية:** لا يوجد LoRA مدرَّب أو Space منشور الآن. آخر فحص أعاد 404 للـSpace وModal workspace معطل. اتبع `MUSIC-BRAIN-GUIDE.md` ولا تعتبر التطبيق brain مدرّباً قبل POST ناجح؛ Gemini fallback يعمل حالياً.

نفس رحلة Fenix Core حرفياً: **تدريب → Drive → Hugging Face → Modal**.

## الفكرة

- **النموذج الأساسي**: `Qwen/Qwen3-4B-Instruct-2507` (نفس الكور — مجاني وقوي)
- **البيانات**: محادثاتك وأمثلتك عن الكلمات والأسلوب الموسيقي (JSONL بتنسيق `messages`)
- **الناتج**: عقل `fenix-music` يجيب عن أسئلة الموسيقى ويكتب الكلمات **بأسلوبك أنت**

## قالب البيانات (data.jsonl)

```json
{"messages": [{"role": "user", "content": "اكتب لي كورس فونك عن الليل والسرعة"}, {"role": "assistant", "content": "[Chorus]\nالليل صاحي والسرعة في دمي..."}]}
```

اجمع 30-100 مثال بهذا الشكل، ثم استخدم نوتبوك التدريب الخاص بـ Fenix Core
(`training/colab_train.ipynb` في مستودع Fenix-ai) مع تغيير سطرين فقط:

1. اسم المستودع المستنسخ → `hakarikenji/Fenix-music-`
2. `REPO_ID` عند الرفع → `<حسابك>/fenix-music-lora`

## التشغيل (كما تعلمت)

1. خلية 2: سحب المستودع  2. خلية 3: تثبيت  3. رفع data.jsonl  4. خلية التدريب  5. خلية 6: حفظ في Drive  6. خلية 8: رفع Hugging Face
7. نشر على Modal بنفس `fenix-brain-modal/app.py` مع تغيير `ADAPTER_REPO = '<حسابك>/fenix-music-lora'`

## التوصيل

```bash
freebuff-env set --file .env.local '{"MUSIC_BRAIN_URL":"https://<workspace>--fenix-music-brain.modal.run/v1"}'
```

قبل التدريب الخادم يستخدم **Gemini كعقل مؤقت** — التطبيق كامل الوظائف من اليوم الأول،
والعقل الخاص يتوصّل لحظة جاهزيته بدون أي تغيير في التطبيق.

## المسار الآلي (الأسرع اليوم)

بدون Colab — كل شي من داخل Modal:

```bash
python fenix-music/training/gen_examples.py --count 24   # بيانات جديدة تُضاف فوق الموجود
modal run fenix-brain-modal/train_all.py --only music     # يرفع البيانات ويقرّب
modal run fenix-brain-modal/publish_adapters.py            # يرفع الـ adapter إلى HF
modal deploy fenix-music/generator/music_brain_modal.py    # العقل الحي على Modal
```

نسخة الـ Space المجانية `hakari66684-fenix-music.hf.space` تدخل سلسلة العقول تلقائياً
(فوق fenix-core وتحت عقل Modal)، وتبقى حية 24/7 بواسطة `brains-keepalive.yml`.
