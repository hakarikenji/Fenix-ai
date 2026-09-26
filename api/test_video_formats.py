"""
Fenix Video — the three formats.

A format is only real if the director actually writes to it. These checks go
from the catalog in the brain, through the prompt the director receives, to
the JSON the route returns, and confirm that picking a different format
produces a genuinely different brief rather than the same generic short with
a different label.

Run:  python3 api/test_video_formats.py
"""
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-formats-test-")
os.environ["FENIX_DATA_DIR"] = _TMP
os.environ["QUOTA_ENABLED"] = "0"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "fenix-video", "api"))
sys.path.insert(0, HERE)

import brain  # noqa: E402

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


print("the catalog has the three formats, aimed at the two audiences")
check("exactly three formats", set(brain.FORMATS) == {"explain", "ship", "mood"},
      sorted(brain.FORMATS))
check("the default exists in the catalog", brain.DEFAULT_FORMAT in brain.FORMATS)
audiences = {f["audience"] for f in brain.FORMATS.values()}
check("both developers and creators are covered",
      "developers" in audiences and "creators" in audiences, audiences)
for key, spec in brain.FORMATS.items():
    missing = [k for k in ("id", "label", "blurb", "audience", "style",
                           "camera", "ratio", "duration", "direction", "example")
               if not spec.get(k)]
    check(f"{key} is complete", not missing, f"missing {missing}")
    check(f"{key} duration is sane", 10 <= int(spec["duration"]) <= 180, spec["duration"])
    check(f"{key} ratio is one the studio offers",
          spec["ratio"] in ("9:16", "16:9", "1:1", "4:5"), spec["ratio"])

print("a bad or missing format falls back instead of failing")
check("unknown id returns the default", brain.get_format("nope")["id"] == brain.DEFAULT_FORMAT)
check("empty id returns the default", brain.get_format("")["id"] == brain.DEFAULT_FORMAT)
check("case is ignored", brain.get_format("  EXPLAIN ")["id"] == "explain")
check("a real id is honoured", brain.get_format("ship")["id"] == "ship")

print("the format actually reaches the director's prompt")
prompts = {k: brain.script_system("English", "x", "a topic", 30, k) for k in brain.FORMATS}
for key, spec in brain.FORMATS.items():
    p = prompts[key]
    check(f"{key}: its direction is in the prompt", spec["direction"] in p)
    check(f"{key}: it is labelled as a format", "FORMAT:" in p)
    check(f"{key}: the camera language is in the prompt", spec["camera"] in p)
    check(f"{key}: the schema survived", '"scenes"' in p and "valid JSON" in p)
    check(f"{key}: the persona survived", brain.PERSONA in p)
bodies = {prompts[k] for k in prompts}
check("the three prompts are genuinely different", len(bodies) == 3, len(bodies))
check("no format bleeds into another",
      brain.FORMATS["mood"]["direction"] not in prompts["ship"],
      "mood direction leaked into ship")
check("a default-format call still produces a usable prompt",
      "FORMAT:" in brain.script_system("English", "x", "t", 30))

print("the duration budget still applies inside a format")
count, per, rule = brain.scene_budget(45)
check("a 45s brief is a real scene count", count >= 5, (count, per))
check("the rule is stated in the prompt", rule in brain.script_system("English", "x", "t", 45, "explain"))

print("the route serves the catalog and honours the format")
import server  # noqa: E402

server.music_hosts = lambda: []
server.video_hosts = lambda: []
server.app.config["TESTING"] = True
client = server.app.test_client()

r = client.get("/api/video/formats")
d = r.get_json()
check("GET /api/video/formats answers 200", r.status_code == 200, r.status_code)
check("it serves all three", len(d.get("formats", [])) == 3, d)
check("it names a default", d.get("default") in brain.FORMATS, d.get("default"))
served = {f["id"] for f in d["formats"]}
check("the served ids match the brain", served == set(brain.FORMATS), served)
for f in d["formats"]:
    check(f"{f['id']} is JSON-safe and complete",
          {"id", "label", "blurb", "audience", "ratio", "duration"} <= set(f), f)
check("nothing internal leaks to the client",
      not any("direction" in f for f in d["formats"]), "prompt text exposed")

print("a real script request comes back labelled with its format")
seen = {}


def fake_write(language, style, topic, temperature=0.9, duration=25, fmt=None):
    seen["fmt"] = fmt
    seen["style"] = style
    return {"title": "T", "scenes": [{"n": 1, "visual": "v", "vo": "x", "secs": 5}],
            "format": brain.get_format(fmt)["id"]}


vb = server._video_brain()
vb.write_script = fake_write

r = client.post("/api/video/script", json={"topic": "a race condition", "format": "ship"})
d = r.get_json()
check("the route accepted it", r.status_code == 200, (r.status_code, d))
check("the format reached the director", seen["fmt"] == "ship", seen)
check("the reply is labelled", d.get("format") == "ship", d)

r = client.post("/api/video/script", json={"topic": "x", "format": "not-a-format"})
d = r.get_json()
check("a bad format still produces a script", r.status_code == 200, r.status_code)
check("and falls back to the default", d.get("format") == brain.DEFAULT_FORMAT, d)

print("the client sends and shows the format")
ui = open(os.path.join(ROOT, "web", "index_new.html"), encoding="utf-8").read()
check("the picker reads the catalog from the server",
      "apiUrl('/api/video/formats')" in ui)
check("the brief carries the format", "format: VD.format || ''" in ui)
check("the format card markup is present", 'id="vd-formats"' in ui)
check("the storyboard names the format", "VD_FORMATS.byId[d.format]" in ui)
# The cards must be built from the server's catalog, not written into the
# markup — otherwise adding a format means shipping a new front end. Only the
# non-script part of the page counts here; the string inside the builder is
# exactly where a card *should* appear.
markup = re.sub(r"<style[^>]*>[\s\S]*?</style>", "",
                re.sub(r"<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?</script>", "", ui))
check("no format card is baked into the HTML",
      "fmt-card" not in markup, "a card is hard-coded in the markup")
check("the container is empty in the markup",
      'id="vd-formats"' in markup and "Loading formats" in markup)
check("the cards are built from the catalog at runtime",
      "box.innerHTML = list.map" in ui and "loadVideoFormats()" in ui)
check("the state carries the choice", "format: ''" in ui)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
