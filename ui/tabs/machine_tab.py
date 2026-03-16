import tkinter as tk
from tkinter import ttk
from ui.tabs.scrollable_tab_base import ScrollableTabBase


class MachineTab(ScrollableTabBase):
    def __init__(self, parent_frame, app, ui_helper):
        self.app = app
        self.helper = ui_helper
        
        # Initialize scrollable area from base class
        super().__init__(parent_frame)

        self._create_widgets()

    def _create_widgets(self):
        tk.Label(self.content, text="Machine Settings", font=("Arial", 12, "bold"), pady=10).pack()
        
        # --- Machine Coordinate System (Post-Processor) ---
        f_coords = ttk.LabelFrame(self.content, text="Machine Coordinate System (Post-Processor)")
        f_coords.pack(fill="x", padx=10, pady=10)
        
        # Info Label
        tk.Label(f_coords, text="Dönüşüm: X_machine = (X_global - origin_x) × direction", 
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5)
        
        # Machine Origin (in Global Coords)
        f_origin = ttk.Frame(f_coords)
        f_origin.pack(fill="x", padx=5, pady=5)
        tk.Label(f_origin, text="Machine Origin (Global Coords):").pack(anchor="w")
        
        f_origin_inputs = ttk.Frame(f_coords)
        f_origin_inputs.pack(fill="x", padx=5, pady=2)
        
        # Origin X
        tk.Label(f_origin_inputs, text="X:").pack(side="left", padx=2)
        var_origin_x = tk.DoubleVar(value=self.app.params.get("machine_origin_x", 0.0))
        def on_origin_x_change():
            try: self.app.on_param_change("machine_origin_x", var_origin_x.get(), "none")
            except: pass
        e_origin_x = ttk.Entry(f_origin_inputs, textvariable=var_origin_x, width=8)
        e_origin_x.pack(side="left", padx=2)
        e_origin_x.bind("<Return>", lambda ev: on_origin_x_change())
        e_origin_x.bind("<FocusOut>", lambda ev: on_origin_x_change())
        
        # Origin Z
        tk.Label(f_origin_inputs, text="Z:").pack(side="left", padx=(10, 2))
        var_origin_z = tk.DoubleVar(value=self.app.params.get("machine_origin_z", 0.0))
        def on_origin_z_change():
            try: self.app.on_param_change("machine_origin_z", var_origin_z.get(), "none")
            except: pass
        e_origin_z = ttk.Entry(f_origin_inputs, textvariable=var_origin_z, width=8)
        e_origin_z.pack(side="left", padx=2)
        e_origin_z.bind("<Return>", lambda ev: on_origin_z_change())
        e_origin_z.bind("<FocusOut>", lambda ev: on_origin_z_change())
        
        tk.Label(f_origin_inputs, text="mm").pack(side="left", padx=2)
        
        # Axis Direction Inversion
        f_invert = ttk.Frame(f_coords)
        f_invert.pack(fill="x", padx=5, pady=5)
        
        var_invert_x = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_x", False)))
        def on_invert_x_toggle(): self.app.on_param_change("machine_invert_x", var_invert_x.get(), "none")
        ttk.Checkbutton(f_invert, text="Invert X Axis (+↔-)", variable=var_invert_x, command=on_invert_x_toggle).pack(side="left", padx=5)
        
        var_invert_z = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_z", False)))
        def on_invert_z_toggle(): self.app.on_param_change("machine_invert_z", var_invert_z.get(), "none")
        ttk.Checkbutton(f_invert, text="Invert Z Axis (+↔-)", variable=var_invert_z, command=on_invert_z_toggle).pack(side="left", padx=5)
        
        # Output Mode (Radius/Diameter)
        f_output_mode = ttk.LabelFrame(self.content, text="Output Mode")
        f_output_mode.pack(fill="x", padx=10, pady=10)
        
        var_output_mode = tk.StringVar(value=self.app.params.get("output_mode", "diameter"))
        def on_output_mode_change(): self.app.on_param_change("output_mode", var_output_mode.get(), "none")
        
        ttk.Radiobutton(f_output_mode, text="Diameter", variable=var_output_mode, value="diameter", command=on_output_mode_change).pack(anchor="w", padx=5, pady=2)
        ttk.Radiobutton(f_output_mode, text="Radius", variable=var_output_mode, value="radius", command=on_output_mode_change).pack(anchor="w", padx=5, pady=2)

        # Additional Work Offsets (G54)
        f_offsets = ttk.LabelFrame(self.content, text="Additional Work Offsets (G54)")
        f_offsets.pack(fill="x", padx=10, pady=10)
        
        def add_offset_spinbox(p, key, title):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = self.app.params.get(key, 0.0)
            
            var = tk.DoubleVar(value=val)
            def on_change(): 
                try: self.app.on_param_change(key, var.get(), "none")
                except: pass
            
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            
        add_offset_spinbox(f_offsets, "machine_gcode_offset_x", "X Offset (mm)")
        add_offset_spinbox(f_offsets, "machine_gcode_offset_z", "Z Offset (mm)")

        # Safety & Limits
        f_safety = ttk.LabelFrame(self.content, text="Safety & Limits")
        f_safety.pack(fill="x", padx=10, pady=10)
        
        def add_int_entry(p, key, title):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = int(self.app.params.get(key, 1))
            
            var = tk.IntVar(value=val)
            def on_change(): 
                try: self.app.on_param_change(key, var.get(), "none")
                except: pass
            
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            
        add_int_entry(f_safety, "max_spin_rpm", "Max Spin (RPM):")

        # --- Safety Settings ---
        f_home = ttk.LabelFrame(self.content, text="Safety Settings (Home / Retract)")
        f_home.pack(fill="x", padx=10, pady=5)
        
        def add_home_spinbox(p, key, title, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            # Default fallback
            if "retract" in key: val_def = 50.0
            elif "x" in key: val_def = 300.0
            else: val_def = 150.0
            
            val = self.app.params.get(key, val_def)
            
            var = tk.DoubleVar(value=val)
            def on_change(): 
                try: self.app.on_param_change(key, var.get(), "paths") 
                except: pass
            
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            # Bind Tooltip
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)
            
        add_home_spinbox(f_home, "home_z", "Safe Z (Home):", "Absolute Z position for Machine Home (Tool Change).")
        add_home_spinbox(f_home, "home_x", "Safe X (Home):", "Absolute X position for Machine Home (Tool Change).")
        add_home_spinbox(f_home, "retract_x", "Pass Retract X (Rel):", "Relative X offset (UP) to move after each pass.")
        add_home_spinbox(f_home, "retract_z", "Pass Retract Z (Rel):", "Relative Z offset (BACK) to move after each pass.")
        
        # Helper to create label+text area
        def add_text_area(p, title, key, height=4):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=10, pady=5)
            lbl = tk.Label(f, text=title, font=("Arial", 9, "bold"), anchor="w")
            lbl.pack(fill="x")
            
            txt = tk.Text(f, height=height, font=("Consolas", 9))
            txt.pack(fill="x")
            # Load initial value
            val = self.app.params.get(key, "")
            txt.insert("1.0", val)
            
            return txt

        self.txt_header = add_text_area(self.content, "G-Code Header", "gcode_header", height=6)
        self.txt_footer = add_text_area(self.content, "G-Code Footer", "gcode_footer", height=4)
        
        # --- Tool Change Section ---
        f_tc = ttk.LabelFrame(self.content, text="Tool Change")
        f_tc.pack(fill="x", padx=10, pady=10)
        
        # Checkbox for enable
        var_tc = tk.BooleanVar(value=bool(self.app.params.get("tool_change_active", False)))
        def on_tc_toggle(): self.app.on_param_change("tool_change_active", var_tc.get(), "none")
        ttk.Checkbutton(f_tc, text="Include M6 Commands in G-Code", variable=var_tc, command=on_tc_toggle).pack(anchor="w", padx=5, pady=5)
        
        # Tool Numbers
        def add_str_entry(p, key, title):
             f = ttk.Frame(p)
             f.pack(fill="x", padx=5, pady=2)
             tk.Label(f, text=title, width=20, anchor="w").pack(side="left")
             val = self.app.params.get(key, "")
             e = ttk.Entry(f)
             e.insert(0, val)
             e.pack(side="right", expand=True, fill="x")
             def on_e_change(ev): self.app.on_param_change(key, e.get(), "none")
             e.bind("<KeyRelease>", on_e_change)
             e.bind("<Button-1>", lambda event: event.widget.focus_force())
             return e

        self.ent_rough_tool = add_str_entry(f_tc, "rough_tool_number", "Rough Tool No:")
        self.ent_finish_tool = add_str_entry(f_tc, "finish_tool_number", "Finish Tool No:")
        
        # Finish Radius
        def add_finish_r_spinbox(p, key, title):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = self.app.params.get(key, 0.0)
            
            var = tk.DoubleVar(value=val)
            def on_change(): 
                try: self.app.on_param_change(key, var.get(), "none")
                except: pass
            
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            
        add_finish_r_spinbox(f_tc, "finish_tool_radius", "Finish Tip R:")
        
        # Num Finish Passes
        def add_int_entry_finish(p, key, title):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = int(self.app.params.get(key, 1))
            var = tk.IntVar(value=val)
            def on_change(): 
                try: self.app.on_param_change(key, var.get(), "paths") 
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())

        add_int_entry_finish(f_tc, "num_finishing_passes", "Finish Pass Count:")

    def sync_params(self):
        # Manually sync text widgets to params
        if hasattr(self, 'txt_header'):
            self.app.params["gcode_header"] = self.txt_header.get("1.0", "end-1c")
        if hasattr(self, 'txt_footer'):
            self.app.params["gcode_footer"] = self.txt_footer.get("1.0", "end-1c")
        
        # Sync Entry fields too just in case KeyRelease missed something
        if hasattr(self, 'ent_rough_tool'):
            self.app.params["rough_tool_number"] = self.ent_rough_tool.get()
        if hasattr(self, 'ent_finish_tool'):
            self.app.params["finish_tool_number"] = self.ent_finish_tool.get()
            
    def refresh_ui(self):
        # Refresh all widgets from app.params
        # NOTE: Since we didn't store widget references in a dict, we have to rely on the closures? NO.
        # The closures use 'var' which is local.
        # Actually, standard Tkinter Vars (BooleanVar, etc) are objects. 
        # If we stored them, we could update them.
        # But we didn't store most of them in 'self'.
        # Solution: Re-create widgets? Too heavy.
        # Better: UIHelper should store references or we should have stored them.
        # Given current structure, simplest way is to destroy and recreate the content.
        for widget in self.content.winfo_children():
            widget.destroy()
        self._create_widgets()
        # This is fast enough for Tabs.

