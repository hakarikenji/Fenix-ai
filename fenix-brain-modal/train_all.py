# Fenix Brains — تدريب ونشر كل العقول بأمر واحد 🧠🔥
#
# يشغّل السلسلة كاملة على Modal:
#   1) رفع بيانات الموسيقى (49 مثال جاهز) → fenix-training-out
#   2) رفع بيانات الفيديو                 → fenix-video-out
#   3) تدريب عقل الموسيقى (QLoRA على A10G)
#   4) تدريب عقل الفيديو   (QLoRA على A10G)
#   5) طباعة أوامر النشر النهائية
#
# الاستخدام:
#   modal run fenix-brain-modal/train_all.py              # كل شي
#   modal run fenix-brain-modal/train_all.py --skip-upload  # البيانات مرفوعة
#   modal run fenix-brain-modal/train_all.py --only music --epochs 3  # أقوى إعداد
#
# بعد النجاح انشر:
#   modal deploy fenix-music/generator/music_brain_modal.py
#   modal deploy fenix-video/training/serve_modal.py
#
# ملاحظة صادقة: التدريب يحتاج مساحة Modal مفعّلة. لو طلع
# "exceeded its spend limit" فعّل المساحة على modal.com ثم أعد هذا الأمر.
import modal

app = modal.App("fenix-train-all")

music_out = modal.Volume.from_name("fenix-training-out", create_if_missing=True)
video_out = modal.Volume.from_name("fenix-video-out", create_if_missing=True)
hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.*", "transformers>=4.51", "peft>=0.11", "accelerate",
    "bitsandbytes", "datasets", "trl>=0.9",
)


@app.local_entrypoint()
def main(skip_upload: bool = False, only: str = "all", epochs: int = 2):
    from pathlib import Path

    root = Path(__file__).parent.parent
    music_data = root / "fenix-music" / "training" / "data.jsonl"
    video_data = root / "fenix-video" / "training" / "data.jsonl"

    if only not in ("all", "music", "video"):
        raise ValueError("--only must be all, music, or video")
    if epochs < 1:
        raise ValueError("--epochs must be >= 1")
    do_music = only in ("all", "music")
    do_video = only in ("all", "video")

    if not skip_upload:
        if do_music:
            assert music_data.exists(), f"missing {music_data} — run fenix-music/training/gen_dataset.py"
            rows = sum(1 for l in open(music_data, encoding="utf-8") if l.strip())
            print(f"📤 uploading music data ({rows} examples) → volume fenix-training-out:/data.jsonl", flush=True)
            with music_out.batch_upload() as batch:
                batch.put_file(str(music_data), "/data.jsonl")
            music_out.commit()
        if do_video:
            assert video_data.exists(), f"missing {video_data} — run fenix-video/training/gen_dataset.py"
            rows = sum(1 for l in open(video_data, encoding="utf-8") if l.strip())
            print(f"📤 uploading video data ({rows} examples) → volume fenix-video-out:/data.jsonl", flush=True)
            with video_out.batch_upload() as batch:
                batch.put_file(str(video_data), "/data.jsonl")
            video_out.commit()
    else:
        print("⏭️ skip-upload: نفترض أن البيانات مرفوعة مسبقاً", flush=True)

    if do_music:
        print("🎧 training fenix-music brain (QLoRA, A10G)…", flush=True)
        train_music(epochs)
    if do_video:
        print("🎬 training fenix-video brain (QLoRA, A10G)…", flush=True)
        train_video(epochs)

    print("""
✅ DONE — الآن انشر العقول:

  modal deploy fenix-music/generator/music_brain_modal.py
  modal deploy fenix-video/training/serve_modal.py

ثم (اختياري) عامل الموسيقى الحقيقي MusicGen:
  modal deploy fenix-music/generator/worker.py
  واضبط MUSIC_GEN_URL على خوادم Fenix.
""", flush=True)


@app.function(image=image, gpu="A10G", timeout=10800,
              volumes={"/root/.cache/huggingface": hf_cache, "/out": music_out},
              env={"HF_HOME": "/root/.cache/huggingface"})
def train_music(epochs: int):
    _train("/out/data.jsonl", "fenix-training-out", epochs)


@app.function(image=image, gpu="A10G", timeout=10800,
              volumes={"/root/.cache/huggingface": hf_cache, "/out": video_out},
              env={"HF_HOME": "/root/.cache/huggingface"})
def train_video(epochs: int):
    _train("/out/data.jsonl", "fenix-video-out", epochs)


def _train(data_path: str, vol_name: str, epochs: int = 2):
    """QLoRA training identical to the per-app train_modal.py scripts."""
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

    rows = [json.loads(l) for l in open(data_path, encoding="utf-8") if l.strip()]
    if not rows:
        raise RuntimeError(f"training dataset is empty: {data_path}")
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
    modal.Volume.from_name(vol_name).commit()
    print(f"✅ ADAPTER SAVED → volume {vol_name}:/adapter", flush=True)
