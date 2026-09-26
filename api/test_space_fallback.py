"""Contract test: the hosted-Space path.

A hosted Space does not answer a plain POST /, so the server has to speak the
queue protocol. These tests run a fake Space that does, and check that the
server reaches it end to end for both audio and video — plus that a broken or
silent Space is reported rather than swallowed.
"""
import json
import os
import struct
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "api"))
# This suite is about reaching the host, not about the allowance. Metering has
# its own suites (api/test_quota*.py); leaving it on here would spend a shared
# loopback allowance across the repeated fake-Space calls and make later checks
# fail for the wrong reason.
os.environ["QUOTA_ENABLED"] = "0"
import server as s  # noqa: E402

MODE = {"v": "audio"}
SEEN = {}


def wav_bytes(n=32000):
    pcm = b"\x00\x01" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 32000, 64000, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def mp4_bytes(n=40000):
    return b"\x00\x00\x00\x20ftypisom" + b"\x00" * n


class FakeSpace(BaseHTTPRequestHandler):
    """Speaks just enough of the Gradio queue protocol to be a real peer."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self._send(200, b'{"status":"ok","service":"fenix-engine"}')
        if self.path.startswith("/file="):
            # The produced file, served the way a real Space serves it.
            return self._send(200, wav_bytes() if MODE["v"] == "audio" else mp4_bytes(),
                              "application/octet-stream")
        # SSE result stream
        if MODE["v"] == "silent":
            return self._send(200, b"")  # ends with no completed event
        if MODE["v"] == "error":
            payload = b'data: ' + json.dumps({"error": "out of daily allowance"}).encode() + b"\n\n"
            return self._send(200, payload, "text/event-stream")
        if MODE["v"] == "noaudio":
            payload = b'data: ' + json.dumps({
                "data": [{"url": "http://127.0.0.1:1/missing.wav"}]}).encode() + b"\n\n"
            return self._send(200, payload, "text/event-stream")
        data = wav_bytes() if MODE["v"] == "audio" else mp4_bytes()
        name = "x.wav" if MODE["v"] == "audio" else "x.mp4"
        payload = b'data: ' + json.dumps({
            "data": [{"url": f"http://127.0.0.1:{self.server.server_port}/file={name}"}],
            "is_completed": True}).encode() + b"\n\n"
        self._send(200, payload, "text/event-stream")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        if "/call/" not in self.path:
            return self._send(404, b'{"error":"no such route"}')
        try:
            SEEN["last_call"] = json.loads(raw.decode())
        except ValueError:
            SEEN["last_call"] = None
        self._send(200, json.dumps({"event_id": "abc123"}).encode())


srv = HTTPServer(("127.0.0.1", 0), FakeSpace)
SPACE_URL = f"http://127.0.0.1:{srv.server_port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)

c = s.app.test_client()
ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


def clear():
    for k in ("MUSIC_GEN_URL", "VIDEO_GEN_URL", "HF_TOKEN"):
        s.os.environ.pop(k, None)


# 1. audio through the Space
MODE["v"] = "audio"
clear()
s.os.environ["MUSIC_GEN_SPACE_URL"] = SPACE_URL
r = c.post("/api/music/generate", json={"prompt": "dark phonk", "duration": 8, "seed": 5})
d = r.get_json()
check("audio via Space returns 200", r.status_code == 200, str(d)[:120])
check("audio source is the hosted engine", d.get("source") == "hosted-engine", str(d.get("source")))
check("audio bytes are real", isinstance(d.get("bytes"), int) and d["bytes"] > 1000, str(d.get("bytes")))
_args = SEEN.get("last_call", {}).get("data", [])
check("the prompt reached the engine", "dark phonk" in _args, str(_args)[:100])
check("the engine's own signature is used", _args[0] == "small-music", str(_args)[:60])
check("the duration reached the engine", 8 in _args, str(_args)[:100])
check("the seed reached the engine", 5 in _args, str(_args)[:100])

# 2. clip through the Space
MODE["v"] = "video"
s.os.environ["VIDEO_GEN_SPACE_URL"] = SPACE_URL
r = c.post("/api/video/clip", json={"prompt": "neon street", "seconds": 4})
d = r.get_json()
check("clip via Space returns 200", r.status_code == 200, str(d)[:120])
check("clip source is the hosted engine", d.get("source") == "hosted-engine", str(d.get("source")))
check("clip is served back", (d.get("url") or "").startswith("/clip/"), str(d.get("url")))

# 3. a Space that errors must say why, not pretend
MODE["v"] = "error"
r = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
d = r.get_json()
check("Space error surfaces", r.status_code == 503 and "out of daily allowance" in
      str(d.get("last_failure")), str(d.get("last_failure"))[:110])

# 4. a Space that answers but produces nothing usable
MODE["v"] = "silent"
r = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("silent Space is not a success", r.status_code == 503, str(r.status_code))

MODE["v"] = "noaudio"
r = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("Space with no file is not a success", r.status_code == 503, str(r.status_code))

# 5. no host at all -> still an honest 503. An empty value is how the shared
#    public host is turned off.
MODE["v"] = "audio"
clear()
s.os.environ["MUSIC_GEN_SPACE_URL"] = ""
s.os.environ["VIDEO_GEN_SPACE_URL"] = ""
r = c.post("/api/music/generate", json={"prompt": "x", "duration": 5})
check("no host -> 503", r.status_code == 503, str(r.status_code))
# The 503 the user sees stays short on purpose; the check route is what names
# both ways to connect an engine.
d = c.get("/api/music/generator-check").get_json()
check("the check names both host options",
      "MUSIC_GEN_URL" in (d.get("problem") or "")
      and "MUSIC_GEN_SPACE_URL" in (d.get("problem") or ""),
      str(d.get("problem"))[:120])

# 6. the checks see the Space
s.os.environ["MUSIC_GEN_SPACE_URL"] = SPACE_URL
d = c.get("/api/music/generator-check").get_json()
check("audio check reaches the Space", d.get("space_reachable") is True, str(d)[:110])
s.os.environ["VIDEO_GEN_SPACE_URL"] = SPACE_URL
d = c.get("/api/video/clip-check").get_json()
check("clip check reaches the Space", d.get("space_reachable") is True, str(d)[:110])
check("brains advertises both engines",
      c.get("/api/brains").get_json().get("audio_gen") is True)

# 7. a Space URL that points nowhere
s.os.environ["VIDEO_GEN_SPACE_URL"] = "http://127.0.0.1:1"
d = c.get("/api/video/clip-check").get_json()
check("dead Space is reported, not hidden", d.get("space_reachable") is not True and
      bool(d.get("problem")), str(d.get("problem"))[:90])

clear()
srv.shutdown()
print("\nALL SPACE FALLBACK TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
