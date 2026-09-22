# رسالة جاهزة — انسخها والصقها في مساحة Fenix-video الجديدة

**أولاً**: من freebuff.com/cloud → Connect a repository → اختر `Fenix-video`
(أنشئه من GitHub أولاً إن لم يكن موجوداً: github.com/new — اسمه `Fenix-video` مع README).

ثم في محادثة المساحة الجديدة، الصق:

---

أنشئ تطبيق Fenix Video المستقل من المستودع العام hakarikenji/Fenix-ai (مجلد fenix-video):

1. استنسخ: git clone --depth 1 https://github.com/hakarikenji/Fenix-ai /tmp/fv
2. انسخ كل محتويات /tmp/fv/fenix-video/ إلى جذر هذا المستودع (ملفات المجلد نفسه):
   server.py · api/brain.py · web/ (index.html + manifest.json + sw.js + config.js) ·
   training/ (train_modal.py + serve_modal.py + README.md) ·
   capacitor.config.json · package.json · requirements.txt · README.md
3. من /tmp/fv/fenix-video/ ... لا يوجد workflow ضمن المجلد — أنشئ .github/workflows/build-apk.yml
   بنفس محتوى workflow APK الموجود في /tmp/fv/fenix-music-apk-kit/workflows/build-apk.yml
   مع تغيير اسم الأرباكت إلى: Fenix-Video-debug-apk
4. احذف README.md الافتراضي إن كان موجوداً قبل النسخ (README بتاع Fenix Video يحل محله)
5. git add -A && git commit -m "Fenix Video: free-tier AI video studio — brain chain, scene images, on-device render" && git push origin main
6. نظّف /tmp/fv، وأرني نتيجة workflow الـ Actions

---

## بعد الاكتمال — معمارية Fenix 🦅 مكتملة الثلاثي:
| التطبيق | المستودع | العقل الخاص |
|---|---|---|
| Fenix AI (المساعد) | Fenix-ai | fenix-core ✓ حي |
| Fenix Music | Fenix-music- | fenix-music (يدرب عند رجوع Modal) |
| Fenix Video | Fenix-video | fenix-video (يدرب عند رجوع Modal) |
