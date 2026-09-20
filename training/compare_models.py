"""Fenix Core — Step 4: base vs fine-tuned, scored on the frozen eval set.

Two modes:
  A) Local GPU: score the base model and your LoRA run in-process.
       python training/compare_models.py --run training/runs/<stamp>
  B) Two endpoints (e.g. Ollama/llama.cpp/vLLM serving base and tuned):
       python training/compare_models.py --base-url http://localhost:11434/v1 \
            --base-model qwen3:4b --tuned-url http://localhost:11435/v1 --tuned-model fenix-core

Scoring is deterministic (no judge model): must_include / must_not_include /
regex checks from eval.jsonl. Report prints both models side by side and an
honest verdict line, then saves runs/compare-<stamp>.json + .md.
"""
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = Path(__file__).resolve().parent / "data" / "eval.jsonl"


def load_eval() -> list[dict]:
    return [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------- generation backends ----------------

def gen_endpoint(base_url: str, model: str, system: str, prompt: str, timeout: int = 120) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 600,
    }).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def gen_local(model_dir: str, system: str, prompt: str) -> str:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.bfloat16, device_map="auto")
    texts = tok.apply_chat_template(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True)
    ids = tok(texts, return_tensors="pt").to(model.device)
    out = model.generate(**ids, max_new_tokens=600, temperature=0.2, do_sample=True)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)


class LocalRunner:
    """Loads a model once, generates many — for in-process mode A."""

    def __init__(self, model_dir: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, torch_dtype=torch.bfloat16, device_map="auto")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def __call__(self, system: str, prompt: str) -> str:
        text = self.tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            tokenize=False, add_generation_prompt=True)
        ids = self.tok(text, return_tensors="pt").to(self.model.device)
        out = self.model.generate(**ids, max_new_tokens=600, temperature=0.2, do_sample=True)
        return self.tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)


# ---------------- deterministic scoring ----------------

def score_case(case: dict, answer: str) -> tuple[float, list[str]]:
    checks, notes = [], []
    a = answer or ""
    for s in case.get("must_include", []):
        ok = s.lower() in a.lower()
        checks.append(ok)
        if not ok:
            notes.append(f"missing: {s!r}")
    for s in case.get("must_not_include", []):
        bad = s.lower() in a.lower()
        checks.append(not bad)
        if bad:
            notes.append(f"forbidden present: {s!r}")
    return (1.0 if all(checks) else 0.0), notes


def run_eval(name: str, gen) -> dict:
    rows, passed = [], 0
    for case in load_eval():
        t0 = time.time()
        try:
            answer = gen(FENIX_SYSTEM, case["prompt"])
        except Exception as e:
            answer, err = "", str(e)
        else:
            err = None
        sc, notes = score_case(case, answer)
        passed += sc
        rows.append({"id": case["id"], "category": case["category"], "score": sc,
                     "notes": notes, "answer": (answer or err or "")[:400],
                     "secs": round(time.time() - t0, 1)})
        print(f"  [{name}] {case['id']} ({case['category']}): {'PASS' if sc else 'FAIL'}")
    return {"name": name, "passed": passed, "total": len(rows), "rows": rows}


FENIX_SYSTEM = ("You are Fenix, an AI assistant built by Hakari. "
                "Answer in the user's language. Be honest about what you did and did not do.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="path to a training run dir (in-process LoRA eval)")
    ap.add_argument("--base-url"); ap.add_argument("--base-model", default="base")
    ap.add_argument("--tuned-url"); ap.add_argument("--tuned-model", default="fenix-core")
    args = ap.parse_args()

    results = []
    if args.base_url:
        results.append(run_eval("base", lambda s, p: gen_endpoint(args.base_url, args.base_model, s, p)))
    else:
        results.append(run_eval("base", LocalRunner(BASE := "Qwen/Qwen3-4B-Instruct-2507")))

    if args.run:
        if args.tuned_url:
            results.append(run_eval("fine-tuned", lambda s, p: gen_endpoint(args.tuned_url, args.tuned_model, s, p)))
        else:
            results.append(run_eval("fine-tuned", LocalRunner(args.run)))
    else:
        print("\n(no --run given: base scored only)")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(__file__).resolve().parent / "runs"
    out.mkdir(exist_ok=True)
    (out / f"compare-{stamp}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n================ VERDICT ================")
    lines = []
    for r in results:
        pct = 100 * r["passed"] / max(1, r["total"])
        lines.append(f"{r['name']:<12} {r['passed']:.0f}/{r['total']}  ({pct:.0f}%)")
        print(lines[-1])
    if len(results) == 2:
        b, t = results
        if t["passed"] > b["passed"]:
            print("✅ Fine-tuned BEATS base — safe to deploy as Fenix Core.")
        elif t["passed"] == b["passed"]:
            print("⚖️  Tie — fine-tuning added nothing measurable. Decide on style manually.")
        else:
            print("❌ Fine-tuned is WORSE than base — do NOT deploy; retrain with more/better data.")
    md = "\n".join(["# Fenix Core comparison", "", *lines, ""])
    (out / f"compare-{stamp}.md").write_text(md, encoding="utf-8")
    print(f"\nSaved: runs/compare-{stamp}.json / .md")


if __name__ == "__main__":
    main()
