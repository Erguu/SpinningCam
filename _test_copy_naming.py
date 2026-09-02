# -*- coding: utf-8 -*-
"""Headless test for numbered copy names (user request 2026-09-02).

Copies used to be "<name> (copy)", so duplicating a duplicate produced
"Rough (copy) (copy) (copy)". Now a trailing counter is used instead. What has
to hold:
  * a name with no number starts at 2 (the original is implicitly 1);
  * a name that ALREADY ends in a number continues it, never "Rough 1 2";
  * the number skips whatever is already taken, case-insensitively;
  * legacy "(copy)" markers are dropped rather than built on — in ANY of the
    three languages, because a name made in EN survives into a TR session;
  * copying several ops at once hands out DIFFERENT numbers;
  * an unnamed op stays unnamed (the list falls back to the type).
"""
from ui.tabs.program_tab import next_copy_name, strip_copy_suffixes
from i18n import STRINGS

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


def eq(got, want, msg):
    check(got == want, f"{msg}  (got {got!r}, want {want!r})")


# ── no number yet → starts at 2 ───────────────────────────────────────────
eq(next_copy_name("Rough", {"Rough"}), "Rough 2", "unnumbered name starts at 2")
eq(next_copy_name("Rough", {"Rough", "Rough 2"}), "Rough 3", "skips a taken 2")
eq(next_copy_name("Rough", {"Rough", "Rough 2", "Rough 3", "Rough 5"}), "Rough 4",
   "fills the first free gap rather than jumping to the end")

# ── already numbered → continues, never appends a second number ───────────
eq(next_copy_name("Rough 1", {"Rough 1"}), "Rough 2", "numbered name continues")
eq(next_copy_name("Rough 7", {"Rough 7"}), "Rough 8", "continues from 7")
check(" 1 2" not in next_copy_name("Rough 1", {"Rough 1"}),
      "never produces 'Rough 1 2'")
eq(next_copy_name("Finish 2", {"Finish 2", "Finish 3", "Finish 4"}), "Finish 5",
   "continues past a run of taken numbers")

# ── case / whitespace insensitivity ───────────────────────────────────────
eq(next_copy_name("Rough", {"rough 2", "ROUGH 3"}), "Rough 4",
   "taken names match case-insensitively")
eq(next_copy_name("Rough", {"  Rough 2  "}), "Rough 3",
   "taken names are trimmed before matching")

# ── legacy "(copy)" markers are stripped, not built on ────────────────────
for lang, word in STRINGS["lbl_copy_suffix"].items():
    eq(next_copy_name(f"Rough ({word})", {"Rough"}), "Rough 2",
       f"legacy {lang} suffix '({word})' is dropped")
eq(next_copy_name("Rough (copy) (copy)", {"Rough"}), "Rough 2",
   "a pile of legacy suffixes is dropped in one go")
eq(next_copy_name("Rough 2 (copy)", {"Rough 2"}), "Rough 3",
   "a legacy suffix on a numbered name still continues the number")
eq(strip_copy_suffixes("Rough (COPY) (Kopya)"), "Rough",
   "stripping ignores case and mixes languages")
eq(strip_copy_suffixes("Copy of Rough"), "Copy of Rough",
   "only a TRAILING marker is stripped — a name that merely contains the word survives")

# ── separators before the number ──────────────────────────────────────────
eq(next_copy_name("Rough-1", {"Rough-1"}), "Rough 2", "dash separator normalises")
eq(next_copy_name("Rough_3", {"Rough_3"}), "Rough 4", "underscore separator normalises")

# ── degenerate names ──────────────────────────────────────────────────────
eq(next_copy_name("2", {"2"}), "3", "a name that is only a number still counts up")
eq(next_copy_name("", set()), "", "an empty name stays empty (op keeps no name)")
eq(next_copy_name(None, set()), "", "None is tolerated")
eq(next_copy_name("   ", set()), "", "whitespace-only is treated as no name")

# ── multi-op copy hands out distinct numbers (mirrors copy_ops' loop) ─────
ops = [{"name": "Rough"}, {"name": "Rough"}, {"name": "Finish 1"}]
used = {o["name"] for o in ops}
out = []
for o in ops:
    n = next_copy_name(o["name"], used)
    used.add(n)
    out.append(n)
eq(out, ["Rough 2", "Rough 3", "Finish 2"],
   "copying three ops at once gives three distinct names")
check(len(set(out)) == len(out), "no duplicate names across one multi-copy")

# ── through the REAL copy_ops, repeatedly — the case that used to pile up ──
#    The pure helper can be right while the caller still feeds it the wrong
#    "taken" set, which is exactly how the old code produced "(copy) (copy)".
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab

root = tk.Tk()
root.withdraw()
app = MagicMock()
app.params = {"operations": [
    {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101",
     "name": "my rough"},
    {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0202"},
]}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False
helper = MagicMock(); helper.HINT_COLOR = "#9a9a9a"; helper.HINT_FONT = ("Arial", 7)
tab = ProgramTab(ttk.Frame(root), app, MagicMock(), helper)
root.update_idletasks()

names = []
for _ in range(4):                       # copy the LATEST copy, four times over
    idx = max(i for i, o in enumerate(app.params["operations"]) if o.get("name"))
    tab._batch_checked.clear()
    tab.tree_ops.selection_set(str(idx))
    tab.copy_ops()
    names.append(app.params["operations"][idx + 1]["name"])
eq(names, ["my rough 2", "my rough 3", "my rough 4", "my rough 5"],
   "copying a copy keeps counting up instead of piling markers")
check(not any("(" in n for n in names), "no '(copy)' marker appears anywhere")
_fin = [o for o in app.params["operations"] if o["type"] == "finishing"]
check(len(_fin) == 1 and _fin[0].get("name") is None,
      "the unnamed finishing op was neither copied nor given a name")

# Copying a MIDDLE one when later numbers exist takes the next free number.
tab._batch_checked.clear()
tab.tree_ops.selection_set("0")           # "my rough" again, with 2..5 taken
tab.copy_ops()
eq(app.params["operations"][1]["name"], "my rough 6",
   "re-copying the original skips every number already in use")
root.destroy()

print()
print("FAILED" if fails else "ALL PASS", f"({fails} failure(s))")
raise SystemExit(1 if fails else 0)
