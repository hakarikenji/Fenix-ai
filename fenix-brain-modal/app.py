# Fenix Brain on Modal — مجاني $30/شهر، بدون بطاقة، deploy بأمر واحد من أي كمبيوتر.
# يحمّل Qwen3-4B + عقل Fenix المدرَّب (adapter من Hugging Face) ويقدّم API متوافق مع OpenAI.
import os
import urllib.request
import zipfile
from pathlib import Path

import modal

app = modal.App("fenix-brain")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.*",
    "transformers>=4.51",
    "peft>=0.11",
    "accelerate",
    "fastapi[standard]",
)

ADAPTER_URL = os.environ.get(
    "ADAPTER_ZIP_URL",
    "https://huggingface.co/Hakari66684/fenix-core-lora/resolve/main/fenix-core-adapter.zip",
)


@app.cls(image=image, cpu=8, memory=16384, timeout=900, scaledown_window=600)
class FenixBrain:
    @modal.enter()
    def load(self):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        base = "Qwen/Qwen3-4B-Instruct-2507"
        print("loading base:", base, flush=True)
        self.tok = AutoTokenizer.from_pretrained(base)
        self.model = AutoModelForCausalLM.from_pretrained(
            base, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
        print("attaching Fenix adapter...", flush=True)
        req = urllib.request.Request(ADAPTER_URL)
        if os.environ.get("HF_TOKEN"):
            req.add_header("Authorization", "Bearer " + os.environ["HF_TOKEN"])
        zpath = "/tmp/fenix-adapter.zip"
        with urllib.request.urlopen(req) as r, open(zpath, "wb") as f:
            f.write(r.read())
        with zipfile.ZipFile(zpath) as z:
            z.extractall("/tmp/fenix-adapter")
        adir = str(next(Path("/tmp/fenix-adapter").rglob("adapter_config.json")).parent)
        self.model = PeftModel.from_pretrained(self.model, adir)
        self.model.eval()
        print("Fenix Brain READY", flush=True)

    @modal.method()
    def reply(self, messages: list, max_new_tokens: int = 512, temperature: float = 0.6) -> str:
        import torch

        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = self.tok(prompt, return_tensors="pt")
        kwargs = dict(
            max_new_tokens=min(max_new_tokens, 1024),
            do_sample=temperature > 0,
            top_p=0.9,
            pad_token_id=self.tok.eos_token_id,
        )
        if temperature > 0:
            kwargs["temperature"] = temperature
        with torch.no_grad():
            out = self.model.generate(**ids, **kwargs)
        return self.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


@app.function(image=image)
@modal.fastapi_endpoint(method="POST", label="fenix-brain")
def chat(data: dict):
    msgs = (data or {}).get("messages") or [{"role": "user", "content": "hi"}]
    max_new = int((data or {}).get("max_tokens") or 512)
    temp = float((data or {}).get("temperature") or 0.6)
    text = FenixBrain().reply.remote(msgs, max_new, temp)
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}
