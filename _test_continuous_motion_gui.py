"""Widget smoke test for "Continuous-motion export (CMD=2)" (2026-09-14).

_test_continuous_motion.py proves the recipe is right. This proves the operator
can reach it: the box is in the PLC section, it follows PLC mode, its five
settings are greyed out until it is ticked, typing a number writes the machine
key, and a nonsense number (0, negative, text) is put back instead of stored —
T = 0 would divide by zero in the planner.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from i18n import set_language, t
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.machine_tab import MachineTab

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


set_language("EN")
root = tk.Tk()
# Key events are only delivered to a mapped, focused widget, so the window is
# shown off-screen instead of withdrawn — this drives the real <Return> binding.
root.geometry("+-3000+-3000")

written = {}
app = MagicMock()
app.params = {"plc_mode": True, "plc_auto_tune": False, "plc_target_lines": 1000,
              "plc_pass_markers": False, "plc_tolerance": 0.5, "plc_exit_tolerance": 0.5,
              "plc_continuous": False, "plc_scan_time_s": 0.1, "plc_corner_tol_mm": 0.1,
              "plc_feed_min": 30, "plc_reversal_deg": 90.0, "plc_stop_slowdown": False}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False


def _on_param_change(key, value, mode="none"):
    written[key] = value
    app.params[key] = value


app.on_param_change = _on_param_change
helper = MagicMock()
helper.bind_tooltip = lambda *a, **k: None
helper.register_param_var = lambda *a, **k: None

frame = ttk.Frame(root)
try:
    MachineTab(frame, app, helper)
    built = True
except Exception as e:
    built = False
    print("   tab build raised:", e)
check(built, "the Machine tab still builds with the continuous-motion block in it")
frame.pack(fill="both", expand=True)
root.update()


def press_return(entry, text):
    entry.delete(0, "end")
    entry.insert(0, text)
    entry.focus_force()
    root.update()
    entry.event_generate("<Return>")
    root.update()


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def checkbutton(text):
    return [c for c in walk(frame) if isinstance(c, (ttk.Checkbutton, tk.Checkbutton))
            and str(c.cget("text")) == text]


def entry_for(label_text):
    """The Entry that sits in the same row as the label."""
    for c in walk(frame):
        if isinstance(c, tk.Label) and str(c.cget("text")) == label_text:
            return [s for s in c.master.winfo_children() if isinstance(s, ttk.Entry)]
    return []


cont = checkbutton(t("cb_plc_continuous"))
check(len(cont) == 1, f"exactly one continuous-motion checkbox (found {len(cont)})")
check("EXPERIMENTAL PLC ONLY" in t("cb_plc_continuous"),
      "its label says EXPERIMENTAL PLC ONLY")

rows = {k: entry_for(t(k)) for k in ("lbl_plc_scan_time", "lbl_plc_corner_tol",
                                     "lbl_plc_feed_min", "lbl_plc_reversal")}
check(all(len(v) == 1 for v in rows.values()),
      f"all four number fields exist ({ {k: len(v) for k, v in rows.items()} })")
stop = checkbutton(t("cb_plc_stop_slowdown"))
check(len(stop) == 1, "the 'slow down before stops' box exists")

if cont and all(len(v) == 1 for v in rows.values()) and stop:
    box = cont[0]
    fields = [v[0] for v in rows.values()] + [stop[0]]
    check(str(box.cget("state")) != "disabled", "the box is enabled while PLC mode is on")
    check(all(str(f.cget("state")) == "disabled" for f in fields),
          "its settings are greyed out while the box is off")

    box.invoke()
    check(written.get("plc_continuous") is True, "ticking writes plc_continuous=True")
    check(all(str(f.cget("state")) != "disabled" for f in fields),
          "its settings become editable once ticked")

    e = rows["lbl_plc_reversal"][0]
    press_return(e, "10")
    check(written.get("plc_reversal_deg") == 10.0, f"typing 10 writes plc_reversal_deg=10 ({written.get('plc_reversal_deg')!r})")

    press_return(e, "500")
    check(written.get("plc_reversal_deg") == 180.0, "the stop angle is capped at 180")

    t_entry = rows["lbl_plc_scan_time"][0]
    for bad in ("0", "-1", "abc"):
        press_return(t_entry, bad)
    check("plc_scan_time_s" not in written,
          f"0 / negative / text is not stored as the scan time ({written.get('plc_scan_time_s')!r})")
    check(t_entry.get() == "0.1", f"and the field shows the stored value again ({t_entry.get()!r})")

    press_return(t_entry, "0,08")
    check(written.get("plc_scan_time_s") == 0.08, "a comma decimal is accepted (0,08 -> 0.08)")

    f_entry = rows["lbl_plc_feed_min"][0]
    press_return(f_entry, "25.7")
    check(written.get("plc_feed_min") == 25, "the lowest feed is stored as a whole number")

    stop[0].invoke()
    check(written.get("plc_stop_slowdown") is True, "ticking 'slow down before stops' writes True")

    box.invoke()
    check(written.get("plc_continuous") is False, "un-ticking writes False again")
    check(all(str(f.cget("state")) == "disabled" for f in fields),
          "and greys the settings out again")

root.destroy()
print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
raise SystemExit(1 if fails else 0)
