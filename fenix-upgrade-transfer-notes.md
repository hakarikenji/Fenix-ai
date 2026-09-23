# رسائل جاهزة للصق — ترقية Fenix Music و Fenix Video بنفس ترقية منظومة Fenix-ai

انسخ الرسالة المناسبة والصقها في محادثة مساحة Freebuff الخاصة بكل تطبيق.
(هذه التعديلات نفسها منفّذة فعلاً هنا في Fenix-ai: `server.py` + `web/index_new.html` + `web/sw.js`)

---

## 1️⃣ الرسالة لمساحة Fenix Music

انسخ من هنا ⬇️

**ترقية استوديو Fenix Music — نفس ترقية منظومة Fenix-ai. طبّقها على هذا المستودع.**

احتفظ بكل المنطق الشغال (سلسلة العقول fenix-music → fenix-core → Gemini، الهوية البصرية، PWA) ولا تستبدل شي بمكان فاضي. المطلوب:

1. **إصلاح كريشر**: صندوق "Audio prompt" لازم يكون عنصر حقيقي قابل للتعديل (`id="mu-prompt-out"`) — لو كان الكود يكتب فيه وهو غير موجود فهذا كريشر، أصلحه.
2. **أضف سلايدر Tempo / BPM** (60–200، افتراضي 140) وسلايدر **Energy** (5 مستويات: Very low → Maximum) في قسم Creation setup، وأرسل قيمهم في نداء `/api/music/audio-prompt` (بدون أي BPM ثابت).
3. **الوضع الصوتي (Vocal style)** لازم يوصل لكل شيء: لو "Instrumental only" → برومبت الكلمات يقول "instrumental — no lyrics, structure labels only"، وقيمته توصل برومبت الصوت والتوليد.
4. **زر Variation**: زر بجانب Generate + زر shuffle بجانب كل تراك في المكتبة — يعيد التوليد بنفس الإعدادات مع seed جديد (أضف `seed` اختياري لنداء `/api/music/generate`).
5. لو المستخدم ما بنى برومبت صوت، كوّن برومبت احتياطي من إعداداته (genre, mood, bpm, energy, vocal, duration, topic) — التوليد لا يمشي أبداً ببرومبت فاضي.
6. نفس الهوية: دارك نيفي + بنفسجي + ذهبي، إنجليزي افتراضي مع عربي اختياري. ولا تخفي أي functionality شغالة — أي ميزة غير مدعومة من النموذج علّمها "غير متاح" بأمانة بدل التمثيل.

بعد التطبيق: شغّل التطبيق وتأكد أن "Build audio prompt" يعرض النتيجة في الصندوق، وأن Variation يضيف تراك جديد للمكتبة.

انسخ إلى هنا ⬆️

---

## 2️⃣ الرسالة لمساحة Fenix Video

انسخ من هنا ⬇️

**ترقية استوديو Fenix Video — نفس ترقية منظومة Fenix-ai. طبّقها على هذا المستودع.**

احتفظ بكل المنطق الشغال (سلسلة العقول fenix-video → fenix-core → Gemini، الرندر على الجهاز، PWA) ولا تستبدل شي بمكان فاضي. المطلوب:

1. **أضف إلى Project settings**: قائمة **Target duration** (~15s / ~25s / ~40s) وقائمة **Camera style** (Slow dolly-in / Handheld energy / Aerial drone sweep / Static tripod / Dynamic tracking). أرسل `duration` و `camera` في نداء `/api/video/script` — والبرومبت النظامي في `api/brain.py` يذكّر العقل بهما (المشاهد تُبنى حول المدة المطلوبة، وأسلوب الكاميرا يدخل في وصف كل مشهد).
2. **منتقي Background music**: None / **Fenix Music brain** / Upload my own file.
   - خيار Fenix Music brain: يجيب `/api/music/generate` (نفس سلسلة عقول الموسيقى) ببرومبت "instrumental underscore" ومدة = مدة الفيديو الفعلية (سقف 30 ثانية). لو التوليد غير مُهيأ (لا GPU worker ولا HF_TOKEN) → رسالة صادقة "Music unavailable" ولا يفشل الرندر — الرندر يكمل بدون موسيقى.
   - خيار Upload: يبقى كما هو (ملف محلي).
3. **التوافق مع سرفر الفيديو**: في `api/brain.py` قَبِل حقلي `duration` و `camera` إختياريين في `write_script()` ومرّرهما للبرومبت — كذلك في سرفر Fenix-ai الرئيسي إذا كان يستدعي `write_script`.
4. مدة الفيديو المعروضة تُحسب من مجموع مدد المشاهد الحقيقية بعد توليد السيناريو.
5. الرندر الحالي صادق ويحترم المفاتيح (voice-over / captions / watermark) — لا تغيّر هذا السلوك.
6. نفس الهوية: دارك نيفي + بنفسجي + ذهبي، إنجليزي افتراضي مع عربي اختياري.

بعد التطبيق: ولّد سيناريو وتأكد أن المدة الكلية تقارب الاختيار، وأن خيار موسيقى الفينكس يعمل أو يعرض رسالة صادقة.

انسخ إلى هنا ⬆️

---

## 3️⃣ (اختياري) لو تبي ترقية Fenix-ai نفسها تنزل لـ GitHub

التعديلات هنا جاهزة وغير مدفوعة بعد (Feniff's Changes panel يدير الحفظ):
- `server.py` — +350 سطر: عقول Music/Video مدمجة + `/api/brains` + `/api/music/*` + `/api/video/*` + إرسال energy/vocal لبرومبت الصوت + seed للتوليد
- `web/index_new.html` — واجهة المنظومة الكاملة (جديدة، غير مُتتبّعة)
- `web/sw.js` — ترقية كاش v11-ecosystem

لو تبي أنا أدفعهم، قل "ادفع" وأنا أنفذ commit + push من هنا.
