/* Fenix — developer configuration (NON-SECRET, safe to commit).
   ─────────────────────────────────────────────────────────────────
   The AI key itself is NEVER here. It lives only on the server as the
   environment variable GEMINI_API_KEY (Freebuff: Settings → Environment,
   GitHub CI/deploy: repository secrets).

   FENIX_SERVER is the URL of your Fenix server. It is used ONLY by the
   Android APK (WebView) to reach the API. In a normal browser the app
   always talks to its own origin and this value is ignored.

   To point released APKs at a production server without editing this file,
   add a repository *variable* named FENIX_SERVER in GitHub (Settings →
   Secrets and variables → Actions → Variables) — the build injects it
   automatically and it wins over the value below.

   Example:
   window.FENIX_SERVER = "https://your-fenix-server.example.com";
*/
window.FENIX_SERVER = "https://8000-iawl27qtbmjaeoxrj3nl4.e2b.app";
