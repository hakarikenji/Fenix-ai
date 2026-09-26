"""The engine token must actually reach the host.

A hosted GPU host meters its daily allowance per caller, and an anonymous
caller gets a small slice of a pool anyone can drain. So the token is the
difference between a working engine and a quota refusal — which means a
silently missing token is a real failure, not a cosmetic one.

These tests check the request actually carries the token, on every request the
app makes, and that no token means no header.
"""
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "api"))
import gradio_client as gc  # noqa: E402

SEEN = {}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        SEEN.setdefault("get", []).append(self.headers.get("Authorization"))
        self._send(b'{"status":"ok"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        SEEN.setdefault("post", []).append(self.headers.get("Authorization"))
        self._send(b'{"event_id":"e1"}')


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)
URL = f"http://127.0.0.1:{srv.server_port}"
ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


saved = os.environ.get("HF_TOKEN")

try:
    # with a token
    os.environ["HF_TOKEN"] = "hf_testtoken123"
    try:
        gc.run("infer", ["small-music", "x", 5, 8, 1.0, "euler", 0], URL, timeout=30)
    except Exception:
        pass  # the fake space has no result; the request is what is under test
    check("the job request carries the token",
          SEEN["post"] and SEEN["post"][-1] == "Bearer hf_testtoken123", str(SEEN["post"]))

    try:
        gc.health(URL)
    except Exception:
        pass
    check("the health request carries the token",
          SEEN["get"] and SEEN["get"][-1] == "Bearer hf_testtoken123", str(SEEN["get"]))

    # without a token
    os.environ.pop("HF_TOKEN", None)
    try:
        gc.run("infer", ["small-music", "x", 5, 8, 1.0, "euler", 0], URL, timeout=30)
    except Exception:
        pass
    check("no token means no header, not a broken one",
          SEEN["post"][-1] is None, str(SEEN["post"][-1:]))

    # a blank token must not send an empty bearer
    os.environ["HF_TOKEN"] = "   "
    try:
        gc.run("infer", ["small-music", "x", 5, 8, 1.0, "euler", 0], URL, timeout=30)
    except Exception:
        pass
    check("a blank token is treated as no token", SEEN["post"][-1] is None, str(SEEN["post"][-1:]))
finally:
    if saved is None:
        os.environ.pop("HF_TOKEN", None)
    else:
        os.environ["HF_TOKEN"] = saved
    srv.shutdown()

print("\nALL ENGINE TOKEN TESTS PASSED" if ok else "\nSOME TESTS FAILED")
sys.exit(0 if ok else 1)
