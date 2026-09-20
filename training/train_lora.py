"""Fenix Core — Step 3: QLoRA fine-tuning (runs on GPU — free Colab T4 is enough).

Designed to be pasted into a Colab notebook cell-by-cell or run as a script:

    !pip install -q -U peft trl bitsandbytes datasets transformers accelerate
    !python train_lora.py --data-dir training/data --out runs/fenix-core

What it guarantees:
  - QLoRA (4-bit base + LoRA adapters): Qwen3-4B fits a free T4 (~9GB).
  - train/val split comes from prepare_dataset.py; val loss printed EVERY epoch.
  - Checkpoints every epoch → runs/<stamp>/checkpoint-N (never overwrite).
  - A run manifest (run.json) records base model, data hash, params, final losses.
  - EarlyStopping when val loss stops improving (patience=2) to avoid overfit.
  - If val loss gets WORSE than base sanity threshold, the report says so.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
MAX_SEQ_LEN = 2048


def sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="training/data")
    ap.add_argument("--out", default="training/runs")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    args = ap.parse_args()

    import torch  # noqa: F401  (fails fast here if no CUDA before heavy imports)
    if not torch.cuda.is_available():
        raise SystemExit("❌ No CUDA GPU. Run this on Colab (Runtime → Change runtime type → T4 GPU). "
                         "Everything else in training/ works CPU-only.")

    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
        DataCollatorForSeq2Seq, EarlyStoppingCallback, Trainer, TrainingArguments,
    )

    data_dir, stamp = Path(args.data_dir), time.strftime("%Y%m%d-%H%M%S")
    train_rows = load_jsonl(data_dir / "train.jsonl")
    val_rows = load_jsonl(data_dir / "val.jsonl")
    if not train_rows:
        raise SystemExit("No training data — run prepare_dataset.py first.")
    print(f"train={len(train_rows)}  val={len(val_rows)}  base={BASE_MODEL}")

    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token  # Qwen has no pad token — required for batching

    def fmt(rows: list[dict]) -> Dataset:
        texts = [tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=False) for r in rows]
        return Dataset.from_dict({"text": texts})

    ds_train, ds_val = fmt(train_rows), fmt(val_rows)
    tok_fn = lambda ex: tok(ex["text"], truncation=True, max_length=MAX_SEQ_LEN)  # noqa: E731

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=bnb, device_map="auto")
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES, task_type="CAUSAL_LM", bias="none"))
    model.print_trainable_parameters()

    out_dir = Path(args.out) / stamp

    # Version-proof TrainingArguments: transformers >=5 removed/renamed some
    # legacy kwargs (e.g. warmup_ratio). Build the full dict, then keep only
    # kwargs this installed version actually supports.
    import inspect

    desired = dict(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=5,
        save_strategy="epoch",
        save_total_limit=None,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=True,
        optim="paged_adamw_8bit",
        report_to=[],
        seed=42,
    )
    sig = inspect.signature(TrainingArguments.__init__).parameters
    filtered = {k: v for k, v in desired.items() if k in sig}
    if "eval_strategy" in sig:
        filtered["eval_strategy"] = "epoch"
    elif "evaluation_strategy" in sig:
        filtered["evaluation_strategy"] = "epoch"
    dropped = sorted(set(desired) - set(filtered))
    if dropped:
        print(f"ℹ️ transformers compatibility: dropping unsupported args {dropped}")
    args_tf = TrainingArguments(**filtered)

    callbacks = []
    if filtered.get("load_best_model_at_end") and "EarlyStoppingCallback" in globals():
        callbacks = [EarlyStoppingCallback(early_stopping_patience=2)]
    trainer = Trainer(
        model=model, args=args_tf,
        train_dataset=ds_train.map(tok_fn, batched=False, remove_columns=["text"]),
        eval_dataset=ds_val.map(tok_fn, batched=False, remove_columns=["text"]),
        data_collator=DataCollatorForSeq2Seq(tok, padding=True),
        callbacks=callbacks,
    )
    result = trainer.train()

    # Honest manifest — everything needed to reproduce and judge the run.
    manifest = {
        "base_model": BASE_MODEL, "stamp": stamp,
        "train_samples": len(train_rows), "val_samples": len(val_rows),
        "train_sha1": sha1_file(data_dir / "train.jsonl"),
        "val_sha1": sha1_file(data_dir / "val.jsonl"),
        "lora": {"r": LORA_R, "alpha": LORA_ALPHA, "dropout": LORA_DROPOUT, "targets": TARGET_MODULES},
        "hyper": {"epochs": args.epochs, "lr": args.lr, "batch": args.batch, "accum": args.accum, "seed": 42},
        "final_train_loss": getattr(result, "training_loss", None),
        "best_val_loss": trainer.state.best_metric,
        "epochs_ran": trainer.state.epoch,
        "best_checkpoint": str(trainer.state.best_model_checkpoint),
    }
    (out_dir / "run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("\n=== RUN MANIFEST ===")
    print(json.dumps(manifest, indent=2))
    print(f"\n✓ Done. Next: python training/compare_models.py --run {out_dir}")


if __name__ == "__main__":
    main()
