# تحضير مرة واحدة: تنزيل النموذج الأساسي إلى المخزن الدائم (حجم Modal الدائم)
# التشغيل:  modal run fenix-brain-modal/warm.py
import modal

app = modal.App("fenix-brain-warm")

hf_cache = modal.Volume.from_name("fenix-hf-cache", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface_hub",
)


@app.function(image=image, cpu=4, timeout=3600,
              volumes={"/root/.cache/huggingface": hf_cache},
              env={"HF_HOME": "/root/.cache/huggingface"})
def warm():
    from huggingface_hub import snapshot_download

    p = snapshot_download("Qwen/Qwen3-4B-Instruct-2507")
    print("downloaded to:", p, flush=True)


@app.local_entrypoint()
def main():
    warm.remote()
    print("✅ النموذج محفوظ في المخزن الدائم — البدايات الباردة صارت سريعة")
