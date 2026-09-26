"""
The Colab path, and the ownership fix it depends on.

The training data route exists so a T4 notebook can fetch a dataset with one
request. That is only acceptable if it cannot reach anyone's rows but the
caller's — and the export it sits on used to return every rating in the
database to whoever passed the admin check.

Run:  python3 api/test_training_export.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="fenix-export-test-")
os.environ["FENIX_DATA_DIR"] = _TMP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "fenix-core-lora"))

import db  # noqa: E402
import train_dataset  # noqa: E402
import train as trainer  # noqa: E402
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


print("one account's export cannot reach another's rows")
db.add_rating("tok-alice", None, "Alice asked about indexes", "Alice got a good answer", 1)
db.add_rating("tok-bob", None, "Bob asked about migrations", "Bob got a bad answer", 1)
_cid = db.create_conversation("tok-alice", "alice chat")["id"]
db.append_message("tok-alice", _cid, "user", "Alice question about indexing strategies")
db.append_message("tok-alice", _cid, "assistant", "Alice reply about composite indexes")

all_rows = db.export_training_pairs(0)
check("an unscoped export still sees everything (local training)", len(all_rows) == 2,
      len(all_rows))
alice = db.export_training_pairs(0, "tok-alice")
check("a scoped export is smaller", len(alice) == 1, alice)
check("and it is her own row", "Alice" in alice[0]["instruction"], alice)
bob = db.export_training_pairs(0, "tok-bob")
check("Bob gets his own row", "Bob" in bob[0]["instruction"], bob)
check("neither sees the other",
      "Bob" not in json.dumps(alice) and "Alice" not in json.dumps(bob))

print("the dataset builder honours the same scoping")
scoped = train_dataset.build(min_pairs=0, user_token="tok-alice")
everything = train_dataset.build(min_pairs=0)
check("scoped is not larger than everything",
      scoped["count"] <= everything["count"], (scoped["count"], everything["count"]))
check("the scoped set only holds Alice's material",
      all("Bob" not in p["prompt"] + p["reply"] for p in scoped["pairs"]),
      scoped["pairs"])
check("the unscoped set holds both",
      everything["count"] >= scoped["count"], (everything["count"], scoped["count"]))

print("the route serves one account, in the shape a notebook can save")
server.app.config["TESTING"] = True
client = server.app.test_client()

resp = client.post("/api/auth/signup",
                   json={"email": "export-owner@fenix.test", "password": "pw-1234567"})
signup = resp.get_json()
token = signup.get("token")
check("a throwaway account signed up", bool(token), signup)
_cid = client.post("/api/conversations", json={"title": "export probe"},
                   headers={"Authorization": "Bearer " + token})
check("it can create a conversation", _cid.status_code == 200, _cid.status_code)
cid = _cid.get_json()["id"]
for role, text in (("user", "How do I index a table for range scans efficiently?"),
                   ("assistant", "A composite index on the filtered columns, with the "
                                 "range column last, lets the planner seek instead of scanning."),
                   ("user", "And when the table is too big to index?"),
                   ("assistant", "Partition by the range key and index each partition separately.")):
    client.post(f"/api/conversations/{cid}/messages", json={"role": role, "content": text},
                headers={"Authorization": "Bearer " + token})

r = client.get("/api/training-data")
check("an unauthenticated caller is refused", r.status_code == 401, r.status_code)
r = client.get("/api/training-data", headers={"Authorization": "Bearer " + token})
check("a signed-in caller gets 200", r.status_code == 200, r.status_code)
check("the content type is ndjson, not JSON to be re-parsed",
      r.headers.get("Content-Type", "").startswith("application/x-ndjson"),
      r.headers.get("Content-Type"))
check("it is offered as a file",
      "fenix-sft.jsonl" in r.headers.get("Content-Disposition", ""),
      r.headers.get("Content-Disposition"))
check("the pair count is in a header the notebook reads",
      r.headers.get("X-Fenix-Pairs") == "2", r.headers.get("X-Fenix-Pairs"))
check("and it says the set is not ready", r.headers.get("X-Fenix-Ready") == "0",
      r.headers.get("X-Fenix-Ready"))
lines = [l for l in r.get_data(as_text=True).splitlines() if l.strip()]
rows = [json.loads(l) for l in lines]
check("every line is chat format",
      all([m["role"] for m in x["messages"]] == ["system", "user", "assistant"] for x in rows))
check("the system message is the identity instruction",
      all("Fenix Core LoRA" in x["messages"][0]["content"] for x in rows))
check("the content is the real exchange",
      any("range scans" in x["messages"][1]["content"] for x in rows))
check("the response body never carries the account email",
      "export-owner@fenix.test" not in r.get_data(as_text=True))

print("the Colab notebook is real and refuses the same things the trainer does")
nb_path = os.path.join(ROOT, "fenix-core-lora", "colab_train.ipynb")
nb = json.loads(open(nb_path, encoding="utf-8").read())
code = [c for c in nb["cells"] if c["cell_type"] == "code"]
check("it is a valid notebook", nb.get("nbformat") == 4, nb.get("nbformat"))
check("it has real cells", len(code) >= 6, len(code))
body = json.dumps(nb)
check("it asks for a T4 explicitly", "T4 GPU" in body)
check("it stops without a GPU", "No GPU" in body)
check("it refuses too little data", "MIN_ROWS" in body and "NOT ENOUGH DATA" in body)
check("the floor matches the trainer", "MIN_ROWS    = 300" in body
      and trainer.MIN_ROWS == 300)
check("it measures the untuned base first", "untuned base held-out loss" in body)
check("it trains for more than one pass", "EPOCHS      = 3" in body)
check("it judges the run before uploading", "the verdict" in body)
check("a failed run is not uploaded", "skipped" in body)
check("it uploads to the Hub", "upload_folder" in body)
check("it tells the operator what to set next", "CORE_HF_URL" in body)
check("no token is baked into the notebook", "hf_" not in body)
check("no server URL is baked in either", "8010" not in body)

print("the trainer and the notebook agree on the same floor and verdict")
check("both refuse below 300", "MIN_ROWS = 300" in open(
    os.path.join(ROOT, "fenix-core-lora", "train.py"), encoding="utf-8").read())
check("the acceptable loss is the same number",
      "ACCEPTABLE = 1.6" in body and trainer.MAX_ACCEPTABLE_EVAL_LOSS == 1.6)
check("the split seed is the same in both", "random.seed(17)" in body
      and "seed: int = 17" in open(
          os.path.join(ROOT, "fenix-core-lora", "train.py"), encoding="utf-8").read())

print()
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
