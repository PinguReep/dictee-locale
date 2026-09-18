"""Liquid-metal pill + click-to-open settings panel (preset "chromatic dark").

- The pill is ringed by 4 px of liquid metal: fine diagonal stripes that
  run from near-white to near-black, with chromatic dispersion (red and
  blue channels sampled slightly apart) and a cold #88ccff tint, lit from
  above, flowing slowly around the perimeter. A white rim light sits on the
  inner top edge and a wandering hot spot glides along the ring, lingers,
  then fades out and reappears somewhere else.
- The face is dark and felted (#1E1F22, soft inner vignette). The colour
  comes from the voice glow: seven "colorful" lobes (rose, cyan, violet,
  green, amber, indigo, teal) rising from the bottom edge with the mic
  level, plus a band line (white core, chromatic fringes) that bulges in
  the middle. While processing the lobes compact into a narrow beam that
  sweeps left and right.
- Status dot: rose while recording (REC), ice spinner while processing.
  Buttons are metal circles: padlock (hands-free lock, filled when locked),
  resend with an ice countdown ring, rose cross to cancel, language flag
  that opens the settings panel (FR / EN / FR+EN and the microphone list).
  Everything auto-closes when dictation ends.
- Both windows carry WS_EX_NOACTIVATE: clicks never steal keyboard focus
  from the app being dictated into.

Rendering: tkinter Canvas has neither alpha nor blur, so the heavy parts
are pre-computed once with Pillow (3x supersampled, LANCZOS) and shown by
small Labels placed over the canvas: the metal ring as an indexed image
whose palette is rotated over 64 frames (the flow, 1/4 px per frame) with
the hot spot composited per frame (~0.5 ms), the glow + band line as a
bank of 32 images indexed by level, six morph images and one beam image
for processing. The canvas itself keeps only classic items (face, dot,
buttons, halos), so every item still answers to `-fill`. The Labels relay
mouse events to the canvas handlers. Without Pillow the module falls back
to stacked ovals and ring segments, all vector.
"""

import ctypes
import math
import random
import time
import tkinter as tk
from types import SimpleNamespace

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
    HAVE_PIL = True
except Exception:  # pragma: no cover - pure-tk fallback
    HAVE_PIL = False

# Any pixel painted with this color becomes fully transparent on Windows,
# which is what gives the pill its rounded shape.
TRANSPARENT = "#010203"

# Cold steel palette
BG = "#1E1F22"          # pill face (centre)
BG_SOFT = "#26272B"     # button faces
BG_HOVER = "#2E3035"
BORDER = "#3A3C41"      # ~ rgba(255,255,255,.10) over #272727
BORDER_SEL = "#9FD9FF"
ACCENT = "#9FD9FF"      # ice
DOT_COLOR = "#FF5C7A"   # recording dot and cancel cross (rose)
PROCESS_COLOR = "#C9E9FF"
TEXT = "#F2F4F7"
TEXT_DIM = "#9AA0A8"
EDGE = "#0E0F11"        # 1 px dark outer edge of the pill
LOCK_FILL = "#8FD0FF"   # padlock face when locked
LOCK_INK = "#0E1C2C"
PANEL_BG = "#1C1C1E"
PANEL_BORDER = "#333336"
FACE_LAYERS = ((6, "#2A2B2F"), (8, "#242528"), (11, BG))  # inner vignette

# Ice gradient (countdown ring, panel rim), cyan -> pale blue
GRAD_FROM = (0x8F, 0xE3, 0xFF)
GRAD_TO = (0x7F, 0xA8, 0xFF)

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
RESEND_R = 14
CANCEL_X = 356     # discard the current dictation
CANCEL_R = 13
FLAG_X = WIDTH - 42  # language flag: opens the settings panel
FLAG_HALF_W = 24
HOVER_FILL = "#2B3A44"
MARGIN_BOTTOM = 90

# --- metal ring -----------------------------------------------------------
EDGE_W = 1                 # dark outer edge (px)
RING_W = 4                 # ring thickness (px)
RING_MID = EDGE_W + RING_W / 2  # centre line of the ring, from the outer edge
PILL_R = HEIGHT / 2
STRAIGHT = WIDTH - 2 * PILL_R
PERIMETER = 2 * STRAIGHT + 2 * math.pi * PILL_R   # outer silhouette
CAP_LEN = math.pi * (PILL_R - RING_MID)
PERIMETER_MID = 2 * STRAIGHT + 2 * CAP_LEN        # ring centre line (vector)
STRIPES = int(round(PERIMETER / 16))              # fine stripes (~16 px)
STRIPE_PERIOD = PERIMETER / STRIPES
PAL_N = 192                # palette entries per stripe period (64 x 3)
RING_FRAMES = 64           # flow phases per period (1/4 px per frame)
RING_FLOW = 6.0            # frames of flow per phase unit (~3 s per period)
DISPERSION = 0.05          # channel shift, in periods (~0.8 px)
SLANT = 0.7                # diagonal of the stripes across the ring depth
TINT = (0.916, 0.964, 1.0) # #88ccff at 18 % (color-burn approximation)
STRIPE_LO, STRIPE_HI = 0.30, 0.74  # attenuated stripe contrast
METAL_DARK = (26, 29, 34)
METAL_LIGHT = (243, 246, 249)
LIGHT_TOP, LIGHT_BOTTOM = 1.02, 0.74   # top-lit shading of the ring
POOLS = 3                  # static brightness pools along the perimeter
SS = 3                     # supersampling of the pre-rendered background
HOT_SIGMA = 30             # wandering hot spot: gaussian radius (px)
HOT_BLOB = 96
HOT_LEVELS = 16
HOT_CYCLE = 14.4           # phase units per stop (~4 s at 30 fps)
HOT_RGB = (236, 244, 255)
RIM_PEAK = 0.75            # rim light opacity on the inner top edge
# vector fallback
STRIPE_REP = 3             # broad bands per perimeter (buttons, fallback)
STRIPE_N = 2048
STRIPE_SHIFT = 0.0025
METAL_FLOW = 0.014
SEGS_STRAIGHT = 46
SEGS_CAP = 10
BUTTON_ARCS = 12           # arcs per metal circle button

# --- voice glow -----------------------------------------------------------
GLOW_CX = 150              # centre of the glow zone (x 44 -> 256)
GLOW_SCALE = 0.95
GLOW_RINGS = 6             # stacked ovals per lobe (vector fallback)
GLOW_REACH = 1.5
GLOW_XSPREAD = 0.8         # lobe x offsets, keeps the far lobes in the zone
GLOW_SPREAD = 1.05
GLOW_BEND = 10             # band-line bulge (px) at full level
GLOW_LEVELS = 32           # images in the level bank
GLOW_W, GLOW_H = 212, 44   # glow image (x 44..256, y 10..54)
GLOW_X0, GLOW_Y0 = GLOW_CX - GLOW_W // 2, HEIGHT - 6 - GLOW_H
PROC_W = 100               # processing beam image width
PROC_SWEEP = 56            # beam travel (px) each side of the centre
PROC_RATE = 0.09           # sweeps per phase unit (~3.7 s there and back)
PROC_LEVEL = 0.55
MORPH_N = 6                # recording -> processing morph images
MORPH_LEN = 1.8            # phase units (~0.5 s)
DOT_X = 36                 # status dot
# Static strips of the pre-rendered pill shown as Labels over the canvas
# (the canvas keeps only items that have a -fill option): edge + metal
# ring + rim, cut around the dot, the flag and its halo.
RING_REGIONS = (
    (0, 0, WIDTH, 6), (0, HEIGHT - 6, WIDTH, HEIGHT),          # top, bottom
    (0, 6, 26, HEIGHT - 6),                                     # left cap
    (WIDTH - 30, 6, WIDTH, 13), (WIDTH - 15, 13, WIDTH, HEIGHT - 13),
    (WIDTH - 30, HEIGHT - 13, WIDTH, HEIGHT - 6),               # right cap
)
# Lobes: (x offset, w, h, colour) at scale 1; palette "colorful" (centre, pairs)
GLOW_LOBES = (
    (0, 74, 46, (255, 70, 120)),
    (-36, 54, 40, (60, 190, 255)),
    (36, 54, 40, (175, 70, 255)),
    (-72, 48, 32, (60, 220, 130)),
    (72, 48, 32, (255, 150, 40)),
    (-108, 42, 26, (90, 100, 255)),
    (108, 42, 26, (40, 200, 190)),
)
BAND_CORE = (236, 246, 255)
BAND_TOP = (255, 190, 200)
BAND_BOTTOM = (150, 200, 255)

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


def _hex(rgb):
    return "#%02X%02X%02X" % rgb


def _rgb(hex_color):
    return (int(hex_color[1:3], 16), int(hex_color[3:5], 16),
            int(hex_color[5:7], 16))


def _mix(c1, c2, a):
    """Hex colour of c1 blended towards c2 by a (0..1); emulates alpha.
    Never returns HOVER_FILL (reserved for the hover halo count)."""
    if a <= 0:
        out = _hex(c1)
    elif a >= 1:
        out = _hex(c2)
    else:
        out = "#%02X%02X%02X" % (int(c1[0] + (c2[0] - c1[0]) * a),
                                 int(c1[1] + (c2[1] - c1[1]) * a),
                                 int(c1[2] + (c2[2] - c1[2]) * a))
    return "#2B3A45" if out == HOVER_FILL else out


def _smoothstep(t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)


def gradient_color(t):
    r = int(GRAD_FROM[0] + (GRAD_TO[0] - GRAD_FROM[0]) * t)
    g = int(GRAD_FROM[1] + (GRAD_TO[1] - GRAD_FROM[1]) * t)
    b = int(GRAD_FROM[2] + (GRAD_TO[2] - GRAD_FROM[2]) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


BG_RGB = _rgb(BG)
BORDER_RGB = _rgb(BORDER)
ACCENT_RGB = _rgb(ACCENT)
TRANSPARENT_RGB = _rgb(TRANSPARENT)


# --------------------------------------------------------------- metal --

def _stripe_profile(u):
    """Liquid-metal brightness of the fine stripes at u (in periods):
    main streak + thin secondary streak + broad light + dark seam."""
    u %= 1.0
    core = math.exp(-((u - 0.5) / 0.17) ** 2)
    second = math.exp(-((u - 0.16) / 0.07) ** 2)
    body = 0.5 + 0.5 * math.cos(2 * math.pi * (u - 0.5))
    seam = math.exp(-(u / 0.06) ** 2) + math.exp(-((u - 1.0) / 0.06) ** 2)
    g = 0.30 + 0.26 * body + 0.42 * core + 0.12 * second - 0.10 * seam
    g = min(0.98, max(0.10, g))
    return STRIPE_LO + (STRIPE_HI - STRIPE_LO) * (g - 0.10) / 0.88


def _stripe_rgb(u):
    """Palette entry of the stripes at u (periods), with dispersion + tint."""
    out = []
    for ch, shift in ((0, DISPERSION), (1, 0.0), (2, -DISPERSION)):
        g = _stripe_profile(u + shift)
        v = (METAL_DARK[ch] + (METAL_LIGHT[ch] - METAL_DARK[ch]) * g) * TINT[ch]
        out.append(max(0, min(255, int(v))))
    return tuple(out)


def _metal_profile(t):
    """Broad specular bands (0..1) at perimeter fraction t (buttons and the
    vector fallback ring)."""
    a = 2 * math.pi * t * STRIPE_REP
    band = (0.5 + 0.5 * math.cos(a)) ** 2.6
    hair = (0.5 + 0.5 * math.cos(a * 5 + 0.7)) ** 3
    echo = (0.5 + 0.5 * math.cos(a * 2 + 2.4)) ** 4
    return min(1.0, 0.10 + 0.72 * band + 0.16 * hair + 0.30 * echo)


def _build_metal_lut():
    lut = []
    for k in range(STRIPE_N):
        t = k / STRIPE_N
        br = _metal_profile(t + STRIPE_SHIFT)
        bg = _metal_profile(t)
        bb = _metal_profile(t - STRIPE_SHIFT)
        lut.append((
            (METAL_DARK[0] + (METAL_LIGHT[0] - METAL_DARK[0]) * br) * TINT[0],
            (METAL_DARK[1] + (METAL_LIGHT[1] - METAL_DARK[1]) * bg) * TINT[1],
            (METAL_DARK[2] + (METAL_LIGHT[2] - METAL_DARK[2]) * bb) * TINT[2]))
    return lut


METAL_LUT = _build_metal_lut()


def _metal_color(u, light, tint=None, tint_a=0.0):
    """Hex colour of the broad-band metal at fraction u under lighting.

    Channels are quantised (steps of 4) so Tk can reuse its colour cache
    frame after frame instead of allocating hundreds of new colours."""
    r, g, b = METAL_LUT[int((u % 1.0) * STRIPE_N) % STRIPE_N]
    r *= light
    g *= light
    b *= light
    if tint_a > 0:
        r += (tint[0] - r) * tint_a
        g += (tint[1] - g) * tint_a
        b += (tint[2] - b) * tint_a
    return "#%02X%02X%02X" % ((255 if r > 255 else int(r)) & ~3,
                              (255 if g > 255 else int(g)) & ~3,
                              (255 if b > 255 else int(b)) & ~3)


def _pill_coords(x, y, scale):
    """(depth, s, ny) of a point of the stadium, in scaled pixels.

    depth = distance inside the outer edge (negative outside), s = arc
    length along the outer perimeter (clockwise from the top-left cap end),
    ny = y of the outward normal (-1 at the top edge, +1 at the bottom)."""
    r = PILL_R * scale
    w, h = WIDTH * scale, HEIGHT * scale
    cy = h / 2
    if r <= x <= w - r:
        if y < cy:
            return y, x - r, -1.0
        return h - y, STRAIGHT * scale + math.pi * r + (w - r - x), 1.0
    cx = r if x < r else w - r
    dx, dy = x - cx, y - cy
    d = math.hypot(dx, dy)
    ny = dy / d if d > 0 else 0.0
    if x > cx:
        return r - d, STRAIGHT * scale + r * math.atan2(dx, -dy), ny
    return (r - d, 2 * STRAIGHT * scale + math.pi * r + r * math.atan2(-dx, dy),
            ny)


def _ring_point(s):
    """(x, y, nx, ny) of the outer silhouette at arc length s (1x px)."""
    s %= PERIMETER
    r = PILL_R
    cy = HEIGHT / 2
    if s < STRAIGHT:
        return r + s, 0.0, 0.0, -1.0
    s -= STRAIGHT
    if s < math.pi * r:
        a = s / r
        nx, ny = math.sin(a), -math.cos(a)
        return WIDTH - r + r * nx, cy + r * ny, nx, ny
    s -= math.pi * r
    if s < STRAIGHT:
        return WIDTH - r - s, HEIGHT, 0.0, 1.0
    a = (s - STRAIGHT) / r
    nx, ny = -math.sin(a), math.cos(a)
    return r + r * nx, cy + r * ny, nx, ny


def _build_ring_segments():
    """Vector-fallback geometry of the ring: straight lines + cap arcs.

    Each entry: (kind, coords, u, light, xn) where u is the position along
    the perimeter (0..1), light the top-lit shading factor and xn the
    normalised x along the top edge (hot-spot target) or None.
    """
    segs = []
    r = PILL_R - RING_MID
    y_bot = HEIGHT - RING_MID
    step = STRAIGHT / SEGS_STRAIGHT
    dist = 0.0
    for i in range(SEGS_STRAIGHT):                      # top, left -> right
        x0 = PILL_R + i * step
        u = (dist + (i + 0.5) * step) / PERIMETER_MID
        segs.append(("rect", (x0, EDGE_W, x0 + step, EDGE_W + RING_W), u,
                     LIGHT_TOP, (i + 0.5) / SEGS_STRAIGHT))
    dist += STRAIGHT
    ext = 180 / SEGS_CAP
    bbox = (WIDTH - PILL_R - r, RING_MID, WIDTH - PILL_R + r, HEIGHT - RING_MID)
    for j in range(SEGS_CAP):                           # right cap, clockwise
        start = 90 - j * ext
        mid = math.radians(start - ext / 2)
        u = (dist + (j + 0.5) * CAP_LEN / SEGS_CAP) / PERIMETER_MID
        light = LIGHT_BOTTOM + (LIGHT_TOP - LIGHT_BOTTOM) * (0.5 + 0.5 * math.sin(mid))
        segs.append(("arc", (bbox, start, -ext), u, light, None))
    dist += CAP_LEN
    for i in range(SEGS_STRAIGHT):                      # bottom, right -> left
        x0 = WIDTH - PILL_R - i * step
        u = (dist + (i + 0.5) * step) / PERIMETER_MID
        segs.append(("rect", (x0 - step, y_bot - RING_W / 2, x0,
                              y_bot + RING_W / 2), u, LIGHT_BOTTOM, None))
    dist += STRAIGHT
    bbox = (PILL_R - r, RING_MID, PILL_R + r, HEIGHT - RING_MID)
    for j in range(SEGS_CAP):                           # left cap, clockwise
        start = 270 - j * ext
        mid = math.radians(start - ext / 2)
        u = (dist + (j + 0.5) * CAP_LEN / SEGS_CAP) / PERIMETER_MID
        light = LIGHT_BOTTOM + (LIGHT_TOP - LIGHT_BOTTOM) * (0.5 + 0.5 * math.sin(mid))
        segs.append(("arc", (bbox, start, -ext), u, light, None))
    return segs


RING_SEGMENTS = _build_ring_segments()


# ------------------------------------------------- pre-rendered images --

class _MetalRing:
    """Pre-renders the pill background (edge, liquid-metal ring, rim light,
    border, felted face) with Pillow at 3x and shows it through Labels
    placed over the canvas. The ring is an indexed image whose palette is
    rotated for each flow frame; per frame the wandering hot spot is
    composited and the Label photos are pasted."""

    def __init__(self, master):
        s = SS
        w, h = WIDTH * s, HEIGHT * s
        edge, ring_t = EDGE_W * s, RING_W * s
        idx = bytearray(w * h)
        light = bytearray(w * h)
        ringm = bytearray(w * h)
        rim = bytearray(w * h)
        period = STRIPE_PERIOD * s
        rim_depth = edge + ring_t + 0.5 * s
        rim_sigma = 0.55 * s
        r = PILL_R * s
        limit = edge + ring_t + 2 * s
        for py in range(h):
            row = py * w
            y = py + 0.5
            inner_row = limit <= py < h - limit
            for px in range(w):
                if inner_row and r <= px < w - r:
                    continue                    # plain face, fast path
                depth, arc, ny = _pill_coords(px + 0.5, y, s)
                if depth < edge or depth >= limit:
                    continue
                i = row + px
                if depth < edge + ring_t:
                    d_in = depth - edge
                    u = (arc + SLANT * d_in) / period
                    idx[i] = int((u % 1.0) * PAL_N) % PAL_N
                    pool = 0.87 + 0.13 * math.cos(
                        2 * math.pi * POOLS * arc / (PERIMETER * s) + 0.9)
                    lt = (0.84 - 0.14 * ny) * pool
                    light[i] = int(min(1.0, lt) * 255)
                    ringm[i] = 255
                if ny < 0:                      # rim light, inner top edge
                    a = RIM_PEAK * (-ny) ** 1.3 * math.exp(
                        -((depth - rim_depth) / rim_sigma) ** 2)
                    v = int(a * 255)
                    if v > rim[i]:
                        rim[i] = v
        self._pimg = Image.frombytes("P", (w, h), bytes(idx))
        self._light = Image.merge(
            "RGB", (Image.frombytes("L", (w, h), bytes(light)),) * 3)
        self._ring_mask = Image.frombytes("L", (w, h), bytes(ringm))
        self._rim = Image.frombytes("L", (w, h), bytes(rim))
        self._white = Image.new("RGB", (w, h), (255, 255, 255))
        # static layers: edge, border, felted face
        static = Image.new("RGB", (w, h), TRANSPARENT_RGB)
        d = ImageDraw.Draw(static)

        def pill(inset, color):
            d.rounded_rectangle([inset * s, inset * s, w - 1 - inset * s,
                                 h - 1 - inset * s],
                                radius=(h - 2 * inset * s) / 2, fill=color)

        pill(0, _rgb(EDGE))
        pill(EDGE_W + RING_W, BORDER_RGB)
        for inset, color in FACE_LAYERS:
            pill(inset, _rgb(color))
        self._static = static
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                               radius=h / 2, fill=255)
        self._silhouette = mask.resize((WIDTH, HEIGHT), Image.LANCZOS).point(
            lambda v: 255 if v >= 110 else 0)
        self._outside = Image.new("RGB", (WIDTH, HEIGHT), TRANSPARENT_RGB)
        palette = [_stripe_rgb(i / PAL_N) for i in range(PAL_N)]
        self.frames = [self._render(palette, k) for k in range(RING_FRAMES)]
        # hot-spot mask (ring + rim) at 1x, and the soft blob at 16 levels
        hot = ImageChops.lighter(self._ring_mask, self._rim)
        self._hot_mask = hot.resize((WIDTH, HEIGHT), Image.LANCZOS)
        n = HOT_BLOB
        blob = bytearray(n * n)
        for by in range(n):
            for bx in range(n):
                d2 = (bx + 0.5 - n / 2) ** 2 + (by + 0.5 - n / 2) ** 2
                blob[by * n + bx] = int(255 * math.exp(-d2 / (2 * HOT_SIGMA ** 2)))
        blob_img = Image.frombytes("L", (n, n), bytes(blob))
        self._blobs = [blob_img.point([v * j // HOT_LEVELS for v in range(256)])
                       for j in range(HOT_LEVELS + 1)]
        self._hot_rgb = Image.new("RGB", (WIDTH, HEIGHT), HOT_RGB)
        self.labels = []
        for box in RING_REGIONS:
            photo = ImageTk.PhotoImage(self.frames[0].crop(box), master=master)
            lbl = tk.Label(master, image=photo, bd=0, padx=0, pady=0,
                           highlightthickness=0, bg=TRANSPARENT)
            lbl.place(x=box[0], y=box[1])
            self.labels.append((box, photo, lbl))
        self._last = None

    def _render(self, palette, k):
        shift = k * PAL_N // RING_FRAMES
        pal = []
        for i in range(PAL_N):
            pal.extend(palette[(i + shift) % PAL_N])
        pal.extend([0] * (3 * (256 - PAL_N)))
        self._pimg.putpalette(pal)
        ring = ImageChops.multiply(self._pimg.convert("RGB"), self._light)
        frame = self._static.copy()
        frame.paste(ring, mask=self._ring_mask)
        frame.paste(self._white, mask=self._rim)
        small = frame.resize((WIDTH, HEIGHT), Image.LANCZOS)
        return Image.composite(small, self._outside, self._silhouette)

    def base_crop(self, box):
        """Static background under a glow image (flow frame 0)."""
        return self.frames[0].crop(box)

    def update(self, phase, hot_s, hot_i):
        """Shows flow frame for `phase` with the hot spot at arc length
        hot_s (intensity hot_i); pastes only when something changed."""
        k = int(phase * RING_FLOW) % RING_FRAMES
        x, y, nx, ny = _ring_point(hot_s)
        cx = int(x - nx * RING_MID - HOT_BLOB / 2)
        cy = int(y - ny * RING_MID - HOT_BLOB / 2)
        level = int(round(hot_i * HOT_LEVELS))
        key = (k, cx, cy, level)
        if key == self._last:
            return
        self._last = key
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        mask.paste(self._blobs[level], (cx, cy))
        mask = ImageChops.multiply(mask, self._hot_mask)
        frame = Image.composite(self._hot_rgb, self.frames[k], mask)
        for box, photo, _lbl in self.labels:
            photo.paste(frame.crop(box))

    def destroy(self):
        for _box, _photo, lbl in self.labels:
            lbl.destroy()
        self.labels = []


def _glow_window(size, fade):
    """Soft horizontal (and top) fade mask so the glow never hard-clips."""
    w, h = size
    mask = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(mask)
    for i in range(fade):
        v = int(255 * (0.5 - 0.5 * math.cos(math.pi * i / fade)))
        d.line([i, 0, i, h], fill=(v, v, v))
        d.line([w - 1 - i, 0, w - 1 - i, h], fill=(v, v, v))
    for j in range(6):
        v = int(255 * (j + 1) / 7)
        d.line([fade, j, w - fade, j], fill=(v, v, v))
    return mask


def _render_glow(base, window, eff, compact=0.0):
    """Seven additive lobes rising from the bottom edge of `base`, plus the
    band line (white core, chromatic fringes, bulging with the level).
    `compact` 0..1 morphs the lobes into the processing beam. Rendered at
    3x with a gaussian blur and downsampled."""
    s = 3
    w, h = base.size[0] * s, base.size[1] * s
    acc = Image.new("RGB", (w, h), (0, 0, 0))
    alpha = min(0.92, (0.15 + 0.85 * eff) * 1.3 * (1 + 0.25 * compact))
    hscale = (0.5 + GLOW_REACH * eff) * GLOW_SCALE * (1 - 0.12 * eff)
    wscale = (0.85 + GLOW_SPREAD * eff) * GLOW_SCALE * (1 - 0.62 * compact)
    xspread = GLOW_XSPREAD * (1 - 0.55 * compact)
    cx, cy = w / 2, h
    steps = 18
    for dx, lw, lh, color in GLOW_LOBES:
        layer = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        rx, ry = lw * wscale / 2 * s, lh * hscale / 2 * s
        x = cx + dx * GLOW_SCALE * xspread * s
        for k in range(steps):
            sk = 1 - k / steps
            a = alpha * ((k + 1) / steps) ** 1.1
            col = tuple(min(255, int(ch * a)) for ch in color)
            d.ellipse([x - rx * sk, cy - ry * sk, x + rx * sk, cy + ry * sk],
                      fill=col)
        acc = ImageChops.add(acc, layer)
    acc = acc.filter(ImageFilter.GaussianBlur(3 * s))
    big = ImageChops.add(base.resize((w, h), Image.LANCZOS),
                         ImageChops.multiply(acc, window.resize((w, h))))
    # band line along the bottom edge: white core, red fringe above, blue
    # below, bulging at the centre, fading out towards both ends
    d = ImageDraw.Draw(big)
    bend = GLOW_BEND * eff * s
    half = w / 2 - 2 * s
    fade = (30 - 16 * compact) * s
    n = 48
    a_core = 0.22 + 0.78 * eff
    a_fringe = a_core * 0.5
    prev = None
    for i in range(n + 1):
        x = cx - half + 2 * half * i / n
        dd = (x - cx) / (half * 0.55)
        y = h - 1.5 * s - bend * math.exp(-dd * dd)
        if prev is not None:
            edge = min(x - (cx - half), cx + half - x)
            k = min(1.0, edge / fade)
            k = k * k * (3 - 2 * k)
            for dy, color, a in ((-0.9, BAND_TOP, a_fringe),
                                 (0.9, BAND_BOTTOM, a_fringe),
                                 (0.0, BAND_CORE, a_core)):
                d.line([(prev[0], prev[1] + dy * s), (x, y + dy * s)],
                       fill=_rgb(_mix(BG_RGB, color, a * k)), width=s)
        prev = (x, y)
    return big.resize(base.size, Image.LANCZOS)


# --------------------------------------------------------------- flags --

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
        self.hover = None  # name of the pill button under the mouse
        self._hot_seed = random.uniform(0, 1000)
        self._proc_start = None  # phase at which processing began (morph)

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
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self._ring = None       # _MetalRing (pre-rendered background)
        self._glow_bank = []    # PhotoImages: glow by level
        self._glow_morph = []   # PhotoImages: recording -> processing
        self._glow_proc = None  # PhotoImage: processing beam
        self._glow_label = None
        self._glow_shown = None
        self._prerender()
        prevent_activation(self.win)
        self.win.withdraw()
        self._tick()

    def _prerender(self):
        """Builds the image banks with Pillow and the Labels that show them
        over the canvas (skipped -> vector fallback)."""
        if not HAVE_PIL:
            return
        try:
            t0 = time.perf_counter()
            c = self.canvas
            self._ring = _MetalRing(c)
            base = self._ring.base_crop((GLOW_X0, GLOW_Y0, GLOW_X0 + GLOW_W,
                                         GLOW_Y0 + GLOW_H))
            window = _glow_window(base.size, 34)
            bank = [_render_glow(base, window, i / (GLOW_LEVELS - 1))
                    for i in range(GLOW_LEVELS)]
            morph = [_render_glow(base, window, PROC_LEVEL, i / (MORPH_N - 1))
                     for i in range(MORPH_N)]
            px0 = GLOW_CX - PROC_W // 2
            pbase = self._ring.base_crop((px0, GLOW_Y0, px0 + PROC_W,
                                          GLOW_Y0 + GLOW_H))
            proc = _render_glow(pbase, _glow_window(pbase.size, 22),
                                PROC_LEVEL, 1.0)
            self._glow_bank = [ImageTk.PhotoImage(g, master=c) for g in bank]
            self._glow_morph = [ImageTk.PhotoImage(g, master=c) for g in morph]
            self._glow_proc = ImageTk.PhotoImage(proc, master=c)
            self._glow_label = tk.Label(c, image=self._glow_bank[0], bd=0,
                                        padx=0, pady=0, highlightthickness=0,
                                        bg=BG)
            self._glow_label.place(x=GLOW_X0, y=GLOW_Y0)
            # the Labels sit over the canvas: relay the mouse to its handlers
            labels = [lbl for _b, _p, lbl in self._ring.labels]
            labels.append(self._glow_label)
            for lbl in labels:
                lbl.bind("<Motion>", self._relay_motion)
                lbl.bind("<Button-1>", self._relay_click)
                lbl.bind("<Leave>", self._on_leave)
            print(f"[ui  ] pill pre-rendered in {time.perf_counter() - t0:.2f}s")
        except Exception as exc:
            print(f"[warn] Pill pre-render failed, vector fallback: {exc}")
            if self._ring is not None:
                self._ring.destroy()
            if self._glow_label is not None:
                self._glow_label.destroy()
            self._ring, self._glow_label = None, None
            self._glow_bank, self._glow_morph, self._glow_proc = [], [], None

    # ------------------------------------------------------------- pill --

    def _pill(self, x1, y1, x2, y2, fill):
        r = (y2 - y1) / 2
        self.canvas.create_oval(x1, y1, x1 + 2 * r, y2, fill=fill, width=0)
        self.canvas.create_oval(x2 - 2 * r, y1, x2, y2, fill=fill, width=0)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, width=0)

    def _voice_level(self):
        """Mic level 0..1: fast attack (last blocks), slow decaying release.

        The deque itself is the history, so this is stateless and stays
        consistent whatever the frame rate."""
        recent = list(self.levels)[-24:]
        if not recent:
            return 0.0
        head = recent[-3:]
        attack = sum(head) / len(head)
        release = wsum = 0.0
        w = 1.0
        for v in reversed(recent):
            release += v * w
            wsum += w
            w *= 0.87
        level = max(attack, release / wsum)
        return min(1.0, (level * 6.5) ** 0.75)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        cy = HEIGHT / 2
        phase = self.phase
        recording = self.state["value"] == "recording"
        processing = self.state["value"] == "processing"

        # --- silhouette, face and liquid-metal ring -------------------------
        self._pill(0, 0, WIDTH, HEIGHT, EDGE)
        self._pill(EDGE_W + RING_W, EDGE_W + RING_W, WIDTH - EDGE_W - RING_W,
                   HEIGHT - EDGE_W - RING_W, BORDER)
        for inset, color in FACE_LAYERS:
            self._pill(inset, inset, WIDTH - inset, HEIGHT - inset, color)
        hot_s, hot_i = self._hotspot()
        if self._ring is not None:
            self._ring.update(phase, hot_s, hot_i)

        # --- voice glow (all the colour lives here) ------------------------
        if processing:
            eff = PROC_LEVEL
        else:
            eff = self._voice_level()
        idle = 0.23 * (0.5 + 0.5 * math.sin(phase * 0.58))
        eff = eff + idle * (1 - eff)
        self._draw_glow(eff, processing)

        if self._ring is None:
            flow = phase * METAL_FLOW
            c.create_line(PILL_R, HEIGHT - 5.5, WIDTH - PILL_R, HEIGHT - 5.5,
                          fill=BORDER, width=1)
            c.create_line(PILL_R, HEIGHT - 0.5, WIDTH - PILL_R, HEIGHT - 0.5,
                          fill=EDGE, width=1)
            self._draw_ring(flow, hot_s, hot_i)

        # --- status dot: pulsing rose REC dot / ice spinner while processing
        dx = DOT_X
        if recording:
            pulse = 1 + 0.25 * math.sin(phase * 2.2)
            radius = 3.5 * pulse
            dot = _rgb(DOT_COLOR)
            c.create_oval(dx - radius - 5, cy - radius - 5,
                          dx + radius + 5, cy + radius + 5,
                          fill=_mix(BG_RGB, dot, 0.16), width=0)
            c.create_oval(dx - radius - 2.5, cy - radius - 2.5,
                          dx + radius + 2.5, cy + radius + 2.5,
                          fill=_mix(BG_RGB, dot, 0.42), width=0)
            c.create_oval(dx - radius, cy - radius, dx + radius, cy + radius,
                          fill=DOT_COLOR, width=0)
        else:
            c.create_oval(dx - 7, cy - 7, dx + 7, cy + 7, outline=BORDER,
                          width=2)
            c.create_arc(dx - 7, cy - 7, dx + 7, cy + 7,
                         start=(-phase * 55) % 360, extent=110, style="arc",
                         outline=PROCESS_COLOR, width=2)

        self._draw_lock_button(cy)
        self._draw_resend_button(cy)
        self._draw_cancel_button(cy)

        # Current language as flag(s), right side of the pill
        if self.hover == "flag":
            self._halo(FLAG_X, cy, FLAG_HALF_W, 14, margin=2.5)
        draw_language(self.canvas, self.config.get("language", "mix"),
                      FLAG_X, cy, small=True)

    def _morph(self):
        """0..1 progress of the recording -> processing morph (1 = beam)."""
        if self._proc_start is None:
            return 1.0
        return min(1.0, (self.phase - self._proc_start) / MORPH_LEN)

    def _beam_center(self):
        """x of the processing beam: left <-> right, sinusoidal easing,
        starting from the centre once the morph is over."""
        t = self.phase
        if self._proc_start is not None:
            t = max(0.0, t - self._proc_start - MORPH_LEN)
        return GLOW_CX + PROC_SWEEP * math.sin(2 * math.pi * PROC_RATE * t)

    def _draw_glow(self, eff, processing):
        """Lobes rising from the bottom edge + the band line."""
        c = self.canvas
        phase = self.phase
        y_base = HEIGHT - 6
        cx = GLOW_CX
        if processing:
            cx = self._beam_center()
        if self._glow_label is not None:
            # pre-rendered lobes + band line, shown by a Label over the canvas
            if processing:
                m = self._morph()
                if m < 1.0:
                    shown = (self._glow_morph[int(m * MORPH_N)], GLOW_X0)
                else:
                    shown = (self._glow_proc, int(round(cx)) - PROC_W // 2)
            else:
                sway = int(round(4 * eff * math.sin(phase * 0.6)))
                idx = int(round(eff * (GLOW_LEVELS - 1)))
                shown = (self._glow_bank[idx], GLOW_X0 + sway)
            if shown != self._glow_shown:
                self._glow_shown = shown
                self._glow_label.configure(image=shown[0])
                self._glow_label.place_configure(x=shown[1], y=GLOW_Y0)
            return
        self._draw_glow_ovals(eff, processing, cx)

        # band line: white core with chromatic fringes, bulging at the centre
        bend = GLOW_BEND * eff
        half = 130 * (0.5 if processing else 1.0)
        pts_top, pts_core, pts_bot = [], [], []
        n = 13
        for i in range(n):
            x = cx - half + 2 * half * i / (n - 1)
            d = (x - cx) / (half * 0.55)
            y = y_base - 1 - bend * math.exp(-d * d)
            pts_top += [x, y - 1.3]
            pts_core += [x, y]
            pts_bot += [x, y + 1.3]
        a_core = 0.22 + 0.78 * eff
        a_fringe = a_core * 0.45
        c.create_line(*pts_top, fill=_mix(BG_RGB, BAND_TOP, a_fringe),
                      width=1, smooth=True)
        c.create_line(*pts_bot, fill=_mix(BG_RGB, BAND_BOTTOM, a_fringe),
                      width=1, smooth=True)
        c.create_line(*pts_core, fill=_mix(BG_RGB, BAND_CORE, a_core),
                      width=1, smooth=True)

    def _draw_glow_ovals(self, eff, processing, cx):
        """Vector fallback: stacked ovals with colours faded to the face."""
        c = self.canvas
        phase = self.phase
        y_base = HEIGHT - 6
        alpha = min(0.95, 0.15 + 0.85 * eff)
        hscale = (0.5 + GLOW_REACH * eff) * GLOW_SCALE
        wscale = (0.85 + GLOW_SPREAD * eff) * GLOW_SCALE
        xspread = GLOW_XSPREAD
        if processing:
            wscale *= 0.4
            xspread = 0.45
        lobes = []
        for i, (dx, w, h, color) in enumerate(GLOW_LOBES):
            drift = 0 if processing else 7 * eff * math.sin(phase * 0.6 + i * 1.3)
            lobes.append((cx + dx * GLOW_SCALE * xspread + drift,
                          w * wscale / 2, h * hscale / 2, color))
        order = (1, 2, 3, 4, 5, 6, 0)
        for k in range(GLOW_RINGS):
            sk = 1.0 - 0.14 * k
            ak = alpha * (0.06 + 0.94 * ((k + 1) / GLOW_RINGS) ** 1.7)
            for i in order:
                x, rx, ry, color = lobes[i]
                rx *= sk
                ry *= sk
                c.create_oval(x - rx, y_base - ry, x + rx, y_base + ry,
                              fill=_mix(BG_RGB, color, ak), width=0)

    def _hotspot(self):
        """(arc length along the perimeter, intensity 0.34..1) of the
        wandering hot spot: a pseudo-random stop every ~4 s, appears in
        ~300 ms, lingers, fades in ~450 ms, with a slow local sway."""
        cycle = (self.phase + self._hot_seed) / HOT_CYCLE
        n = math.floor(cycle)
        t = cycle - n
        h = math.sin(n * 12.9898) * 43758.5453
        h -= math.floor(h)
        s = (PERIMETER * h + 15 * math.sin(self.phase * 0.35)) % PERIMETER
        if t < 0.075:
            k = _smoothstep(t / 0.075)                    # appears (300 ms)
        elif t < 0.72:
            k = 1.0                                       # lingers
        elif t < 0.83:
            k = 1 - _smoothstep((t - 0.72) / 0.11)        # fades (450 ms)
        else:
            k = 0.0
        return s, 0.34 + 0.66 * k

    def _draw_ring(self, flow, hot_s, hot_i):
        """Vector fallback ring: flowing stripes, top-lit, hot spot, rim."""
        c = self.canvas
        hot_x = hot_s / STRAIGHT if hot_s < STRAIGHT else None
        rect, arc = c.create_rectangle, c.create_arc
        for kind, coords, u, light, xn in RING_SEGMENTS:
            if xn is not None and hot_x is not None:
                d = (xn - hot_x) / 0.055
                light = light + hot_i * math.exp(-d * d)
            color = _metal_color(u + flow, light)
            if kind == "rect":
                rect(*coords, fill=color, width=0)
            else:
                bbox, start, extent = coords
                arc(*bbox, start=start, extent=extent, style="arc",
                    outline=color, width=RING_W)
        x0, x1 = PILL_R + 4, WIDTH - PILL_R - 4
        y_rim = EDGE_W + RING_W + 0.5
        n = 5
        for i in range(n):
            xa = x0 + (x1 - x0) * i / n
            xb = x0 + (x1 - x0) * (i + 1) / n
            bell = math.sin(math.pi * (i + 0.5) / n)
            c.create_line(xa, y_rim, xb, y_rim, width=1,
                          fill=_mix(BORDER_RGB, (236, 240, 245), 0.18 + 0.62 * bell))

    def _metal_circle(self, x, cy, r, seed, fill):
        """Round button: face + 2 px chromatic metal ring."""
        c = self.canvas
        c.create_oval(x - r, cy - r, x + r, cy + r, fill=fill, width=0)
        ext = 360 / BUTTON_ARCS
        flow = self.phase * METAL_FLOW * 2.5
        for j in range(BUTTON_ARCS):
            start = j * ext
            mid = math.radians(start + ext / 2)
            light = 0.76 + 0.30 * (0.5 + 0.5 * math.sin(mid))
            u = seed + (j + 0.5) / BUTTON_ARCS / STRIPE_REP + flow
            c.create_arc(x - r, cy - r, x + r, cy + r, start=start,
                         extent=ext + 2, style="arc", width=2,
                         outline=_metal_color(u, light))

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
        if self.hover == "lock":
            self._halo(x, cy, r + 5)
        if locked:  # lit ice disc, dark ink: on at a glance
            self._metal_circle(x, cy, r, 0.05, LOCK_FILL)
            ink = LOCK_INK
        else:
            self._metal_circle(x, cy, r, 0.05, BG_SOFT)
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
        if self.hover == "resend":
            self._halo(x, cy, r + 3)  # leaves room for the countdown label
        # Metal track + ice countdown ring draining counter-clockwise
        self._metal_circle(x, cy, r, 0.4, BG_SOFT)
        extent = max(1.0, min(359.0, 360.0 * remaining / ttl))
        self.canvas.create_arc(x - r, cy - r, x + r, cy + r, start=90,
                               extent=extent, style="arc", width=2,
                               outline=gradient_color(1 - remaining / ttl))
        self.canvas.create_text(x, cy - 1, text="↺", fill=TEXT,
                                font=("Segoe UI", 10, "bold"))
        self.canvas.create_text(x, cy + r + 5, text=f"{math.ceil(remaining)}s",
                                fill=TEXT, font=FONT_TINY)

    def _draw_cancel_button(self, cy):
        x, r, d = CANCEL_X, CANCEL_R, 4
        if self.hover == "cancel":
            self._halo(x, cy, r + 5)
        self._metal_circle(x, cy, r, 0.7, BG_SOFT)
        ink = DOT_COLOR  # destructive action: rose, like the REC dot
        self.canvas.create_line(x - d, cy - d, x + d, cy + d, fill=ink, width=2)
        self.canvas.create_line(x - d, cy + d, x + d, cy - d, fill=ink, width=2)

    def _button_at(self, x, y):
        """Name of the pill button under (x, y), or None."""
        cy = HEIGHT / 2
        if math.hypot(x - LOCK_X, y - cy) <= LOCK_R + 3:
            return "lock"
        if (math.hypot(x - RESEND_X, y - cy) <= RESEND_R + 3
                and self._resend_remaining() > 0):
            return "resend"
        if math.hypot(x - CANCEL_X, y - cy) <= CANCEL_R + 3:
            return "cancel"
        if abs(x - FLAG_X) <= FLAG_HALF_W and abs(y - cy) <= 15:
            return "flag"
        return None

    def _on_motion(self, event):
        hover = self._button_at(event.x, event.y)
        if hover != self.hover:
            self.hover = hover
            self.canvas.configure(cursor="hand2" if hover else "")

    def _on_leave(self, _event=None):
        self.hover = None
        self.canvas.configure(cursor="")

    def _relay(self, event):
        """Mouse event of a Label placed over the canvas -> canvas coords."""
        w = event.widget
        return SimpleNamespace(x=event.x + w.winfo_x(), y=event.y + w.winfo_y())

    def _relay_motion(self, event):
        self._on_motion(self._relay(event))

    def _relay_click(self, event):
        self.on_pill_click(self._relay(event))

    def _halo(self, x, cy, rx, ry=None, margin=5.0):
        """Hover halo: three soft ice rings around one HOVER_FILL oval."""
        ry = rx if ry is None else ry
        c = self.canvas
        for k, a in ((1.0, 0.10), (2 / 3, 0.20), (1 / 3, 0.34)):
            m = margin * k
            c.create_oval(x - rx - m, cy - ry - m, x + rx + m, cy + ry + m,
                          fill=_mix(BG_RGB, ACCENT_RGB, a), width=0)
        c.create_oval(x - rx, cy - ry, x + rx, cy + ry,
                      fill=HOVER_FILL, outline=ACCENT, width=1)

    def on_pill_click(self, event):
        button = self._button_at(event.x, event.y)
        if button == "lock":
            locked = not self.config.get("hands_free_lock", False)
            self.config["hands_free_lock"] = locked
            self.save_config(self.config)
            print(f"[ui  ] hands-free lock {'on' if locked else 'off'}")
        elif button == "resend" and self.state["value"] == "recording":
            print("[ui  ] resend clicked")
            self.close_panel()
            self.actions.get("resend", lambda: None)()
        elif button == "cancel":
            print("[ui  ] cancel clicked")
            self.close_panel()
            self.actions.get("cancel", lambda: None)()
        elif button == "flag":
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
        if current == "processing":
            if self.last_state != "processing":
                self._proc_start = self.phase  # start the glow -> beam morph
        else:
            self._proc_start = None
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
            self.hover = None
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
            cv.create_rectangle(0, 0, 64, 36, outline="#3E5A6B", width=1)
        else:  # top rim light, like the pill
            cv.create_line(3, 3, 61, 3, fill="#4A4D53", width=1)
        draw_language(cv, mode, 32, 18)
        cv.bind("<Button-1>", lambda e, m=mode: self._set_language(m))
        if not selected:
            cv.bind("<Enter>", lambda e, c=cv: c.create_rectangle(
                2, 2, 62, 34, outline="#5E6670", width=1, tags="hover"))
            cv.bind("<Leave>", lambda e, c=cv: c.delete("hover"))
        return cv

    def _mic_row(self, parent, text, selected, command):
        row = tk.Frame(parent, bg=BG_HOVER if selected else PANEL_BG)
        row.pack(fill="x", pady=1)
        bar = tk.Frame(row, width=3, bg=ACCENT if selected else PANEL_BG)
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
                    row.config(bg=PANEL_BG), label.config(bg=PANEL_BG)))

    def _build_panel(self):
        self.close_panel()
        panel = tk.Toplevel(self.root)
        self.panel = panel
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.attributes("-alpha", 0.97)
        panel.config(bg=PANEL_BORDER)  # 1px border, white 10 %
        inner = tk.Frame(panel, bg=PANEL_BG)
        inner.pack(padx=1, pady=1, fill="both", expand=True)

        # Thin rim light across the top: the metal signature
        accent_line = tk.Canvas(inner, height=2, bg=PANEL_BG,
                                highlightthickness=0)
        accent_line.pack(fill="x")
        panel_rgb = _rgb(PANEL_BG)
        for i in range(40):
            bell = math.sin(math.pi * (i + 0.5) / 40)
            accent_line.create_rectangle(
                i * 9, 0, i * 9 + 9, 1,
                fill=_mix(panel_rgb, (226, 238, 248), 0.12 + 0.6 * bell),
                width=0)

        header = tk.Frame(inner, bg=PANEL_BG)
        header.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(header, text="R É G L A G E S", bg=PANEL_BG, fg=TEXT,
                 font=FONT_BOLD).pack(side="left")
        close = tk.Label(header, text="✕", bg=PANEL_BG, fg=TEXT_DIM, font=FONT,
                         cursor="hand2", padx=4)
        close.pack(side="right")
        close.bind("<Button-1>", self.close_panel)
        close.bind("<Enter>", lambda e: close.config(fg=TEXT))
        close.bind("<Leave>", lambda e: close.config(fg=TEXT_DIM))

        # --- Language (flag buttons) ---------------------------------------
        tk.Label(inner, text="L A N G U E", bg=PANEL_BG, fg=TEXT_DIM,
                 font=FONT_TINY, anchor="w", padx=14).pack(fill="x")
        lang_frame = tk.Frame(inner, bg=PANEL_BG)
        lang_frame.pack(fill="x", padx=14, pady=(4, 10))
        current = self.config.get("language", "mix")
        self._flag_widgets = {}
        for mode in ("fr", "en", "mix"):
            btn = self._flag_button(lang_frame, mode, current == mode)
            btn.pack(side="left", padx=(0, 8))
            self._flag_widgets[mode] = btn

        # --- Microphone ----------------------------------------------------
        tk.Label(inner, text="M I C R O P H O N E", bg=PANEL_BG, fg=TEXT_DIM,
                 font=FONT_TINY, anchor="w", padx=14).pack(fill="x")
        mic_frame = tk.Frame(inner, bg=PANEL_BG)
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
