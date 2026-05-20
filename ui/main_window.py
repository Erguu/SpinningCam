import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import logging
from PIL import Image, ImageTk
import sys
import os
import webbrowser
import json

from main import SpinningApp
from ui.helpers_ui import UIHelper
from ui.tabs.process_tab import ProcessTab
from ui.tabs.program_tab import ProgramTab
from ui.tabs.machine_tab import MachineTab
from ui.dialogs.tool_manager import ToolManager

logger = logging.getLogger("SpinningCam")

class SpinningCamWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EMS SoftSpinner V1.002")
        self.geometry("1400x900")
        
        # Load Icon
        try:
            self.iconbitmap("logo.ico") # If exists
        except: pass
        
        # Core App Logic
        self.app = SpinningApp(headless=True)
        
        # UI Setup
        self._setup_layout()
        
        # Hook: refresh Pass Info panel whenever paths are recalculated
        _orig_update_scene = self.app.update_scene
        def _hooked_update_scene(update_type="all", force_path_calc=False):
            _orig_update_scene(update_type, force_path_calc)
            if update_type in ("all", "paths", "shell_and_paths", "visual"):
                try:
                    self.ui_program.refresh_pass_info()
                except Exception:
                    pass
        self.app.update_scene = _hooked_update_scene

        # Load Tools
        self.tool_library = []
        self.load_tools()
        
        # Show Plotter (Create Window first)
        # Note: We must show it before embedding so HWND exists
        self.app.plotter.show(auto_close=False, interactive_update=True)
                
        # Ask for STEP File
        self.after(600, self.load_step_prompt)
        
        # Start Visual Loop
        self.check_sim_loop()
        
        # Menu
        self._create_menu()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Project", command=self.open_project_action)
        file_menu.add_command(label="Save Project As...", command=self.save_project_action)
        file_menu.add_separator()
        file_menu.add_command(label="Load Model (.STEP)", command=self.load_step_prompt)
        file_menu.add_separator()
        file_menu.add_command(label="Export Recipe for PLC (.csv)", command=self.export_recipe_action)
        file_menu.add_command(label="Export SCL for TIA Portal (.scl)", command=self.export_scl_action)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        
        # Tools Menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Tool Library...", command=self.open_tool_library) 
        
        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self.var_ontop_menu = tk.BooleanVar(value=True)
        def toggle_ontop_menu():
             self.attributes("-topmost", self.var_ontop_menu.get())
        view_menu.add_checkbutton(label="Always on Top", onvalue=True, offvalue=False, variable=self.var_ontop_menu, command=toggle_ontop_menu)
        view_menu.add_command(label="Reset Camera", command=lambda: self.app.plotter.reset_camera())
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "EMS SoftSpinner V1.002\n\nOptimized for 2-Axis CNC Spinning."))

    def open_project_action(self):
        path = filedialog.askopenfilename(filetypes=[("Spinning Project", "*.ssp"), ("All Files", "*.*")])
        if path:
             if self.app.load_project(path):
                 self.lbl_info.config(text=f"Loaded Project: {os.path.basename(path)}")
                 # Sync UI with loaded params
                 if hasattr(self, 'ui_machine'): self.ui_machine.refresh_ui()
                 if hasattr(self, 'ui_process'): self.ui_process.refresh_ui()
                 # Program tab generally updates via events or manual refresh, but we could add it if needed.
                 
                 messagebox.showinfo("Project Loaded", f"Project loaded successfully from:\n{os.path.basename(path)}")
    
    def save_project_action(self):
        # Sync all tabs first
        if hasattr(self, 'ui_machine'): self.ui_machine.sync_params()
        if hasattr(self, 'ui_process'): self.ui_process.sync_params() # If any
        if hasattr(self, 'ui_program'): self.ui_program._flush_entries()
        
        path = filedialog.asksaveasfilename(defaultextension=".ssp", filetypes=[("Spinning Project", "*.ssp")])
        if path:
            self.app.save_project(path)
            self.lbl_info.config(text=f"Saved Project: {os.path.basename(path)}")

    def open_tool_library(self):
        # We need to ensure we have a reference to the tool list, which we do via self.tool_library
        dlg = ToolManager(self, self) # Pass self as UI instance (has tool_library)
        self.wait_window(dlg)
        # After close, save changes?
        # ToolManager usually updates the list in-place.
        self.save_tools()

    def _setup_layout(self):
        # Sidebar (Left)
        self.sidebar = tk.Frame(self, width=350, bg="#f0f0f0", relief="raised", bd=2)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        self._init_logo()
        
        # Status Bar Area (Bottom of Sidebar? No, Bottom of Root)
        # But we want Sidebar to be full height left?
        # Layout: Sidebar LEFT, Plotter RIGHT.
        # Status Bar BOTTOM (spanning full width? or just Plotter?)
        # Step 2983 showed Status Bar packed BOTTOM of self (Root).
        # So it spans full width.
        
        frame_status = tk.Frame(self, bg="#333", height=30)
        frame_status.pack(side="bottom", fill="x")
        
        self.lbl_info = tk.Label(frame_status, text="Ready.", bg="#333", fg="#ddd", justify="left", anchor="w", font=("Consolas", 9))
        self.lbl_info.pack(side="left", fill="both", expand=True, padx=5)
        
        self.lbl_monitor = tk.Label(frame_status, text="--", bg="#333", fg="gold", justify="right", anchor="e", font=("Consolas", 10, "bold"))
        self.lbl_monitor.pack(side="right", padx=10)
        
        # UI Helper
        # We assume helpers will update lbl_info
        self.helper = UIHelper(self.lbl_info)
        
        # Tabs in Sidebar
        self.tabs = ttk.Notebook(self.sidebar)
        self.tabs.pack(fill="both", expand=True)
        
        # Process Tab
        self.tab_process = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_process, text="Process & Visual")
        self.ui_process = ProcessTab(self.tab_process, self.app, self, self.helper)
        
        # Program Tab
        self.tab_program = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_program, text="Program List")
        self.ui_program = ProgramTab(self.tab_program, self.app, self, self.helper)
        
        # Machine Tab
        self.tab_machine = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_machine, text="Machine Settings")
        self.ui_machine = MachineTab(self.tab_machine, self.app, self.helper)
        
        
        # Plotter Container
        self.plot_frame = tk.Frame(self, bg="white")
        self.plot_frame.pack(side="right", fill="both", expand=True)
        
        # Embed Logic
        self.after(200, self.embed_plotter)

    def embed_plotter(self, attempt=0):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            
            # Constants
            GWL_STYLE = -16
            WS_POPUP = 0x80000000
            WS_CHILD = 0x40000000
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            
            # 1. Find Window Handle (Robust Search)
            # Try FindWindowW first (Title based)
            hwnd_plotter = user32.FindWindowW(None, "SpinningCam3D")
            
            # Fallback to internal if not found (or if title changed)
            if not hwnd_plotter and hasattr(self.app.plotter, 'render_window'):
                 hwnd_plotter = self.app.plotter.render_window.GetGenericWindowId()
            
            # 2. Get Tkinter Parent Handle
            hwnd_parent = self.plot_frame.winfo_id()
            
            if not hwnd_plotter or not hwnd_parent:
                if attempt < 10:
                    # Retry in 200ms
                    logger.warning(f"Embedding retry {attempt+1}: Handles not ready (Plot: {hwnd_plotter}, Parent: {hwnd_parent})")
                    self.after(200, lambda: self.embed_plotter(attempt+1))
                    return
                else:
                    logger.error("Embedding Timeout: Could not find windows.")
                    tk.Label(self.plot_frame, text="Embedding Failed: Window not found.", fg="red").pack()
                    return

            # 3. Modify Style BEFORE Parent Change
            style = user32.GetWindowLongW(hwnd_plotter, GWL_STYLE)
            style = style & ~WS_POPUP # Remove Popup
            style = style & ~WS_CAPTION # Remove Title Bar
            style = style & ~WS_THICKFRAME # Remove Border
            style = style | WS_CHILD # Add Child
            user32.SetWindowLongW(hwnd_plotter, GWL_STYLE, style)

            # 4. Reparent
            # SetParent(child, parent)
            prev_parent = user32.SetParent(hwnd_plotter, hwnd_parent)
            if prev_parent == 0:
                 logger.warning(f"SetParent failed? Error: {ctypes.get_last_error()}")
            
            # 5. Bind Resize Logic
            def resize_plotter(event):
                w = event.width
                h = event.height
                if w > 1 and h > 1:
                    user32.MoveWindow(hwnd_plotter, 0, 0, w, h, True)
                    self.app.plotter.render()
                
            self.plot_frame.bind("<Configure>", resize_plotter)
            
            # Trigger initial resize
            self.update_idletasks()
            w = self.plot_frame.winfo_width()
            h = self.plot_frame.winfo_height()
            user32.MoveWindow(hwnd_plotter, 0, 0, w, h, True)
            
            logger.info(f"PyVista Window Embedded successfully (HWND: {hwnd_plotter} -> {hwnd_parent}).")
            
        except Exception as e:
            logger.error(f"Embedding Failed: {e}")
            tk.Label(self.plot_frame, text=f"Embedding Error: {e}", fg="red").pack()
        
    def _init_logo(self):
        try:
            if os.path.exists("logo.png"):
                img = Image.open("logo.png")
                # Resize
                base_width = 200
                w_percent = (base_width / float(img.size[0]))
                h_size = int((float(img.size[1]) * float(w_percent)))
                img = img.resize((base_width, h_size), Image.LANCZOS)
                
                self.logo_img = ImageTk.PhotoImage(img)
                lbl_logo = tk.Label(self.sidebar, image=self.logo_img) 
                lbl_logo.pack(side="top", pady=5)
                
                tk.Label(self.sidebar, text="V1.002", font=("Arial", 9, "bold"), fg="#555").place(relx=0.98, rely=0.01, anchor="ne")
        except: pass

    def check_sim_loop(self):
        if self.app.sim_controller.is_running:
            pos = self.app.sim_controller.current_pos
            rad = self.app.sim_controller.current_radius
            if pos is not None:
                self.app.update_roller_visual(pos, rad)
                try:
                    self.app.plotter.render()
                except: pass
                
                self._update_live_monitor(pos)
                
            self.after(20, self.check_sim_loop) # 50fps

    def _update_live_monitor(self, pos):
        if pos is None: return
        z_curr = pos[2]
        
        txt_s = "--"; txt_f = "--"; mode_s = ""; mode_f = ""
        
        ops = self.app.params.get("operations", [])
        matched = False
        
        for op in ops:
             if not op.get("enabled", True): continue
             def_s = float(op.get("speed", 0))
             def_f = float(op.get("feed", 0))
             zones = op.get("zones", [])
             
             for zdata in zones:
                 try:
                     sz = float(zdata.get("start_z")); ez = float(zdata.get("end_z"))
                     if min(sz, ez) <= z_curr <= max(sz, ez):
                          txt_s = str(int(float(zdata.get("speed", def_s))))
                          txt_f = f"{float(zdata.get('feed', def_f)):.1f}"
                          mode_s = op.get("speed_mode", "CSS")
                          mode_f = op.get("feed_mode", "mm_min")
                          matched = True
                          break
                 except: pass
             if matched: break
             
        p = self.app.params
        _ox = p.get("home_x", 0.0) if p.get("origin_use_home", False) else p.get("machine_origin_x", 0.0)
        _oz = p.get("home_z", 0.0) if p.get("origin_use_home", False) else p.get("machine_origin_z", 0.0)
        _dx = -1.0 if p.get("machine_invert_x", False) else 1.0
        _dz = -1.0 if p.get("machine_invert_z", False) else 1.0
        x_disp = ((pos[0] - _ox) * _dx) + p.get("machine_gcode_offset_x", 0.0)
        z_disp = ((pos[2] - _oz) * _dz) + p.get("machine_gcode_offset_z", 0.0)
        msg = f"POS: X{x_disp:.2f} Z{z_disp:.2f}"
        if matched and txt_s != "--":
            msg += f"  |  S: {txt_s} ({mode_s})  |  F: {txt_f} ({mode_f})"
        else:
            msg += "  |  (Transit/Default)"
            
        self.lbl_monitor.config(text=msg)

    def load_step_prompt(self):
        # Check if already loaded (e.g. from settings?)
        # SpinningApp loads settings but not step file automatically unless configured.
        path = filedialog.askopenfilename(
            title="Open STEP File Model",
            filetypes=[("STEP Files", "*.step;*.stp"), ("All Files", "*.*")]
        )
        if path:
            self.app.load_step_file(path)
            # Center view
            self.app.update_scene("all")
            # Force focus back to UI using Topmost trick
            self.attributes('-topmost', True)
            self.update()
            self.attributes('-topmost', False)
            self.lift()
            self.focus_force()
        else:
            # User cancelled, maybe load default dummy or warn?
            pass

    def run_sim(self):
        # Hook UI for updates? The loop handles it via polling.
        seq = getattr(self.app.path_gen, 'last_calculated_sequence', None)
        self.app.sim_controller.run(True, self.app.path_gen.last_calculated_paths, self.app.params, sequence=seq)
        self.check_sim_loop()

    def stop_sim(self):
        self.app.sim_controller.stop(True)

    def exit_btn(self):
        self.on_close()

    def on_close(self):
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        if hasattr(self, 'ui_program'):
            self.ui_program._flush_entries()
        self.app.save_settings_json()
        try: self.app.plotter.close()
        except: pass
        self.destroy()
        sys.exit()

    def load_tools(self):
        try:
            with open("tools.json", "r") as f:
                self.tool_library = json.load(f)
        except:
            self.tool_library = []
            
    def save_tools(self):
        with open("tools.json", "w") as f:
            json.dump(self.tool_library, f, indent=4)
            
    def save_gcode_logic(self):
        # Sync Params from Machine Tab first
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        if hasattr(self, 'ui_program'):
            self.ui_program._flush_entries()
            
        path = filedialog.asksaveasfilename(
             defaultextension=".nc",
             filetypes=[("G-Code", "*.nc"), ("All Files", "*.*")],
             title="Save G-Code",
             initialfile="EMS_Spinning.nc"
        )
        if path:
             self.app.save_gcode(True, filepath=path)
             if messagebox.askyesno("View G-Code", f"Saved: {os.path.basename(path)}\n\nOpen in NCViewer (Web)?"):
                 webbrowser.open("https://ncviewer.com/")
                 try: os.startfile(path)
                 except: pass

    def export_pdf_action(self):
        """Export operation sheet as PDF."""
        from export_manager import ExportManager
        
        # Sync params first
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
            title="Export Operation Sheet",
            initialfile="SpinningCam_OperationSheet.pdf"
        )
        if path:
            paths = self.app.path_gen.last_calculated_paths
            success = ExportManager.export_pdf(self.app.params, paths, path, self.tool_library)
            if success:
                messagebox.showinfo("Export Complete", f"PDF saved to:\n{os.path.basename(path)}")
                if messagebox.askyesno("Open PDF?", "Would you like to open the PDF now?"):
                    try: os.startfile(path)
                    except: pass
            else:
                messagebox.showerror("Export Error", "Failed to export PDF. Check log for details.")

    def export_stl_action(self):
        """Export part shell preview as STL."""
        from export_manager import ExportManager
        
        # Generate shell mesh from current mandrel + shell thickness
        shell_mesh = self.app.mandrel_mgr.generate_shell_mesh(
            self.app.params.get("shell_thickness", 0.0) + self.app.params.get("final_part_thickness_on_mandrel", 2.0),
            self.app.params.get("mandrel_pos_x_offset", 0.0)
        )
        
        if shell_mesh is None:
            messagebox.showwarning("No Mesh", "Cannot export STL: No shell mesh available.\nPlease load a model first.")
            return
        
        path = filedialog.asksaveasfilename(
            defaultextension=".stl",
            filetypes=[("STL Files", "*.stl"), ("All Files", "*.*")],
            title="Export Part Preview STL",
            initialfile="SpinningCam_PartPreview.stl"
        )
        if path:
            success = ExportManager.export_stl(shell_mesh, path)
            if success:
                messagebox.showinfo("Export Complete", f"STL saved to:\n{os.path.basename(path)}")
            else:
                messagebox.showerror("Export Error", "Failed to export STL. Check log for details.")

    def export_recipe_action(self):
        """
        Export G-code as PLC Recipe format.
        
        Converts the last saved or selected NC file to compact CSV recipe format
        for use with Siemens S7-1200 PLC. This format is more memory-efficient
        and eliminates string parsing overhead on the PLC.
        """
        from export_manager import ExportManager
        
        # Ask user for the source NC file
        nc_path = filedialog.askopenfilename(
            title="Select G-Code File to Convert",
            filetypes=[("G-Code Files", "*.nc"), ("All Files", "*.*")],
            initialdir=os.path.dirname(os.path.abspath("spinning_output.nc"))
        )
        
        if not nc_path:
            return
        
        # Ask for output CSV path
        default_name = os.path.splitext(os.path.basename(nc_path))[0] + "_recipe.csv"
        csv_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Recipe CSV", "*.csv"), ("All Files", "*.*")],
            title="Save PLC Recipe As",
            initialfile=default_name
        )
        
        if not csv_path:
            return
        
        # Convert
        success, stats = ExportManager.export_recipe(nc_path, csv_path)
        
        if success:
            # Show detailed statistics
            msg = (
                f"Recipe converted successfully!\n\n"
                f"📊 Statistics:\n"
                f"   Total Lines: {stats.get('total_lines', 0)}\n"
                f"   Rapid Moves (G0): {stats.get('rapid_moves', 0)}\n"
                f"   Linear Moves (G1): {stats.get('linear_moves', 0)}\n"
                f"   Tool Changes: {stats.get('tool_changes', 0)}\n\n"
                f"💾 Estimated PLC Memory: {stats.get('estimated_bytes', 0):,} bytes\n\n"
                f"File saved to:\n{os.path.basename(csv_path)}"
            )
            messagebox.showinfo("Recipe Export Complete", msg)
            
            # Offer to open the file
            if messagebox.askyesno("Open File?", "Would you like to open the recipe file?"):
                try:
                    os.startfile(csv_path)
                except:
                    pass
        else:
            messagebox.showerror("Export Error", "Failed to convert G-code to recipe format.\nCheck the log for details.")

    def export_scl_action(self):
        """
        Export G-code as SCL Data Block for TIA Portal.

        Generates G-code in-memory from current params and converts directly
        to SCL — no need to save a .nc file first.
        """
        from export_manager import ExportManager
        from tkinter import simpledialog

        # Sync machine tab text fields (header/footer) before generating
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()

        # Generate G-code string in-memory
        try:
            from recipe_to_scl import GCodeToSCLConverter
            gcode_str = self.app.path_gen.generate_gcode(params=self.app.params)
        except Exception as e:
            messagebox.showerror("Export Error", f"G-code generation failed:\n{e}")
            return

        # Pre-parse to get line count for the array size dialog
        try:
            _pre_converter = GCodeToSCLConverter()
            _pre_converter.parse_gcode(gcode_str)
            _parsed_line_count = len(_pre_converter.lines)
        except Exception:
            _parsed_line_count = None

        # Ask for Data Block name
        db_name = simpledialog.askstring(
            "Data Block Name",
            "Enter TIA Portal Data Block name:",
            initialvalue="DB_RecipeProgram1",
            parent=self
        )
        
        if not db_name:
            return
        
        # Ask for program title
        program_title = simpledialog.askstring(
            "Program Title",
            "Enter program title (for header comment):",
            initialvalue="SpinningCam Program",
            parent=self
        )
        
        if not program_title:
            program_title = "SpinningCam Program"

        # Ask user for recipe database array size
        if _parsed_line_count is not None:
            _default_array = max(_parsed_line_count, 1000)
            _array_size_str = simpledialog.askstring(
                "Reçete Database Boyutu",
                f"G-code analiz edildi: {_parsed_line_count} satır oluşturulacak.\n\n"
                f"PLC reçete database'i kaç elemanlı olsun?\n"
                f"(Minimum: {_parsed_line_count}, önerilen: {_default_array})",
                initialvalue=str(_default_array),
                parent=self
            )
            if _array_size_str is None:
                return
            try:
                custom_array_size = max(int(_array_size_str), _parsed_line_count)
            except ValueError:
                custom_array_size = _default_array
        else:
            custom_array_size = None

        # Ask for output SCL path
        default_name = db_name + ".scl"
        scl_path = filedialog.asksaveasfilename(
            defaultextension=".scl",
            filetypes=[("SCL Files", "*.scl"), ("All Files", "*.*")],
            title="Save SCL Data Block As",
            initialfile=default_name
        )
        
        if not scl_path:
            return
        
        # First attempt - check for limit
        success, stats = ExportManager.export_scl(
            scl_filepath=scl_path,
            db_name=db_name,
            program_title=program_title,
            force=False,
            params=self.app.params,
            custom_array_size=custom_array_size,
            gcode_string=gcode_str
        )
        
        # Check if limit exceeded
        if not success and stats.get('limit_exceeded'):
            actual = stats.get('actual_lines', 0)
            max_lines = stats.get('max_lines', 1000)
            
            # Ask user if they want to continue
            should_continue = messagebox.askyesno(
                "Line Limit Exceeded",
                f"⚠️ Recipe line limit aşıldı!\n\n"
                f"Mevcut satır sayısı: {actual}\n"
                f"Maksimum limit: {max_lines}\n"
                f"Aşım: {actual - max_lines} satır\n\n"
                f"PLC programı bu limiti aşan dosyaları\n"
                f"işleyemeyebilir.\n\n"
                f"Yine de devam etmek istiyor musunuz?",
                icon='warning'
            )
            
            if should_continue:
                # Retry with force=True
                success, stats = ExportManager.export_scl(
                    scl_filepath=scl_path,
                    db_name=db_name,
                    program_title=program_title,
                    force=True,
                    params=self.app.params,
                    custom_array_size=custom_array_size,
                    gcode_string=gcode_str
                )
            else:
                messagebox.showinfo("İptal", "SCL export işlemi iptal edildi.")
                return
        
        if success:
            # Show detailed statistics
            msg = (
                f"SCL Data Block generated successfully!\n\n"
                f"📦 Data Block: {stats.get('db_name', db_name)}\n\n"
                f"📊 Statistics:\n"
                f"   Total Lines: {stats.get('total_lines', 0)}\n"
                f"   Rapid Moves (G0): {stats.get('rapid_moves', 0)}\n"
                f"   Linear Moves (G1): {stats.get('linear_moves', 0)}\n"
                f"   Tool Changes: {stats.get('tool_changes', 0)}\n\n"
                f"💾 SCL File Size: {stats.get('scl_size_bytes', 0):,} bytes\n"
                f"💾 Est. PLC Memory: {stats.get('estimated_plc_bytes', 0):,} bytes\n\n"
                f"🛠️ TIA Portal Import:\n"
                f"   1. External Source Files → Add new\n"
                f"   2. Select this .scl file\n"
                f"   3. Right-click → Generate blocks"
            )
            messagebox.showinfo("SCL Export Complete", msg)
            
            # Offer to open the file location
            if messagebox.askyesno("Open File?", "Would you like to open the SCL file?"):
                try:
                    os.startfile(scl_path)
                except:
                    pass
        else:
            messagebox.showerror("Export Error", "Failed to convert G-code to SCL format.\nCheck the log for details.")
