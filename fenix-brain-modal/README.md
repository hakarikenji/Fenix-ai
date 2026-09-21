# نشر عقلك المدرَّب كـ API بـ Modal — بدائل Colab و GGUF تماماً

مجاني: **$30 رصيد شهري** (يكفي آلاف الرسائل)، بدون بطاقة بنكية.

## النشر (أمر واحد)

```bash
pip install modal
modal token new          # يفتح المتصفح لتسجيل الدخول (مرة واحدة)
modal deploy fenix-brain-modal/app.py
```

في النهاية يطبع رابط مثل:
`https://<username>--fenix-brain-chat.modal.run`

## اختبار سريع

```bash
curl -X POST <الرابط> -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"من أنت؟"}]}'
```

## الربط بخادم Fenix

على الخادم (بيئة النشر):

```
CUSTOM_LLM_BASE_URL=<الرابط>
CUSTOM_LLM_MODEL=fenix-core
```

أي فشل → خادم Fenix يرجع تلقائياً لـ Gemini.

## لو مستودع النموذج Private

أضف secret قبل الرفع:

```bash
modal secret create hf-read HF_TOKEN=<التوكن>
```

واستبدل `@app.cls(...)` في `app.py` بـ:
`@app.cls(image=image, cpu=8, memory=16384, timeout=900, scaledown_window=600, secrets=[modal.Secret.from_name("hf-read")])`
