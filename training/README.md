# 🧠 Fenix Core — Fine-tuning System (repeatable, honest)

Fenix's default brain is Gemini (server-side key). This directory builds a
**private brain** on top of a strong open-weight model, so Fenix can run on
your own weights — with an automatic, honest fallback to Gemini if the custom
model ever fails.

## The chosen base model (verified live on Hugging Face)

| Model | License | Why |
|---|---|---|
| **Qwen/Qwen3-4B-Instruct-2507** | Apache-2.0 | Best quality/size for free GPUs (Colab T4 fits QLoRA); multilingual (great Arabic) |
| Qwen/Qwen3-8B | Apache-2.0 | Step-up when you rent a bigger GPU (A100/L4) |

Apache-2.0 = commercial use, modification and redistribution are fully allowed.

## Where each part runs

| Part | Runs on | Notes |
|---|---|---|
| `prepare_dataset.py`, `build_eval_set.py` | **anywhere** (this sandbox included) | Pure stdlib — no GPU needed |
| `train_lora.py` (QLoRA) | **GPU**: free Colab T4 (4B), Kaggle, or rented A100 (8B) | ~40–90 min for 4B on T4 |
| `compare_models.py` | GPU machine or against two served endpoints | Base vs fine-tuned scoring |
| `merge_export.py` → GGUF | GPU machine (small RAM use) | Produces an Ollama/llama.cpp model |
| `serve_custom_brain.py` | any small server (CPU ok with llama.cpp) | OpenAI-compatible endpoint |
| App routing + fallback | **Fenix server** (`CUSTOM_LLM_BASE_URL` env) | Already wired in `server.py` |

## The pipeline (repeatable)

```
1) python training/prepare_dataset.py            # .data + optional chat export
   → training/data/train.jsonl / val.jsonl       # cleaned, deduped, PII-scrubbed
2) python training/build_eval_set.py             # FROZEN eval (never trained on)
   → training/data/eval.jsonl
3) [GPU/Colab] python training/train_lora.py     # QLoRA + checkpoints + val loss
   → training/runs/<stamp>/checkpoint-*/
4) [GPU] python training/compare_models.py       # base vs tuned on eval.jsonl
5) [GPU] python training/merge_export.py         # merged full model + GGUF
6) Serve it (Ollama/llama.cpp/serve_custom_brain.py), then on the Fenix server:
   CUSTOM_LLM_BASE_URL=http://localhost:11434/v1  CUSTOM_LLM_MODEL=fenix-core
7) Restart. Fenix now answers with your brain; ANY failure → Gemini automatically.
```

## Honest guarantees (Fenix identity rules apply to training too)

- The eval set is **frozen and independent** — never part of training data.
- `compare_models.py` prints raw scores side by side; if fine-tuning didn't help,
  the report says so — no vanity numbers.
- The app tags every reply with the brain that actually produced it
  (`Fenix Core` vs `Gemini`), and falls back to Gemini on any error/timeout.
- No fabricated results anywhere in this pipeline.
