"""Generate MLX-Moxy-Wirks app icon — dark terminal aesthetic with <Mx/> code tag."""

import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_PNG = ROOT / "assets" / "MLX-Moxy-Wirks-1024.png"
ICONSET = ROOT / "assets" / "MLX-Moxy-Wirks.iconset"

SIZE = 1024

# ── Colour palette ────────────────────────────────────────────────────────────
BG          = (10,  13,  22)        # near-black navy
BG2         = (18,  22,  38)        # slightly lighter panel
BORDER      = (40,  50,  80)        # panel border
TITLEBAR    = (20,  26,  44)        # terminal title bar
RED         = (255, 95,  87)        # traffic light – close
AMBER       = (254, 188, 46)        # traffic light – minimise
GREEN       = (40,  200, 64)        # traffic light – maximise
BRACKET     = (80, 140, 220, 160)   # < > dim blue
TAG_COL     = (100, 180, 255)       # <Mx/>  electric blue
SLASH_COL   = (255, 115,  50)       # the / orange accent
PROMPT_COL  = (80,  200, 120)       # >_ green
CURSOR_COL  = (100, 180, 255, 200)  # blinking cursor
LINE_DIM    = (50,   80, 140,  60)  # dim code lines
GLOW_COL    = (70,  140, 255,  55)  # glow halo


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=0):
    draw.rounded_rectangle(box, radius=radius, fill=fill,
                           outline=outline, width=width)


def make_icon(size: int) -> Image.Image:
    s = size
    scale = s / SIZE

    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Background ───────────────────────────────────────────────────────────
    r_bg = round(190 * scale)
    rounded_rect(draw, [0, 0, s - 1, s - 1], r_bg, BG)

    # Subtle radial glow behind the main text
    glow_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gx, gy = s * 0.5, s * 0.48
    gr = s * 0.38
    gd.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=GLOW_COL)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=round(s * 0.12)))
    img.alpha_composite(glow_layer)

    # ── Terminal panel ───────────────────────────────────────────────────────
    px, py = round(70 * scale), round(170 * scale)
    pw, ph = s - px * 2, round(680 * scale)
    r_panel = round(20 * scale)
    rounded_rect(draw, [px, py, px + pw, py + ph], r_panel,
                 BG2, outline=BORDER, width=max(1, round(2 * scale)))

    # Title bar
    tb_h = round(58 * scale)
    rounded_rect(draw, [px, py, px + pw, py + tb_h], r_panel, TITLEBAR)
    draw.rectangle([px, py + r_panel, px + pw, py + tb_h], fill=TITLEBAR)

    # Traffic lights
    tly = py + round(29 * scale)
    for i, col in enumerate([RED, AMBER, GREEN]):
        tx = px + round((48 + i * 44) * scale)
        tr = round(13 * scale)
        draw.ellipse([tx - tr, tly - tr, tx + tr, tly + tr], fill=col)

    # Title bar label
    lbl_size = max(8, round(20 * scale))
    try:
        lbl_font = ImageFont.truetype("/System/Library/Fonts/SFNSText.ttf", lbl_size)
    except Exception:
        lbl_font = ImageFont.load_default()
    lbl_text = "moxy — neural inference"
    bb = draw.textbbox((0, 0), lbl_text, font=lbl_font)
    lbl_w = bb[2] - bb[0]
    draw.text(((s - lbl_w) // 2, py + round(19 * scale)),
              lbl_text, fill=(120, 140, 180), font=lbl_font)

    # ── Faint background code lines ──────────────────────────────────────────
    try:
        mono_sm = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", max(6, round(22 * scale)))
    except Exception:
        mono_sm = ImageFont.load_default()

    lines = [
        "import mlx.core as mx",
        "from moxy import Model, Persona",
        "",
        "model = Model.load()",
        "voice = Persona('nayara')",
    ]
    lx = px + round(30 * scale)
    ly_start = py + tb_h + round(28 * scale)
    line_gap = round(34 * scale)
    for i, ln in enumerate(lines):
        draw.text((lx, ly_start + i * line_gap), ln,
                  fill=(50, 80, 140, 80), font=mono_sm)

    # ── Main <Mx/> tag ───────────────────────────────────────────────────────
    try:
        big_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",
                                      max(20, round(210 * scale)))
    except Exception:
        try:
            big_font = ImageFont.truetype("/System/Library/Fonts/Courier.ttc",
                                          max(20, round(210 * scale)))
        except Exception:
            big_font = ImageFont.load_default()

    # Render each piece separately for colour control
    pieces = [("<", BRACKET[:3]), ("Mx", TAG_COL), ("/", SLASH_COL), (">", BRACKET[:3])]
    widths = []
    for ch, _ in pieces:
        bb = draw.textbbox((0, 0), ch, font=big_font)
        widths.append(bb[2] - bb[0])
    total_w = sum(widths)

    tag_cx = s // 2
    tag_cy = round(540 * scale)
    tx_start = tag_cx - total_w // 2
    # vertical baseline: use textbbox of full string for consistent baseline
    bb_full = draw.textbbox((0, 0), "<Mx/>", font=big_font)
    ty = tag_cy - (bb_full[3] - bb_full[1]) // 2 - bb_full[1]

    cur_x = tx_start
    for ch, col in pieces:
        draw.text((cur_x, ty), ch, fill=col, font=big_font)
        bb = draw.textbbox((0, 0), ch, font=big_font)
        cur_x += bb[2] - bb[0]

    # ── Prompt bar ───────────────────────────────────────────────────────────
    bar_y = py + ph - round(80 * scale)
    bar_h = round(52 * scale)
    bar_x = px + round(20 * scale)
    bar_w = pw - round(40 * scale)
    rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                 round(8 * scale), (12, 18, 34, 220))

    try:
        prompt_font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",
                                         max(8, round(30 * scale)))
    except Exception:
        prompt_font = ImageFont.load_default()

    prompt_x = bar_x + round(20 * scale)
    prompt_y = bar_y + (bar_h - round(30 * scale)) // 2

    draw.text((prompt_x, prompt_y), ">", fill=PROMPT_COL, font=prompt_font)
    bb_gt = draw.textbbox((0, 0), "> ", font=prompt_font)
    draw.text((prompt_x + bb_gt[2], prompt_y), "build",
              fill=(180, 190, 210), font=prompt_font)

    # blinking cursor rect
    bb_cmd = draw.textbbox((0, 0), "> build", font=prompt_font)
    cur_x2 = prompt_x + bb_cmd[2] + round(4 * scale)
    cur_w = round(16 * scale)
    cur_h = round(28 * scale)
    draw.rectangle([cur_x2, prompt_y + round(2 * scale),
                    cur_x2 + cur_w, prompt_y + cur_h], fill=CURSOR_COL)

    # ── Round-clip to keep rounded corners ───────────────────────────────────
    mask = Image.new("L", (s, s), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, s - 1, s - 1], radius=r_bg, fill=255)
    img.putalpha(mask)

    return img


def main():
    ICONSET.mkdir(parents=True, exist_ok=True)

    sizes = {
        "icon_16x16":       16,
        "icon_16x16@2x":    32,
        "icon_32x32":       32,
        "icon_32x32@2x":    64,
        "icon_128x128":     128,
        "icon_128x128@2x":  256,
        "icon_256x256":     256,
        "icon_256x256@2x":  512,
        "icon_512x512":     512,
        "icon_512x512@2x":  1024,
    }

    master = make_icon(1024)
    master.save(str(OUT_PNG))
    print(f"Saved 1024px master → {OUT_PNG}")

    for name, px in sizes.items():
        if px == 1024:
            img = master
        else:
            img = make_icon(px)
        path = ICONSET / f"{name}.png"
        img.save(str(path))
        print(f"  {path.name}  ({px}px)")

    print("Done — run: iconutil -c icns assets/MLX-Moxy-Wirks.iconset -o assets/MLX-Moxy-Wirks.icns")


if __name__ == "__main__":
    main()
