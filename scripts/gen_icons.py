"""توليد أيقونات Fenix Studio (Pillow) — تشغيل لمرة واحدة."""
import math

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
CENTER = SIZE // 2

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def flame_shape(size):
    """مسار شكل اللهب (فلسفة التصميم: شعلة مبسطة)."""
    s = size
    # شعلة بثلاث نقاط: قمة، جناحان، وقاع
    return [
        (s * 0.50, s * 0.10),  # القمة
        (s * 0.72, s * 0.34),  # جناح أيمن أعلى
        (s * 0.66, s * 0.52),  # خصر أيمن
        (s * 0.78, s * 0.68),  # جناح أيمن أسفل
        (s * 0.50, s * 0.92),  # القاع
        (s * 0.22, s * 0.68),  # جناح أيسر أسفل
        (s * 0.34, s * 0.52),  # خصر أيسر
        (s * 0.28, s * 0.34),  # جناح أيسر أعلى
    ]

def draw_flame(draw, size, offset=0, scale=1.0, colors=((20, 184, 166), (8, 145, 178))):
    pts = flame_shape(size)
    cx, cy = CENTER + offset, CENTER + offset
    scaled = [
        (cx + (x - size / 2) * scale, cy + (y - size / 2) * scale)
        for x, y in pts
    ]
    # تدرج عمودي داخل الشعلة
    layers = 24
    for i in range(layers):
        t = i / (layers - 1)
        color = lerp(colors[0], colors[1], t)
        shrink = 1 - t * 0.55
        layer_pts = [
            (cx + (x - cx) * shrink, cy + (y - cy) * shrink) for x, y in scaled
        ]
        draw.polygon(layer_pts, fill=color)

def make_icon(path, size, maskable=False):
    img = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Soft teal halo
    for r in range(SIZE, int(SIZE * 0.45), -8):
        t = (SIZE - r) / (SIZE * 0.55)
        alpha = int(22 * (1 - t))
        color = (13, 148, 136, alpha)
        draw.ellipse(
            [CENTER - r, CENTER - r, CENTER + r, CENTER + r],
            fill=color,
        )

    draw_flame(draw, SIZE, scale=0.78 if not maskable else 0.62)

    # Fenix eye inside the flame
    eye_color = (255, 255, 255, 255)
    if not maskable:
        eye_r = SIZE * 0.045
        ey = CENTER + SIZE * 0.02
        draw.ellipse(
            [CENTER - eye_r, ey - eye_r * 1.4, CENTER + eye_r, ey + eye_r * 1.4],
            fill=eye_color,
        )

    img = img.resize((size, size), Image.LANCZOS)
    img.save(path, "PNG")
    print(f"✓ {path}")


if __name__ == "__main__":
    import os

    os.makedirs("web/icons", exist_ok=True)
    make_icon("web/icons/icon-192.png", 192)
    make_icon("web/icons/icon-512.png", 512)
    make_icon("web/icons/icon-512-maskable.png", 512, maskable=True)
    print("🔥 الأيقونات جاهزة")
