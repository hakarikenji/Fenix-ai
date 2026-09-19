/* Fenix — developer configuration (NON-SECRET, safe to commit).
   ─────────────────────────────────────────────────────────────────
   The AI key itself is NEVER here. It lives only on the server as the
   environment variable GEMINI_API_KEY (Freebuff: Settings → Environment,
   GitHub CI/deploy: repository secrets).

   The ONLY thing you may set here is the production server URL, used by
   the Android APK build to reach your Fenix server. Leave "" while
   developing — the APK will then ask nothing and simply show that the
   server is not linked yet. Web/PWA users never need this: the app talks
   to its own origin automatically.

   Example:
   window.PHOENIX_SERVER = "https://your-phoenix-server.example.com";
*/
window.PHOENIX_SERVER = "";
