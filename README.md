# 🔥 Fenix AI

A Claude-style multimodal AI chat app — clean white interface with a teal accent, full conversation memory, and a confident, human personality. Works as an installable PWA on any phone and as a native Android APK.

## 💬 The app

- **Real chat with memory**: the model remembers the entire conversation, including images and documents you shared earlier
- **Floating composer** at the bottom, Enter to send, auto-growing textarea
- **Chats drawer**: multiple conversations saved locally, rename-free titles, one-tap switch and delete
- **Settings sheet**: Intelligence (Flash / Pro), Reply style (Concise / Detailed), Light / Dark theme
- **Attachments**: photo library, camera capture, and documents (PDF, text, code, CSV, JSON…) — previewed before sending
- **Markdown rendering**: headings, lists, tables, code blocks, with one-tap copy on every reply
- **Prompt library** built into the API: Smart Video Finder, Smart Workspace Mode, Side Artifacts
- Model fallback chain: if a Gemini model is under pressure or retired, the server automatically tries the next one — the app never stops

## 🤖 Android APK

The app is wrapped with [Capacitor](https://capacitorjs.com) — the same web UI inside a native Android app with its own Fenix icon and splash screen.

**Automatic build:**
- Every push to `main` runs the GitHub Actions workflow (`.github/workflows/build-apk.yml`)
- Download the APK from **Actions → Build Android APK → Artifacts**
- Install it on your phone (enable "Install from unknown sources" when asked)

**Manual build on your machine:**
```bash
npm install
npx cap sync android
cd android && ./gradlew assembleDebug
# Output: android/app/build/outputs/apk/debug/app-debug.apk
```

> ⚠️ The installed app needs a running server (locally or hosted). Open **Chats → API Server** in the app and set the server URL once — it is saved locally.

## 📱 PWA (quick alternative, no APK)

Installable web app: own icon, full-screen, offline shell, English LTR UI.

- `server.py` — dev server (Flask): serves the UI + `/api/*` endpoints (the API key stays hidden server-side)
- `web/` — the app UI (HTML/CSS/JS) + Manifest + Service Worker + icons
- `api/` — shared AI logic, also usable as cloud functions

**Run locally:**
```bash
pip install -r requirements.txt
python server.py        # serves on 0.0.0.0:8000
```

**Install on your phone:**
1. Open the app URL in Chrome on Android
2. Tap **Install** in the bottom bar (or browser menu → "Add to Home screen")
3. Fenix appears with its fire icon — full screen, no browser bar

## 🗂️ Project structure

```
server.py                Flask dev server: UI + /api/chat /api/enhance /api/library
api/                     Shared AI logic (chat with memory, enhancer, prompt library)
web/                     App UI (used by both PWA and the Capacitor APK)
android/                 Capacitor Android project
capacitor.config.json    Capacitor settings
scripts/                 Icon / splash generators for web + Android
fenix.py, enhance.py     Terminal tools (interactive chat, prompt enhancer)
```

## ⚙️ Setup

Put the key in `.env` (or via Freebuff Settings → Environment):
```
GEMINI_API_KEY=your-api-key-here
```
Get one free at [Google AI Studio](https://aistudio.google.com/app/apikey).

Terminal tools:
```bash
python fenix.py                     # interactive terminal chat
python enhance.py "write a sales report"   # instant Enhanced Prompt
```

## 🧠 Model notes

- Pro models require a paid plan (free-tier quota = 0)
- The server uses a fallback model chain: when any model is pressed or unavailable it automatically moves to the next best one
