"""Crop the left leaf out of the Leaf001 (two-leaves-side-by-side) texture set
and pad it onto a square black-background canvas, aligned across the height,
color and opacity maps so they share one UV layout.

Run: python prep_leaf.py
"""
from PIL import Image
import os

DIR = os.path.dirname(os.path.abspath(__file__))
PAD_FRAC = 0.06  # margin around the leaf as a fraction of the output canvas


def load(name):
    return Image.open(os.path.join(DIR, name))


opacity = load("Leaf001_1K-JPG_Opacity.jpg").convert("L")
height = load("Leaf001_1K-JPG_Displacement.jpg").convert("L")
color = load("Leaf001_1K-JPG_Color.jpg").convert("RGB")

w, h = opacity.size
half = w // 2

# Left leaf lives in the left half; find its tight bounding box from opacity.
left_mask = opacity.crop((0, 0, half, h))
bbox = left_mask.point(lambda p: 255 if p > 10 else 0).getbbox()
if bbox is None:
    raise SystemExit("Could not find leaf silhouette in opacity map")

x0, y0, x1, y1 = bbox
leaf_w, leaf_h = x1 - x0, y1 - y0
side = int(max(leaf_w, leaf_h) / (1 - 2 * PAD_FRAC))

canvas_size = (side, side)
off_x = (side - leaf_w) // 2
off_y = (side - leaf_h) // 2


def make_canvas(mode, bg):
    return Image.new(mode, canvas_size, bg)


def place(src, mode, bg):
    canvas = make_canvas(mode, bg)
    crop = src.crop((x0, y0, x1, y1))
    canvas.paste(crop, (off_x, off_y))
    return canvas


height_out = place(height, "L", 0)
opacity_out = place(opacity, "L", 0)
color_out = place(color, "RGB", (0, 0, 0))

height_out.save(os.path.join(DIR, "leaf_height.png"))
opacity_out.save(os.path.join(DIR, "leaf_opacity.png"))
color_out.save(os.path.join(DIR, "leaf_color.png"))
print(f"leaf bbox {bbox}, canvas {canvas_size} -> leaf_height.png / leaf_opacity.png / leaf_color.png")
