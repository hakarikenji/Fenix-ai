"""Fenix Core — Step 6 (option B): serve the custom brain as an OpenAI-compatible API.

Serves a GGUF with llama-cpp-python on CPU or GPU — the smallest possible
production brain server. Works with the Fenix app's CUSTOM_LLM_BASE_URL.

    pip install llama-cpp-python
    python training/serve_custom_brain.py --gguf models/fenix-core/gguf/fenix-core-q4_k_m.gguf --port 5001

Then on the Fenix server environment:
    CUSTOM_LLM_BASE_URL=http://127.0.0.1:5001/v1
    CUSTOM_LLM_MODEL=fenix-core
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL_PATH = ""
LLM = None


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            body = json.dumps({"ok": True, "model": MODEL_PATH}).encode()
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self.send_response(404); self.end_headers(); return
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        messages = req.get("messages") or []
        temperature = float(req.get("temperature", 0.6))
        max_tokens = int(req.get("max_tokens", 1024))
        try:
            out = LLM.create_chat_completion(messages=messages, temperature=temperature, max_tokens=max_tokens)
            text = out["choices"][0]["message"]["content"]
            err = None
        except Exception as e:
            text, err = "", str(e)
        body = json.dumps({
            "id": "fenix-core", "object": "chat.completion", "created": int(time.time()),
            "model": req.get("model", "fenix-core"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop" if not err else "error"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            **({"error": err} if err else {}),
        }).encode()
        self.send_response(200 if not err else 500); self._cors()
        self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("[fenix-core]", fmt % args)


def main() -> None:
    global MODEL_PATH, LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--gpu-layers", type=int, default=0, help="offload N layers to GPU (0 = CPU)")
    args = ap.parse_args()

    from llama_cpp import Llama
    MODEL_PATH = args.gguf
    print(f"loading {MODEL_PATH} (ctx={args.ctx}, gpu_layers={args.gpu_layers}) …")
    LLM = Llama(model_path=MODEL_PATH, n_ctx=args.ctx, n_gpu_layers=args.gpu_layers, verbose=False)
    print(f"✓ Fenix Core brain ready on http://0.0.0.0:{args.port}/v1")
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
