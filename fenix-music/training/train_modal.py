# تدريب عقل Fenix Music على Modal GPU — بدون Colab ولا نوتبوك 🧠🎵
# نفس كور Fenix Core: Qwen3-4B-Instruct + LoRA — بس هنا كل شي آلي من داخل Modal.
#
# 1) جهّز البيانات (محلياً، من العقل الحي):
#      python fenix-music/training/gen_dataset.py
# 2) ارفعها للفولدر الدائم:
#      modal volume put fenix-training-out fenix-music/training/data.jsonl data.jsonl
# 3) درّب (A10G، دقائق معدودة):
#      modal run fenix-music/training/train_modal.py
# 4) انشر العقل:
#      modal deploy fenix-music/generator/music_brain_modal.py
#
# الناتج: adapter/ داخل فولدر fenix-training-out الدائم — يقرأه عامل الخدمة مباشرة.
import modal

app = modal.App("fenix-music-train")

hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)
out_vol = modal.Volume.from_name("fenix-training-out", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.*", "transformers>=4.51", "peft>=0.11", "accelerate", "bitsandbytes", "datasets", "trl>=0.9",
)


@app.function(image=image, gpu="A10G", timeout=10800,
              volumes={"/root/.cache/huggingface": hf_cache, "/out": out_vol},
              env={"HF_HOME": "/root/.cache/huggingface"})
def train(epochs: int = 2):
    import json

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    base = "Qwen/Qwen3-4B-Instruct-2507"
    print("loading base:", base, flush=True)
    tok = AutoTokenizer.from_pretrained(base)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base,
        quantization_config=quantization,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    from peft import prepare_model_for_kbit_training
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    rows = [json.loads(l) for l in open("/out/data.jsonl", encoding="utf-8") if l.strip()]
    print("training examples:", len(rows), flush=True)
    ds = Dataset.from_list([{"messages": r["messages"]} for r in rows])

    peft_cfg = LoraConfig(
        r=32, lora_alpha=64, lora_dropout=0.05, use_rslora=True,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    common = dict(output_dir="/out/lora", per_device_train_batch_size=1,
                  gradient_accumulation_steps=8, num_train_epochs=epochs,
                  learning_rate=1e-4, bf16=True, gradient_checkpointing=True,
                  logging_steps=5, save_strategy="epoch", report_to=[])
    try:
        tcfg = SFTConfig(max_length=4096, packing=False, **common)
    except TypeError:  # توافق النسخ الأقدم من TRL
        tcfg = SFTConfig(max_seq_length=4096, packing=False, **common)

    trainer = SFTTrainer(model=model, args=tcfg, train_dataset=ds,
                         peft_config=peft_cfg, processing_class=tok)
    trainer.train()
    trainer.save_model("/out/adapter")
    tok.save_pretrained("/out/adapter")
    out_vol.commit()
    print("✅ ADAPTER SAVED → volume fenix-training-out:/adapter", flush=True)


@app.local_entrypoint()
def main(epochs: int = 2):
    train.remote(epochs)
