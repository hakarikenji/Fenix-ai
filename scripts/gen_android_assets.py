"""توليد أيقونات وشاشة البداية لأندرويد من هوية Fenix — تشغيل لمرة واحدة."""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_icons import CENTER, SIZE, draw_flame, lerp  # noqa: E402

DARK_BG = (250, 249, 245, 255)  # #faf9f5 — الأبيض الدافئ بهوية Claude
RES = "android/app/src/main/res"

LAUNCHER_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
FOREGROUND_SIZES = {
    "mipmap-mdpi": 108,
    "mipmap-hdpi": 162,
    "mipmap-xhdpi": 216,
    "mipmap-xxhdpi": 324,
    "mipmap-xxxhdpi": 432,
}
SPLASH_SIZES = {
    "drawable-port-mdpi": (480, 800),
    "drawable-port-hdpi": (800, 1280),
    "drawable-port-xhdpi": (960, 1600),
    "drawable-port-xxhdpi": (1600, 2560),
    "drawable-port-xxxhdpi": (1920, 3200),
    "drawable-land-mdpi": (800, 480),
    "drawable-land-hdpi": (1280, 800),
    "drawable-land-xhdpi": (1600, 960),
    "drawable-land-xxhdpi": (2560, 1600),
    "drawable-land-xxxhdpi": (2880, 1800),
}


def base_flame_image(with_eye: bool = True, scale: float = 0.78) -> Image.Image:
    """صورة 1024x1024 لشعلة Fenix على خلفية ليلية."""
    img = Image.new("RGBA", (SIZE, SIZE), DARK_BG)
    draw = ImageDraw.Draw(img)
    draw_flame(draw, SIZE, scale=scale)
    if with_eye:
        eye_r = SIZE * 0.045
        ey = CENTER + SIZE * 0.02
        draw.ellipse(
            [CENTER - eye_r, ey - eye_r * 1.4, CENTER + eye_r, ey + eye_r * 1.4],
            fill=(255, 240, 200, 255),
        )
    return img


def make_launcher(size: int, out_dir: str, round_shape: bool = False) -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if round_shape:
        draw.ellipse([0, 0, SIZE, SIZE], fill=DARK_BG)
    else:
        # مربع بحواف مستديرة خفيفة (نمط لانشر حديث)
        radius = SIZE // 8
        draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=radius, fill=DARK_BG)
    flame = base_flame_image(with_eye=True, scale=0.62)
    img.alpha_composite(flame)
    img = img.resize((size, size), Image.LANCZOS)
    name = "ic_launcher_round.png" if round_shape else "ic_launcher.png"
    img.save(f"{RES}/{out_dir}/{name}", "PNG")


def make_foreground(size: int, out_dir: str) -> None:
    """طبقة أمامية للأيقونة التكيفية — الشعلة في الأوسط مع هوامش أمان 33%."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    flame = base_flame_image(with_eye=True, scale=0.42)
    img.alpha_composite(flame)
    img = img.resize((size, size), Image.LANCZOS)
    img.save(f"{RES}/{out_dir}/ic_launcher_foreground.png", "PNG")


def make_splash(width: int, height: int, out_dir: str) -> None:
    """شاشة بداية بلون الخلفية الليلية مع شعار Fenix في المنتصف."""
    img = Image.new("RGBA", (SIZE, SIZE), DARK_BG)
    flame = base_flame_image(with_eye=True, scale=0.5)
    img.alpha_composite(flame)
    logo = img.resize((360, 360), Image.LANCZOS)
    splash = Image.new("RGBA", (width, height), DARK_BG)
    splash.alpha_composite(logo, ((width - 360) // 2, (height - 360) // 2))
    splash = splash.convert("RGB")
    splash.save(f"{RES}/{out_dir}/splash.png", "PNG")


if __name__ == "__main__":
    for folder, size in LAUNCHER_SIZES.items():
        make_launcher(size, folder)
        make_launcher(size, folder, round_shape=True)
        print(f"✓ launcher {folder} ({size}px)")
    for folder, size in FOREGROUND_SIZES.items():
        make_foreground(size, folder)
        print(f"✓ foreground {folder} ({size}px)")
    for folder, (w, h) in SPLASH_SIZES.items():
        make_splash(w, h, folder)
        print(f"✓ splash {folder} ({w}x{h})")
    print("🔥 أصول أندرويد جاهزة")
