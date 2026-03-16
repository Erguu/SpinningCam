import tkinter as tk
from tkinter import ttk
from ui.tabs.scrollable_tab_base import ScrollableTabBase


class ProcessTab(ScrollableTabBase):
    def __init__(self, parent_frame, app, ui_root, ui_helper):
        self.app = app
        self.root = ui_root
        self.helper = ui_helper
        
        # Initialize scrollable area from base class
        super().__init__(parent_frame)
        
        self._create_widgets()


    def _create_widgets(self):
        # --- Visual Settings ---
        self.helper.add_section_header(self.content, "Visual Settings", color="darkgreen")
        
        self.helper.add_checkbox(self.content, self.app, "calc_active", "Show Passes", "Toggle path visualization.")
        self.helper.add_checkbox(self.content, self.app, "velocity_color_mode", "Velocity Colors", "Color passes by feed rate (green=slow, red=fast).")
        self.helper.add_checkbox(self.content, self.app, "auto_calc_angle", "Auto-Calc Angle (Y)", "Automatically calculate Y-rotation relative to surface.")
        self.helper.add_checkbox(self.content, self.app, "show_heatmap", "Show Collision Heatmap", "Colorize path based on deviation from mandrel.")

        # Camera Controls
        f_cam = ttk.Frame(self.content)
        f_cam.pack(fill="x", padx=10, pady=5)
        
        def save_cam():
            if hasattr(self.app, 'plotter'):
                pos = self.app.plotter.camera.position
                foc = self.app.plotter.camera.focal_point
                up = self.app.plotter.camera.up
                self.app.params["camera"] = {"pos": pos, "foc": foc, "up": up}
                if hasattr(self.app, 'save_settings_json'):
                     self.app.save_settings_json()
                     tk.messagebox.showinfo("Camera Saved", "Camera angle saved to settings.json")
                
        def reset_cam():
            if hasattr(self.app, 'plotter'):
                saved = self.app.params.get("camera", {})
                if saved and "pos" in saved:
                    self.app.plotter.camera.position = saved["pos"]
                    self.app.plotter.camera.focal_point = saved["foc"]
                    self.app.plotter.camera.up = saved["up"]
                else:
                    self.app.plotter.camera_position = [(500, 500, 500), (0, 0, 0), (0, 0, 1)]
                self.app.plotter.reset_camera()
        
        self.helper.add_button(self.content, "Save Current Angle", save_cam, "lightgray", "Save current camera position as default.")
        self.helper.add_button(self.content, "Reset Camera", reset_cam, "lightgray", "Reset camera to default isometric view.")
        
        # Camera Presets (Lathe XZ orientation: Z=right, X=up)
        ttk.Label(self.content, text="Camera Presets:", font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(5,2))
        f_presets = ttk.Frame(self.content)
        f_presets.pack(fill="x", padx=10, pady=2)
        
        def set_view(direction):
            if not hasattr(self.app, 'plotter'): return
            # Distance from origin - Lathe orientation: X=up, Z=right(spindle), Y=into screen
            d = 400
            # Views: (camera_pos, focal_point, up_vector)
            # For lathe: looking from Y-axis toward XZ plane, with X pointing up
            views = {
                "front": [(0, d, 50), (0, 0, 50), (1, 0, 0)],     # Looking from +Y toward origin, X up
                "back": [(0, -d, 50), (0, 0, 50), (1, 0, 0)],     # Looking from -Y
                "left": [(-d, 0, 50), (0, 0, 50), (1, 0, 0)],     # Looking from -X (from below)
                "right": [(d, 0, 50), (0, 0, 50), (1, 0, 0)],     # Looking from +X (from above)
                "top": [(0, 0, d+50), (0, 0, 50), (0, 1, 0)],     # Looking down Z axis
                "iso": [(d, d, d), (0, 0, 50), (1, 0, 0)],        # Isometric
            }
            v = views.get(direction)
            if v:
                self.app.plotter.camera.position = v[0]
                self.app.plotter.camera.focal_point = v[1]
                self.app.plotter.camera.up = v[2]
                self.app.plotter.reset_camera()
        
        tk.Button(f_presets, text="Front", command=lambda: set_view("front"), width=6).pack(side="left", padx=1)
        tk.Button(f_presets, text="Back", command=lambda: set_view("back"), width=6).pack(side="left", padx=1)
        tk.Button(f_presets, text="Left", command=lambda: set_view("left"), width=6).pack(side="left", padx=1)
        tk.Button(f_presets, text="Right", command=lambda: set_view("right"), width=6).pack(side="left", padx=1)
        tk.Button(f_presets, text="Top", command=lambda: set_view("top"), width=6).pack(side="left", padx=1)
        tk.Button(f_presets, text="Iso", command=lambda: set_view("iso"), width=6, bg="lightblue").pack(side="left", padx=1)
        
        # Camera Rotation Buttons (around Y axis - vertical in view)
        ttk.Label(self.content, text="Rotate View:", font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(5,2))
        f_rotate = ttk.Frame(self.content)
        f_rotate.pack(fill="x", padx=10, pady=2)
        
        def rotate_view(angle):
            """Rotate camera around vertical axis using PyVista's azimuth."""
            if not hasattr(self.app, 'plotter'): return
            try:
                self.app.plotter.camera.azimuth += angle
                self.app.plotter.render()
            except Exception as e:
                print(f"Rotation error: {e}")
        
        tk.Button(f_rotate, text="◀ -45°", command=lambda: rotate_view(-45), width=7).pack(side="left", padx=2)
        tk.Button(f_rotate, text="+45° ▶", command=lambda: rotate_view(45), width=7).pack(side="left", padx=2)
        tk.Button(f_rotate, text="◀ -15°", command=lambda: rotate_view(-15), width=7).pack(side="left", padx=2)
        tk.Button(f_rotate, text="+15° ▶", command=lambda: rotate_view(15), width=7).pack(side="left", padx=2)
        
        # Fix Clipping Button (for invisible geometry bug)
        def fix_clipping():
            if hasattr(self.app, 'plotter'):
                self.app.plotter.reset_camera()
                # Set generous clipping range
                self.app.plotter.camera.clipping_range = (0.1, 10000)
                self.app.plotter.render()
                
        tk.Button(f_rotate, text="Fix View", command=fix_clipping, width=8, bg="yellow").pack(side="right", padx=2)


        # --- Safety & Correction Settings ---
        self.helper.add_section_header(self.content, "Safety & Correction", color="purple")
        self.helper.add_spinbox(self.content, self.app, "collision_resolution", "Collision Resolution (mm)", 0.1, 5.0, 0.5, "Step size for gouge detection.")
        self.helper.add_spinbox(self.content, self.app, "target_clearance", "Target Clearance (mm)", 0.0, 10.0, 0.5, "Minimum distance from mandrel surface to all pass points.")
        self.helper.add_checkbox(self.content, self.app, "show_analysis_lines", "Show Analysis Lines", "Visualize clearance at each point of every pass.")
        
        # --- Geometry Settings ---
        self.helper.add_section_header(self.content, "Geometry Settings", color="darkblue")
        
        self.helper.add_button(self.content, "LOAD MODEL (.STEP)", self.root.load_step_prompt, "orange", "Load a 3D model (STEP/STP).")
        
        self.helper.add_scale(self.content, self.app, "blank_radius", "Sheet Radius", 50, 500, "all", "Radius of the blank sheet materials.")
        self.helper.add_scale(self.content, self.app, "roller_visual_x_offset", "Roller X Pos", -200, 200, "none", "Visual initial X position of the roller.")
        self.helper.add_scale(self.content, self.app, "roller_visual_z_offset", "Roller Z Pos", -200, 200, "none", "Visual initial Z position of the roller.")
        
        self.helper.add_scale(self.content, self.app, "mandrel_pos_x_offset", "Mandrel X Offset", -500, 500, "all", "Shift Mandrel position in X.")
        self.helper.add_scale(self.content, self.app, "mandrel_pos_z_offset", "Mandrel Z Offset", -500, 500, "all", "Shift Mandrel position in Z.")
        
        # Mandrel Rotation
        f_rot = ttk.Frame(self.content)
        f_rot.pack(fill="x", padx=10, pady=5)
        ttk.Label(f_rot, text="Mandrel Rot:").pack(side="left")
        
        def rot_x(): self.app.rotate_mandrel('x')
        def rot_y(): self.app.rotate_mandrel('y')
        def rot_z(): self.app.rotate_mandrel('z')
        def reset_rot(): 
            self.app.params["mandrel_rot_x"] = 0.0
            self.app.params["mandrel_rot_y"] = 0.0
            self.app.params["mandrel_rot_z"] = 0.0
            self.app.update_scene("all")
        
        tk.Button(f_rot, text="X+90", command=rot_x, width=6).pack(side="left", padx=2)
        tk.Button(f_rot, text="Y+90", command=rot_y, width=6).pack(side="left", padx=2)
        tk.Button(f_rot, text="Z+90", command=rot_z, width=6).pack(side="left", padx=2)
        tk.Button(f_rot, text="RESET", command=reset_rot, bg="lightgray", width=8).pack(side="left", padx=2)
        
        self.helper.add_spinbox(self.content, self.app, "shell_thickness", "Shell Thickness", 0, 20, 0.1, "Thickness of the spun part shell.")
        self.helper.add_spinbox(self.content, self.app, "finish_step_radial", "Finish Radial Step (mm)", 0, 50, 2.0, "Radial offset for finishing.")

        # --- Actions ---
        self.helper.add_section_header(self.content, "Actions", color="darkblue")
        
        def force_calc():
             self.app.update_scene("paths", force_path_calc=True)
             self.root.ui_program.update_time_estimate()
             
        self.helper.add_button(self.content, "UPDATE / CALCULATE PATHS", force_calc, "orange", "Recalculate all toolpaths based on current settings.")
        
        self.helper.add_button(self.content, "Save G-Code", self.root.save_gcode_logic, "lightgreen", "Export toolpaths to .NC file.")
        self.helper.add_button(self.content, "Export PDF", self.root.export_pdf_action, "#4169E1", "Generate PDF operation sheet.")
        self.helper.add_button(self.content, "Export STL", self.root.export_stl_action, "#20B2AA", "Export shell mesh as STL.")
        
        # --- Simulation ---
        self.helper.add_section_header(self.content, "Simulation", color="darkblue")
        self.helper.add_button(self.content, "Run Simulation", self.root.run_sim, "cyan", "Start real-time simulation.")
        self.helper.add_button(self.content, "Stop Simulation", self.root.stop_sim, "red", "Stop simulation.")
        
        # --- EXIT at very bottom ---
        ttk.Separator(self.content, orient="horizontal").pack(fill="x", pady=10)
        self.helper.add_button(self.content, "EXIT APPLICATION", self.root.exit_btn, "darkred", "Close application.")

    def sync_params(self):
        # Optional: if we had manual entry fields that need saving back to params
        pass
