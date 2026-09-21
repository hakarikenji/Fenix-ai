# Fenix Brain — OpenAI-compatible API for the fine-tuned mind.
# Loads the BASE model + the LoRA adapter straight from Hugging Face.
# No merging, no GGUF, no Colab, no GPU needed.
import io
import os
import zipfile

import torch
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
ADAPTER_ZIP_URL = os.environ.get(
    "ADAPTER_ZIP_URL",
    "https://huggingface.co/Hakari66684/fenix-core-lora/resolve/main/fenix-core-adapter.zip",
)

print("[1/3] downloading base model:", BASE_MODEL, flush=True)
tok = AutoTokenizer.from_pretrained(BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
)

print("[2/3] attaching the trained Fenix mind...", flush=True)
ad_zip = Path("/tmp/fenix-adapter.zip")
req = urllib.request.Request(ADAPTER_ZIP_URL)
if os.environ.get("HF_TOKEN"):
    req.add_header("Authorization", "Bearer " + os.environ["HF_TOKEN"])
with urllib.request.urlopen(req) as r, open(ad_zip, "wb") as f:
    f.write(r.read())
with zipfile.ZipFile(ad_zip) as z:
    z.extractall("/tmp/fenix-adapter")
ad_dir = str(next(Path("/tmp/fenix-adapter").rglob("adapter_config.json")).parent)
model = PeftModel.from_pretrained(model, ad_dir)
model.eval()
print("[3/3] Fenix Brain is READY", flush=True)

app = Flask(__name__)


@app.get("/")
def health():
    return jsonify(status="ok", brain="fenix-core", base=BASE_MODEL)


@app.post("/v1/chat/completions")
def chat_completions():
    data = request.get_json(force=True) or {}
    msgs = data.get("messages") or [{"role": "user", "content": "hi"}]
    max_new = min(int(data.get("max_tokens") or 512), 1024)
    temp = float(data.get("temperature") or 0.6)
    try:
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **ids,
                max_new_tokens=max_new,
                do_sample=temp > 0,
                temperature=temp if temp > 0 else None,
                top_p=0.9,
                pad_token_id=tok.eos_token_id,
            )
        answer = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        return jsonify({"choices": [{"message": {"role": "assistant", "content": answer.strip()}}]})
    except Exception as e:  # noqa: BLE001
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7860")), threaded=True)
