# Fenix Video Brain on Modal — عقل الفيديو المدرّب (نفس نمط fenix-brain).
#   modal deploy fenix-video/training/serve_modal.py
#   → https://<workspace>--fenix-video-brain.modal.run
import modal

app = modal.App("fenix-video-brain")

hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)
train_vol = modal.Volume.from_name("fenix-video-out", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.*", "transformers>=4.51", "peft>=0.11", "accelerate",
    "huggingface_hub", "fastapi[standard]",
)


@app.cls(
    image=image, cpu=8, memory=16384, timeout=900, scaledown_window=900,
    volumes={"/root/.cache/huggingface": hf_cache, "/vol": train_vol},
    env={"HF_HOME": "/root/.cache/huggingface"},
)
class VideoBrain:
    @modal.enter()
    def load(self):
        import torch
        from pathlib import Path
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        base = "Qwen/Qwen3-4B-Instruct-2507"
        print("loading base:", base, flush=True)
        self.tok = AutoTokenizer.from_pretrained(base)
        self.model = AutoModelForCausalLM.from_pretrained(
            base, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
        adir = Path("/vol/adapter")
        if not (adir / "adapter_config.json").exists():
            raise RuntimeError("لا يوجد adapter — شغّل أولاً: modal run fenix-video/training/train_modal.py")
        print("attaching fenix-video adapter...", flush=True)
        self.model = PeftModel.from_pretrained(self.model, str(adir))
        self.model.eval()
        print("Fenix Video Brain READY", flush=True)

    @modal.method()
    def reply(self, messages: list, max_new_tokens: int = 1400, temperature: float = 0.9) -> str:
        import torch

        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = self.tok(prompt, return_tensors="pt")
        kwargs = dict(
            max_new_tokens=min(max_new_tokens, 2000),
            do_sample=temperature > 0,
            top_p=0.95,
            pad_token_id=self.tok.eos_token_id,
        )
        if temperature > 0:
            kwargs["temperature"] = temperature
        with torch.no_grad():
            out = self.model.generate(**ids, **kwargs)
        return self.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


@app.function(image=image, timeout=1200)
@modal.asgi_app(label="fenix-video-brain")
def web():
    from fastapi import FastAPI, Request

    webapp = FastAPI()

    @webapp.get("/")
    async def health():
        return {"status": "ok", "brain": "fenix-video"}

    @webapp.post("/v1/chat/completions")
    @webapp.post("/chat/completions")
    async def completions(request: Request):
        data = await request.json()
        data = data or {}
        msgs = data.get("messages") or [{"role": "user", "content": "hi"}]
        max_new = int(data.get("max_tokens") or 1400)
        temp = float(data.get("temperature") or 0.9)
        text = VideoBrain().reply.remote(msgs, max_new, temp)
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    return webapp
