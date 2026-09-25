# Fenix Brains — المجاني 100% بدون Modal (24/7)

الحقيقة أولاً: **لا يوجد GPU مجاني دائم لأي حد** في 2026. Modal تمسّد due spend limit، Koyeb سكّر التسجيل المجاني. اللي موجود فعلاً و**مجاني 100%** هو مسار من طبقتين:

---

## الطبقة 1 — عقول مجانية جاهزة 24/7 (شغّالة فوراً، بدون تدريب)

استضافة صفر، بدون GPU، بدون فلوس. المفاتيح اختيارية — بدون مفتاح تتخطّى الطبقة بصمت.

| المزوّد | المفتاح | ملاحظات |
|---|---|---|
| **Groq** | `GROQ_API_KEY` | أسرع free tier، متوافق OpenAI. موديل افتراضي `qwen/qwen3.8-27b` (عربي قوي)، مع fallback تلقائي إلى `openai/gpt-oss-120b` ثم `gpt-oss-20b` ثم `qwen/qwen3.6-27b` |
| **OpenRouter** | `OPENROUTER_API_KEY` | فيه نماذج `:free` (Llama / Qwen) |
| **Cerebras** | `CEREBRAS_API_KEY` | سريع جداً، free tier |
| **DeepSeek** | `DEEPSEEK_API_KEY` | OpenAI-compatible fallback — depends on account quota |

**الترتيب:** عقل LoRA الخاص (لو متوفر) ← **Groq** ← **OpenRouter** ← **Cerebras** ← Research ← Gemini.
كل رد يعرض اسم العقل اللي جاوب فعلاً — نفس قاعدة الصدق الموجودة.

**التركيب:** ضع المفتاح في **Settings → Environment** بالمشروع:

| المتغير | مطلوب؟ | الوصف |
|---|---|---|
| `GROQ_API_KEY` | اختياري | من console.groq.com |
| `OPENROUTER_API_KEY` | اختياري | من openrouter.ai/keys |
| `CEREBRAS_API_KEY` | اختياري | من cloud.cerebras.ai |
| `DEEPSEEK_API_KEY` | اختياري | DeepSeek OpenAI-compatible API؛ يعتمد على الحصة المتاحة |
| `GROQ_MODEL` | اختياري | الافتراضي `qwen/qwen3.8-27b` |
| `GROQ_MODEL_FALLBACKS` | اختياري | قائمة fallback مفصولة بفواصل |
| `GROQ_BASE_URL` | اختياري | للاختبار/الوكيل — الافتراضي `https://api.groq.com/openai/v1` |
| `OPENROUTER_MODEL` | اختياري | الافتراضي `meta-llama/llama-3.3-70b-instruct:free` |
| `FREE_BRAINS` | اختياري | `off` لتعطيل الطبقة |
| `FREE_BRAINS_TIMEOUT` | اختياري | الافتراضي 45 ثانية |

لتشوف العقول المتاحة: `GET /api/brains` → `free_brains.configured`.

---

## الطبقة 2 — عقلك المدرّب LoRA على HF Space مجاني (دائم مع keepalive)

المساحات الحرة: **2 vCPU / 16GB RAM / $0**. تنام بعد 48 ساعة صمت — و`brains-keepalive.yml` يـping كل 10 دقائق فيمنع النوم.

### المسار (بدون Modal نهائياً)

**1) التدريب — Colab مجاني**
- افتح `fenix-music/training/FENIX_MUSIC_COLAB.ipynb` (Music) أو نظيره لـCore
- Runtime → **T4 GPU**
- شغّل الخلايا بالترتيب حتى ينتهي التدريب
- نزّل `adapter.zip`

**2) الدمج + التكميم (مهم للـCPU المجاني)**
- ادمج الـLoRA في الموديل الأساسي وحوّله لـGGUF مضغوط (Q4_K_M ≈ 2.5GB لـQwen3-4B)
- بدون الدمج، 4B على CPU يحتاج ~16GB RAM وممكن يفشل على المساحة المجانية

**3) رفع الموديل على Hugging Face**
- أنشئ **model repo** مثل `fenix-core-gguf`
- ارفع ملف `.gguf` (اسمه `fenix-core-q4.gguf` مثلاً)

**4) نشر المساحة**
المجلدات جاهزة: `fenix-brain-space/` و`fenix-music-brain-space/` و`fenix-video-brain-space/`
- أنشئ Space جديد من نوع **Docker**
- ارفع محتوى المجلد
- في **Settings → Variables and secrets** أضف:

| المتغير | القيمة |
|---|---|
| `ENABLE_GGUF` | `1` (Docker build arg) |
| `MODEL_GGUF_URL` | `https://huggingface.co/<repo>/resolve/main/<file>.gguf` |
| `HF_TOKEN` | فقط إذا الموديل private |
| `LLAMA_THREADS` | `2` |

> بديل بدون GGUF (لو عندك GPU Space): `ADAPTER_ZIP_URL` فقط، بدون `ENABLE_GGUF`.

**5) التأكد**
- افتح `https://<space>.hf.space/` لازم يرد `{"status":"ok","engine":"gguf",...}`
- اختبر: `POST /v1/chat/completions`
- شغّل `.github/workflows/brains-keepalive.yml` مرة واحدة من **Actions** (بعد الحفظ على GitHub)
- التطبيق يقرأ المسارات تلقائياً — بدون تعديل كود

---

## الترتيب النهائي في السيرفر

```
Fenix LoRA (Modal — اختياري)
  → Fenix LoRA (HF Space مجاني — 24/7 مع keepalive)
  → Groq free        ┐
  → OpenRouter free  ├ طبقة مجانية فورية 24/7
  → Cerebras free    ┘
  → Fenix Research (Serper + Gemini)
  → Gemini
```

كل طبقة ترجع `None` عند أي فشل، والرد النهائي يحمل اسم العقل الحقيقي. لا انقطاع، ولا كذب.

---

## ما يحتاج منك

1. مفتاح مجاني واحد على الأقل من الثلاثة (Groq أسرعهم) — Keys/API keys tab
2. تشغيل keepalive مرة واحدة من Actions بعد الحفظ
3. (اختياري) تدريب الـLoRA على Colab T4 لرفع عقلك الخاص

**ما أقدر أعمله من هنا:** إنشاء الحسابات أو رفع الموديلات نيابة عنك — هذي خطوات لازم تتم بحسابك أنت.

---

## تنبيه مهم عن موديلات Groq (سبتمبر 2026)

حسب توثيق Groq الرسمي:
- `llama-3.1-8b-instant` و `llama-3.3-70b-versatile` صاروا **Enterprise فقط** من 16 أغسطس 2026 —
  إذا حطيتهم يدوي في `GROQ_MODEL` رح يفشلوا على المفتاح المجاني.
- الموديلات المجانية المتاحة: `openai/gpt-oss-120b`، `openai/gpt-oss-20b`، `qwen/qwen3.8-27b`، `qwen/qwen3.6-27b`.
- حدود المجاني: 30 طلب/دقيقة، 1000 طلب/يوم، 8000 توكن/دقيقة، 200,000 توكن/يوم.
  عند تجاوز الحد ترجع 429 والكود ينتقل تلقائياً للموديل التالي ثم لـOpenRouter/Cerebras ثم Gemini.

لذلك Fenix يبدأ بـ`qwen/qwen3.8-27b` (أفضل دعم للعربي) ويجرّب الباقي تلقائياً.
للتأكد من الموديل الحالي فعلياً بعد وضع المفتاح:

```bash
curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```
