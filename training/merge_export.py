"""Fenix Core — Step 5: merge LoRA into a full model and export GGUF (GPU box).

    python training/merge_export.py --run training/runs/<stamp> --out models/fenix-core

Produces:
  models/fenix-core/           — merged full weights (HF format, deployable to vLLM)
  models/fenix-core/gguf/      — Q4_K_M + Q8_0 GGUF files for Ollama / llama.cpp (CPU-friendly)

After export (Ollama example):
    ollama create fenix-core -f Modelfile      # Modelfile: FROM ./gguf/fenix-core-q4_k_m.gguf
    ollama serve                               # http://localhost:11434/v1
"""
import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="training run dir containing checkpoint-* + run.json")
    ap.add_argument("--out", default="models/fenix-core")
    ap.add_argument("--quants", nargs="+", default=["q4_k_m", "q8_0"])
    args = ap.parse_args()

    import torch  # fail fast without CUDA-ish envs before heavy work
    if not torch.cuda.is_available():
        print("⚠️ No GPU: merge will be slow/possible RAM-bound. GGUF quantize works on CPU but slowly.")

    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    import json
    run = Path(args.run)
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    base_model = manifest["base_model"]
    best = manifest.get("best_checkpoint") or str(run / "checkpoint-final")
    print(f"base={base_model}\nadapter={best}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.bfloat16, device_map="auto")
    model = PeftModel.from_pretrained(model, best)
    model = model.merge_and_unload()
    model.save_pretrained(out, safe_serialization=True)
    tok = AutoTokenizer.from_pretrained(base_model)
    tok.save_pretrained(out)
    print(f"✓ merged model → {out}")

    gguf_dir = out / "gguf"
    gguf_dir.mkdir(exist_ok=True)
    try:
        from llama_cpp.server import __main__  # noqa: F401  (presence probe)
    except Exception:
        pass
    try:
        from transformers import AutoModelForCausalLM as _A  # noqa: F401
        try:
            from gguf import GGUFWriter  # noqa: F401
            import subprocess, sys as _sys
            for q in args.quants:
                print(f"quantizing {q} …")
                subprocess.run([ _sys.executable, "-m", "gguf.scripts.convert_hf_to_gguf",
                                 str(out), "--outfile", str(gguf_dir / f"fenix-core-{q}.gguf"),
                                 "--outtype", q], check=True)
        except Exception as e:
            print(f"⚠️ GGUF conversion skipped ({e}). Install: pip install gguf llama-cpp-python")
    except Exception as e:
        print(f"⚠️ GGUF step unavailable: {e}")

    # Ollama Modelfile for one-command serving
    q4 = gguf_dir / "fenix-core-q4_k_m.gguf"
    if q4.exists():
        (out / "Modelfile").write_text(
            f'FROM ./{q4.name}\nPARAMETER temperature 0.6\nSYSTEM """You are Fenix, an AI assistant built by Hakari."""\n',
            encoding="utf-8")
        print(f"✓ Modelfile → ollama create fenix-core -f {out / 'Modelfile'}")
    print("\nDone. Serve it, then point the Fenix server at it:")
    print('  CUSTOM_LLM_BASE_URL=http://localhost:11434/v1  CUSTOM_LLM_MODEL=fenix-core')


if __name__ == "__main__":
    main()
