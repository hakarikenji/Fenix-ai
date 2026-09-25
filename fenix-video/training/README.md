# Fenix Video — دليل عقل الفيديو المدرَّب 🧠🎬

> **حالة حالية:** لا يمكن تأكيد وجود Video LoRA أو HF Space منشور. آخر فحص أعاد `404` للـSpaces وModal workspace معطل. اتبع المسار أدناه، ولا تصف العقل كحي قبل GET وPOST ناجحين. Gemini fallback هو السلوك الحالي.

## 1) البيانات

الملف:

```text
fenix-video/training/data.jsonl
```

كل سطر يحتوي `messages`، والمخرجات أمثلة JSON منظّمة لسيناريو فيديو. السكربت المتاح:

```bash
python3 fenix-video/training/gen_dataset.py --gemini --n 12 --append
```

## 2) التدريب

```bash
modal run fenix-brain-modal/train_all.py --only video --epochs 2
```

البديل اليدوي:

```bash
modal volume put fenix-video-out fenix-video/training/data.jsonl data.jsonl
modal run fenix-video/training/train_modal.py --epochs 2
```

بعد التدريب، Adapter يكون داخل:

```text
fenix-video-out:/adapter
```

## 3) النشر

```bash
modal deploy fenix-video/training/serve_modal.py
modal run fenix-brain-modal/publish_adapters.py --only video
```

لا تنشر Space قبل نجاح التدريب ورفع `fenix-video-adapter.zip`.

## 4) السلسلة

المسار في `fenix-video/api/brain.py`:

```text
Video Modal → Video HF Space → Core Modal → Core HF Space → Gemini
```

الـSpace وkeepalive يجعلان المسار أكثر مرونة، لكن لا تفترض أنهما منشوران قبل اختبار فعلي.
