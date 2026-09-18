"""Renders the settings panel off-screen (y = -4000) to a PNG."""
import ctypes
import ctypes.wintypes as wt
import sys
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, r"C:\Users\Utilisateur\claude\transcribe")
import overlay as ov_mod

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
OUT = Path(__file__).parent / "panel.png"


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
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


root = tk.Tk(); root.withdraw()
devices = lambda: [(1, "Microphone (HyperX Cloud III S"), (3, "Input (4- SSL 2+ MKII USB Audio")]
ov = ov_mod.Overlay(root, [], {"value": "recording"}, SimpleNamespace(is_set=lambda: False),
                    {"language": "fr", "hands_free_lock": True, "transcript_ttl_seconds": 20,
                     "microphone_device": None},
                    lambda c: None, devices, lambda i: None, {"text": None, "at": 0})
ov._tick = lambda: None
ov.pill_y = -4000  # panel is placed above the pill: keeps it off-screen
ov._build_panel()
for _ in range(4):
    root.update(); time.sleep(0.03)
p = ov.panel
w, h = p.winfo_width(), p.winfo_height()
hwnd = user32.GetParent(p.winfo_id()) or p.winfo_id()
img = capture(hwnd, w, h)
img.resize((w * 2, h * 2), Image.LANCZOS).save(OUT)
print("saved", OUT, w, h)
root.destroy()
