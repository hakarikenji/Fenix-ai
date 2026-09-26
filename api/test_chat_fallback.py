"""The chat path the browser actually uses.

The app streams a reply and falls back to a whole-reply JSON call when the
stream cannot be read. That fallback used to point at a route that did not
exist, so any stream hiccup became a dead end reported as "server unreachable".

These tests check the fallback answers, that both transports agree, that the
stream framing is valid, and that a broken brain is reported rather than
silently returning an empty reply.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, ".")
sys.path.insert(0, "api")

import server  # noqa: E402

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
APP = None
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def post(path, payload, timeout=90):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def read_stream(path, payload, timeout=90):
    """Read an SSE response the way the browser does: chunk by chunk."""
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        events, buf = [], ""
        while True:
            chunk = r.read(1)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            if buf.endswith("\n\n"):
                block, buf = buf[:-2], ""
                line = block.find("data:")
                if line < 0:
                    continue
                try:
                    events.append(json.loads(block[line + 5:].strip()))
                except ValueError:
                    events.append({"t": "unparsed", "raw": block})
    return ctype, events


def main():
    global APP
    from werkzeug.serving import make_server

    APP = make_server("127.0.0.1", PORT, server.app, threaded=True)
    threading.Thread(target=APP.serve_forever, daemon=True).start()
    time.sleep(0.6)

    print("\n[1] the stream still works")
    ctype, events = read_stream("/api/chat/stream", {"message": "hi", "history": []})
    check("stream is an event stream", "text/event-stream" in ctype, ctype)
    check("stream ends with a done event",
          any(e.get("t") == "done" for e in events), events)
    check("no frame is left unparsed",
          not any(e.get("t") == "unparsed" for e in events), events)
    stream_text = "".join(e.get("v", "") for e in events if e.get("t") == "delta")

    print("\n[2] the fallback answers, because the route exists")
    status, body = post("/api/chat", {"message": "hi", "history": []})
    check("POST /api/chat is not 405", status == 200, f"status={status} body={body[:160]}")
    data = json.loads(body) if body.startswith("{") else {}
    check("the reply is a real string", bool((data.get("reply") or "").strip()), data)
    check("the brain is named", bool(data.get("brain")), data)

    print("\n[3] both transports answer from the same brain")
    # The wording is sampled fresh on every call, so it cannot be compared.
    # What must match is which brain answered and that both produced a reply:
    # a fallback that quietly reached a different provider is the real bug.
    stream_brain = next((e.get("brain") for e in events if e.get("t") == "done"), None)
    check("the same brain answers either way", stream_brain == data.get("brain"),
          f"stream={stream_brain!r} json={data.get('brain')!r}")
    check("the stream produced a reply too", bool(stream_text.strip()), stream_text)

    print("\n[4] a real user message, the one that failed in the app")
    status, body = post("/api/chat", {"message": "بأي عقل تشتغل", "history": [],
                                      "model": "flash", "style": "concise"})
    check("arabic message is answered", status == 200, f"status={status}")
    data = json.loads(body) if body.startswith("{") else {}
    check("arabic answer is non-empty", bool((data.get("reply") or "").strip()), data)

    print("\n[5] bad input is refused clearly, not as a fake reply")
    status, body = post("/api/chat", {"message": "", "history": []})
    check("empty message is rejected", status == 400, f"status={status} {body[:120]}")
    check("the rejection explains itself", "error" in body, body[:120])

    print("\n[6] a brain that cannot answer is reported, never faked")
    original = server.custom_brain_reply
    original_free = server._free_core_reply
    original_gemini = server.KEY
    try:
        server.custom_brain_reply = lambda *a, **k: None
        server._free_core_reply = lambda *a, **k: None
        server.KEY = "definitely-not-a-valid-key"
        status, body = post("/api/chat", {"message": "hi", "history": []})
        data = json.loads(body) if body.startswith("{") else {}
        check("an unavailable brain is a 5xx", 500 <= status < 600, f"status={status}")
        check("no empty reply is invented", not (data.get("reply") or "").strip(), data)
        check("the reason is given", bool(data.get("error")), data)
    finally:
        server.custom_brain_reply = original
        server._free_core_reply = original_free
        server.KEY = original_gemini

    APP.shutdown()
    print(f"\n{'FAILED: ' + ', '.join(FAILURES) if FAILURES else 'all chat-fallback checks passed'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
