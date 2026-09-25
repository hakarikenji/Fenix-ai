# Fenix Video brain — always-on API for the free HF CPU Space.
# OpenAI-compatible brain API for the free Hugging Face CPU Space.
#
# ENGINE A (recommended on free CPU): merged + quantized GGUF via llama-cpp-python
#   MODEL_GGUF_URL=https://huggingface.co/<repo>/resolve/main/<file>.gguf
# ENGINE B (GPU Space or lots of RAM): base model + trained LoRA adapter
#   ADAPTER_ZIP_URL=https://huggingface.co/<repo>/resolve/main/fenix-video-adapter.zip
import os
import threading
import zipfile
from pathlib import Path

from flask import Flask, jsonify, request

BRAIN = "fenix-video"
BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
GGUF_URL = os.environ.get("MODEL_GGUF_URL", "").strip()
ADAPTER_ZIP_URL = os.environ.get(
    "ADAPTER_ZIP_URL",
    "https://huggingface.co/Hakari66684/fenix-video-lora/resolve/main/fenix-video-adapter.zip",
)
MAX_NEW = min(int(os.environ.get("MAX_NEW_TOKENS", "512")), 1024)
THREADS = int(os.environ.get("LLAMA_THREADS", "2"))

_lock = threading.Lock()
_engine = None          # "gguf" | "transformers"
_llm = None
_tok = None
_model = None


def _download(url: str, dest: Path, token: str = "") -> None:
    import urllib.request

    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def load_engine() -> None:
    """Load the model once, at process start. Honest about what it loaded."""
    global _engine, _llm, _tok, _model
    token = os.environ.get("HF_TOKEN", "").strip()

    if GGUF_URL:
        from llama_cpp import Llama

        gguf = Path("/tmp/brain.gguf")
        if not gguf.exists():
            print(f"[1/2] downloading GGUF: {GGUF_URL}", flush=True)
            _download(GGUF_URL, gguf, token)
        print("[2/2] loading GGUF on CPU ...", flush=True)
        _llm = Llama(model_path=str(gguf), n_ctx=4096, n_threads=THREADS, verbose=False)
        _engine = "gguf"
        print(f"{BRAIN} READY (gguf, cpu)", flush=True)
        return

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[1/2] downloading base model: {BASE_MODEL}", flush=True)
    _tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    _model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=dtype, low_cpu_mem_usage=True)

    ad_zip = Path("/tmp/brain-adapter.zip")
    print(f"[2/2] attaching LoRA adapter: {ADAPTER_ZIP_URL}", flush=True)
    _download(ADAPTER_ZIP_URL, ad_zip, token)
    with zipfile.ZipFile(ad_zip) as z:
        z.extractall("/tmp/brain-adapter")
    ad_dir = str(next(Path("/tmp/brain-adapter").rglob("adapter_config.json")).parent)
    _model = PeftModel.from_pretrained(_model, ad_dir)
    _model.eval()
    _engine = "transformers"
    print(f"{BRAIN} READY (transformers)", flush=True)


def generate(messages: list, max_new: int, temp: float) -> str:
    if _engine == "gguf":
        out = _llm.create_chat_completion(
            messages=messages,
            max_tokens=max(16, min(max_new, MAX_NEW)),
            temperature=temp,
        )
        return (out["choices"][0]["message"]["content"] or "").strip()

    text = _tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = _tok(text, return_tensors="pt")
    import torch

    with torch.no_grad():
        kwargs = dict(max_new_tokens=max(16, min(max_new, MAX_NEW)),
                      pad_token_id=_tok.eos_token_id, do_sample=temp > 0)
        if temp > 0:
            kwargs.update(temperature=temp, top_p=0.9)
        out = _model.generate(**ids, **kwargs)
    return _tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


app = Flask(__name__)


@app.get("/")
def health():
    ready = _engine is not None
    return jsonify(status="ok" if ready else "loading", brain=BRAIN,
                   engine=_engine or "not-loaded", base=BASE_MODEL,
                   gguf=bool(GGUF_URL), adapter=ADAPTER_ZIP_URL)


@app.get("/health")
def health_alias():
    return health()


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
def chat_completions():
    if _engine is None:
        return jsonify({"error": "brain still loading"}), 503
    data = request.get_json(force=True) or {}
    msgs = data.get("messages") or [{"role": "user", "content": "hi"}]
    try:
        max_new = int(data.get("max_tokens") or 512)
        temp = float(data.get("temperature") or 0.6)
    except (TypeError, ValueError):
        max_new, temp = 512, 0.6
    try:
        with _lock:  # one generation at a time: free CPU has 2 vCPUs
            text = generate(msgs, max_new, temp)
        if not text:
            return jsonify({"error": "empty reply"}), 502
        return jsonify({"choices": [{"message": {"role": "assistant", "content": text}}],
                        "brain": BRAIN, "engine": _engine})
    except Exception as e:  # noqa: BLE001
        return jsonify(error=str(e)), 500


load_engine()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7860")), threaded=True)
