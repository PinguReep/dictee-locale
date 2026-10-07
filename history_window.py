"""Window listing the encrypted dictation history (decrypted in memory only).

Double-click or Entrée on a line copies that dictation (kept out of the Win+V
history, like every paste).
"""

import time
import tkinter as tk

import clipboard_win
from review_box import BG, BOLD, BORDER, DIM, FIELD, FONT, SMALL, TEXT, ACCENT

MAX_ROWS = 200


def show_history(root, store):
    records = [r for r in store.records()
               if r.get("final") and not r.get("calibration")][::-1][:MAX_ROWS]
    win = tk.Toplevel(root)
    win.title("Dictée locale — historique")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.geometry("760x520")

    header = tk.Frame(win, bg=BG, padx=12, pady=10)
    header.pack(fill="x")
    tk.Label(header, text="Historique (chiffré, sur ce PC uniquement)", bg=BG,
             fg=TEXT, font=BOLD).pack(side="left")
    status = tk.Label(header, text=f"{len(records)} dictées", bg=BG, fg=DIM,
                      font=SMALL)
    status.pack(side="right")

    body = tk.Frame(win, bg=BORDER)
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    listbox = tk.Listbox(body, bg=FIELD, fg=TEXT, font=FONT, relief="flat",
                         selectbackground=ACCENT, activestyle="none",
                         highlightthickness=0)
    scroll = tk.Scrollbar(body, command=listbox.yview)
    listbox.config(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True, padx=1, pady=1)

    for record in records:
        when = time.strftime("%d/%m %H:%M", time.localtime(record.get("at", 0)))
        text = " ".join(record["final"].split())
        listbox.insert("end", f"{when}   {text[:110]}{'…' if len(text) > 110 else ''}")

    def copy(_event=None):
        selection = listbox.curselection()
        if not selection:
            return
        clipboard_win.set_private_text(records[selection[0]]["final"])
        status.config(text="Copié dans le presse-papier")
        win.after(2000, lambda: status.config(text=f"{len(records)} dictées"))

    listbox.bind("<Double-Button-1>", copy)
    listbox.bind("<Return>", copy)
    win.focus_force()
    return win
