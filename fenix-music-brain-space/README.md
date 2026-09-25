---
title: Fenix Music Brain
emoji: 🎧
colorFrom: purple
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# Fenix Music Brain — API للعقل المدرَّب على الموسيقى

يحمّل `Qwen/Qwen3-4B-Instruct-2507` + adapter تدريب الموسيقى (LoRA) من Hugging Face،
ويقدّم API متوافق مع OpenAI على مسار `/v1/chat/completions` — نفس واجهة سلسلة العقول.

## الربط بخوادم Fenix (يحدث تلقائياً)

`server.py` في Fenix-ai يضيف هذا الـ Space في سلسلة العقول افتراضياً:
`https://hakari66684-fenix-music.hf.space` — بعد نشره يشتغل بدون أي تعديل إضافي.

## تدريب الـ adapter

الـ adapter يأتي من مستودع HF: `Hakari66684/fenix-music-lora` (ملف fenix-music-adapter.zip).
بعد كل تدريب جديد (modal run fenix-brain-modal/train_all.py) ارفع الـ zip المحدث
نفس الملف — الـ Space يعيد التحميل عند إعادة التشغيل.

## الحفاظ على الحياة 24/7

GitHub Action في مستودع Fenix-ai (brains-keepalive.yml) يضرب هذا الـ Space
كل 10 دقائق فلا ينام أبداً — والخدمة مجانية بالكامل على HF Spaces CPU.
