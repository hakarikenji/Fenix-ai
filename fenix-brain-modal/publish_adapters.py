# Fenix Brains — نشر الـ adapters المدرَّبة إلى Hugging Face 📦
#
# الخطوة اللي تربط التدريب بالحياة 24/7: تسحب كل adapter من المجلد الدائم
# الدائم على Modal، تضغطه zip، وترفعه لنفس المستودع والملف اللي تقرأه نسخ
# HF Spaces عند كل إعادة تشغيل — فيتحدّث العقل في كل مكان بدون تعديل أي كود.
#
# مرة واحدة فقط:
#   modal secret create hf-write HF_TOKEN=hf_xxx    # توكن بكتابة write على حسابك
#
# بعد كل تدريب:
#   modal run fenix-brain-modal/publish_adapters.py
import modal

app = modal.App("fenix-publish-adapters")

music_out = modal.Volume.from_name("fenix-training-out", create_if_missing=True)
video_out = modal.Volume.from_name("fenix-video-out", create_if_missing=True)
core_out = modal.Volume.from_name("fenix-core-out", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub")

# فولوم ← (مستودع HF، اسم الملف) — نفس المسارات اللي تقرأها نسخ Spaces
TARGETS = {
    "/music": ("Hakari66684/fenix-music-lora", "fenix-music-adapter.zip"),
    "/video": ("Hakari66684/fenix-video-lora", "fenix-video-adapter.zip"),
    "/core": ("Hakari66684/fenix-core-lora", "fenix-core-adapter.zip"),
}


@app.function(image=image, timeout=1800, secrets=[modal.Secret.from_name("hf-write")])
def publish(vol: str):
    import zipfile
    from pathlib import Path

    from huggingface_hub import HfApi

    repo, fname = TARGETS[vol]
    adir = Path(vol) / "adapter"
    if not (adir / "adapter_config.json").exists():
        print(f"⛔ {vol}: لا يوجد adapter بعد — شغّل التدريب أولاً", flush=True)
        return
    zpath = f"/tmp/{fname}"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(adir.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(adir.parent))
    api = HfApi()  # يقرأ HF_TOKEN من الـ secret تلقائياً
    api.upload_file(
        path_or_fileobj=zpath,
        path_in_repo=fname,
        repo_id=repo,
        repo_type="model",
    )
    print(f"✅ {vol}/adapter → {repo}/{fname} — Spaces ستلتقطه في إعادة التشغيل القادمة", flush=True)


@app.local_entrypoint()
def main(only: str = "all"):
    vols = {k: v for k, v in TARGETS.items() if only in ("all", k.strip("/"))}
    for v in vols:
        publish.remote(v)
