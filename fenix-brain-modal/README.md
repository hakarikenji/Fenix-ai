# عقول Fenix على Modal — تدريب ونشر وتشغيل 🧠🐦‍🔥

هذه العقول تعتمد على `Qwen/Qwen3-4B-Instruct-2507` (Apache-2.0) مع LoRA مستقل لكل عقل:

- `fenix-core`: المساعد المشترك.
- `fenix-music`: كتابة الكلمات والردود الموسيقية.
- `fenix-video`: كتابة سيناريوهات الفيديو.

## حالة حالية

هذا الكود يصف طريقة التشغيل، لكنه لا يثبت نجاح النشر. آخر فحص أعاد `404` على HF Spaces وModal workspace أعاد `workspace ... is disabled`. لا يوجد حالياً LoRA مدرّب ومنشور يمكن تأكيده. التطبيق يمر إلى Gemini fallback.

الدليل المفصل لعقل الموسيقى هو:

```text
fenix-music/training/MUSIC-BRAIN-GUIDE.md
```

## المسار العام

```bash
pip install modal && modal token new
modal run fenix-brain-modal/warm.py
modal run fenix-brain-modal/train_all.py --only music --epochs 2
modal secret create hf-write HF_TOKEN=hf_xxx
modal run fenix-brain-modal/publish_adapters.py --only music
modal deploy fenix-music/generator/music_brain_modal.py
```

للعقول الأخرى:

```bash
modal run fenix-brain-modal/train_all.py --only video --epochs 2
modal run fenix-brain-modal/publish_adapters.py --only video
modal deploy fenix-video/training/serve_modal.py
```

## سلسلة brains

يقرأ الخادم المسار بالترتيب:

1. عقل التطبيق على Modal.
2. نسخة التطبيق على HF Space، إن كانت منشورة.
3. عقل Fenix Core على Modal.
4. نسخة Fenix Core على HF Space، إن كانت منشورة.
5. Gemini كحلقة أخيرة.

أي فشل أو رد فارغ ينتقل للحلقة التالية. الروابط الافتراضية موجودة في `server.py` و`fenix-video/api/brain.py`، لكنها لا تعني أن Spaces منشورة. اختبر كل رابط بـ GET وPOST فعليين.

## keepalive

`.github/workflows/brains-keepalive.yml` يضرب المساحات كل 10 دقائق بعد حفظه في GitHub. شغّل Workflow مرة واحدة بعد نشر Space. هذا يوقظ المساحة، لكنه لا يضمن أن Free CPU Space تستطيع دائماً تحميل نموذج 4B؛ Modal GPU هو الخيار الأساسي.

## التحقق

```bash
curl -X POST <modal-music-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"fenix-music","messages":[{"role":"user","content":"اكتب كورس فونك قصيراً"}]}'
```

لا تسجل النجاح إلا بعد:

- `ADAPTER SAVED` داخل Volume.
- رفع `fenix-music-adapter.zip` إلى Hugging Face.
- Modal يرد على POST.
- HF Space يرد على POST وليس 404.

## إعادة التدريب

```bash
python3 fenix-music/training/gen_examples.py --count 24
modal run fenix-brain-modal/train_all.py --only music --epochs 3
modal run fenix-brain-modal/publish_adapters.py --only music
modal deploy fenix-music/generator/music_brain_modal.py
```

لا تعدّل `server.py` عند إعادة التدريب؛ المسار يقرأ نفس Adapter zip.
