"""GUI smoke test for the predicted sheet-edge toggle on the Process tab.

Guards the wiring the unit tests cannot see: the checkbox is built, flipping it
writes params["show_blank_edge"], calls update_blank_edge, and persists.
Skips cleanly on a machine with no display.
"""
import tkinter as tk
import types
import unittest

try:
    _root = tk.Tk()
    _root.withdraw()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "no display")
class TestBlankEdgeToggle(unittest.TestCase):
    def setUp(self):
        from ui.helpers_ui import UIHelper
        from ui.tabs.process_tab import ProcessTab

        self.calls = {"draw": 0, "save": 0}
        self.app = types.SimpleNamespace()
        self.app.params = {
            "show_deformed_blank": True, "show_blank_edge": True,
            "deformed_blank_offset": 0.0, "shell_thickness": 0.0,
            "operations": [], "pass_colors": {},
        }
        self.app.update_deformed_blank = lambda render=False: None
        self.app.update_blank_edge = self._draw
        self.app.save_settings_json = self._save
        self.app.update_scene = lambda *a, **k: None
        self.app.on_param_change = lambda *a, **k: None

        # ui_root is the main WINDOW object (callback host), not the Tk root.
        noop = lambda *a, **k: None
        ui_root = types.SimpleNamespace(
            load_step_prompt=noop, run_sim=noop, stop_sim=noop,
            ui_program=types.SimpleNamespace(refresh_ops_tree=noop),
        )
        self.frame = tk.Frame(_root)
        self.tab = ProcessTab(self.frame, self.app, ui_root,
                              UIHelper(tk.Label(_root)))

    def _draw(self, render=False):
        self.calls["draw"] += 1

    def _save(self, *a, **k):
        self.calls["save"] += 1

    def test_checkbox_is_built_and_defaults_on(self):
        self.assertTrue(hasattr(self.tab, "_be_var"), "sheet-edge checkbox missing")
        self.assertTrue(self.tab._be_var.get())

    def test_turning_it_off_writes_params_and_redraws(self):
        self.tab._be_var.set(False)
        self.tab._be_var.get()          # settle
        for cb in _walk_checkbuttons(self.tab.content):
            if cb.cget("variable") == str(self.tab._be_var):
                cb.invoke(); cb.invoke()   # off then on, exercising both directions
                break
        else:
            self.fail("sheet-edge checkbutton not found in the tab")
        self.assertGreaterEqual(self.calls["draw"], 1, "overlay was never redrawn")
        self.assertGreaterEqual(self.calls["save"], 1, "setting was never persisted")
        self.assertIn("show_blank_edge", self.app.params)

    def test_it_is_a_separate_layer_from_the_bent_sheet_overlay(self):
        self.assertTrue(hasattr(self.tab, "_db_var"))
        self.assertIsNot(self.tab._be_var, self.tab._db_var,
                         "the two overlays must not share one toggle")

    def tearDown(self):
        try:
            self.frame.destroy()
        except Exception:
            pass


def _walk_checkbuttons(widget):
    from tkinter import ttk
    for child in widget.winfo_children():
        if isinstance(child, (ttk.Checkbutton, tk.Checkbutton)):
            yield child
        yield from _walk_checkbuttons(child)


if __name__ == "__main__":
    unittest.main(verbosity=2)
