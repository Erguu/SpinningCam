# -*- coding: utf-8 -*-
"""Coloured line-length warning (ui/dialogs/line_length_dialog.py, 2026-09-16).

The user asked for colour on the important parts - the parameter suggestions.
Pinned: every kind of line gets its colour role, the NEW value of a suggestion is
tagged on its own, the text is shown unchanged, and the two buttons answer
True / False.
"""
import tkinter as tk

from i18n import set_language, t
from ui.dialogs import line_length_dialog as lld

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


check(lld.classify("    → Change Exit Max Points: 4 → 14", False) == "change", "suggestion line is 'change'")
check(lld.classify("• Op3 rough: 2 lines too long on a curve", False) == "op", "operation line is 'op'")
check(lld.classify("    (The straight start line cannot be made longer)", False) == "note", "side note is 'note'")
check(lld.classify("Some curves are cut into lines that are too long", True) == "head", "first paragraph is 'head'")
check(lld.classify("Export anyway?", False) == "plain", "the question is plain")
two = ["Too short head.", "", "• Op1 a", "    → Change X: 1 → 2", "",
       "Too long head,", "second head line.", "", "• Op2 b", "", "Footer.", "", "Export anyway?"]
check(lld.head_lines(two) == {0, 5, 6}, "BOTH section headings are headings; the footer is not")

set_language("EN")
TEXT = ("Some curves are cut into lines that are too long (best: about 2.5 mm).\n\n"
        "• Op1 probe: 2 lines too long on a curve (longest 11.1 mm)\n"
        "    → Change Exit Max Points: 4 → 14\n\n"
        "These changes never bring the roller closer to the mandrel.\n\nExport anyway?")

root = tk.Tk()
root.withdraw()

# Build without blocking: the modal wait and grab are skipped for the test.
lld.LineLengthDialog.wait_window = lambda self, w=None: None
lld.LineLengthDialog.grab_set = lambda self: None


def build():
    d = lld.LineLengthDialog(root, "Line lengths", TEXT)
    root.update_idletasks()
    return d


d = build()
box = [w for w in d.winfo_children() if isinstance(w, tk.Text)][0]
shown = box.get("1.0", "end").rstrip("\n")
check(shown == TEXT, "the text is shown unchanged")
val_ranges = box.tag_ranges("value")
check(len(val_ranges) == 2 and box.get(val_ranges[0], val_ranges[1]).strip() == "14",
      "only the NEW value (14) carries the 'value' highlight")
chg = box.tag_ranges("change")
check(len(chg) >= 2 and "Change Exit Max Points" in box.get(chg[0], chg[1]), "the suggestion line is green")
check(box.cget("state") == "disabled", "the text cannot be edited")

btns = {}
def walk(w):
    for c in w.winfo_children():
        if c.winfo_class() in ("TButton", "Button"):
            btns[c.cget("text")] = c
        walk(c)
walk(d)
check(set(btns) == {t("btn_line_len_export"), t("btn_line_len_back")}, "two buttons: export / go back")
btns[t("btn_line_len_export")].invoke()
check(d.result is True, "'Export anyway' answers True")

d = build()
btns.clear(); walk(d)
btns[t("btn_line_len_back")].invoke()
check(d.result is False, "'Go back' answers False")

for lang in ("TR", "ES"):
    set_language(lang)
    try:
        dd = build(); dd.destroy(); ok = True
    except Exception as e:
        ok = False; print("   ", e)
    check(ok, f"builds in {lang}")
set_language("EN")
root.destroy()
print("\nALL PASS" if not fails else f"\n{fails} FAILED")
raise SystemExit(1 if fails else 0)
