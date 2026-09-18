"""Renders an overlay module's pill off-screen into a PNG contact sheet and
benchmarks its _draw(). Never shows anything on the user's screen.

usage: python render_variant.py <overlay_module.py> <out.png>
"""
import ctypes
import ctypes.wintypes as wt
import importlib.util
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
module_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])

spec = importlib.util.spec_from_file_location("overlay_variant", module_path)
ov_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ov_mod)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def capture(hwnd, w, h):
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32,
                          0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


root = tk.Tk()
root.withdraw()
cfg = {"language": "fr", "hands_free_lock": True, "transcript_ttl_seconds": 20}
state = {"value": "recording"}
levels = []
lt = {"text": "x", "at": time.time()}
ov = ov_mod.Overlay(root, levels, state, SimpleNamespace(is_set=lambda: False),
                    cfg, lambda c: None, lambda: [], lambda i: None, lt)
ov._tick = lambda: None  # static frames only
W, H = ov_mod.WIDTH, ov_mod.HEIGHT
ov.win.attributes("-transparentcolor", "")  # show the cut-out colour too
ov.win.geometry(f"{W}x{H}+-4000+-4000")
ov.win.deiconify()

def speech(peak, n=64):
    import math
    return [peak * (0.35 + 0.65 * abs(math.sin(i * 0.9)) * abs(math.sin(i * 0.23)))
            for i in range(n)]

STATES = [
    ("recording, silence (level 0.01)", "recording", speech(0.01), None, 0.0),
    ("recording, soft voice (0.06)", "recording", speech(0.06), None, 2.0),
    ("recording, loud voice (0.18)", "recording", speech(0.18), None, 4.0),
    ("processing", "processing", speech(0.02), None, 1.0),
    ("hover: flag", "recording", speech(0.08), "flag", 3.0),
    ("hover: lock", "recording", speech(0.08), "lock", 3.5),
    ("hover: resend", "recording", speech(0.08), "resend", 3.7),
    ("hover: cancel", "recording", speech(0.08), "cancel", 3.9),
]

frames = []
for label, st, lv, hover, phase in STATES:
    state["value"] = st
    levels[:] = lv
    ov.hover = hover
    ov.phase = phase
    ov._draw()
    for _ in range(4):
        root.update()
        time.sleep(0.02)
    hwnd = user32.GetParent(ov.win.winfo_id()) or ov.win.winfo_id()
    frames.append((label, capture(hwnd, W, H)))

# Benchmark: 60 consecutive frames with animation advancing
state["value"] = "recording"
levels[:] = speech(0.12)
ov.hover = None
t0 = time.perf_counter()
for i in range(60):
    ov.phase += 0.12
    ov._draw()
    root.update_idletasks()
draw_ms = (time.perf_counter() - t0) / 60 * 1000
items = len(ov.canvas.find_all())
root.destroy()

scale = 2
row_h = H * scale + 26
sheet = Image.new("RGB", (W * scale, row_h * len(frames)), (24, 24, 28))
d = ImageDraw.Draw(sheet)
for i, (label, f) in enumerate(frames):
    y = i * row_h
    d.text((6, y + 4), label, fill=(170, 170, 190))
    sheet.paste(f.resize((W * scale, H * scale), Image.LANCZOS), (0, y + 22))
sheet.save(out_path)
print(f"saved {out_path}")
print(f"draw_ms={draw_ms:.2f} canvas_items={items}")
