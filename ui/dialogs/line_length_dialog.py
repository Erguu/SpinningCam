# -*- coding: utf-8 -*-
"""The line-length warning before a continuous-motion export, with colour.

User, 2026-09-16: "use colours to indicate the most important parts, parameter
suggestions". A plain messagebox cannot colour anything, so this is a small modal
window around the SAME text short_segments.py builds (the text stays testable on
its own). Each line is coloured by what it is:

    "→ Change …"        the thing to do          bold green on a light band
    "• Op…"             which operation          bold
    "(…)"               side note, nothing to do grey
    section heading     what the warning is      bold dark blue
    last paragraph      the question             normal

``result`` is True to export anyway, False to go back.
"""
import tkinter as tk
from tkinter import ttk

from i18n import t
from ui import dialog_sizing

COLORS = {
    "head": {"foreground": "#1f3a93", "font": ("Arial", 10, "bold")},
    "op": {"foreground": "#111111", "font": ("Arial", 10, "bold")},
    "change": {"foreground": "#0b6b1f", "background": "#e6f6e9", "font": ("Arial", 10, "bold")},
    "value": {"foreground": "#0b6b1f", "background": "#c9ecd0", "font": ("Arial", 11, "bold")},
    "note": {"foreground": "#777777", "font": ("Arial", 9, "italic")},
    "plain": {"foreground": "#222222", "font": ("Arial", 10)},
}


def classify(line, first_block):
    """The colour role of one line of the warning text. Pure, for the test."""
    s = line.strip()
    if not s:
        return "plain"
    if s.startswith("→"):
        return "change"
    if s.startswith("•"):
        return "op"
    if s.startswith("(") or s.startswith("…"):
        return "note"
    if first_block:
        return "head"
    return "plain"


def head_lines(lines):
    """Indices of the lines that belong to a section heading: a paragraph that
    is directly followed by a paragraph of operation lines. The closing
    question is not followed by one, so it stays plain."""
    paras, cur = [], []
    for n, line in enumerate(lines):
        if line.strip():
            cur.append(n)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    out = set()
    for a, b in zip(paras, paras[1:]):
        first_a = lines[a[0]].strip()
        if lines[b[0]].strip().startswith("•") and not first_a.startswith(("•", "→", "(")):
            out.update(a)
    return out


class LineLengthDialog(tk.Toplevel):
    """Modal. ``result`` is True (export anyway) or False (go back)."""

    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.title(title)
        self.result = False
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._no)

        # Button bar FIRST and at the bottom: with a fixed size and a high DPI,
        # a bar packed last is the part that disappears (project rule, #103).
        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text=t("btn_line_len_back"), command=self._no).pack(side="right", padx=4)
        ttk.Button(bar, text=t("btn_line_len_export"), command=self._yes).pack(side="right", padx=4)

        box = tk.Text(self, wrap="word", width=78, height=16, relief="flat",
                      padx=14, pady=12, background="#ffffff", cursor="arrow")
        box.pack(side="top", fill="both", expand=True)
        for tag, style in COLORS.items():
            box.tag_configure(tag, **style)

        lines = text.split(chr(10))
        heads = head_lines(lines)
        for n, line in enumerate(lines):
            role = classify(line, n in heads)
            if role == "change" and "→" in line[line.index("→") + 1:]:
                # Make the NEW value stand out from the rest of the line.
                cut = line.rindex("→") + 1
                box.insert("end", line[:cut], role)
                box.insert("end", line[cut:], "value")
                box.insert("end", "\n", role)
            else:
                box.insert("end", line + "\n", role)
        box.configure(state="disabled")

        self.bind("<Escape>", lambda _e: self._no())
        self.bind("<Return>", lambda _e: self._yes())
        dialog_sizing.fit(self, 640, 380, parent)
        self.grab_set()
        self.wait_window(self)

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.result = False
        self.destroy()


def ask(parent, title, text):
    """Show the warning; True = export anyway."""
    return bool(LineLengthDialog(parent, title, text).result)
