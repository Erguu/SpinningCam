import tkinter as tk
from tkinter import ttk
from ui.dialogs.zone_manager import ZoneManager
from ui.dialogs.tool_manager import ToolManager

class ProgramTab:
    def __init__(self, parent_frame, app, ui_root, ui_helper):
        self.app = app
        self.ui_root = ui_root
        self.helper = ui_helper
        self.frame = parent_frame
        
        self._create_widgets()
        
    def _create_widgets(self):
        # Frame for Treeview
        f_tree = ttk.Frame(self.frame)
        f_tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        cols = ("Idx", "Type", "Count", "Tool")
        self.tree_ops = ttk.Treeview(f_tree, columns=cols, show="headings", height=6)
        self.tree_ops.heading("Idx", text="#"); self.tree_ops.column("Idx", width=30)
        self.tree_ops.heading("Type", text="TYPE"); self.tree_ops.column("Type", width=70)
        self.tree_ops.heading("Count", text="Count"); self.tree_ops.column("Count", width=40)
        self.tree_ops.heading("Tool", text="Tool"); self.tree_ops.column("Tool", width=50)
        self.tree_ops.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(f_tree, orient="vertical", command=self.tree_ops.yview)
        sb.pack(side="right", fill="y")
        self.tree_ops.configure(yscrollcommand=sb.set)
        self.tree_ops.bind("<<TreeviewSelect>>", self.on_op_select)
        
        # Toolbar
        f_tools = ttk.Frame(self.frame)
        f_tools.pack(fill="x", padx=5, pady=2)
        
        # Actions
        ttk.Button(f_tools, text="+ Rough", width=7, command=lambda: self.add_op("roughing")).pack(side="left", padx=1)
        ttk.Button(f_tools, text="+ Finish", width=7, command=lambda: self.add_op("finishing")).pack(side="left", padx=1)
        ttk.Button(f_tools, text="Delete", width=4, command=self.del_op).pack(side="left", padx=1)
        ttk.Button(f_tools, text="Tools", width=5, command=self.open_tool_manager).pack(side="left", padx=5)
        
        # Navigation & Info (Right side)
        ttk.Button(f_tools, text="▲", width=3, command=lambda: self.move_op(-1)).pack(side="right", padx=1)
        ttk.Button(f_tools, text="▼", width=3, command=lambda: self.move_op(1)).pack(side="right", padx=1)
        
        # Time Label (Right of buttons, Left of Arrows)
        self.lbl_time = ttk.Label(f_tools, text="--:--", font=("Arial", 10, "bold"), foreground="#004488")
        self.lbl_time.pack(side="right", padx=10)
        
        # Property Editor
        self.f_prop_editor = ttk.LabelFrame(self.frame, text="Operation Settings")
        self.f_prop_editor.pack(fill="x", padx=5, pady=5)
        
        if "operations" not in self.app.params:
             self.app.params["operations"] = self.app.path_gen._ensure_ops_dict(self.app.params)
        self.refresh_ops_tree()

    def open_tool_manager(self):
        ToolManager(self.frame.winfo_toplevel(), self.ui_root)

    def refresh_ops_tree(self):
        ops = self.app.params.get("operations", [])
        existing_items = self.tree_ops.get_children()
        
        for i, op in enumerate(ops):
            vals = (i+1, op.get("type", "?").upper(), op.get("count", 1), op.get("tool_id", "?"))
            if i < len(existing_items):
                self.tree_ops.item(existing_items[i], values=vals)
            else:
                self.tree_ops.insert("", "end", iid=str(i), values=vals)
        
        if len(existing_items) > len(ops):
            for i in range(len(ops), len(existing_items)):
                self.tree_ops.delete(existing_items[i])
        
        self.update_time_estimate()

    def update_time_estimate(self):
        try:
            sec = self.app.path_gen.calculate_estimated_time(self.app.params)
            m, s = divmod(int(sec), 60)
            if self.lbl_time: self.lbl_time.config(text=f"Est. Time: {m:02d}:{s:02d}")
        except: pass

    def on_op_select(self, event):
        sel = self.tree_ops.selection()
        if not sel: 
            for w in self.f_prop_editor.winfo_children(): w.destroy()
            return
            
        try:
            idx = int(sel[0])
            if idx >= len(self.app.params["operations"]): return
            op = self.app.params["operations"][idx]
        except: return
        
        for w in self.f_prop_editor.winfo_children(): w.destroy()
        
        # --- Speed & Feed ---
        # Speed
        self._add_prop_combo(idx, "speed_mode", "Speed Mode", ["CSS", "RPM"], op, "Constant Surface Speed (G96) or Fixed RPM (G97).")
        s_lbl = "Speed (m/min)" if op.get("speed_mode", "CSS") == "CSS" else "Speed (RPM)"
        self._add_prop_entry(idx, "speed", s_lbl, op, is_float=True, tooltip="Surface Speed or RPM Value.")
        
        # Feed
        self._add_prop_combo(idx, "feed_mode", "Feed Mode", ["mm_min", "mm_rev"], op, "Feed in mm/min (G98) or mm/rev (G99).")
        f_lbl = "Feed (mm/min)" if op.get("feed_mode", "mm_min") == "mm_min" else "Feed (mm/rev)"
        self._add_prop_entry(idx, "feed", f_lbl, op, is_float=True, tooltip="Feed Rate Value.")
        
        # Zones Button
        f_z = ttk.Frame(self.f_prop_editor)
        f_z.pack(fill="x", padx=2, pady=5)
        # Use ZoneManager class logic
        def open_zones():
            ZoneManager(self.frame.winfo_toplevel(), self.app, idx)

        btn_z = tk.Button(f_z, text="Variable Speed Zones...", bg="lightblue", command=open_zones)
        btn_z.pack(fill="x")
        self.helper.bind_tooltip(btn_z, "Configure Feed/Speed changes at specific Z-depths.")
        
        ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=5)
        
        # Common Props
        # Tool ID Selector
        f_tool = ttk.Frame(self.f_prop_editor)
        f_tool.pack(fill="x", padx=10, pady=2)
        tk.Label(f_tool, text="Tool ID").pack(side="left")
        
        tool_ids = [t["id"] for t in self.ui_root.tool_library]
        if not tool_ids: tool_ids = ["T0101", "T0202"]
        
        cb_tool = ttk.Combobox(f_tool, values=tool_ids, width=15)
        cb_tool.pack(side="right")
        cb_tool.set(op.get("tool_id", "T0101"))
        
        def on_tool_change(event): 
            tid = cb_tool.get()
            self.app.on_param_change(f"operations[{idx}].tool_id", tid, "paths")
            # Auto-update radius if found
            found = next((t for t in self.ui_root.tool_library if t["id"] == tid), None)
            if found:
                r = found.get("radius", 0.0)
                self.app.on_param_change(f"operations[{idx}].r_tool", r, "paths")
        
        cb_tool.bind("<<ComboboxSelected>>", on_tool_change)
        self.helper.bind_tooltip(cb_tool, "Select Tool from Library.")
        
        self._add_prop_entry(idx, "r_tool", "Tool Radius", op, is_float=True, tooltip="Radius of the roller (Override).")
        self._add_prop_entry(idx, "count", "Pass Count", op, is_int=True, tooltip="Number of passes to generate.")
        
        # Zone range: Start Z to End Z
        self._add_prop_entry(idx, "start_z", "Zone Start Z", op, is_float=True, tooltip="Starting Z position for this operation zone.")
        self._add_prop_entry(idx, "end_z", "Zone End Z", op, is_float=True, tooltip="Ending Z position for this operation zone.")
        
        op_type = op.get("type", "roughing")
        if op_type == "roughing":
            self._add_prop_entry(idx, "p1_x", "P1 X (Entry)", op, is_float=True, tooltip="Spline Start X Offset from Surface.")
            self._add_prop_entry(idx, "p1_z", "P1 Z (Entry)", op, is_float=True, tooltip="Spline Start Z Offset from Contact.")
            self._add_prop_entry(idx, "p3_z", "P3 Z (Exit)", op, is_float=True, tooltip="Spline End Z Offset (Stroke Length).")
            self._add_prop_entry(idx, "step", "Step (mm)", op, is_float=True, tooltip="Depth of cut per pass (X/Z composite).")
            self._add_prop_entry(idx, "rot", "Rotation (Deg)", op, is_float=True, tooltip="Roller Angle (B-Axis).")
        else:
            self._add_prop_entry(idx, "r_tool", "Tool Radius", op, is_float=True, tooltip="Radius of the finish roller.")
            self._add_prop_entry(idx, "p1_x", "Extend (mm)", op, is_float=True, tooltip="Extend pass start/end beyond mandrel.")
            self._add_prop_entry(idx, "step", "Visual Offset", op, is_float=True, tooltip="Visual shift (unused in G-code).")
            self._add_prop_entry(idx, "rot", "Rotation (Deg)", op, is_float=True, tooltip="Roller Angle.")

    def _add_prop_combo(self, op_idx, key, label, values, op_dict, tooltip=""):
        f = ttk.Frame(self.f_prop_editor)
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")
        
        curr = op_dict.get(key, values[0])
        cb = ttk.Combobox(f, values=values, state="readonly")
        cb.set(curr)
        cb.pack(side="right", fill="x", expand=True)
        
        def save(e):
            self.app.params["operations"][op_idx][key] = cb.get()
            self.on_op_select(None)
            self.update_time_estimate()
            
        cb.bind("<<ComboboxSelected>>", save)
        self.helper.bind_tooltip(cb, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    def _add_prop_entry(self, op_idx, key, label, op_dict, is_int=False, is_float=False, tooltip=""):
        f = ttk.Frame(self.f_prop_editor)
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")
        
        val = op_dict.get(key, "")
        var = tk.StringVar(value=str(val))
        
        def save(e=None):
            try:
                v = var.get()
                if is_int: v = int(v)
                elif is_float: v = float(v)
                
                self.app.params["operations"][op_idx][key] = v
                self.refresh_ops_tree() 
                if self.app.params.get("calc_active", False):
                     self.app.update_scene("paths")
            except: pass
            
        entry = ttk.Entry(f, textvariable=var)
        entry.pack(side="right", fill="x", expand=True)
        entry.bind("<FocusOut>", save)
        entry.bind("<Return>", save)
        entry.bind("<Button-1>", lambda e: e.widget.focus_force())
        self.helper.bind_tooltip(entry, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    def add_op(self, mode):
        # Inherit rotation from last op
        def_rot = 10.0
        if "operations" in self.app.params and self.app.params["operations"]:
             def_rot = self.app.params["operations"][-1].get("rot", 10.0)

        # Choose default tool based on mode
        if mode == "roughing":
            def_tool_id = "T0101"
        else:
            def_tool_id = "T0202"
        
        # Look up tool radius from library
        def_r_tool = 25.0  # fallback default
        for t in self.ui_root.tool_library:
            if t["id"] == def_tool_id:
                def_r_tool = t.get("radius", 25.0)
                break
        
        # If not found by default ID, try to use first available tool of matching type
        if def_r_tool == 25.0 and self.ui_root.tool_library:
            # Just use first tool
            first_tool = self.ui_root.tool_library[0]
            def_tool_id = first_tool.get("id", def_tool_id)
            def_r_tool = first_tool.get("radius", 25.0)

        new_op = {
            "type": mode, "enabled": True, "count": 1, 
            "tool_id": def_tool_id,
            "r_tool": def_r_tool,
            "p1_x": 40.0, "p1_z": 50.0, "p3_z": -20.0, 
            "start_z": 0.0, "end_z": 200.0,  # Zone range
            "step": 1.0, 
            "rot": def_rot,
            "feed": 100.0, "speed": 500.0  # For velocity coloring
        }
        if "operations" not in self.app.params: self.app.params["operations"] = []
        self.app.params["operations"].append(new_op)
        self.refresh_ops_tree()

    def del_op(self):
        sel = self.tree_ops.selection()
        if sel:
            idx = int(sel[0])
            self.app.params["operations"].pop(idx)
            self.refresh_ops_tree()

    def move_op(self, d):
        sel = self.tree_ops.selection()
        if sel:
            idx = int(sel[0])
            new_idx = idx + d
            if 0 <= new_idx < len(self.app.params["operations"]):
                self.app.params["operations"][idx], self.app.params["operations"][new_idx] = self.app.params["operations"][new_idx], self.app.params["operations"][idx]
                self.refresh_ops_tree()
                self.tree_ops.selection_set(str(new_idx))
