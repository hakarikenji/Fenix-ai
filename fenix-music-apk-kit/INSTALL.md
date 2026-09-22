# عدة APK — Fenix Music

انسخ هذه الملفات إلى مستودع `hakarikenji/Fenix-music-` (أنت المالك هناك، والدفع يعمل من مساحتك):

| من هذه العدة | إلى في مستودع Fenix-music- |
|---|---|
| `capacitor.config.json` | `capacitor.config.json` |
| `package.json` | `package.json` |
| `web-index.html` | `web/index.html` (يستبدل الموجود) |
| `web-config.js` | `web/config.js` (جديد) |
| `workflows/build-apk.yml` | `.github/workflows/build-apk.yml` (جديد) |
| `README-apk-section.md` | أضف محتواه في نهاية `README.md` |

ثم:
```bash
git add -A && git commit -m "Android APK via Capacitor + auto-build workflow" && git push origin main
```

بعدها افتح: **Actions → Build Android APK** — وسيبني الـ APK تلقائياً.
حمّله من **Artifacts** وركّبه على جوالك.

## ضبط عنوان الخادم (للـ APK فقط)
عدّل `web/config.js` قبل البناء:
```js
window.FENIX_SERVER = "https://عنوان-خادم-fenix-music";
```
تطبيق الويب/PWA لا يحتاج شيئاً — يتكلم مع أصله مباشرة.
