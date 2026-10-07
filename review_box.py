"""Review box shown before pasting, during the learning phase.

Shows the text about to be pasted with the cleanup's changes highlighted,
lets the user fix it, then pastes. It never takes keyboard focus unless the
user clicks into it, so an untouched box pastes into the app that had focus
when its countdown ends. Clicking a highlighted word swaps it back to what
Whisper heard. The user's own edits are what the vocabulary learns from.
"""

import ctypes
import tkinter as tk
from difflib import SequenceMatcher

from vocab import plain, words

BG = "#0B0B14"
FIELD = "#14141F"
BORDER = "#2B2B44"
TEXT = "#EAEAF5"
DIM = "#8A8AA5"
CHANGED = "#8ACBFF"
ACCENT = "#6D7CFF"
DANGER = "#FF5C7A"
FONT = ("Segoe UI", 11)
SMALL = ("Segoe UI", 9)
BOLD = ("Segoe UI", 9, "bold")

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
_user32 = ctypes.windll.user32


def _hwnd(win):
    win.update_idletasks()
    return _user32.GetParent(win.winfo_id()) or win.winfo_id()


def _set_noactivate(win, enabled):
    hwnd = _hwnd(win)
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW
    style = style | WS_EX_NOACTIVATE if enabled else style & ~WS_EX_NOACTIVATE
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def diff_spans(heard, proposed):
    """Word-level differences between what Whisper heard and the proposal.

    Returns (changes, removed): changes = [(proposed_words, heard_words)] in
    order of appearance, removed = heard words dropped by the cleanup.
    """
    a, b = words(heard), words(proposed)
    ops = SequenceMatcher(None, [plain(w) for w in a], [plain(w) for w in b],
                          autojunk=False).get_opcodes()
    changes, removed = [], []
    for op, i1, i2, j1, j2 in ops:
        if op == "replace":
            changes.append((" ".join(b[j1:j2]), " ".join(a[i1:i2])))
        elif op == "delete":
            removed.extend(a[i1:i2])
    return changes, removed


class ReviewBox:
    def __init__(self, root, screen_margin_bottom=90):
        self.root = root
        self.margin = screen_margin_bottom
        self.win = None

    def show(self, heard, proposed, on_done, timeout=4.0, send=False):
        """Displays the box (Tk thread). on_done(text, how) is called once:
        how = "user" (validated by hand), "timeout" (countdown) or "cancel"
        (text is then None)."""
        self.close()
        self.on_done = on_done
        self.target = _user32.GetForegroundWindow()
        self.activated = False
        self.remaining = timeout
        self.paused = timeout <= 0
        self.send = send

        win = tk.Toplevel(self.root)
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.98)
        win.config(bg=BORDER)
        inner = tk.Frame(win, bg=BG, padx=12, pady=10)
        inner.pack(padx=1, pady=1, fill="both", expand=True)

        header = tk.Frame(inner, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="Relecture", bg=BG, fg=TEXT, font=BOLD).pack(side="left")
        tk.Label(header, text="  clic sur un mot bleu : version entendue",
                 bg=BG, fg=DIM, font=SMALL).pack(side="left")

        width = min(760, win.winfo_screenwidth() - 120)
        lines = max(2, min(9, len(proposed) // 78 + 1))
        self.text = tk.Text(inner, wrap="word", height=lines, bg=FIELD, fg=TEXT,
                            insertbackground=TEXT, relief="flat", font=FONT,
                            padx=10, pady=8, undo=True, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT)
        self.text.pack(fill="both", expand=True, pady=(8, 6))
        self._fill(heard, proposed)

        footer = tk.Frame(inner, bg=BG)
        footer.pack(fill="x")
        changes, removed = diff_spans(heard, proposed)
        if removed:
            shown = ", ".join(removed[:12]) + ("…" if len(removed) > 12 else "")
            tk.Label(footer, text=f"Retiré : {shown}", bg=BG, fg=DIM, font=SMALL,
                     wraplength=width - 260, justify="left").pack(side="left")
        self.ok = tk.Label(footer, bg=ACCENT, fg="white", font=BOLD, padx=12,
                           pady=4, cursor="hand2")
        self.ok.pack(side="right")
        cancel = tk.Label(footer, text="Annuler", bg=FIELD, fg=DANGER, font=BOLD,
                          padx=10, pady=4, cursor="hand2")
        cancel.pack(side="right", padx=(0, 8))
        self.ok.bind("<Button-1>", lambda e: self.validate())
        cancel.bind("<Button-1>", lambda e: self.cancel())
        self._label_ok()

        for widget in (win, self.text):
            widget.bind("<Enter>", self._pause)
        self._bind_tree(win, "<Button-1>", self._activate)
        self.text.bind("<Return>", lambda e: (self.validate(), "break")[1])
        self.text.bind("<Escape>", lambda e: self.cancel())
        self.text.bind("<Key>", self._pause, add="+")

        win.update_idletasks()
        height = win.winfo_reqheight()
        x = (win.winfo_screenwidth() - width) // 2
        y = win.winfo_screenheight() - self.margin - height - 8
        win.geometry(f"{width}x{height}+{x}+{y}")
        _set_noactivate(win, True)
        self._tick()

    def _bind_tree(self, widget, sequence, handler):
        widget.bind(sequence, handler, add="+")
        for child in widget.winfo_children():
            self._bind_tree(child, sequence, handler)

    def _fill(self, heard, proposed):
        """Inserts the proposal, tagging words that differ from what was heard."""
        a, b = words(heard), words(proposed)
        ops = SequenceMatcher(None, [plain(w) for w in a], [plain(w) for w in b],
                              autojunk=False).get_opcodes()
        changed = {}
        for op, i1, i2, j1, j2 in ops:
            if op == "replace":
                for j in range(j1, j2):
                    changed[j] = " ".join(a[i1:i2]) if j == j1 else ""
        self.text.insert("1.0", proposed)
        index, start = 0, "1.0"
        for n, word in enumerate(b):
            pos = self.text.search(word, start, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(word)}c"
            start = end
            if n in changed:
                tag = f"chg{index}"
                index += 1
                self.text.tag_add(tag, pos, end)
                self.text.tag_config(tag, foreground=CHANGED, underline=True)
                original = changed[n]
                self.text.tag_bind(tag, "<Button-1>",
                                   lambda e, t=tag, o=original: self._revert(t, o))
        self.text.edit_reset()

    def _revert(self, tag, original):
        ranges = self.text.tag_ranges(tag)
        if not ranges:
            return
        self.text.delete(ranges[0], ranges[1])
        self.text.insert(ranges[0], original)
        self._pause()

    def _activate(self, event=None):
        """First click: let the box take keyboard focus so the user can type."""
        if self.win is None or self.activated:
            return
        if str(event.widget).startswith(str(self.win)):
            self.activated = True
            self._pause()
            _set_noactivate(self.win, False)
            _user32.SetForegroundWindow(_hwnd(self.win))
            self.text.focus_force()

    def _pause(self, _event=None):
        self.paused = True
        self._label_ok()

    def _label_ok(self):
        verb = "Envoyer" if self.send else "Coller"
        suffix = "" if self.paused else f" ({max(0, int(self.remaining + 0.99))})"
        self.ok.config(text=f"{verb} ⏎{suffix}")

    def _tick(self):
        if self.win is None:
            return
        if not self.paused:
            self.remaining -= 0.1
            self._label_ok()
            if self.remaining <= 0:
                self.validate("timeout")
                return
        self.win.after(100, self._tick)

    def _finish(self, value, how):
        if self.win is None:
            return
        callback = self.on_done
        if self.activated and self.target:
            _user32.SetForegroundWindow(self.target)  # back to the paste target
        self.close()
        callback(value, how)

    def validate(self, how="user"):
        if self.win is not None:
            self._finish(self.text.get("1.0", "end-1c").strip(), how)

    def cancel(self):
        self._finish(None, "cancel")

    def close(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None
