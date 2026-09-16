"""Futuristic floating waveform pill + click-to-open settings panel.

- The pill sits bottom-center while dictating: gradient waveform, drifting
  particles, pulsing dot, current-language flag.
- Clicking the pill opens a glassy settings panel (flag buttons FR / EN /
  FR+EN and microphone list). Everything auto-closes when dictation ends.
- Both windows carry WS_EX_NOACTIVATE: clicks never steal keyboard focus
  from the app being dictated into.
"""

import ctypes
import math
import random
import time
import tkinter as tk

# Any pixel painted with this color becomes fully transparent on Windows,
# which is what gives the pill its rounded shape.
TRANSPARENT = "#010203"

BG = "#0B0B14"
BG_SOFT = "#14141F"
BG_HOVER = "#1D1D2E"
BORDER = "#2B2B44"
BORDER_SEL = "#6D7CFF"
ACCENT = "#6D7CFF"
DOT_COLOR = "#FF5C7A"
PROCESS_COLOR = "#F5A623"
TEXT = "#EAEAF5"
TEXT_DIM = "#8A8AA5"

# Waveform gradient, cyan -> violet
GRAD_FROM = (0x22, 0xD3, 0xEE)
GRAD_TO = (0xA7, 0x8B, 0xFA)

FLAG_BLUE = "#0055A4"
FLAG_RED = "#EF4135"
UK_BLUE = "#012169"
UK_RED = "#C8102E"

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_TINY = ("Segoe UI", 7)

WIDTH, HEIGHT = 440, 60
LOCK_X = 280       # hands-free padlock
LOCK_R = 13
RESEND_X = 318     # paste the last transcript again
RESEND_R = 15
CANCEL_X = 356     # discard the current dictation
CANCEL_R = 13
BARS = 30
BAR_WIDTH = 3
BAR_GAP = 3
MARGIN_BOTTOM = 90
PARTICLES = 14

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def prevent_activation(win):
    """Keeps the window from taking focus when clicked (Windows only)."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception as exc:
        print(f"[warn] Could not set no-activate style: {exc}")


def gradient_color(t):
    r = int(GRAD_FROM[0] + (GRAD_TO[0] - GRAD_FROM[0]) * t)
    g = int(GRAD_FROM[1] + (GRAD_TO[1] - GRAD_FROM[1]) * t)
    b = int(GRAD_FROM[2] + (GRAD_TO[2] - GRAD_FROM[2]) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def draw_flag_fr(canvas, x, y, w, h):
    third = w / 3
    canvas.create_rectangle(x, y, x + third, y + h, fill=FLAG_BLUE, width=0)
    canvas.create_rectangle(x + third, y, x + 2 * third, y + h,
                            fill="#F4F4F8", width=0)
    canvas.create_rectangle(x + 2 * third, y, x + w, y + h,
                            fill=FLAG_RED, width=0)
    canvas.create_rectangle(x, y, x + w, y + h, outline=BORDER, width=1)


def draw_flag_en(canvas, x, y, w, h):
    canvas.create_rectangle(x, y, x + w, y + h, fill=UK_BLUE, width=0)
    canvas.create_line(x, y, x + w, y + h, fill="#F4F4F8", width=3)
    canvas.create_line(x + w, y, x, y + h, fill="#F4F4F8", width=3)
    canvas.create_line(x, y, x + w, y + h, fill=UK_RED, width=1)
    canvas.create_line(x + w, y, x, y + h, fill=UK_RED, width=1)
    canvas.create_rectangle(x + w / 2 - h * 0.18, y, x + w / 2 + h * 0.18,
                            y + h, fill="#F4F4F8", width=0)
    canvas.create_rectangle(x, y + h / 2 - h * 0.18, x + w,
                            y + h / 2 + h * 0.18, fill="#F4F4F8", width=0)
    canvas.create_rectangle(x + w / 2 - h * 0.09, y, x + w / 2 + h * 0.09,
                            y + h, fill=UK_RED, width=0)
    canvas.create_rectangle(x, y + h / 2 - h * 0.09, x + w,
                            y + h / 2 + h * 0.09, fill=UK_RED, width=0)
    canvas.create_rectangle(x, y, x + w, y + h, outline=BORDER, width=1)


def draw_language(canvas, mode, cx, cy, small=False):
    """Draws the fr/en flag, or both joined by '+', centered on (cx, cy)."""
    w, h = (18, 12) if small else (22, 15)
    if mode == "fr":
        draw_flag_fr(canvas, cx - w / 2, cy - h / 2, w, h)
    elif mode == "en":
        draw_flag_en(canvas, cx - w / 2, cy - h / 2, w, h)
    else:  # mix: FR + EN
        sw, sh = (14, 9) if small else (17, 11)
        gap = 7 if small else 9
        draw_flag_fr(canvas, cx - sw - gap, cy - sh / 2, sw, sh)
        canvas.create_text(cx, cy, text="+", fill=TEXT, font=FONT_BOLD)
        draw_flag_en(canvas, cx + gap, cy - sh / 2, sw, sh)


class Overlay:
    def __init__(self, root, levels, state, quit_event, config, save_config,
                 devices_provider, on_microphone, last_transcript=None,
                 actions=None):
        self.last_transcript = last_transcript  # {"text", "at"}
        self.actions = actions or {}  # {"resend": fn, "cancel": fn}
        self.levels = levels          # deque of recent mic RMS levels
        self.state = state            # {"value": "idle"|"recording"|"processing"}
        self.quit_event = quit_event
        self.config = config
        self.save_config = save_config
        self.devices_provider = devices_provider  # -> [(index, name), ...]
        self.on_microphone = on_microphone
        self.root = root
        self.phase = 0.0
        self.visible = False
        self.panel = None
        self.last_state = "idle"
        self.particles = [self._new_particle(first=True)
                          for _ in range(PARTICLES)]

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", TRANSPARENT)
        self.win.attributes("-alpha", 0.96)
        self.win.config(bg=TRANSPARENT)
        self.screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.pill_y = screen_h - HEIGHT - MARGIN_BOTTOM
        x = (self.screen_w - WIDTH) // 2
        self.win.geometry(f"{WIDTH}x{HEIGHT}+{x}+{self.pill_y}")

        self.canvas = tk.Canvas(self.win, width=WIDTH, height=HEIGHT,
                                bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_pill_click)
        self.canvas.configure(cursor="hand2")
        prevent_activation(self.win)
        self.win.withdraw()
        self._tick()

    # ------------------------------------------------------------- pill --

    def _new_particle(self, first=False):
        return {
            "x": random.uniform(58, 262),
            "y": random.uniform(10, 50) if first else 52.0,
            "vy": random.uniform(0.25, 0.7),
            "r": random.uniform(0.8, 1.8),
            "color": random.choice(("#26264A", "#2E2E58", "#243B54")),
        }

    def _pill(self, x1, y1, x2, y2, fill):
        r = (y2 - y1) / 2
        self.canvas.create_oval(x1, y1, x1 + 2 * r, y2, fill=fill, width=0)
        self.canvas.create_oval(x2 - 2 * r, y1, x2, y2, fill=fill, width=0)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, width=0)

    def _draw(self):
        self.canvas.delete("all")
        self._pill(0, 0, WIDTH, HEIGHT, BORDER)          # halo border
        self._pill(1, 1, WIDTH - 1, HEIGHT - 1, BG)
        cy = HEIGHT / 2
        recording = self.state["value"] == "recording"

        # Drifting particles, the subtle "alive" layer behind the waveform
        for p in self.particles:
            p["y"] -= p["vy"]
            if p["y"] < 7:
                p.update(self._new_particle())
            self.canvas.create_oval(
                p["x"] - p["r"], p["y"] - p["r"],
                p["x"] + p["r"], p["y"] + p["r"],
                fill=p["color"], width=0)

        # Status dot: pulsing red ring while recording, amber while processing
        pulse = 1 + 0.25 * math.sin(self.phase * 2.2)
        color = DOT_COLOR if recording else PROCESS_COLOR
        radius = (5 if recording else 4) * (pulse if recording else 1)
        self.canvas.create_oval(26 - radius - 3, cy - radius - 3,
                                26 + radius + 3, cy + radius + 3,
                                outline=color, width=1)
        self.canvas.create_oval(26 - radius, cy - radius, 26 + radius,
                                cy + radius, fill=color, width=0)

        # Waveform: live gradient bars while recording, violet sweep while
        # the transcription is being processed.
        x0 = 72
        if recording:
            recent = list(self.levels)[-BARS:]
            heights = [0.0] * (BARS - len(recent)) + recent
            for i, level in enumerate(heights):
                h = min(4 + level * 260, HEIGHT - 22)
                x = x0 + i * (BAR_WIDTH + BAR_GAP)
                self.canvas.create_rectangle(
                    x, cy - h / 2, x + BAR_WIDTH, cy + h / 2,
                    fill=gradient_color(i / (BARS - 1)), width=0)
        else:
            for i in range(BARS):
                h = 5 + 8 * (1 + math.sin(self.phase * 3 - i * 0.45))
                x = x0 + i * (BAR_WIDTH + BAR_GAP)
                self.canvas.create_rectangle(
                    x, cy - h / 2, x + BAR_WIDTH, cy + h / 2,
                    fill="#4C4C7A", width=0)

        self._draw_lock_button(cy)
        self._draw_resend_button(cy)
        self._draw_cancel_button(cy)

        # Current language as flag(s), right side of the pill
        draw_language(self.canvas, self.config.get("language", "mix"),
                      WIDTH - 38, cy, small=True)

    def _resend_remaining(self):
        """Seconds left before the last transcript is purged, or 0."""
        lt = self.last_transcript
        if not lt or not lt["text"]:
            return 0.0
        ttl = self.config.get("transcript_ttl_seconds", 20)
        return max(0.0, lt["at"] + ttl - time.time())

    def _draw_lock_button(self, cy):
        x, r = LOCK_X, LOCK_R
        locked = self.config.get("hands_free_lock", False)
        c = self.canvas
        if locked:
            c.create_oval(x - r, cy - r, x + r, cy + r, fill=ACCENT, width=0)
            ink = "white"
        else:
            c.create_oval(x - r, cy - r, x + r, cy + r,
                          outline=BORDER, width=2, fill=BG_SOFT)
            ink = TEXT_DIM
        # Shackle: closed sits on the body; open is raised with one free leg
        lift = 0 if locked else 3
        top = cy - 8 - lift
        c.create_arc(x - 4, top, x + 4, top + 8, start=0, extent=180,
                     style="arc", outline=ink, width=2)
        c.create_line(x + 4, top + 4, x + 4, cy - 1, fill=ink, width=2)
        if locked:
            c.create_line(x - 4, top + 4, x - 4, cy - 1, fill=ink, width=2)
        c.create_rectangle(x - 6, cy - 1, x + 6, cy + 7, fill=ink, width=0)

    def _draw_resend_button(self, cy):
        remaining = self._resend_remaining()
        if remaining <= 0:
            return
        ttl = self.config.get("transcript_ttl_seconds", 20)
        x, r = RESEND_X, RESEND_R
        # Track + countdown ring draining counter-clockwise
        self.canvas.create_oval(x - r, cy - r, x + r, cy + r,
                                outline=BORDER, width=2, fill=BG_SOFT)
        extent = max(1.0, min(359.0, 360.0 * remaining / ttl))
        self.canvas.create_arc(x - r, cy - r, x + r, cy + r, start=90,
                               extent=extent, style="arc", width=2,
                               outline=gradient_color(1 - remaining / ttl))
        self.canvas.create_text(x, cy - 1, text="↺", fill=TEXT,
                                font=("Segoe UI", 10, "bold"))
        self.canvas.create_text(x, cy + r + 7, text=f"{math.ceil(remaining)}s",
                                fill=TEXT_DIM, font=FONT_TINY)

    def _draw_cancel_button(self, cy):
        x, r, d = CANCEL_X, CANCEL_R, 4
        self.canvas.create_oval(x - r, cy - r, x + r, cy + r,
                                outline=BORDER, width=2, fill=BG_SOFT)
        self.canvas.create_line(x - d, cy - d, x + d, cy + d,
                                fill=DOT_COLOR, width=2)
        self.canvas.create_line(x - d, cy + d, x + d, cy - d,
                                fill=DOT_COLOR, width=2)

    def on_pill_click(self, event):
        if math.hypot(event.x - LOCK_X, event.y - HEIGHT / 2) <= LOCK_R + 3:
            locked = not self.config.get("hands_free_lock", False)
            self.config["hands_free_lock"] = locked
            self.save_config(self.config)
            print(f"[ui  ] hands-free lock {'on' if locked else 'off'}")
            return
        cy = HEIGHT / 2
        if (math.hypot(event.x - RESEND_X, event.y - cy) <= RESEND_R + 3
                and self._resend_remaining() > 0
                and self.state["value"] == "recording"):
            print("[ui  ] resend clicked")
            self.close_panel()
            self.actions.get("resend", lambda: None)()
            return
        if math.hypot(event.x - CANCEL_X, event.y - cy) <= CANCEL_R + 3:
            print("[ui  ] cancel clicked")
            self.close_panel()
            self.actions.get("cancel", lambda: None)()
            return
        self.toggle_panel()

    def _tick(self):
        if self.quit_event.is_set():
            self.root.destroy()
            return
        lt = self.last_transcript
        if lt and lt["text"] and self._resend_remaining() <= 0 \
                and self.state["value"] not in ("processing", "pasting"):
            lt.update(text=None)  # purge from RAM
            print("[info] Last transcript purged from memory.")
        current = self.state["value"]
        # Hotkey released: dictation left "recording" -> close the panel too
        if self.last_state == "recording" and current != "recording":
            self.close_panel()
        self.last_state = current

        active = current in ("recording", "processing")
        if active:
            if not self.visible:
                self.win.deiconify()
                self.visible = True
            self.phase += 0.12
            self._draw()
        elif self.visible:
            self.win.withdraw()
            self.visible = False
            self.close_panel()
        self.root.after(33, self._tick)

    # ------------------------------------------------------------ panel --

    def toggle_panel(self, _event=None):
        if self.panel is not None and self.panel.winfo_exists():
            self.close_panel()
        else:
            self._build_panel()

    def close_panel(self, _event=None):
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.destroy()
        self.panel = None

    def _flag_button(self, parent, mode, selected):
        cv = tk.Canvas(parent, width=64, height=36, bg=BG_SOFT,
                       highlightthickness=0, cursor="hand2")
        outline = BORDER_SEL if selected else BORDER
        cv.create_rectangle(2, 2, 62, 34, outline=outline,
                            width=2 if selected else 1)
        if selected:  # soft outer glow
            cv.create_rectangle(0, 0, 64, 36, outline="#3A4380", width=1)
        draw_language(cv, mode, 32, 18)
        cv.bind("<Button-1>", lambda e, m=mode: self._set_language(m))
        if not selected:
            cv.bind("<Enter>", lambda e, c=cv: c.create_rectangle(
                2, 2, 62, 34, outline="#4A4A75", width=1, tags="hover"))
            cv.bind("<Leave>", lambda e, c=cv: c.delete("hover"))
        return cv

    def _mic_row(self, parent, text, selected, command):
        row = tk.Frame(parent, bg=BG_HOVER if selected else BG)
        row.pack(fill="x", pady=1)
        bar = tk.Frame(row, width=3, bg=ACCENT if selected else BG)
        bar.pack(side="left", fill="y")
        label = tk.Label(row, text=text, bg=row["bg"],
                         fg=TEXT if selected else TEXT_DIM,
                         font=FONT_BOLD if selected else FONT,
                         anchor="w", padx=10, pady=5, cursor="hand2")
        label.pack(side="left", fill="x", expand=True)
        for widget in (row, label):
            widget.bind("<Button-1>", lambda e: command())
            if not selected:
                widget.bind("<Enter>", lambda e: (
                    row.config(bg=BG_SOFT), label.config(bg=BG_SOFT)))
                widget.bind("<Leave>", lambda e: (
                    row.config(bg=BG), label.config(bg=BG)))

    def _build_panel(self):
        self.close_panel()
        panel = tk.Toplevel(self.root)
        self.panel = panel
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.attributes("-alpha", 0.97)
        panel.config(bg=BORDER)  # 1px border
        inner = tk.Frame(panel, bg=BG)
        inner.pack(padx=1, pady=1, fill="both", expand=True)

        # Thin accent line across the top: the "futuristic" signature
        accent_line = tk.Canvas(inner, height=2, bg=BG, highlightthickness=0)
        accent_line.pack(fill="x")
        for i in range(40):
            accent_line.create_rectangle(i * 9, 0, i * 9 + 9, 2,
                                         fill=gradient_color(i / 39), width=0)

        header = tk.Frame(inner, bg=BG)
        header.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(header, text="R É G L A G E S", bg=BG, fg=TEXT,
                 font=FONT_BOLD).pack(side="left")
        close = tk.Label(header, text="✕", bg=BG, fg=TEXT_DIM, font=FONT,
                         cursor="hand2", padx=4)
        close.pack(side="right")
        close.bind("<Button-1>", self.close_panel)
        close.bind("<Enter>", lambda e: close.config(fg=TEXT))
        close.bind("<Leave>", lambda e: close.config(fg=TEXT_DIM))

        # --- Language (flag buttons) ---------------------------------------
        tk.Label(inner, text="L A N G U E", bg=BG, fg=TEXT_DIM,
                 font=FONT_TINY, anchor="w", padx=14).pack(fill="x")
        lang_frame = tk.Frame(inner, bg=BG)
        lang_frame.pack(fill="x", padx=14, pady=(4, 10))
        current = self.config.get("language", "mix")
        self._flag_widgets = {}
        for mode in ("fr", "en", "mix"):
            btn = self._flag_button(lang_frame, mode, current == mode)
            btn.pack(side="left", padx=(0, 8))
            self._flag_widgets[mode] = btn

        # --- Microphone ----------------------------------------------------
        tk.Label(inner, text="M I C R O P H O N E", bg=BG, fg=TEXT_DIM,
                 font=FONT_TINY, anchor="w", padx=14).pack(fill="x")
        mic_frame = tk.Frame(inner, bg=BG)
        mic_frame.pack(fill="x", padx=8, pady=(4, 12))
        current_dev = self.config.get("microphone_device")
        try:
            devices = self.devices_provider()
        except Exception as exc:
            devices = []
            print(f"[warn] Could not list microphones: {exc}")
        for index, name in [(None, "Défaut système")] + devices:
            label = name if len(name) <= 38 else name[:37] + "…"
            self._mic_row(mic_frame, label, current_dev == index,
                          lambda i=index: self._set_microphone(i))

        panel.update_idletasks()
        w = max(panel.winfo_reqwidth(), 320)
        h = panel.winfo_reqheight()
        x = (self.screen_w - w) // 2
        y = self.pill_y - h - 10
        panel.geometry(f"{w}x{h}+{x}+{y}")
        prevent_activation(panel)
        panel.update()  # full update so widget positions are real
        print(f"[ui  ] settings panel open at {x},{y} ({w}x{h})")
        for mode, widget in self._flag_widgets.items():
            print(f"[ui  ] flag {mode} at "
                  f"{widget.winfo_rootx()},{widget.winfo_rooty()} "
                  f"{widget.winfo_width()}x{widget.winfo_height()}")

    def _set_language(self, mode):
        self.config["language"] = mode
        self.save_config(self.config)
        print(f"[info] Langue: {mode}")
        if self.panel is not None and self.panel.winfo_exists():
            self._build_panel()  # refresh highlights

    def _set_microphone(self, index):
        self.config["microphone_device"] = index
        self.save_config(self.config)
        self.on_microphone(index)
        print(f"[info] Micro: {index if index is not None else 'défaut système'}")
        if self.panel is not None and self.panel.winfo_exists():
            self._build_panel()
