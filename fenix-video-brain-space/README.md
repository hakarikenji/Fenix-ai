---
title: Fenix Video Brain
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Fenix Video Brain — API للعقل المدرَّب على الفيديو

يحمّل `Qwen/Qwen3-4B-Instruct-2507` + adapter تدريب الفيديو (LoRA) من Hugging Face،
ويقدّم API متوافق مع OpenAI على مسار `/v1/chat/completions` — نفس واجهة سلسلة العقول.

## الربط بخوادم Fenix (يحدث تلقائياً)

`server.py` في Fenix-ai و`fenix-video/api/brain.py` يضيفان هذا الـ Space في سلسلة العقول
افتراضياً: `https://hakari66684-fenix-video.hf.space` — بعد نشره يشتغل بدون أي تعديل إضافي.
الترتيب في السلسلة: عقل الفيديو على Modal → **هذا الـ Space** → عقل Fenix Core → نسخته.

## تدريب الـ adapter

الـ adapter يأتي من مستودع HF: `Hakari66684/fenix-video-lora` (ملف fenix-video-adapter.zip).
بعد كل تدريب جديد (modal run fenix-brain-modal/train_all.py) ارفع الـ zip المحدث
نفس الملف — الـ Space يعيد التحميل عند إعادة التشغيل.

## الحفاظ على الحياة 24/7

GitHub Action في مستودع Fenix-ai (brains-keepalive.yml) يضرب هذا الـ Space
كل 10 دقائق فلا ينام أبداً — والخدمة مجانية بالكامل على HF Spaces CPU.
