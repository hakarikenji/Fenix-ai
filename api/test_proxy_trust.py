"""
A header the caller sets is not evidence of anything.

X-Forwarded-For is how Fenix sees the real client when a proxy sits in front.
When there is no such proxy, the same header is just a string the caller
chooses — and believing it handed anyone unlimited rate-limit buckets and,
worse, a fresh generation allowance, by sending a new value each time.

Metering and rate limiting now resolve the caller through one function, so
there is a single answer to "who is this" and it cannot drift. The default is
to disbelieve the header; a deployment behind a real proxy opts in.

Run:  python3 api/test_proxy_trust.py
"""
import importlib
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-proxy-trust-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["QUOTA_ENABLED"] = "1"
# Deliberately NOT trusted: this suite is about the default.
os.environ.pop("FENIX_TRUST_PROXY", None)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import server  # noqa: E402

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


app = server.app
app.config["TESTING"] = True
client = app.test_client()


def set_trust(on):
    if on:
        os.environ["FENIX_TRUST_PROXY"] = "1"
    else:
        os.environ.pop("FENIX_TRUST_PROXY", None)


print("by default a caller cannot invent a new bucket")
set_trust(False)
a = client.get("/api/quota", headers={"X-Forwarded-For": "198.51.100.1"}).get_json()
b = client.get("/api/quota", headers={"X-Forwarded-For": "203.0.113.99"}).get_json()
# Compare what is metered, not the reset timestamp, which moves every call.
stripped = lambda q: {f: (v["used"], v["remaining"], v["limit"]) for f, v in q["features"].items()}
check("the allowance does not change with the header", stripped(a) == stripped(b),
      (stripped(a), stripped(b)))
with app.test_request_context("/api/quota", headers={"X-Forwarded-For": "198.51.100.1"}):
    check("both callers resolve to the same peer", server._client_address() == "unknown",
          server._client_address())

print("the header is believed when a real proxy is declared")
set_trust(True)
with app.test_request_context("/api/quota", headers={"X-Forwarded-For": "198.51.100.1"}):
    check("the forwarded address is used", server._client_address() == "198.51.100.1",
          server._client_address())
with app.test_request_context("/api/quota", headers={"X-Forwarded-For": "1.1.1.1, 198.51.100.1"}):
    check("the rightmost entry wins, not the one the client wrote",
          server._client_address() == "198.51.100.1", server._client_address())
with app.test_request_context("/api/quota"):
    check("a missing header falls back to the peer", server._client_address() == "unknown",
          server._client_address())
set_trust(False)

print("the caller identity is defined once, for both metering and limiting")
src = open(os.path.join(os.path.dirname(HERE), "server.py"), encoding="utf-8").read()
check("_client_address exists", "def _client_address() -> str:" in src)
check("the quota key uses it", 'quota.key_for("addr:" + _client_address())' in src)
check("the rate limiter uses it", "store.bearer_token() or _client_address()" in src)
check("nothing reads the header directly any more",
      "request.headers.get(\"X-Forwarded-For\")" not in src.replace(
          'request.headers.get("X-Forwarded-For", "")', ""),
      "a second reader would drift from the first")

print("trusting the header is a deliberate, visible choice")
check("the switch is documented in the help text",
      "_trust_proxy" in src and "Off by default" in src)
check("a fresh env is not trusted", server._trust_proxy() is False)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
