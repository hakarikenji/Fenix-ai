# Fenix Video — عقل الفيديو المدرّب 🧠🎬

نفس رحلة Fenix Music حرفياً: **بيانات → تدريب على Modal → نشر → ربط تلقائي**.

## 1) البيانات (data.jsonl)

كل سطر: محادثة `messages` — طلب سيناريو → JSON سيناريو صارم (نفس مخطط `/api/script`).
اجمع 25-100 مثال. النموذج الأمثل: اطلبها من العقل الحي (fenix-core) بنفس
`SCHEMA_RULES` الموجود في `fenix-video/api/brain.py` — فتحصل على أمثلة متوافقة 100%.

## 2) التدريب (بدون نوتبوك)

```bash
modal volume put fenix-video-out fenix-video/training/data.jsonl data.jsonl
modal run fenix-video/training/train_modal.py
modal deploy fenix-video/training/serve_modal.py
```

## 3) الربط (تلقائي افتراضياً)

الخادم مدمج افتراضياً على `https://<workspace>--fenix-video-brain.modal.run`.
أي فشل → fenix-core → Gemini — بدون أي تغيير في التطبيق.
