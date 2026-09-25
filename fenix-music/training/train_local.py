"""Train the Fenix Music QLoRA adapter on a local NVIDIA GPU, without Modal.

This is the local counterpart of train_modal.py. It is intentionally kept
small and explicit so it can be inspected before running on your own PC.

Requirements:
  - NVIDIA GPU with CUDA; 12 GB VRAM minimum, 16 GB preferred, 24 GB comfortable.
  - The training command is run from the repository root.
  - Packages: torch, transformers, peft, trl, datasets, accelerate, bitsandbytes.

Example:
  python fenix-music/training/train_local.py --epochs 2 --max-length 2048

The script never reads or writes .env files and never uploads anything.
After it finishes, upload the resulting adapter directory through your
preferred Hugging Face workflow.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="fenix-music/training/data.jsonl")
    parser.add_argument("--out-dir", default="fenix-music/training/local-output")
    parser.add_argument("--base-model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--rank", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU is required for this local QLoRA run. "
            "A normal CPU-only PC is not a practical trainer for Qwen3-4B."
        )

    gpu = torch.cuda.get_device_name(0)
    total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"GPU: {gpu} ({total_gb:.1f} GB VRAM)", flush=True)
    if total_gb < 11:
        raise RuntimeError(
            f"Only {total_gb:.1f} GB VRAM detected. Use at least 12 GB, "
            "or reduce --max-length to 1024 and expect less headroom."
        )

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(data_path)

    rows = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise RuntimeError(f"Dataset is empty: {data_path}")
    if any([m.get("role") for m in row.get("messages", [])] != ["system", "user", "assistant"] for row in rows):
        raise ValueError("Every row must contain system, user, assistant messages")

    if args.dry_run:
        print(f"LOCAL_TRAIN_DRY_RUN_OK gpu={gpu} vram_gb={total_gb:.1f} rows={len(rows)}")
        return

    out_dir = Path(args.out_dir)
    adapter_dir = out_dir / "adapter"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {args.base_model}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=quantization,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    dataset = Dataset.from_list([{"messages": row["messages"]} for row in rows])
    lora = LoraConfig(
        r=args.rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        use_rslora=True,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        task_type="CAUSAL_LM",
    )
    common = dict(
        output_dir=str(out_dir / "checkpoints"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation,
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=5,
        save_strategy="epoch",
        report_to=[],
        seed=args.seed,
    )
    try:
        config = SFTConfig(max_length=args.max_length, packing=False, **common)
    except TypeError:
        config = SFTConfig(max_seq_length=args.max_length, packing=False, **common)

    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=dataset,
        peft_config=lora,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"LOCAL_ADAPTER_SAVED {adapter_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
