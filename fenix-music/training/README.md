# Fenix Music — عقل الموسيقى المدرَّب 🧠🎵

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
