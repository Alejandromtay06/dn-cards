#!/usr/bin/env python3
"""Shareable QR images (WhatsApp-ready) for each card in people.json.

For every person writes to qr/share/:
  <slug>-qr-logo.png     QR with the brand icon in the centre, on white, 1600 px (drop into any design)
  <slug>-share.png       1080x1350 dark card: QR tile, name, title, "Scan to open my digital card", lockup
Error correction H (30%) so the centre logo never breaks scanning.

Usage: python tools/make_share_qr.py
"""
from __future__ import annotations

import json
import pathlib

import segno
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "people.json").read_text(encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/")
OUT = ROOT / "qr" / "share"
OUT.mkdir(parents=True, exist_ok=True)
FONTS = ROOT / "tools" / "fonts"

BRAND = {
    "dni": {"bg": "#0E1014", "ink": "#263E56", "text": "#F8F3F0", "muted": "#8CA5BD", "tile": "#161A20",
            "mark": "assets/dni-mark-dark.png", "lockup": "assets/dni-lockup-sand.png"},
    "dnr": {"bg": "#24212A", "ink": "#413C7C", "text": "#FAF5EF", "muted": "#B8B9DE", "tile": "#2C2833",
            "mark": None, "lockup": "assets/dnr-white.png"},  # mark is cropped from the lockup below
}
BRAND["crystal"] = BRAND["dnr"]


def font(name: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
    return f


def brand_mark(brand: str, ink: str) -> Image.Image:
    """Icon only, recoloured to the brand ink, on transparent."""
    if brand == "dni":
        im = Image.open(ROOT / BRAND["dni"]["mark"]).convert("RGBA")
    else:
        lock = Image.open(ROOT / "assets" / "dnr-purple.png").convert("RGBA")
        im = lock.crop((0, 0, 545, lock.height))  # the square icon sits left of the wordmark gap
    im = im.crop(im.getbbox())
    r, g, b = tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5))
    solid = Image.new("RGBA", im.size, (r, g, b, 255))
    solid.putalpha(im.getchannel("A"))
    return solid


def qr_with_logo(url: str, brand: str, size: int = 1600) -> Image.Image:
    b = BRAND[brand]
    q = segno.make(url, error="h")
    n = q.symbol_size(border=0)[0]
    quiet = 4
    scale = size // (n + 2 * quiet)
    buf = pathlib.Path(OUT / "_tmp.png")
    q.save(str(buf), scale=scale, border=quiet, dark=b["ink"], light="#FFFFFF")
    im = Image.open(buf).convert("RGBA")
    buf.unlink()
    # centre logo: ~19% of the code width, on a white rounded plate
    W = im.width
    plate = int(W * 0.24)
    logo = int(W * 0.17)
    mark = brand_mark(brand, b["ink"])
    mark.thumbnail((logo, logo), Image.LANCZOS)
    cx = cy = W // 2
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((cx - plate // 2, cy - plate // 2, cx + plate // 2, cy + plate // 2), radius=plate // 6, fill="#FFFFFF")
    im.alpha_composite(mark, (cx - mark.width // 2, cy - mark.height // 2))
    return im


def share_card(p: dict, url: str) -> Image.Image:
    b = BRAND[p["brand"]]
    W, H = 1080, 1350
    im = Image.new("RGBA", (W, H), b["bg"])
    d = ImageDraw.Draw(im)

    # QR tile
    tile = 760
    tx, ty = (W - tile) // 2, 150
    d.rounded_rectangle((tx, ty, tx + tile, ty + tile), radius=48, fill="#FFFFFF")
    qr = qr_with_logo(url, p["brand"], size=1600).resize((tile - 80, tile - 80), Image.LANCZOS)
    im.alpha_composite(qr, (tx + 40, ty + 40))

    # text
    y = ty + tile + 64
    eyebrow = font("DMMono-Medium.ttf", 22)
    title_txt = p["title"].upper()
    # letter-spaced eyebrow
    x = 0
    widths = [d.textlength(ch, font=eyebrow) for ch in title_txt]
    total = sum(widths) + 5 * (len(title_txt) - 1)
    x = (W - total) / 2
    for ch, w in zip(title_txt, widths):
        d.text((x, y), ch, font=eyebrow, fill=b["muted"])
        x += w + 5
    y += 46
    name_f = font("Manrope.ttf", 64, "Light")
    name = f"{p['first']} {p['last']}"
    d.text(((W - d.textlength(name, font=name_f)) / 2, y), name, font=name_f, fill=b["text"])
    y += 96
    sub_f = font("Manrope.ttf", 28, "Regular")
    sub = "Scan to open my digital card"
    d.text(((W - d.textlength(sub, font=sub_f)) / 2, y), sub, font=sub_f, fill=b["muted"])

    # footer lockup + rule
    d.line((60, H - 150, W - 60, H - 150), fill=b["tile"], width=2)
    lock = Image.open(ROOT / b["lockup"]).convert("RGBA")
    lock = lock.crop(lock.getbbox())
    lh = 64
    lock = lock.resize((int(lock.width * lh / lock.height), lh), Image.LANCZOS)
    im.alpha_composite(lock, (60, H - 150 + 43))
    url_f = font("DMMono-Medium.ttf", 20)
    short = url.replace("https://", "").rstrip("/")
    d.text((W - 60 - d.textlength(short, font=url_f), H - 150 + 60), short, font=url_f, fill=b["muted"])
    return im


def main() -> None:
    for p in CFG["people"]:
        url = f"{BASE}/{p['slug']}/"
        qr_with_logo(url, p["brand"]).convert("RGB").save(OUT / f"{p['slug']}-qr-logo.png", optimize=True)
        share_card(p, url).convert("RGB").save(OUT / f"{p['slug']}-share.png", optimize=True, quality=95)
        print(p["slug"], "->", url)


if __name__ == "__main__":
    main()
