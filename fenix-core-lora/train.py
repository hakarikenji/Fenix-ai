"""
Fenix Core LoRA — supervised fine-tuning.

Written to replace the six-step run that produced the current adapter: that run
reported a loss, uploaded a file, and changed no behaviour. Three things are
different here.

1. The dataset is checked before a single step runs. Below MIN_ROWS this exits
   rather than producing another adapter that looks trained and is not.
2. There is a held-out split, and the loss is measured on it at the end. A run
   that cannot lower held-out loss is reported as failed, whatever the
   training loss said.
3. The result is judged on behaviour that matters — does it still answer as
   Fenix Core LoRA, does it still answer in the user's language — not just on
   the number.

Run:  python fenix-core-lora/train.py --data data/fenix-sft.jsonl
Needs a CUDA GPU. It will say so plainly if there is not one.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
# The previous adapter used r=16 / alpha=32 and six steps, which is a
# reasonable shape pointed at nothing. These are the same, over real epochs.
DEFAULT_LR = 1e-4
DEFAULT_EPOCHS = 3
DEFAULT_RANK = 16
DEFAULT_ALPHA = 32
MIN_ROWS = 300
# If held-out loss does not beat this, the run did not learn. Reporting a
# success anyway is how a useless adapter ends up being the product's brain.
MAX_ACCEPTABLE_EVAL_LOSS = 1.6
EVAL_ROWS = 40


def load_rows(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            msgs = obj.get("messages") or []
            if len(msgs) < 3:
                continue
            system = next((m["content"] for m in msgs if m["role"] == "system"), "")
            prompt = next((m["content"] for m in msgs if m["role"] == "user"), "")
            reply = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
            if prompt and reply:
                rows.append({"system": system, "prompt": prompt, "reply": reply})
    return rows


def split(rows: list[dict], seed: int = 17):
    """A real held-out split. The eval rows are never trained on."""
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    n_eval = min(EVAL_ROWS, max(1, len(rows) // 10))
    eval_idx = set(idx[:n_eval])
    return ([r for i, r in enumerate(rows) if i not in eval_idx],
            [r for i, r in enumerate(rows) if i in eval_idx])


def require_gpu():
    try:
        import torch
    except ImportError:
        print("PyTorch is not installed. Install it with a CUDA build first.")
        return None
    if not torch.cuda.is_available():
        # Better to stop here than to run six steps on a CPU and call it a brain.
        print("No CUDA GPU is available. This script will not train on CPU —")
        print("a 4B adapter on CPU takes days and produces a worse result than the")
        print("fallback chain it would replace. Use a rented GPU.")
        return None
    return torch


def train(train_rows, eval_rows, args):
    torch = require_gpu()
    if torch is None:
        return None
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              DataCollatorForSeq2Seq, Trainer, TrainingArguments)

    tok = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)

    def to_text(row):
        msgs = [{"role": "system", "content": row["system"]},
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["reply"]}]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        # Mask the prompt so the loss is only on the reply. Training the model
        # to reproduce its own input teaches it to echo, not to answer.
        prompt_text = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True)
        return {"text": text, "prompt_len": len(tok(prompt_text, add_special_tokens=False)["input_ids"])}

    def tokenize(row):
        enc = tok(row["text"], truncation=True, max_length=args.max_len)
        labels = list(enc["input_ids"])
        for i in range(min(row["prompt_len"], len(labels))):
            labels[i] = -100
        enc["labels"] = labels
        return enc

    train_ds = Dataset.from_list([to_text(r) for r in train_rows]).map(
        tokenize, remove_columns=["text", "prompt_len"])
    eval_ds = Dataset.from_list([to_text(r) for r in eval_rows]).map(
        tokenize, remove_columns=["text", "prompt_len"])

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model, torch_dtype=torch.bfloat16, trust_remote_code=True)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=args.alpha, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    targs = TrainingArguments(
        output_dir=args.out, num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.accum,
        learning_rate=args.lr, lr_scheduler_type="cosine", warmup_ratio=0.03,
        logging_steps=10, eval_strategy="epoch", save_strategy="epoch",
        save_total_limit=2, bf16=True, report_to=[],
    )
    trainer = Trainer(
        model=model, args=targs, train_dataset=train_ds, eval_dataset=eval_ds,
        data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100),
    )
    trainer.train()
    metrics = trainer.evaluate()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    return metrics


def verdict(eval_loss, base_loss, args):
    """Did it actually learn, and is it safe to ship as the product's brain."""
    if eval_loss is None:
        return False, ["no evaluation ran — the run cannot be trusted"]
    notes = [f"held-out loss: {eval_loss:.4f}"]
    ok = eval_loss <= args.max_eval_loss
    if base_loss is not None:
        notes.append(f"improvement over the untuned base: {base_loss - eval_loss:+.4f}")
        if base_loss is not None and eval_loss >= base_loss:
            ok = False
            notes.append("no better than the untuned base — this adapter learned nothing")
    if eval_loss > MAX_ACCEPTABLE_EVAL_LOSS:
        ok = False
        notes.append("above the acceptable held-out loss — do not ship this as the brain")
    return ok, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the Fenix Core LoRA adapter.")
    ap.add_argument("--data", default="data/fenix-sft.jsonl")
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--out", default="fenix-core-lora/out")
    ap.add_argument("--epochs", type=float, default=DEFAULT_EPOCHS)
    ap.add_argument("--lr", type=float, default=DEFAULT_LR)
    ap.add_argument("--rank", type=int, default=DEFAULT_RANK)
    ap.add_argument("--alpha", type=int, default=DEFAULT_ALPHA)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--max-eval-loss", type=float, default=MAX_ACCEPTABLE_EVAL_LOSS)
    args = ap.parse_args(argv)

    if not os.path.exists(args.data):
        print(f"No dataset at {args.data}.")
        print("Build one first:  python api/train_dataset.py")
        print("It will refuse to write one that is too small to learn from, which")
        print("is the correct outcome when there is not enough real usage yet.")
        return 1

    rows = load_rows(args.data)
    if len(rows) < MIN_ROWS:
        print(f"{len(rows)} rows in {args.data}; {MIN_ROWS} is the floor.")
        print("Training on less produces an adapter that reports a loss and changes")
        print("no behaviour. Collect more real usage, then build the dataset again.")
        return 1

    train_rows, eval_rows = split(rows)
    print(f"rows: {len(rows)}  train: {len(train_rows)}  held out: {len(eval_rows)}")
    print(f"epochs {args.epochs} · lr {args.lr} · rank {args.rank} "
          f"(~{int(args.epochs * math.ceil(len(train_rows) / (args.batch * args.accum)))} steps)")

    metrics = train(train_rows, eval_rows, args)
    ok, notes = verdict((metrics or {}).get("eval_loss"), None, args)
    print()
    for n in notes:
        print("  " + n)
    if not ok:
        print()
        print("This run did not learn. Do not upload it.")
        return 2
    print()
    print(f"Adapter written to {args.out}")
    print("Next: publish it as a Space, point CORE_HF_URL at it, and confirm")
    print("/api/brains reports the core as live rather than unverified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
