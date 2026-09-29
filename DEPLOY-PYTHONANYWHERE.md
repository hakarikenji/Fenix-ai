# Fenix on PythonAnywhere (free, no card)

PythonAnywhere is the one host that runs Flask with a real filesystem and takes
no card. It imports a WSGI file instead of starting a process, which is why
`fenix_wsgi.py` exists and why the Docker and Render files are gone rather than
left in place for a host that would never build them.

## Getting the code onto the host

The repository is public, so the **Bash** tab can clone it directly — no key,
no token, no upload.

```bash
cd ~
git clone https://github.com/hakarikenji/Fenix-ai.git
```

Three details that are easy to get wrong on this host:

- **Clone into the home directory, not into `~/Fenix-ai` under a web app's own
  source root.** PythonAnywhere's *Files* tab and the Bash tab are the same
  filesystem, but the web app's "source code" path is a separate absolute path
  and pasting files there does not update a clone.
- **The WSGI file does not have to sit next to the clone.** PythonAnywhere
  imports the file in the *WSGI configuration file* box, so pasting
  `fenix_wsgi.py` there is enough. If you point that box at the cloned file
  instead, use the absolute path — `~/Fenix-ai` is not a valid import path.
- **Pull, do not re-clone, on every later change:**
  ```bash
  cd ~/Fenix-ai && git pull
  ```
  then **Reload** the web app.

If you prefer not to use git at all, the **Files** tab can upload a zip, but it
has to be unzipped in place and there is no record of what version is running.
Git is the only route that leaves a trace.

## Setup

1. Create a **Beginner** account at pythonanywhere.com (free, no card).
2. **Web** tab → **Add a new web app** → **Manual configuration** → Python 3.11.
   Pick the `username.pythonanywhere.com` domain; no card is needed for it.
3. Open the **WSGI configuration file** and paste the whole of `fenix_wsgi.py`.
   Because that file lives in the config box and not next to the code, paste the
   file body rather than importing it — the import form only works if the
   absolute path is right, and a wrong path fails silently at reload with an
   import error in the log.
4. **Environment variables** in the web app (not the shell, not a dotfile):

   ```
   FENIX_DATA_DIR    /home/username/fenix-data
   GEMINI_API_KEY    your key
   SERPER_API_KEY    your key
   FENIX_ADMIN_EMAIL your email
   ```

   Then install the dependencies from the Bash tab, into the **same** Python
   the web app runs — not into a venv you make yourself, which the WSGI file
   would never import:

   ```bash
   pip install --user -r ~/Fenix-ai/requirements.txt
   ```

   `--user` is the right call here. The site-packages directory is read-only on
   this host, and installing into your home is what the web app's interpreter
   picks up. If the `pip` on PATH is not 3.11, check the exact version the web
   app reports in the **Web** tab and use `pip3.11` instead.

   `FENIX_DATA_DIR` must exist and be writable: `mkdir -p ~/fenix-data`.
   This is the one host where the data survives a restart, so it is the one
   place the training flywheel can accumulate.
5. **Reload** the web app. The log should show the app importing, not a traceback.

## What will not work, and why

This host has limits that are not ours to lift. They are written down here so
none of them is discovered later as a mystery failure.

### Outbound requests are allowlisted

Free accounts may only call allowlisted sites, and only sites with a public,
documented API can be added. Submit a request from the "Anaconda Notebooks /
PythonAnywhere Allow List Request" form, giving the API documentation and the
domain.

| destination | outcome |
|---|---|
| `generativelanguage.googleapis.com` (chat) | requestable — official documented API |
| `serper.dev` (research) | requestable |
| Cohere / OpenRouter / Groq / DeepSeek | requestable |
| `*.modal.run` (a brain you deployed) | **will be refused** — not a public API |
| `*.hf.space` (the music and video engines) | **will be refused** |
| `translate.google.com` (server TTS) | **will be refused** — scraped, not an API |

The last row degrades gracefully: the app already falls back to the browser's
own voice when the server cannot speak. The two before it are real losses, and
the app says so through `/api/music/generator-check` and `/api/video/clip-check`
rather than pretending a track is coming.

### One web worker

The free plan serves the app from a single worker. A streaming chat holds that
worker for the length of the answer, so a second request queues behind it. Fine
for one person, not for a busy site.

### CPU allowance

100 CPU-seconds a day applies to consoles and scheduled tasks. Web requests are
not counted against it, but the single worker still has a real ceiling, and
image generation is the most expensive thing Fenix does in a request.

## Verify after deploying

```bash
curl -s https://username.pythonanywhere.com/healthz          # 200
curl -s https://username.pythonanywhere.com/api/brains | head -c 400
```

Then, in the browser:

- **Does text stream, or arrive all at once?** This is the single most
  important check. A single worker plus a buffering proxy can break SSE, and it
  is not visible from any log.
- **Does `storage.durable` in `/api/brains` say `true`?** It should, on this
  host. If it says `false`, `FENIX_DATA_DIR` was not picked up and the training
  counter will reset.
- **Does the training count survive a reload?** Sign in, send a message, reload
  the web app, and check the counter. This is the whole reason for choosing this
  host.

## On X-Forwarded-For

`_client_address()` ignores `X-Forwarded-For` unless `FENIX_TRUST_PROXY=1`, so
a caller cannot mint a fresh generation allowance by inventing a header. If
this host's proxy does supply that header, the per-account allowance collapses
into one shared bucket until you set the variable.

Do not set it on trust. Call `/api/quota` from two different networks and
compare: if both show the same allowance, they are sharing a bucket and the
variable is needed.
