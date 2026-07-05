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
import i18n
from i18n import t, set_language, get_language, LANGUAGES, LANGUAGE_NAMES

logger = logging.getLogger("SpinningCam")

class SpinningCamWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("1400x900")

        try:
            self.iconbitmap("logo.ico")
        except: pass

        self.app = SpinningApp(headless=True)
        self.title(f"EMS SoftSpinner V{self.app.params.get('app_version', '?')}")

        # Load saved language before building UI
        saved_lang = self.app.params.get("language", "EN")
        set_language(saved_lang)

        self._machine_ready = False
        self._load_machine_profile()
        if not self._machine_ready:
            return

        self._setup_layout()

        _orig_update_scene = self.app.update_scene
        def _hooked_update_scene(update_type="all", force_path_calc=False, **kwargs):
            _orig_update_scene(update_type, force_path_calc, **kwargs)
            if update_type in ("all", "paths", "shell_and_paths", "visual"):
                try:
                    self.ui_program.refresh_pass_info()
                    # Keep the "Real End Z" column in sync with fresh toolpaths
                    # (updates rows in place; selection is preserved).
                    self.ui_program.refresh_ops_tree()
                except Exception:
                    pass
        self.app.update_scene = _hooked_update_scene

        self.tool_library = []
        self.load_tools()

        self.app.plotter.show(auto_close=False, interactive_update=True)

        self.after(600, self.load_step_prompt)
        self.check_sim_loop()
        self._create_menu()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File Menu
        self._file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_file"), menu=self._file_menu)
        self._file_menu.add_command(label=t("menu_open_project"), command=self.open_project_action)
        self._file_menu.add_command(label=t("menu_save_project"), command=self.save_project_action)
        self._file_menu.add_separator()
        self._file_menu.add_command(label=t("menu_load_model"), command=self.load_step_prompt)
        self._file_menu.add_separator()
        # Machine-type-specific exports: the Siemens SCL / recipe pipeline only
        # applies to machines whose adapter lists those formats (ID111). The
        # ID112 CODESYS machine gets its own post-processor later (TODO.md #52).
        adapter = getattr(self.app, "active_adapter", None)
        formats = adapter.get_export_formats() if adapter else ["scl", "recipe_csv"]
        if "recipe_csv" in formats:
            self._file_menu.add_command(label=t("menu_export_recipe"), command=self.export_recipe_action)
        if "scl" in formats:
            self._file_menu.add_command(label=t("menu_export_scl"), command=self.export_scl_action)
        self._file_menu.add_separator()
        self._file_menu.add_command(label=t("menu_exit"), command=self.on_close)

        # Tools Menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_tools"), menu=tools_menu)
        tools_menu.add_command(label=t("menu_tool_library"), command=self.open_tool_library)

        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_view"), menu=view_menu)
        self.var_ontop_menu = tk.BooleanVar(value=True)
        def toggle_ontop_menu():
             self.attributes("-topmost", self.var_ontop_menu.get())
        view_menu.add_checkbutton(label=t("menu_always_on_top"), onvalue=True, offvalue=False,
                                  variable=self.var_ontop_menu, command=toggle_ontop_menu)
        view_menu.add_command(label=t("menu_reset_camera"), command=lambda: self.app.plotter.reset_camera())

        # Language Menu
        lang_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_language"), menu=lang_menu)
        self._lang_var = tk.StringVar(value=get_language())
        for code in LANGUAGES:
            lang_menu.add_radiobutton(
                label=LANGUAGE_NAMES[code],
                value=code,
                variable=self._lang_var,
                command=lambda c=code: self._change_language(c)
            )

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_help"), menu=help_menu)
        def _open_user_guide():
            from ui.dialogs.help_window import HelpWindow
            HelpWindow(self)
        help_menu.add_command(label=t("menu_user_guide"), command=_open_user_guide)
        help_menu.add_separator()
        help_menu.add_command(label=t("menu_about"), command=lambda: messagebox.showinfo(
            t("menu_about"), t("about_text")))

    def _change_language(self, lang: str):
        set_language(lang)
        self.app.params["language"] = lang
        self.app.save_settings_json()
        # Rebuild menu and all tabs
        self._create_menu()
        self.rebuild_all_tabs()

    def rebuild_all_tabs(self):
        """Rebuild all tab labels and content for the active language."""
        # Update tab titles
        self.tabs.tab(self.tab_process, text=t("tab_process"))
        self.tabs.tab(self.tab_program, text=t("tab_program"))
        self.tabs.tab(self.tab_machine, text=t("tab_machine"))

        # Rebuild tab content
        if hasattr(self, 'ui_process'):
            self.ui_process.rebuild()
        if hasattr(self, 'ui_machine'):
            self.ui_machine.refresh_ui()
        if hasattr(self, 'ui_program'):
            self.ui_program.rebuild()

        # Status bar
        self.lbl_info.config(text=t("status_ready"))

    def open_project_action(self):
        path = filedialog.askopenfilename(
            title=t("fd_open_project"),
            filetypes=[(t("fd_spinning_project"), "*.ssp"), (t("fd_all_files"), "*.*")]
        )
        if path:
             if self.app.load_project(path):
                 self.lbl_info.config(text=f"Loaded Project: {os.path.basename(path)}")
                 if hasattr(self, 'ui_machine'): self.ui_machine.refresh_ui()
                 if hasattr(self, 'ui_process'): self.ui_process.refresh_ui()
                 if hasattr(self, 'ui_program'):
                     self.ui_program.refresh_ops_tree()
                     self.ui_program.refresh_pass_info()
                 messagebox.showinfo(t("msg_project_loaded_title"),
                                     t("msg_project_loaded").format(os.path.basename(path)))

    def save_project_action(self):
        if hasattr(self, 'ui_machine'): self.ui_machine.sync_params()
        if hasattr(self, 'ui_process'): self.ui_process.sync_params()
        if hasattr(self, 'ui_program'): self.ui_program._flush_entries()

        path = filedialog.asksaveasfilename(
            title=t("fd_save_project"),
            defaultextension=".ssp",
            filetypes=[(t("fd_spinning_project"), "*.ssp")]
        )
        if path:
            self.app.save_project(path)
            self.lbl_info.config(text=f"Saved Project: {os.path.basename(path)}")

    def open_tool_library(self):
        dlg = ToolManager(self, self)
        self.wait_window(dlg)
        self.save_tools()

    def refresh_clamp_status(self):
        """Surface the clamp-zone advisory (#62) after a path calculation. Reads
        path_gen.last_clamp_warnings (set by calculate_paths). Always updates the
        status bar (amber persistent indicator). ALSO pops a modal warning with
        Confirm / Don't-show-again buttons, unless the operator suppressed it this
        session. Called from both the async poller and the synchronous Calculate
        button so it fires whichever path the user takes."""
        try:
            cw = getattr(self.app.path_gen, "last_clamp_warnings", None) or []
            # Persistent status-bar indicator
            if cw:
                self.lbl_info.config(
                    text=t("status_clamp_warn").format(n=len(cw), idx=cw[0]["op_index"] + 1),
                    fg="#ffb020")
            else:
                self.lbl_info.config(text=t("status_ready"), fg="#ddd")

            # Modal popup (unless suppressed for the session via "Don't show again")
            if cw and not getattr(self, "_clamp_popup_suppressed", False):
                top = cw[0]["clamp_top_z"]
                ops = "\n".join(
                    "  • " + t("msg_clamp_warn_op").format(
                        idx=w["op_index"] + 1, type=w["op_type"], sz=round(w["start_z"], 1))
                    for w in cw)
                self._show_clamp_popup(
                    t("msg_clamp_warn_body").format(n=len(cw), top=round(top, 1), ops=ops))
        except Exception:
            pass

    def _show_clamp_popup(self, body):
        """Modal clamp-zone warning with two buttons: Confirm (acknowledge, may reappear
        next calc) and Don't show again (suppress for the rest of this session; the amber
        status bar stays as the persistent cue). Session-only by design — a safety cue
        should re-alert on the next app launch."""
        win = tk.Toplevel(self)
        win.title(t("msg_clamp_warn_title"))
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text="⚠", font=("Arial", 20), fg="#d08000").pack(anchor="w")
        tk.Label(frm, text=body, justify="left", wraplength=460).pack(anchor="w", pady=(4, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))

        def _dont_show():
            self._clamp_popup_suppressed = True
            win.destroy()

        ttk.Button(btns, text=t("btn_dont_show_again"), command=_dont_show).pack(side="left")
        ttk.Button(btns, text=t("btn_confirm"), command=win.destroy).pack(side="right")
        win.grab_set()
        win.update_idletasks()
        try:  # center over the main window
            x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        self.wait_window(win)

    def _load_machine_profile(self):
        from machine_loader import list_machine_profiles, migrate_from_settings, get_unique_types
        from machine_adapter import get_adapter
        from ui.dialogs.machine_selector import MachineSelector

        base_path = self.app.get_base_path()
        if not list_machine_profiles(base_path):
            migrate_from_settings(self.app.params, base_path)

        type_list = get_unique_types(base_path)

        saved_lic_path      = self.app.params.get("_last_license_path", "")
        saved_settings_path = self.app.params.get("_last_settings_path", "")

        self.withdraw()
        sel = MachineSelector(self, type_list, base_path,
                              saved_license_path=saved_lic_path,
                              saved_settings_path=saved_settings_path)
        self.wait_window(sel)
        self.deiconify()
        if sel.result is None:
            self.destroy()
            return

        result   = sel.result
        profile  = result["profile"]
        license_ = result["license"]
        settings = result["settings"]

        # Optional customer settings applied first; machine profile overrides last
        if settings:
            from machine_loader import MACHINE_PROFILE_KEYS
            _mkeys = set(MACHINE_PROFILE_KEYS) | {"machine_id", "machine_name"}
            # Exclude underscore-prefixed keys — those are internal session state and
            # must not be carried over from a customer settings file (they would
            # overwrite _last_license_path / _last_settings_path with stale paths).
            clean = {k: v for k, v in settings.items()
                     if k not in _mkeys and not k.startswith("_")}
            self.app.params.update(clean)

        self.app.params.update(profile)
        self.app.params["_customer_name"] = license_.get("customer_name", "")
        self.app.params["_admin"]         = license_.get("admin", False)

        # Persist paths AFTER all param updates so customer settings cannot
        # overwrite them in memory before the first save.
        self.app.params["_last_license_path"]  = result.get("license_path", "")
        self.app.params["_last_settings_path"] = result.get("settings_path", "")
        self.app.save_settings_json()

        self.app.active_machine_profile = profile
        self.app.active_adapter = get_adapter(profile["machine_id"])

        # Machine types may use a different path generator (tilt-arm kinematics
        # later gets its own class — TODO.md #50). Swap only when the adapter
        # returns a different class, so machine #1 keeps the pre-built instance.
        gen_cls = self.app.active_adapter.get_path_generator_class()
        if gen_cls is not None and not isinstance(self.app.path_gen, gen_cls):
            self.app.path_gen = gen_cls()

        self._machine_ready = True

    def _setup_layout(self):
        frame_header = tk.Frame(self, bg="#222222", height=26)
        frame_header.pack(side="top", fill="x")
        frame_header.pack_propagate(False)
        tk.Label(frame_header, text="EMS SoftSpinner", bg="#222222", fg="#aaaaaa",
                 font=("Arial", 9)).pack(side="left", padx=10)
        tk.Label(frame_header, text=f"v{self.app.params.get('app_version', '?')}", bg="#222222", fg="#ffffff",
                 font=("Arial", 10, "bold")).pack(side="right", padx=12)

        # Status bar packed BEFORE the paned area so the pane gets the rest.
        # pack_propagate(False) LOCKS the height at 30px: multi-line tooltip
        # text set into lbl_info can no longer grow this bar and steal vertical
        # space from the paned area above it (which would make the sidebar jump
        # under the cursor every time a hint changed line-count).
        frame_status = tk.Frame(self, bg="#333", height=30)
        frame_status.pack(side="bottom", fill="x")
        frame_status.pack_propagate(False)

        self.lbl_info = tk.Label(frame_status, text=t("status_ready"), bg="#333", fg="#ddd",
                                  justify="left", anchor="w", font=("Consolas", 9))
        self.lbl_info.pack(side="left", fill="both", expand=True, padx=5)

        self.lbl_monitor = tk.Label(frame_status, text="--", bg="#333", fg="gold",
                                     justify="right", anchor="e", font=("Consolas", 10, "bold"))
        self.lbl_monitor.pack(side="right", padx=10)

        self.helper = UIHelper(self.lbl_info)

        # Sidebar | 3D view divider is draggable (PanedWindow sash). The
        # embedded PyVista window already follows plot_frame <Configure>
        # events (see embed_plotter), so sash drags resize it safely.
        self._paned = tk.PanedWindow(self, orient="horizontal", sashwidth=6,
                                     sashrelief="raised", bd=0, bg="#c9c9c9")
        self._paned.pack(side="left", fill="both", expand=True)

        self.sidebar = tk.Frame(self._paned, bg="#f0f0f0", relief="raised", bd=2)
        _sb_w = 350
        try:
            _sb_w = max(280, int(self.app.params.get("sidebar_width", 350)))
        except (TypeError, ValueError):
            pass
        self._paned.add(self.sidebar, width=_sb_w, minsize=280)

        self._init_logo()

        self.tabs = ttk.Notebook(self.sidebar)
        self.tabs.pack(fill="both", expand=True)

        self.tab_process = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_process, text=t("tab_process"))
        self.ui_process = ProcessTab(self.tab_process, self.app, self, self.helper)

        self.tab_program = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_program, text=t("tab_program"))
        self.ui_program = ProgramTab(self.tab_program, self.app, self, self.helper)

        self.tab_machine = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_machine, text=t("tab_machine"))
        self.ui_machine = MachineTab(self.tab_machine, self.app, self.helper)

        self.plot_frame = tk.Frame(self._paned, bg="white")
        self._paned.add(self.plot_frame, minsize=300)

        # Persist the chosen sidebar width when the sash drag ends.
        def _save_sidebar_width(event=None):
            try:
                w = self.sidebar.winfo_width()
                if w > 50 and w != int(self.app.params.get("sidebar_width", 350)):
                    self.app.params["sidebar_width"] = w
                    self.app.save_settings_json()
            except Exception:
                pass
        self._paned.bind("<ButtonRelease-1>", _save_sidebar_width)

        self.after(200, self.embed_plotter)

    def embed_plotter(self, attempt=0):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            GWL_STYLE = -16
            WS_POPUP = 0x80000000
            WS_CHILD = 0x40000000
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000

            hwnd_plotter = user32.FindWindowW(None, "SpinningCam3D")

            if not hwnd_plotter and hasattr(self.app.plotter, 'render_window'):
                 hwnd_plotter = self.app.plotter.render_window.GetGenericWindowId()

            hwnd_parent = self.plot_frame.winfo_id()

            if not hwnd_plotter or not hwnd_parent:
                if attempt < 10:
                    logger.warning(f"Embedding retry {attempt+1}: Handles not ready (Plot: {hwnd_plotter}, Parent: {hwnd_parent})")
                    self.after(200, lambda: self.embed_plotter(attempt+1))
                    return
                else:
                    logger.error("Embedding Timeout: Could not find windows.")
                    tk.Label(self.plot_frame, text="Embedding Failed: Window not found.", fg="red").pack()
                    return

            style = user32.GetWindowLongW(hwnd_plotter, GWL_STYLE)
            style = style & ~WS_POPUP
            style = style & ~WS_CAPTION
            style = style & ~WS_THICKFRAME
            style = style | WS_CHILD
            user32.SetWindowLongW(hwnd_plotter, GWL_STYLE, style)

            prev_parent = user32.SetParent(hwnd_plotter, hwnd_parent)
            if prev_parent == 0:
                 logger.warning(f"SetParent failed? Error: {ctypes.get_last_error()}")

            def resize_plotter(event):
                w = event.width
                h = event.height
                if w > 1 and h > 1:
                    user32.MoveWindow(hwnd_plotter, 0, 0, w, h, True)
                    self.app.plotter.render()

            self.plot_frame.bind("<Configure>", resize_plotter)

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
                base_width = 200
                w_percent = (base_width / float(img.size[0]))
                h_size = int((float(img.size[1]) * float(w_percent)))
                img = img.resize((base_width, h_size), Image.LANCZOS)

                self.logo_img = ImageTk.PhotoImage(img)
                lbl_logo = tk.Label(self.sidebar, image=self.logo_img)
                lbl_logo.pack(side="top", pady=5)

                tk.Label(self.sidebar, text=f"V{self.app.params.get('app_version', '?')}", font=("Arial", 9, "bold"), fg="#555").place(relx=0.98, rely=0.01, anchor="ne")
        except: pass

    def _set_sim_lines_visibility(self, visible: bool):
        v = 1 if visible else 0
        for key in ("pass_dist_lines", "analysis_lines"):
            for actor in self.app.actors.get(key, []):
                try: actor.SetVisibility(v)
                except: pass
        self._sim_lines_hidden = not visible

    def check_sim_loop(self):
        if self.app.sim_controller.is_running:
            if not getattr(self, "_sim_lines_hidden", False):
                self._set_sim_lines_visibility(False)

            pos = self.app.sim_controller.current_pos
            rad = self.app.sim_controller.current_radius
            tilt = self.app.sim_controller.current_tilt
            if pos is not None:
                self.app.update_roller_visual(pos, rad, tilt_deg=tilt)
                try:
                    self.app.plotter.render()
                except: pass
                self._update_live_monitor(pos, tilt)

            try: self.ui_program.refresh_sim_controls()
            except: pass
            try: self.ui_process.refresh_sim_controls()
            except: pass

            self.after(20, self.check_sim_loop)
        else:
            if getattr(self, "_sim_lines_hidden", False):
                self._set_sim_lines_visibility(True)
                try: self.app.plotter.render()
                except: pass
            try: self.ui_program.refresh_sim_controls()
            except: pass
            try: self.ui_process.refresh_sim_controls()
            except: pass

    def _update_live_monitor(self, pos, tilt=None):
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
        if tilt is not None:
            msg += f" B{tilt:.1f}"
        if matched and txt_s != "--":
            msg += f"  |  S: {txt_s} ({mode_s})  |  F: {txt_f} ({mode_f})"
        else:
            msg += f"  |  {t('status_transit')}"

        self.lbl_monitor.config(text=msg)

    def load_step_prompt(self):
        path = filedialog.askopenfilename(
            title=t("fd_open_step"),
            filetypes=[(t("fd_step_files"), "*.step;*.stp"), (t("fd_all_files"), "*.*")]
        )
        if path:
            self.app.load_step_file(path)
            self.attributes('-topmost', True)
            self.update()
            self.attributes('-topmost', False)
            self.lift()
            self.focus_force()

    def run_sim(self):
        seq = getattr(self.app.path_gen, 'last_calculated_sequence', None)
        tilts = getattr(self.app.path_gen, 'last_tilt_angles', None)  # tilt-arm machines only
        self.app.sim_controller.run(True, self.app.path_gen.last_calculated_paths, self.app.params,
                                    sequence=seq, tilts=tilts)
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
        path = os.path.join(self.app.get_base_path(), "tools.json")
        try:
            with open(path, "r") as f:
                self.tool_library = json.load(f)
        except:
            self.tool_library = []
        self.app.tool_library = self.tool_library
        # tools.json is the single source of truth for r_tool; re-sync operations now
        # that the library is loaded (the "at settings load" case for the r_tool fix).
        try:
            self.app.sync_operation_r_tools()
        except Exception:
            pass

    def save_tools(self):
        path = os.path.join(self.app.get_base_path(), "tools.json")
        with open(path, "w") as f:
            json.dump(self.tool_library, f, indent=4)
        self.app.tool_library = self.tool_library
        self.app.tool_step_loader.invalidate()
        # tools.json is the single source of truth for r_tool; re-sync operations now
        # so an edited tool's reach propagates immediately instead of lagging one calc.
        try:
            self.app.sync_operation_r_tools()
        except Exception:
            pass

    def save_gcode_logic(self):
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        if hasattr(self, 'ui_program'):
            self.ui_program._flush_entries()

        if not getattr(self.app.path_gen, 'last_calculated_paths', None):
            messagebox.showwarning(t("msg_no_paths_title"), t("msg_no_paths"))
            return

        path = filedialog.asksaveasfilename(
             defaultextension=".nc",
             filetypes=[(t("fd_gcode_files"), "*.nc"), (t("fd_all_files"), "*.*")],
             title=t("fd_save_gcode"),
             initialfile="EMS_Spinning.nc"
        )
        if path:
             self.app.save_gcode(True, filepath=path)
             if messagebox.askyesno(t("msg_view_gcode_title"),
                                    t("msg_view_gcode").format(os.path.basename(path))):
                 webbrowser.open("https://ncviewer.com/")
                 try: os.startfile(path)
                 except: pass

    def export_pdf_action(self):
        from export_manager import ExportManager

        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[(t("fd_pdf_files"), "*.pdf"), (t("fd_all_files"), "*.*")],
            title=t("fd_export_pdf"),
            initialfile="SpinningCam_OperationSheet.pdf"
        )
        if path:
            paths = self.app.path_gen.last_calculated_paths
            success = ExportManager.export_pdf(self.app.params, paths, path, self.tool_library,
                                               mandrel_mgr=self.app.mandrel_mgr,
                                               tilt_angles=getattr(self.app.path_gen,
                                                                   "last_tilt_angles", None))
            if success:
                messagebox.showinfo(t("msg_export_complete_title"),
                                    t("msg_pdf_saved").format(os.path.basename(path)))
                if messagebox.askyesno(t("msg_open_pdf_title"), t("msg_open_pdf")):
                    try: os.startfile(path)
                    except: pass
            else:
                messagebox.showerror(t("msg_export_error_title"), t("msg_pdf_error"))

    def export_stl_action(self):
        from export_manager import ExportManager

        shell_mesh = self.app.mandrel_mgr.generate_shell_mesh(
            self.app.params.get("shell_thickness", 0.0) + self.app.params.get("final_part_thickness_on_mandrel", 2.0),
            self.app.params.get("mandrel_pos_x_offset", 0.0)
        )

        if shell_mesh is None:
            messagebox.showwarning(t("msg_no_mesh_title"), t("msg_no_mesh"))
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".stl",
            filetypes=[(t("fd_stl_files"), "*.stl"), (t("fd_all_files"), "*.*")],
            title=t("fd_export_stl"),
            initialfile="SpinningCam_PartPreview.stl"
        )
        if path:
            success = ExportManager.export_stl(shell_mesh, path)
            if success:
                messagebox.showinfo(t("msg_export_complete_title"),
                                    t("msg_stl_saved").format(os.path.basename(path)))
            else:
                messagebox.showerror(t("msg_export_error_title"), t("msg_stl_error"))

    def export_recipe_action(self):
        from export_manager import ExportManager

        nc_path = filedialog.askopenfilename(
            title=t("fd_select_nc"),
            filetypes=[(t("fd_nc_files"), "*.nc"), (t("fd_all_files"), "*.*")],
            initialdir=os.path.dirname(os.path.abspath("spinning_output.nc"))
        )

        if not nc_path:
            return

        default_name = os.path.splitext(os.path.basename(nc_path))[0] + "_recipe.csv"
        csv_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[(t("fd_csv_files"), "*.csv"), (t("fd_all_files"), "*.*")],
            title=t("fd_save_csv"),
            initialfile=default_name
        )

        if not csv_path:
            return

        success, stats = ExportManager.export_recipe(nc_path, csv_path)

        if success:
            msg = t("msg_recipe_success_body").format(
                total_lines=stats.get('total_lines', 0),
                rapid=stats.get('rapid_moves', 0),
                linear=stats.get('linear_moves', 0),
                tool_changes=stats.get('tool_changes', 0),
                mem_bytes=stats.get('estimated_bytes', 0),
                filename=os.path.basename(csv_path)
            )
            messagebox.showinfo(t("msg_recipe_complete_title"), msg)
            if messagebox.askyesno(t("msg_open_file_title"), t("msg_open_recipe_file")):
                try: os.startfile(csv_path)
                except: pass
        else:
            messagebox.showerror(t("msg_export_error_title"), t("msg_recipe_error"))

    def export_scl_action(self):
        from export_manager import ExportManager
        from tkinter import simpledialog

        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()

        try:
            from recipe_to_scl import GCodeToSCLConverter
            gcode_str = self.app.path_gen.generate_gcode(params=self.app.params)
        except Exception as e:
            messagebox.showerror(t("msg_export_error_title"), t("msg_gcode_gen_error").format(e))
            return

        try:
            _pre_converter = GCodeToSCLConverter()
            _pre_converter.parse_gcode(gcode_str)
            _parsed_line_count = len(_pre_converter.lines)
        except Exception:
            _parsed_line_count = None

        db_name = simpledialog.askstring(
            t("dlg_db_name_title"),
            t("dlg_db_name_prompt"),
            initialvalue="DB_RecipeProgram1",
            parent=self
        )
        if not db_name:
            return

        program_title = simpledialog.askstring(
            t("dlg_prog_title_title"),
            t("dlg_prog_title_prompt"),
            initialvalue="SpinningCam Program",
            parent=self
        )
        if not program_title:
            program_title = "SpinningCam Program"

        if _parsed_line_count is not None:
            _default_array = max(_parsed_line_count, 1000)
            _array_size_str = simpledialog.askstring(
                t("dlg_array_title"),
                t("dlg_array_prompt").format(_parsed_line_count, _parsed_line_count, _default_array),
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

        default_name = db_name + ".scl"
        scl_path = filedialog.asksaveasfilename(
            defaultextension=".scl",
            filetypes=[(t("fd_scl_files"), "*.scl"), (t("fd_all_files"), "*.*")],
            title=t("fd_save_scl"),
            initialfile=default_name
        )
        if not scl_path:
            return

        success, stats = ExportManager.export_scl(
            scl_filepath=scl_path,
            db_name=db_name,
            program_title=program_title,
            force=False,
            params=self.app.params,
            custom_array_size=custom_array_size,
            gcode_string=gcode_str
        )

        if not success and stats.get('limit_exceeded'):
            actual = stats.get('actual_lines', 0)
            max_lines = stats.get('max_lines', 1000)

            should_continue = messagebox.askyesno(
                t("msg_limit_exceeded_title"),
                t("msg_limit_exceeded").format(
                    actual=actual, max_l=max_lines, excess=actual - max_lines),
                icon='warning'
            )

            if should_continue:
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
                messagebox.showinfo(t("msg_cancelled_title"), t("msg_cancelled"))
                return

        if success:
            msg = t("msg_scl_success_body").format(
                db_name=stats.get('db_name', db_name),
                total_lines=stats.get('total_lines', 0),
                rapid=stats.get('rapid_moves', 0),
                linear=stats.get('linear_moves', 0),
                tool_changes=stats.get('tool_changes', 0),
                scl_bytes=stats.get('scl_size_bytes', 0),
                plc_bytes=stats.get('estimated_plc_bytes', 0)
            )
            messagebox.showinfo(t("msg_scl_complete_title"), msg)
            if messagebox.askyesno(t("msg_open_file_title"), t("msg_open_scl_file")):
                try: os.startfile(scl_path)
                except: pass
        else:
            messagebox.showerror(t("msg_export_error_title"), t("msg_scl_error"))
