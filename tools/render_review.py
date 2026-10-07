"""Renders the review box off-screen to a PNG (synthetic text, no input).

Usage: .venv\\Scripts\\python tools\\render_review.py out.png
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from review_box import ReviewBox  # noqa: E402

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32


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
    info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32,
                            0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


heard = ("euh du coup t'as vu le mail de cloud sur le projet ouais je pense "
         "qu'on qu'on peut le faire avec quen ce soir")
proposed = ("Du coup, t'as vu le mail de Claude sur le projet ? Ouais, je pense "
            "qu'on peut le faire avec Qwen ce soir.")
root = tk.Tk()
root.withdraw()
box = ReviewBox(root, screen_margin_bottom=6000)  # drawn above the screen: never visible
box.show(heard, proposed, lambda text, how: None, timeout=4)
box.win.update()
w, h = box.win.winfo_width(), box.win.winfo_height()
box.win.geometry(f"{w}x{h}+-4000+-4000")
for _ in range(5):
    root.update()
    time.sleep(0.05)
hwnd = user32.GetParent(box.win.winfo_id()) or box.win.winfo_id()
image = capture(hwnd, w, h)
out = Path(sys.argv[1] if len(sys.argv) > 1 else "review.png")
image.save(out)
box.close()
root.destroy()
print(f"saved {out} ({w}x{h})")
