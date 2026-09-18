"""Hover + click routing on the pill. No visible window, no input injection."""
import sys
import time
import tkinter as tk
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1
                else r"C:\Users\Utilisateur\claude\transcribe")
import overlay as ov_mod

failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}")
    if not ok:
        failures.append(label)


root = tk.Tk()
root.withdraw()
calls = []
cfg = {"language": "mix", "hands_free_lock": False, "transcript_ttl_seconds": 20}
state = {"value": "recording"}
lt = {"text": "texte", "at": time.time()}
ov = ov_mod.Overlay(root, [], state, SimpleNamespace(is_set=lambda: False), cfg,
                    lambda c: None, lambda: [], lambda i: None, lt,
                    actions={"resend": lambda: calls.append("resend"),
                             "cancel": lambda: calls.append("cancel")})
ov.win.withdraw()
ov._build_panel = lambda: calls.append("panel")  # never show a window
cy = ov_mod.HEIGHT / 2
at = SimpleNamespace

positions = {"lock": ov_mod.LOCK_X, "resend": ov_mod.RESEND_X,
             "cancel": ov_mod.CANCEL_X, "flag": ov_mod.FLAG_X}
for name, x in positions.items():
    ov._on_motion(at(x=x, y=cy))
    check(f"hover {name}", ov.hover, name)
    check(f"cursor hand on {name}", str(ov.canvas["cursor"]), "hand2")
    ov._draw()
    halos = [i for i in ov.canvas.find_all()
             if ov.canvas.type(i) == "oval"
             and ov.canvas.itemcget(i, "fill") == ov_mod.HOVER_FILL]
    check(f"one halo drawn for {name}", len(halos), 1)

ov._on_motion(at(x=150, y=cy))          # waveform area
check("no hover on waveform", ov.hover, None)
check("arrow cursor on waveform", str(ov.canvas["cursor"]), "")
ov._draw()
check("no halo without hover", sum(
    1 for i in ov.canvas.find_all()
    if ov.canvas.itemcget(i, "fill") == ov_mod.HOVER_FILL), 0)

ov.on_pill_click(at(x=150, y=cy))
ov.on_pill_click(at(x=30, y=cy))
check("click outside buttons does nothing", calls, [])
ov.on_pill_click(at(x=ov_mod.FLAG_X, y=cy))
check("flag opens settings", calls, ["panel"])
ov.on_pill_click(at(x=ov_mod.CANCEL_X, y=cy))
ov.on_pill_click(at(x=ov_mod.RESEND_X, y=cy))
ov.on_pill_click(at(x=ov_mod.LOCK_X, y=cy))
check("other buttons still work", (calls, cfg["hands_free_lock"]),
      (["panel", "cancel", "resend"], True))

lt["text"] = None
ov._on_motion(at(x=ov_mod.RESEND_X, y=cy))
check("hidden resend has no hover", ov.hover, None)
ov._on_leave()
check("leave clears hover", ov.hover, None)
gap = ov_mod.FLAG_X - ov_mod.FLAG_HALF_W - (ov_mod.CANCEL_X + ov_mod.CANCEL_R + 3)
check("flag and cancel hit areas separate", gap > 0, True)
root.destroy()

print("ALL PASSED" if not failures else f"FAILED: {failures}")
sys.exit(1 if failures else 0)
