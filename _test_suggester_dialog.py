"""Widget smoke test for OpSuggesterDialog: builds the dialog against a stub
app (default cone profile), verifies the preview renders, simulates material
change + recalc + apply callback, then tears down. No main window needed."""
import sys
import tkinter as tk

from mandrel_analyzer import MandrelManager
from ui.dialogs.op_suggester import OpSuggesterDialog


class StubApp:
    def __init__(self):
        self.mandrel_mgr = MandrelManager()
        self.mandrel_mgr.create_default_cone()
        self.mandrel_mgr.update_geometry(0, 0, 0, 0.0, 0.0)
        self.params = {
            "final_part_thickness_on_mandrel": 2.0,
            "mandrel_pos_x_offset": 0.0,
            "max_spin_rpm": 2000,
            "operations": [],
        }

    def on_param_change(self, key, val, mode="paths"):
        self.params[key] = val


applied = {}

def on_apply(ops, thickness):
    applied["ops"] = ops
    applied["thickness"] = thickness


root = tk.Tk()
root.withdraw()
app = StubApp()
tools = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0},
         {"id": "T0202", "r_tool": None, "radius": 22.5}]

dlg = OpSuggesterDialog(root, app, tools, on_apply)
root.update()

assert dlg.result is not None, "no suggestion computed on open"
preview = dlg.txt.get("1.0", "end")
assert "ROUGHING" in preview and "FINISHING" in preview, f"preview incomplete:\n{preview}"
from i18n import t
assert t("sug_h_why") in preview, "WHY section missing from preview"
assert preview.count("•") >= 7, "why-notes not rendered"
print("preview renders rough+finish + WHY section OK")

# Insert button bar must be packed side="bottom" (and before the preview) so
# it can never be clipped when the window is resized small.
_bar = dlg.btn_apply.master
assert _bar.pack_info()["side"] == "bottom", "button bar not bottom-anchored"
_children = dlg.pack_slaves()
assert _children.index(_bar) < len(_children) - 1, "button bar packed after preview"
print("insert button bottom-anchored (cannot be clipped) OK")

# Material switch triggers recalc
dlg.cmb_material.current(3)  # stainless
dlg._recalculate()
assert dlg.result["ops"][0]["count"] >= 4, "stainless recalc did not raise pass count"
print("material switch recalculates OK")

# Thickness edit flows into apply callback
dlg.ent_thick.delete(0, "end"); dlg.ent_thick.insert(0, "1.5")
dlg._recalculate()
assert abs(dlg.result["analysis"]["blank_thickness"] - 1.5) < 1e-9
# bypass the confirm messagebox: call the callback path directly
dlg.on_apply(dlg.result["ops"], dlg.result["analysis"]["blank_thickness"])
assert len(applied["ops"]) == 2 and applied["thickness"] == 1.5
print("apply callback delivers ops + thickness OK")

dlg.destroy()
root.destroy()
print("DIALOG SMOKE TEST PASSED")
sys.exit(0)
