#!/usr/bin/env python3
"""
Generate the ProjectMind VS Code extension icon.
Run: python3 scripts/generate_icon.py
Requires: pip install pillow
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 128
OUT = Path(__file__).parent.parent / "vscode-extension" / "media" / "icon.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Dark navy background with rounded corners
RADIUS = 22
BG = (15, 17, 35, 255)
draw.rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], radius=RADIUS, fill=BG)

# Purple accent gradient strip at top
for y in range(14):
    alpha = int(255 * (1 - y / 14))
    draw.line([(RADIUS if y < 4 else 0, y), (SIZE - (RADIUS if y < 4 else 0), y)],
              fill=(99, 102, 241, alpha))

# Subtle dot-grid texture
for gx in range(4, SIZE - 4, 16):
    for gy in range(20, SIZE - 4, 16):
        draw.ellipse([(gx - 1, gy - 1), (gx + 1, gy + 1)], fill=(99, 102, 241, 35))

# "PM" text — try system fonts, fall back to default
font_paths = [
    "/System/Library/Fonts/Helvetica.ttc",        # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "C:/Windows/Fonts/arialbd.ttf",               # Windows
]
font_big = font_sub = None
for fp in font_paths:
    try:
        font_big = ImageFont.truetype(fp, 52)
        font_sub = ImageFont.truetype(fp, 14)
        break
    except (OSError, IOError):
        pass
if font_big is None:
    font_big = ImageFont.load_default()
    font_sub = font_big

# Drop shadow
draw.text((37, 39), "PM", font=font_big, fill=(0, 0, 0, 120))
# Main white text
draw.text((35, 37), "PM", font=font_big, fill=(255, 255, 255, 255))

# Purple accent underline
draw.rounded_rectangle([(35, 98), (93, 102)], radius=2, fill=(99, 102, 241, 255))

# "AI" sub-label
draw.text((52, 107), "AI", font=font_sub, fill=(148, 163, 184, 200))

img.save(str(OUT))
print(f"✓ Icon saved to {OUT}  ({img.size[0]}x{img.size[1]})")
