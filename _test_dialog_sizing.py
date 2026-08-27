# -*- coding: utf-8 -*-
"""#103 — dialogs must open big enough to show their own buttons.

The bug: every dialog asked for a fixed pixel size while the main window sets Tk
scaling from the monitor DPI. On a 125% display the waypoint editor's content
needed 654 px and the window opened at 600 — the missing 54 px was the OK row,
so the operator saw a dialog he could not accept.

Run:  python _test_dialog_sizing.py
"""
import sys
import tkinter as tk

from ui import dialog_sizing

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


class FakeWin:
    """Just the four measurements `measure` reads."""
    def __init__(self, req_w, req_h, screen_w=1920, screen_h=1080):
        self._v = (req_w, req_h, screen_w, screen_h)

    def winfo_reqwidth(self):     return self._v[0]
    def winfo_reqheight(self):    return self._v[1]
    def winfo_screenwidth(self):  return self._v[2]
    def winfo_screenheight(self): return self._v[3]


def test_measure():
    print("\n[1] the sizing rule")
    # The real measurement from the probe: 125% DPI, waypoint editor.
    w, h, mw, mh = dialog_sizing.measure(FakeWin(786, 654), 820, 600)
    check("a window that needs more than it asked for GROWS", h == 654, f"h={h}")
    check("the wish still wins when it is larger", w == 820, f"w={w}")
    check("minsize is the content requirement", (mw, mh) == (786, 654), f"{(mw, mh)}")

    # 96 dpi: content fits, nothing changes — no regression on the dev machine.
    w, h, _, _ = dialog_sizing.measure(FakeWin(781, 594), 820, 600)
    check("a window that already fits is left alone", (w, h) == (820, 600), f"{(w, h)}")

    # Content larger than the screen must clamp, and never exceed it.
    w, h, mw, mh = dialog_sizing.measure(FakeWin(2400, 1000), 2400, 1000)
    check("width clamps to 95% of the screen", w == int(1920 * 0.95), f"w={w}")
    check("height clamps to 90% of the screen", h == int(1080 * 0.90), f"h={h}")

    w, h, mw, mh = dialog_sizing.measure(FakeWin(1400, 1000, 1366, 768), 1400, 1000)
    check("on a 1366x768 laptop nothing exceeds the screen",
          w <= 1366 and h <= 768, f"{(w, h)}")
    check("minsize is clamped too, so the window stays draggable",
          mw <= 1366 and mh <= 768, f"{(mw, mh)}")

    # Degenerate: a window measured before its widgets exist reports 1x1.
    w, h, _, _ = dialog_sizing.measure(FakeWin(1, 1), 720, 480)
    check("an unbuilt window falls back to the wish", (w, h) == (720, 480), f"{(w, h)}")


def test_real_dialogs():
    print("\n[2] real dialogs at operator DPI")
    try:
        from mandrel_analyzer import MandrelManager
        from path_generator import PathGenerator
        from ui.dialogs.exit_tail_dialog import ExitTailDialog
        from ui.dialogs.break_points_dialog import BreakPointsDialog
    except Exception as e:                                   # pragma: no cover
        print(f"  SKIP  {type(e).__name__}: {e}")
        return

    mgr = MandrelManager(); mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0.0, 0.0)
    op = {"type": "roughing", "name": "R1", "count": 3, "start_z": 30.0, "end_z": 55.0,
          "r_tool": 25.0, "clearance": 2.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0,
          "p3_z": -25.0, "pass_shape": "linear_approach", "direction": "forward",
          "p2_radius": 4.0}

    class App:
        def __init__(self):
            self.params = {"operations": [op], "target_clearance": 2.0,
                           "mandrel_pos_x_offset": 0.0, "blank_radius": 0.0,
                           "final_part_thickness_on_mandrel": 2.0,
                           "shell_thickness": 0.0, "roller_positive_x_side": True}
            self.mandrel_mgr = mgr
            self.path_gen = PathGenerator()

    for scaling in (1.333, 1.667, 2.0):
        root = tk.Tk()
        root.tk.call("tk", "scaling", scaling)
        root.geometry("200x100+20+20")
        app = App()
        for label, mk in (
                ("ExitTail", lambda: ExitTailDialog(root, app, 0, 0, (70.0, 30.0),
                                                    lambda *a, **k: None)),
                ("BreakPoints", lambda: BreakPointsDialog(root, app, 0, 0,
                                                          lambda *a: None))):
            d = mk()
            d.update_idletasks()
            w, h, _, _ = dialog_sizing.measure(d, 1, 1)   # what fit() would choose
            check(f"{label} @ scaling {scaling:.3f} opens tall enough",
                  h >= d.winfo_reqheight(), f"{h} < {d.winfo_reqheight()}")
            d.destroy()
        root.destroy()


def test_button_bar_last_resort():
    print("\n[3] the buttons survive a window too small to fit anything")
    try:
        from mandrel_analyzer import MandrelManager
        from path_generator import PathGenerator
        from ui.dialogs.break_points_dialog import BreakPointsDialog
    except Exception as e:                                   # pragma: no cover
        print(f"  SKIP  {type(e).__name__}: {e}")
        return
    mgr = MandrelManager(); mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0.0, 0.0)

    class App:
        def __init__(self):
            self.params = {"operations": [{"type": "roughing", "name": "R1",
                                           "count": 2, "pass_shape": "linear_approach",
                                           "r_tool": 25.0}],
                           "target_clearance": 2.0, "mandrel_pos_x_offset": 0.0,
                           "roller_positive_x_side": True}
            self.mandrel_mgr = mgr
            self.path_gen = PathGenerator()

    root = tk.Tk(); root.geometry("200x100+20+20")
    d = BreakPointsDialog(root, App(), 0, 0, lambda *a: None)
    # Let fit()'s deferred callback run FIRST — otherwise it fires later and
    # undoes the shrink below, and the test measures nothing.
    d.deiconify(); d.update(); d.update_idletasks()
    # Now force it far smaller than its content needs — the screen-too-small
    # case that no amount of resizing can fix.
    d.minsize(1, 1)
    d.geometry("500x150+30+30")
    d.update(); d.update_idletasks()

    ok = None
    for child in d.winfo_children():
        for gc in child.winfo_children():
            if isinstance(gc, tk.ttk.Button) and gc.cget("text") in ("OK", "Tamam", "Aceptar"):
                ok = gc
    check("the OK button exists", ok is not None)
    if ok is not None:
        check("and it is still mapped inside the squeezed window",
              bool(ok.winfo_ismapped()) and ok.winfo_rooty() < d.winfo_rooty() + 150,
              f"mapped={ok.winfo_ismapped()} y={ok.winfo_rooty()} win_y={d.winfo_rooty()}")
    d.destroy(); root.destroy()


if __name__ == "__main__":
    test_measure()
    test_real_dialogs()
    test_button_bar_last_resort()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
