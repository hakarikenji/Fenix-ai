# 🐦‍🔥 Fenix

**Fenix — an AI assistant built by Hakari**, powered by the **Fenix Core LoRA** brain. The public identity is one thing: every Fenix product answers as Fenix Core LoRA. Under the hood a private brain chain keeps it online 24/7 — the routing stays server-side and never reaches the client.

Works as an installable PWA on any phone and as a native Android APK. **Zero user configuration**: the AI key lives only on the server; users open the app, sign in, and chat.

## 🔐 Where the AI key lives (developer)

| Environment | Where to set it |
|---|---|
| Freebuff sandbox / preview | `.env.local` → `GEMINI_API_KEY` (already set) |
| Freebuff production hosting | **Deploy → Environment** → add `GEMINI_API_KEY` |
| GitHub Actions / other hosting | Repository secret `GEMINI_API_KEY` |

The client never sees any key. The APK needs only **one non-secret value**: your server URL, set by you in `web/config.js` (`window.PHOENIX_SERVER`) before building. Web/PWA users need nothing at all — the app talks to its own origin.

## 💬 The app

- **Email accounts**: sign up / sign in (PBKDF2-hashed passwords, bearer tokens). Guests can chat — everything stays on-device
- **Structured memory (user-controlled)**: six categories — preferences, projects, goals, working style, facts, temporary context. View, edit, delete, clear, and export everything. Fenix never stores anything behind your back
- **Fenix Evolution**: a separate layer that learns how Fenix should *work with you* — only from repeated evidence (3+ observations before an insight becomes active), never invented. Fully inspectable Evolution Log; correct, delete or disable it entirely
- **Fenix Coder (projects)**: create a project (name, stack, goal, files) — every message runs through the elite code-builder persona with full project context. Verification honesty built in: code is labeled **Proposed** until you actually run it — Fenix never says "Fixed" or "Test passed" without a real confirmation
- **Challenge Mode**: when Fenix sees a materially better approach it offers a factual comparison instead of blindly following
- **Web research**: for time-sensitive questions Fenix searches the web, fetches pages, and shows numbered **Sources** — only when `SERPER_API_KEY` is configured on the server; otherwise it says so honestly instead of faking results (get a free key at [serper.dev](https://serper.dev))
- **Real chat with memory**: the model remembers the whole conversation including images and documents
- **Voice input 🎙**: native speech recognition in the APK, Web Speech API in browsers
- **Attachments**: photo library, native camera, documents (PDF, code, CSV, JSON…)
- Model fallback chain: if a Gemini model is under pressure or retired, the app moves to the next one automatically

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

> ✅ **Secure by design** — no AI key in the app, ever. The APK calls your Fenix server, which holds `GEMINI_API_KEY` in its environment. Set your server URL once in `web/config.js` before `npx cap sync android`.
>
> Native camera capture uses the `@capacitor/camera` and voice input the `@capacitor-community/speech-recognition` plugin — both open a proper native permission prompt on first use.
>
> 🔐 Server-side data (accounts, projects, memory, evolution) lives in `.data/` (gitignored JSON with PBKDF2-hashed passwords). Memory and evolution are per-user and fully user-controlled (view / edit / delete / export / disable).

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
3. Fenix appears with its phoenix icon — full screen, no browser bar

## 🗂️ Project structure

```
server.py                Flask server: UI + /api/chat /api/auth/* /api/projects* /api/memory* /api/evolution*
api/
  common.py              Fenix personas (identity, coder, verification honesty) + Gemini calls
  store.py               Accounts (PBKDF2) + cloud projects
  memory.py              Structured memory store (6 categories, CRUD + export)
  evolution.py           Evidence-based evolution profile + log
  research.py            Serper web search + Gemini synthesis (honest when unconfigured)
  quota.py               Server-side generation allowance for Music + Video (FREE-GENERATION-ALLOWANCE.md)
web/
  index.html             App UI (PWA + Capacitor APK)
  config.js              The ONLY config file: server URL for the APK (non-secret)
android/                 Capacitor Android project
```

## ⚙️ Setup

Server environment variables (users never see or enter these):

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | ✅ yes | The AI engine (server-side only) — [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `SERPER_API_KEY` | optional | Enables live web research with sources — [serper.dev](https://serper.dev) |
| `SANDBOX_URL` | optional | Isolated code-execution service URL; Fenix never executes generated code in-process |
| `SANDBOX_API_KEY` | optional | Server-only credential for the isolated sandbox provider |
| `SANDBOX_TIMEOUT_MS` | optional | Maximum execution budget, capped at 10 seconds (default `5000`) |
| `MUSIC_DAILY_CREDITS` | optional | Free audio generations per window (default `3`) |
| `VIDEO_DAILY_CREDITS` | optional | Free motion scenes per window (default `5`) |
| `VIDEO_MAX_DURATION_SECONDS` | optional | Hard ceiling on one rendered scene (default `10`) |
| `QUOTA_ENABLED` | optional | `0` turns generation metering off entirely |

Chat, research, memory, lyrics and the whole storyboard half of the video studio
are never metered. See **[FREE-GENERATION-ALLOWANCE.md](FREE-GENERATION-ALLOWANCE.md)**.

On Freebuff: **Settings → Environment** for the sandbox/preview, and **Deploy → Environment** for production hosting. The key is read by the server only — it never reaches any client.

Terminal tools:
```bash
python fenix.py                     # interactive terminal chat
python enhance.py "write a sales report"   # instant Enhanced Prompt
```

## 🧠 Model notes

- Pro models require a paid plan (free-tier quota = 0)
- The server uses a fallback model chain: when any model is pressed or unavailable it automatically moves to the next best one
