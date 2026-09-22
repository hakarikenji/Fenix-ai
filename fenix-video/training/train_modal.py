# تدريب عقل Fenix Video على Modal GPU — نفس نمط Fenix Music تماماً.
#   modal run fenix-video/training/train_modal.py     (بعد وضع data.jsonl في الفولدر)
#   modal deploy fenix-video/training/serve_modal.py  (بعد التدريب)
import modal

app = modal.App("fenix-video-train")

hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)
out_vol = modal.Volume.from_name("fenix-video-out", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.*", "transformers>=4.51", "peft>=0.11", "accelerate", "datasets", "trl>=0.9",
)


@app.function(image=image, gpu="A10G", timeout=10800,
              volumes={"/root/.cache/huggingface": hf_cache, "/out": out_vol},
              env={"HF_HOME": "/root/.cache/huggingface"})
def train(epochs: int = 2):
    import json

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    base = "Qwen/Qwen3-4B-Instruct-2507"
    print("loading base:", base, flush=True)
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(
        base, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
    )

    rows = [json.loads(l) for l in open("/out/data.jsonl", encoding="utf-8") if l.strip()]
    print("training examples:", len(rows), flush=True)
    ds = Dataset.from_list([{"messages": r["messages"]} for r in rows])

    peft_cfg = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    common = dict(output_dir="/out/lora", per_device_train_batch_size=2,
                  gradient_accumulation_steps=4, num_train_epochs=epochs,
                  learning_rate=2e-4, bf16=True, logging_steps=5, report_to=[])
    try:
        tcfg = SFTConfig(max_length=2048, packing=False, **common)
    except TypeError:
        tcfg = SFTConfig(max_seq_length=2048, packing=False, **common)

    trainer = SFTTrainer(model=model, args=tcfg, train_dataset=ds,
                         peft_config=peft_cfg, processing_class=tok)
    trainer.train()
    trainer.save_model("/out/adapter")
    tok.save_pretrained("/out/adapter")
    out_vol.commit()
    print("✅ ADAPTER SAVED → volume fenix-video-out:/adapter", flush=True)


@app.local_entrypoint()
def main(epochs: int = 2):
    train.remote(epochs)
