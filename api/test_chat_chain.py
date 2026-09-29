"""
A 502 that cannot be explained is a 502 nobody can fix.

When the deployment moved host, every message started failing while the access
log showed one bare "502 Bad Gateway" and nothing else. Three unrelated causes
— no key in the environment, the host refusing the outbound connection, a
model name the upstream does not know — all produced exactly that, because the
chain caught the failure, fell through to the next brain, and kept the reason
in a local that was assigned and then never read.

So the chain now has to leave a trace: one line per failed model in the host
error log, a short reason code on the JSON, and an early exit when there is no
key, because asking an unauthorized question of every model in the chain is
three identical failures and one of them is a lie about the cause.

Run:  python3 api/test_chat_chain.py
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stderr

_TMP = tempfile.mkdtemp(prefix="fenix-chat-chain-")
os.environ["FENIX_DATA_DIR"] = _TMP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import server  # noqa: E402

_client = server.app.test_client()

_failures: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _failures.append(label)


def _silence_earlier_brains() -> None:
    """The chain is LoRA -> free cores -> Gemini; only the last one is under test."""
    server.custom_brain_reply = lambda *a, **k: None
    server._free_core_reply = lambda *a, **k: None


def _restore() -> None:
    for name in ("custom_brain_reply", "_free_core_reply", "KEY", "EMBEDDED_MODEL_CHAINS"):
        setattr(server, name, _ORIGINALS[name])
    server.urllib.request.urlopen = _ORIGINALS["urlopen"]


_ORIGINALS = {
    "custom_brain_reply": server.custom_brain_reply,
    "_free_core_reply": server._free_core_reply,
    "KEY": server.KEY,
    "EMBEDDED_MODEL_CHAINS": server.EMBEDDED_MODEL_CHAINS,
    "urlopen": server.urllib.request.urlopen,
}


# ---------------------------------------------------------------- no key ----
print("no key in the environment")
_silence_earlier_brains()
server.KEY = ""
reached_network = []
server.urllib.request.urlopen = lambda *a, **k: reached_network.append(a)
_logged = io.StringIO()
with redirect_stderr(_logged):
    response = _client.post("/api/chat", json={"message": "hello"})
body = response.get_json() or {}

check("an empty chain answers 502", response.status_code == 502)
check("the body says why, not just that it failed", body.get("reason") == "no-key")
check("no reply is invented", body.get("reply") == "")
check("the network is never touched", not reached_network)
check("the reason is written to the host log", "no API key" in _logged.getvalue())
check("the log names no caller-visible vendor", "gemini" not in _logged.getvalue().lower())

# ------------------------------------------------------------- one bill ----
print("\none message is billed once")
server.urllib.request.urlopen = _ORIGINALS["urlopen"]
server.KEY = "test-key-not-used"
server.EMBEDDED_MODEL_CHAINS = dict(_ORIGINALS["EMBEDDED_MODEL_CHAINS"])
server.EMBEDDED_MODEL_CHAINS["flash"] = []
scopes: list[str] = []
server._rate_limit = lambda scope, limit, window_s=60: scopes.append(scope) or (True, None)

with redirect_stderr(io.StringIO()):
    _client.post("/api/chat", json={"message": "hello"})
    _client.post("/api/chat/stream", json={"message": "hello"})

check("the JSON route charges its own bucket only", scopes == ["chat", "chat_stream"])
check("no message is charged twice", len(scopes) == len(set(scopes)))

# ----------------------------------------------------- a real failure ----
print("\na genuine upstream failure is legible")
server.EMBEDDED_MODEL_CHAINS = {"flash": ["brain-one", "brain-two"]}


def _refuse(*a, **k):
    raise OSError("connection refused by peer")


server.urllib.request.urlopen = _refuse
server._chain_error.reason = None
_logged = io.StringIO()
with redirect_stderr(_logged):
    response = _client.post("/api/chat", json={"message": "hello"})
log_text = _logged.getvalue()

check("it still answers 502", response.status_code == 502)
check("the reason distinguishes it from a missing key",
      (response.get_json() or {}).get("reason") == "all-models-failed")
check("every model tried is named in the log",
      "brain-one" in log_text and "brain-two" in log_text)
check("the underlying error text survives", "connection refused" in log_text)
check("the exception class is recorded", "OSError" in log_text)

_restore()

print()
if _failures:
    print(f"{len(_failures)} failed: " + ", ".join(_failures))
    sys.exit(1)
print("ALL CHAT CHAIN TESTS PASSED")
