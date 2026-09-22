## 🤖 تطبيق أندرويد (APK)

التطبيق ملفوف بـ [Capacitor](https://capacitorjs.com) — نفس واجهة الويب داخل تطبيق أندرويد أصلي:

**بناء آلي:** كل دفع على `main` يبني الـ APK تلقائياً
→ **Actions → Build Android APK → Artifacts** → حمّل وركّب (فعّل "مصادر غير معروفة")

**بناء يدوي:**
```bash
npm install
npx cap add android
npx cap sync android
cd android && ./gradlew assembleDebug
```

> 🔐 **آمن بالتصميم**: لا مفاتيح داخل التطبيق أبداً — الـ APK يتصل بخادم Fenix Music.
> عنوان الخادم الوحيد المطلوب: ضعه في `web/config.js` (`window.FENIX_SERVER`) قبل `npx cap sync android`.
