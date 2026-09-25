# Fenix Music — مذكرة تدريب عقل الموسيقى من الصفر إلى 24/7

هذه المذكرة هي المرجع التنفيذي الوحيد لعقل **Fenix Music** فقط. نفّذها من جذر مستودع `Fenix-ai` بالترتيب. استخدم الملفات الجاهزة الموجودة في المستودع؛ لا تنشئ Trainer جديداً ولا تعِد بناء الخادم أو الواجهة.

## حالة اليوم — بلا تجميل

- لا يوجد حالياً LoRA مدرَّب ومنشور لعقل الموسيقى.
- آخر فحص للروابط أعاد `404` على HF Spaces، وModal workspace أعاد `workspace ... is disabled`.
- التطبيق يعمل حالياً عبر Gemini كـfallback.
- لا تصف العقل بأنه «منشور» أو «حي» قبل اجتياز أوامر GET وPOST في هذا الدليل.

## 1) النتيجة المستهدفة

```text
بيانات JSONL منظفة
  ↓
QLoRA على Qwen/Qwen3-4B-Instruct-2507
  ↓
fenix-training-out:/adapter
  ↓
Hugging Face: Hakari66684/fenix-music-lora/fenix-music-adapter.zip
  ↓
Modal GPU: fenix-music-brain
  ↓
HF Docker Space: hakari66684-fenix-music.hf.space
  ↓
Music Modal → Music Space → Core Modal → Core Space → Gemini
```

أي حلقة تفشل تنتقل تلقائياً إلى التالية. Gemini يبقى آخر حلقة احتياطية.

## 2) المتطلبات

### Modal

فعّل workspace وطريقة الدفع على Modal أولاً. بعد ذلك:

```bash
pip install modal
modal token new
modal profile current
```

لا تضع توكن Modal في Git أو في التطبيق.

### Hugging Face

أنشئ Write Token، ثم احفظه كـModal Secret:

```bash
modal secret create hf-write HF_TOKEN=hf_xxxxxxxxx
```

مستودع الـLoRA هو Model repository باسم:

```text
Hakari66684/fenix-music-lora
```

ولا تنشئ Space قبل نجاح التدريب ورفع ملف `fenix-music-adapter.zip`.

### توليد البيانات

`gen_examples.py` يحتاج `GEMINI_API_KEY` في بيئة التنفيذ. ضعه من **Freebuff → Settings → Environment** أو في جهازك المحلي، ولا تضعه في Git.

## 3) تجهيز البيانات

الملف الوحيد الذي يتدرب عليه عقل الموسيقى:

```text
fenix-music/training/data.jsonl
```

كل سطر JSON واحد، والأدوار بالترتيب:

```json
{
  "messages": [
    {"role": "system", "content": "Fenix Music persona: release-ready multilingual lyrics."},
    {"role": "user", "content": "اكتب chorus trap دارجة عن الخروج من الحي midnight."},
    {"role": "assistant", "content": "[Chorus]\n..."}
  ]
}
```

الملف الحالي يحتوي **49 صفاً**، ويغطي أنماطاً ولغات متعددة. لا تحذفه ولا تستبدله.

### زيادة البيانات قبل التدريب

```bash
python3 fenix-music/training/gen_examples.py --count 24
python3 fenix-music/training/gen_examples.py --count 24
```

الأداة تضيف الصفوف فقط إذا اجتازت فلاتر الصيغة والبنية والطول ومنع التكرار. راجع عينة يدوية من كل دفعة، واستبعد الصف الذي يجيب بطلب بدلاً من كلمات، أو يشرح تعليمات LLM، أو يخلط اللغة المطلوبة.

الهدف:

| عدد الصفوف | الاستخدام |
|---:|---|
| 49 | أول smoke run |
| 100–149 | تدريب أول جيد |
| 150–300 | الإعداد الموصى به للقوة |
| 300+ | زد التنوع والجودة، لا الكمية الضعيفة |

### فحص البيانات بدون API

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("fenix-music/training/data.jsonl")
rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
assert rows
assert all([m["role"] for m in r["messages"]] == ["system", "user", "assistant"] for r in rows)
assert all("[Verse" in r["messages"][2]["content"] or "[Chorus" in r["messages"][2]["content"] for r in rows)
print(f"MUSIC_DATA_OK rows={len(rows)}")
PY
```

## 4) تجهيز كاش النموذج — مرة واحدة

```bash
modal run fenix-brain-modal/warm.py
modal volume ls fenix-hf-cache
```

هذا ينزل `Qwen/Qwen3-4B-Instruct-2507` إلى `fenix-hf-cache`، ويستخدمه التدريب وخدمة Modal. إذا فشل الأمر، أصلح Modal workspace قبل التدريب.

## 5) التدريب الموحد — عقل الموسيقى فقط

المسار الأساسي:

```bash
modal run fenix-brain-modal/train_all.py --only music --epochs 2
```

بعد رفع البيانات إلى 150 صفاً على الأقل:

```bash
modal run fenix-brain-modal/train_all.py --only music --epochs 3
```

هذا الأمر:

1. يرفع `data.jsonl` إلى `fenix-training-out:/data.jsonl`.
2. يستخدم A10G وكاش `fenix-hf-cache`.
3. يحمّل base model بوضع QLoRA NF4 مع double quantization.
4. يطبق LoRA rank 32 وalpha 64 مع `use_rslora`.
5. يغطي `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`.
6. يتدرّب على messages فقط مع batch 1 وaccumulation 8 وgradient checkpointing.
7. يحفظ tokenizer وadapter في `fenix-training-out:/adapter`.

يجب أن تنتهي العملية بـ:

```text
✅ ADAPTER SAVED → volume fenix-training-out:/adapter
```

فحص Adapter:

```bash
modal volume ls fenix-training-out
modal volume get fenix-training-out adapter/adapter_config.json ./music-adapter-config.json
```

يجب أن تجد `adapter_config.json` و`adapter_model.safetensors` وملفات tokenizer. لا تعتبر التدريب ناجحاً عند `ADAPTER SAVED` إذا ظهر loss بقيمة NaN أو لم تُحفظ الملفات.

### بديل يدوي

```bash
modal volume put fenix-training-out fenix-music/training/data.jsonl data.jsonl
modal run fenix-music/training/train_modal.py --epochs 2
```

المسار الموحد `train_all.py --only music` هو الأساسي. لا تشغّل تدريبين على نفس Volume في نفس الوقت.

### المسار المحلي على PC — بدون Modal

إذا كان عندك NVIDIA GPU، هذا هو البديل المباشر. لا يحتاج Trainer جديداً؛ استخدم الملف الجاهز `fenix-music/training/train_local.py`.

**حدود العتاد:**

| VRAM | الإعداد المقترح |
|---:|---|
| أقل من 12 GB | غير موصى به لـQwen3-4B؛ جرّب 1024 فقط وقد يفشل |
| 12–16 GB | QLoRA + `--max-length 2048` |
| 24 GB أو أكثر | `--max-length 4096` مع نفس إعداد QLoRA |

ثبّت الحزم في بيئة Python 3.11، ثم شغّل من جذر المستودع:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install "transformers>=4.51" "peft>=0.11" "trl>=0.9" datasets accelerate bitsandbytes huggingface_hub
```

**Dry run سريع** يتحقق من GPU والبيانات بدون تحميل النموذج:

```bash
python fenix-music/training/train_local.py --dry-run
```

التدريب المحلي على 12–16 GB:

```bash
python fenix-music/training/train_local.py --epochs 2 --max-length 2048
```

على 24 GB أو أكثر:

```bash
python fenix-music/training/train_local.py --epochs 3 --max-length 4096
```

الناتج المحلي:

```text
fenix-music/training/local-output/adapter/
```

بعد نجاح التدريب، ارفعه محلياً إلى Hugging Face بدون Modal:

```bash
# ضع HF_TOKEN في بيئة التنفيذ فقط، ولا تكتبه في Git
HF_TOKEN=hf_xxx python fenix-music/training/publish_local_adapter.py \
  --adapter-dir fenix-music/training/local-output/adapter
```

السكربت يحوّل `adapter/` إلى `fenix-music-adapter.zip` ويرفعه إلى `Hakari66684/fenix-music-lora`، وهي نفس النسخة التي يقرأها Modal أو HF Space.

**مهم:** Freebuff لا يستطيع رؤية GPU جهازك الشخصي. شغّل `nvidia-smi` عندك، وإذا لم تظهر بطاقة NVIDIA فلا تبدأ التدريب المحلي.

## 6) التقييم قبل النشر

اختبر خمسة prompts لم تكن في البيانات:

1. فونك دارجة باللهجة.
2. trap إنجليزي مع Hook عربي.
3. soundtrack cyberpunk instrumental.
4. راب بالفرنسية مع عنوان عربي.
5. طلب غامض عن الانتقال من الحزن إلى القوة.

المطلوب: أقسام واضحة، Hook قابل للغناء، لغة متسقة، وبدون commentary أو صدى prompt. إذا ظهر prompt echo، أصلح البيانات ولا ترفع adapter معطوباً.

## 7) نشر Adapter إلى Hugging Face

بعد نجاح التدريب:

```bash
modal secret create hf-write HF_TOKEN=hf_xxxxxxxxx
modal run fenix-brain-modal/publish_adapters.py --only music
```

الناتج المتوقع:

```text
Hakari66684/fenix-music-lora/
└── fenix-music-adapter.zip
```

إذا ظهر `لا يوجد adapter بعد`، ارجع للتدريب. وإذا ظهر `401` أو `403`، راجع Write permission في التوكن. لا تنشر Space قبل نجاح هذه الخطوة.

## 8) نشر عقل الموسيقى على Modal GPU

```bash
modal deploy fenix-music/generator/music_brain_modal.py
```

الخدمة تقرأ Adapter من:

```text
fenix-training-out:/adapter
```

احفظ رابط Modal الذي يطبعه الأمر، وغالباً يكون بصيغة:

```text
https://<workspace>--fenix-music-brain.modal.run
```

فحص Health:

```bash
curl -i https://<modal-music-url>/
```

فحص Brain حقيقي:

```bash
curl -sS -X POST \
  https://<modal-music-url>/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"fenix-music","temperature":0.8,"max_tokens":700,"messages":[{"role":"system","content":"You are Fenix Music. Output only structured song lyrics."},{"role":"user","content":"Write a dark Moroccan Darija phonk chorus about a midnight escape."}]}'
```

يجب أن يرجع JSON فيه `choices[0].message.content` وكلمات فعلية. Health وحده لا يثبت أن Adapter يعمل.

## 9) نشر HF Space

مجلد الجاهز:

```text
fenix-music-brain-space/
├── Dockerfile
├── app.py
├── requirements.txt
└── README.md
```

على Hugging Face:

1. أنشئ Space جديداً واختر **Docker**.
2. سمّه `fenix-music`، أو اضبط الرابط الحقيقي في `MUSIC_HF_URL`.
3. ارفع محتوى المجلد كاملاً، وليس `app.py` فقط.
4. أضف Space Secret باسم `HF_TOKEN` إذا كان LoRA repository خاصاً.
5. افتح Logs وتأكد من:

```text
attaching the trained Fenix Music mind...
Fenix Music Brain is READY
```

فحص Space:

```bash
curl -i https://hakari66684-fenix-music.hf.space/
```

ثم أرسل POST payload نفسه إلى:

```text
https://hakari66684-fenix-music.hf.space/v1/chat/completions
```

### keepalive

بعد حفظ `.github/workflows/brains-keepalive.yml` في GitHub:

1. افتح Actions.
2. اختر **Fenix Brains Keepalive**.
3. شغّل **Run workflow** مرة واحدة.
4. بعد ذلك يتكرر كل 10 دقائق.

هذا يوقظ المساحة، لكنه لا يضمن أن Free CPU Space تستطيع تحميل Qwen 4B دائماً. Modal GPU هو الأساسي، وHF Space fallback. لا تصف Space كـ24/7 مضمون قبل POST ناجح.

## 10) الربط داخل Fenix

في `server.py` ترتيب الموسيقى:

```text
1. MUSIC_BRAIN_URL       Modal Music
2. MUSIC_HF_URL          Music HF Space
3. CORE_BRAIN_URL        Modal Core
4. CORE_HF_URL           Core HF Space
5. Gemini                fallback
```

عند اختلاف الروابط، اضبطها من **Freebuff → Settings → Environment**:

```text
MUSIC_BRAIN_URL=https://<modal-music-url>
MUSIC_HF_URL=https://<music-space-url>
CORE_BRAIN_URL=https://<modal-core-url>
CORE_HF_URL=https://<core-space-url>
```

استخدم base URL بلا `/v1`، لأن الخادم يضيف `/chat/completions` بنفسه. لتعطيل حلقة محددة ضع `off` مثل `MUSIC_HF_URL=off`.

اختبار route من الخادم:

```bash
curl -sS -X POST http://localhost:5000/api/music/lyrics \
  -H 'Content-Type: application/json' \
  -d '{"genre":"phonk","mood":"dark","language":"Darija","topic":"midnight escape"}'
```

إذا عاد الرد من Gemini بينما Modal وSpace غير جاهزين، التطبيق سليم لكن العقل المدرّب لم يُستخدم بعد.

## 11) رسالة نسخ جاهزة لمساحة Fenix Music chat

انسخ الرسالة التالية حرفياً. لا تطلب من المساحة بناء Trainer جديداً:

```text
جهّز Fenix Music brain من مستودع Fenix-ai باستخدام الملفات الجاهزة فقط. لا تعِد بناء الخادم ولا الواجهة ولا Trainer.

انسخ أو حدّث:
- fenix-music/generator/music_brain_modal.py
- fenix-music-brain-space/ كاملاً
- fenix-music/training/MUSIC-BRAIN-GUIDE.md
- .github/workflows/brains-keepalive.yml

لا تغيّر chain logic في server.py إلا إذا كان مفقوداً:
Music Modal → Music HF Space → Core Modal → Core HF Space → Gemini.

لا تضع مفاتيح داخل Git. استخدم Settings → Environment للمفاتيح، وModal Secret لـ HF Write token.
لا تدّعي أن Space أو LoRA منشور قبل GET وPOST فعليين. إذا كان Space يعيد 404 أو Modal يعطي disabled، أبقِ Gemini fallback واذكر أن النشر لم يكتمل.
بعد نشر Space شغّل keepalive مرة واحدة، واضبط MUSIC_BRAIN_URL وMUSIC_HF_URL على الروابط الحقيقية.
اختبر <BASE>/chat/completions ثم /api/music/lyrics في التطبيق.
```

لا ترسل الرسالة قبل أن تكون ملفات Fenix-ai ظاهرة في commit يمكن للمساحة الأخرى قراءته.

## 12) إعادة التدريب

بعد جمع feedback حقيقي:

```bash
python3 fenix-music/training/gen_examples.py --count 24
python3 -m py_compile fenix-music/training/gen_examples.py
modal run fenix-brain-modal/train_all.py --only music --epochs 3
modal run fenix-brain-modal/publish_adapters.py --only music
modal deploy fenix-music/generator/music_brain_modal.py
```

ثم أعد تشغيل HF Space من Hugging Face. لا تحتاج تعديل `server.py` عند إعادة التدريب.

## 13) متى نعتبر المهمة منتهية

لا تسجل النجاح إلا بعد تحقق كل البنود:

- [ ] `train_all.py --only music` ينتهي `ADAPTER SAVED`.
- [ ] `fenix-training-out:/adapter` فيه Adapter وTokenizer.
- [ ] `publish_adapters.py --only music` رفع `fenix-music-adapter.zip`.
- [ ] Modal Music يرد على GET وPOST.
- [ ] HF Space موجود، build ناجح، وPOST يرد وليس 404.
- [ ] Fenix يستخدم Music Modal/Space، ويصل إلى Core/Gemini عند الفشل.
- [ ] keepalive أُعيد تشغيله بعد نشر Space.

حتى تنجح القائمة، الحالة الصحيحة هي: **التجهيزات موجودة، والعقل المدرّب غير منشور بعد، والتطبيق يعتمد على Gemini fallback**.
