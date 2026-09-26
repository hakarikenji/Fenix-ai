"""
The training flywheel, end to end — minus the GPU.

Three claims are checked here, because each one has already been false once:

1. A conversation is actually stored on the server. The route existed and the
   client never called it, so the flywheel had no input.
2. The dataset builder refuses to hand over a set too small to learn from.
   The current adapter is what happens when nobody refuses.
3. The training script refuses to run without a GPU and judges the result on a
   held-out split, instead of reporting success on training loss alone.

Run:  python3 api/test_training_flywheel.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-flywheel-test-")
os.environ["FENIX_DATA_DIR"] = _TMP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "fenix-core-lora"))

import train_dataset  # noqa: E402
import train as trainer  # noqa: E402

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


print("the client actually stores the exchange")
ui = open(os.path.join(ROOT, "web", "index_new.html"), encoding="utf-8").read()
server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
check("there is a helper that posts both turns", "async function persistExchange(" in ui)
check("it writes to the messages route", "/messages'" in ui and "persistExchange" in ui)
check("it is called after a streamed reply", ui.count("persistExchange(c, text, reply)") >= 2)
check("a failed reply is not stored as a good example",
      "**Connection failed**" in ui)
check("the conversation id is awaited before it is used",
      "await ensureServerConversation(c);" in ui,
      "the id races the first message")
check("the server route the client targets exists",
      '@app.route("/api/conversations/<cid>/messages"' in server)
check("the route requires a signed-in owner", "_require_user()" in server[
    server.index('def api_conversation_append'):][:400])

print("the dataset builder rejects what is not worth training on")
check("it refuses below a floor", train_dataset.MIN_PAIRS >= 100, train_dataset.MIN_PAIRS)
check("it drops one-word exchanges", 'prompt.strip().lower() in ("hi"' in
      open(os.path.join(HERE, "train_dataset.py"), encoding="utf-8").read())
check("it drops duplicates", '"duplicate"' in open(
    os.path.join(HERE, "train_dataset.py"), encoding="utf-8").read())
check("it checks for a repetitive set", train_dataset.MAX_DUPLICATE_SHARE <= 0.1)
check("it refuses a reply that names another engine",
      train_dataset.FORBIDDEN.search("I am powered by GPT") is not None)
check("it allows a reply that does not", train_dataset.FORBIDDEN.search(
    "I am Fenix Core LoRA, built by Hakari.") is None)
check("an empty exchange is not a pair",
      train_dataset.looks_like_a_real_exchange("", "x") is False)
check("a real exchange is a pair",
      train_dataset.looks_like_a_real_exchange(
          "Why does my migration lock the table for four minutes?",
          "Because ALTER TABLE without a lock timeout waits for every reader to finish.")
      is True)
check("a placeholder is not a pair",
      train_dataset.looks_like_a_real_exchange("(see attachment)", "here is the file") is False)

report = train_dataset.build()
check("a build with no real usage reports not-ready", report["ready"] is False, report)
check("and says why, in numbers", any("usable pairs" in p for p in report["problems"]),
      report["problems"])
check("it does not pretend a handful of rows is a dataset",
      report["count"] < train_dataset.MIN_PAIRS)

print("it writes a well-formed file when the set is genuinely good")
good = [{"prompt": f"A real question number {i} about how a database index works?",
         "reply": f"Answer {i}: the index is a sorted structure the planner can seek with.",
         "source": "rating", "rated": True, "fingerprint": f"fp{i}"} for i in range(400)]
path = train_dataset.write_jsonl({"pairs": good}, os.path.join(_TMP, "sft.jsonl"))
check("the file is written", os.path.exists(path))
lines = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
check("one line per pair", len(lines) == 400, len(lines))
check("each line is a chat format", all(
    [m["role"] for m in l["messages"]] == ["system", "user", "assistant"] for l in lines))
check("the identity instruction is on every row",
      all("Fenix Core LoRA" in l["messages"][0]["content"] for l in lines))

print("the training script will not fake a result")
src = open(os.path.join(ROOT, "fenix-core-lora", "train.py"), encoding="utf-8").read()
check("it refuses to train on CPU", "No CUDA GPU is available" in src)
check("it will not run without a dataset", "No dataset at" in src)
check("it has a row floor too", "rows in {args.data}" in src)
check("it holds out a split the model never trains on", "def split(" in src
      and "eval_idx" in src)
check("it measures loss on the held-out split", "trainer.evaluate()" in src)
check("it masks the prompt so the model is not trained to echo", "labels[i] = -100" in src)
check("it trains for epochs, not six steps", "num_train_epochs=args.epochs" in src
      and "DEFAULT_EPOCHS = 3" in src)
check("it judges the run on held-out loss", "def verdict(" in src)
check("a bad result is reported as failed", "This run did not learn" in src)
check("there is more than one full pass by default", trainer.DEFAULT_EPOCHS >= 3)
check("the loss ceiling is a real number", 0 < trainer.MAX_ACCEPTABLE_EVAL_LOSS < 5)

print("the split is genuinely held out")
rows = trainer.load_rows(path)
tr, ev = trainer.split(rows, seed=3)
check("both sides are populated", len(tr) > 0 and len(ev) > 0, (len(tr), len(ev)))
check("they do not overlap", not ({r["prompt"] for r in tr} & {r["prompt"] for r in ev}))
check("together they are the whole set", len(tr) + len(ev) == len(rows))
check("the same seed gives the same split",
      [r["prompt"] for r in trainer.split(rows, seed=3)[1]]
      == [r["prompt"] for r in ev])

print("verdicts are decided by evidence, not by optimism")
ok, notes = trainer.verdict(0.9, None, type("A", (), {"max_eval_loss": 1.6})())
check("a good loss passes", ok is True, notes)
ok, notes = trainer.verdict(2.4, None, type("A", (), {"max_eval_loss": 1.6})())
check("a bad loss fails", ok is False, notes)
ok, notes = trainer.verdict(2.0, 1.1, type("A", (), {"max_eval_loss": 1.6})())
check("no better than the untuned base fails", ok is False, notes)
ok, notes = trainer.verdict(0.8, 1.9, type("A", (), {"max_eval_loss": 1.6})())
check("a clear improvement passes", ok is True, notes)
ok, notes = trainer.verdict(None, None, type("A", (), {"max_eval_loss": 1.6})())
check("no evaluation at all fails", ok is False, notes)

print("the status page no longer claims a brain that cannot answer")
check("routing is computed", "def brain_routing()" in server)
check("it says when nothing trained is serving", "no trained brain is serving" in server)
check("core.active reflects what answered", '"active": "fenix-core-lora" if CUSTOM_BRAIN_STATE == "live" else "fallback"' in server)
check("the routing is no longer a literal",
      '"routing": brain_routing()' in server and
      '"order": ["fenix-core-lora"]' not in server)

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
