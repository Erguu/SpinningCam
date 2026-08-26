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
from version import APP_VERSION

logger = logging.getLogger("SpinningCam")


def _enable_windows_dpi_awareness():
    """Render at the monitor's native resolution instead of being bitmap-
    stretched (blurry) by Windows on high-DPI / scaled laptops. Must run before
    the Tk root is realized. Tries per-monitor awareness, then the legacy
    system-aware API; every failure is non-fatal (non-Windows, or already set by
    an app manifest)."""
    try:
        from ctypes import windll
    except Exception:
        return
    for _attempt in (
        lambda: windll.shcore.SetProcessDpiAwareness(2),   # per-monitor aware
        lambda: windll.user32.SetProcessDPIAware(),         # legacy system-aware
    ):
        try:
            _attempt()
            return
        except Exception:
            continue


class SpinningCamWindow(tk.Tk):
    def __init__(self):
        _enable_windows_dpi_awareness()
        super().__init__()

        # Match Tk's point->pixel scaling to the real device DPI so text stays
        # legible (doesn't shrink) now that we render at native resolution. On a
        # standard 96-DPI display this resolves to ~1.333, i.e. a no-op.
        try:
            _dpi = self.winfo_fpixels("1i")
            if _dpi and _dpi > 0:
                self.tk.call("tk", "scaling", _dpi / 72.0)
        except Exception:
            pass

        # Size to the actual monitor. The clamped geometry is the *restore* size
        # (so un-maximizing never lands the window off a small screen); state
        # 'zoomed' then fills the work area, respecting the taskbar. minsize keeps
        # the sidebar / toolbar (Undo-Redo etc.) reachable on any resolution.
        try:
            _sw, _sh = self.winfo_screenwidth(), self.winfo_screenheight()
            _w, _h = min(1400, _sw - 80), min(900, _sh - 120)
            _x, _y = max(0, (_sw - _w) // 2), max(0, (_sh - _h) // 2 - 20)
            self.geometry(f"{_w}x{_h}+{_x}+{_y}")
        except Exception:
            self.geometry("1400x900")
        self.minsize(1000, 640)
        try:
            self.state("zoomed")
        except Exception:
            pass

        try:
            self.iconbitmap("logo.ico")
        except: pass

        self.app = SpinningApp(headless=True)
        self.title(f"SoftSpinner V{APP_VERSION}")

        # First-run seeding (Phase 2 pull-collision fix): create the runtime-owned data
        # files (tools.json + machines/*.json) from their tracked .default seeds if they
        # are missing. Must run BEFORE _load_machine_profile / load_tools so a fresh clone
        # or exe finds its machines and tools; existing live files are never overwritten.
        try:
            import first_run_seed
            first_run_seed.seed_all(self.app.get_base_path())
        except Exception:
            pass

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

        self._bind_camera_preset_keys()

        self.after(600, self._startup_tasks)
        self.check_sim_loop()
        self._create_menu()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Re-assert the maximized state AFTER the PyVista window is shown and
        # Win32-embedded (embed_plotter, after 200 ms) — that reparenting
        # silently drops the initial zoom on some setups, so the window would
        # open at the restore size instead of maximized.
        self.after(250, self._reassert_zoom)
        self.after(900, self._reassert_zoom)

    def _reassert_zoom(self):
        """Force the window back to maximized if it isn't already (called a
        couple of times shortly after startup; see __init__)."""
        try:
            if self.state() != "zoomed":
                self.state("zoomed")
        except Exception:
            pass

    def _bind_camera_preset_keys(self):
        """Number keys 1-9 jump to saved camera views (Process tab → Saved Views,
        listed 1., 2., …). Bound BOTH on the Tk toplevel — so it works when focus
        is in the control panel, while ignoring keystrokes typed into an entry —
        and on the VTK render window, so it also works when the 3D view has focus.
        Numpad digits require NumLock ON (keysym KP_1…KP_9). Visual only."""
        _TEXT = ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox")

        def _make_tk(idx):
            def _cb(event):
                try:
                    if event.widget.winfo_class() in _TEXT:
                        return  # user is typing a number into a field
                except Exception:
                    pass
                self.app.apply_camera_preset(idx)
            return _cb

        for n in range(1, 10):
            tk_cb = _make_tk(n - 1)
            self.bind(f"<Key-{n}>", tk_cb)
            self.bind(f"<KP_{n}>", tk_cb)

        # 3D-view (VTK) focus: a single KeyPressEvent observer reads the pressed
        # digit straight off the interactor. This covers both the main number row
        # and the numpad, and avoids pyvista.add_key_event (which rejects callbacks
        # that take arguments and only matches one exact keysym per registration).
        try:
            self.app.plotter.iren.add_observer("KeyPressEvent", self._on_vtk_key)
        except Exception:
            pass

    def _on_vtk_key(self, *args):
        """VTK KeyPressEvent handler: number keys 1-9 jump to saved camera views.
        Reads GetKeyCode (the typed char, '1'..'9' for both main row and numpad
        with NumLock) with a GetKeySym fallback for KP_/digit keysyms."""
        try:
            vi = self.app.plotter.iren.interactor
            code = vi.GetKeyCode() or ""
            sym = vi.GetKeySym() or ""
        except Exception:
            return
        idx = None
        if len(code) == 1 and code in "123456789":
            idx = int(code) - 1
        elif sym[:3] == "KP_" and sym[3:].isdigit():
            idx = int(sym[3:]) - 1
        elif sym.isdigit():
            idx = int(sym) - 1
        if idx is not None:
            self.app.apply_camera_preset(idx)

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
        self._file_menu.add_command(label=t("menu_exit"), command=self.on_close)

        # Export Menu — every "produce a file for someone else" action in one
        # place. These were split between the File menu (SCL / recipe CSV) and
        # buttons at the bottom of the Process tab (G-code / PDF / STL), so
        # which menu to look in depended on the format.
        # Machine-type gating unchanged: the Siemens SCL / recipe pipeline only
        # applies to machines whose adapter lists those formats (ID111). The
        # ID112 CODESYS machine gets its own post-processor later (TODO.md #52).
        adapter = getattr(self.app, "active_adapter", None)
        formats = adapter.get_export_formats() if adapter else ["scl", "recipe_csv"]

        export_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_export"), menu=export_menu)
        export_menu.add_command(label=t("menu_save_gcode"), command=self.save_gcode_logic)
        if "scl" in formats:
            export_menu.add_command(label=t("menu_export_scl"), command=self.export_scl_action)
        if "recipe_csv" in formats:
            export_menu.add_command(label=t("menu_export_recipe"), command=self.export_recipe_action)
        export_menu.add_separator()
        export_menu.add_command(label=t("menu_export_pdf"), command=self.export_pdf_action)
        export_menu.add_command(label=t("menu_export_stl"), command=self.export_stl_action)

        # Tools Menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("menu_tools"), menu=tools_menu)
        tools_menu.add_command(label=t("menu_tool_library"), command=self.open_tool_library)
        # NB: the recipe check lives under Help, not here — see the Help menu below.
        # SCL Inspector — the .nc is always full resolution, so a G-code viewer
        # shows intent, not what the PLC receives. Gated to machines whose adapter
        # actually has the SCL pipeline, same rule as the export entry above.
        if "scl" in formats:
            tools_menu.add_command(label=t("menu_scl_inspector"),
                                   command=self.open_scl_inspector)

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
        # First entry, above the guide: when a pass misbehaves this is the thing
        # to open first, and Help is where people look before Tools (user, 2026-07-28).
        help_menu.add_command(label=t("menu_recipe_audit"),
                              command=self.open_recipe_audit)
        help_menu.add_separator()
        help_menu.add_command(label=t("menu_user_guide"), command=_open_user_guide)
        help_menu.add_separator()
        help_menu.add_command(label=t("menu_about"), command=lambda: messagebox.showinfo(
            t("menu_about"), t("about_text").format(v=APP_VERSION)))

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
             # A program stores the whole params dict, machine settings included.
             # Those stay as the operator has them unless they say otherwise here
             # (field incident 2026-08-14 — an old program silently restored an
             # old PLC line limit, which autosave then made permanent).
             def _ask_machine_conflicts(conflicts):
                 from ui.dialogs.project_params_diff import ProjectParamsDiffDialog
                 dlg = ProjectParamsDiffDialog(self, conflicts,
                                               filename=os.path.basename(path))
                 return dlg.result

             if self.app.load_project(path, on_machine_conflict=_ask_machine_conflicts):
                 self.lbl_info.config(text=f"Loaded Project: {os.path.basename(path)}")
                 if hasattr(self, 'ui_machine'): self.ui_machine.refresh_ui()
                 if hasattr(self, 'ui_process'): self.ui_process.refresh_ui()
                 if hasattr(self, 'ui_program'):
                     # #66: undo history is per-project — snapshots of the old
                     # project's ops must not be restorable into the new one.
                     self.ui_program.clear_undo_history()
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
            cw_all = getattr(self.app.path_gen, "last_clamp_warnings", None) or []
            # Partition: "hard" = full amber alarm + modal (real, unexpected low start);
            # "soft" = intentional low start because start-fillet straightening is on →
            # calm status-bar note only, no modal.
            hard = [w for w in cw_all if not w.get("softened")]
            soft = [w for w in cw_all if w.get("softened")]

            # Persistent status-bar indicator (hard takes priority on the single line)
            if hard:
                self.lbl_info.config(
                    text=t("status_clamp_warn").format(n=len(hard), idx=hard[0]["op_index"] + 1),
                    fg="#ffb020")
            elif soft:
                self.lbl_info.config(
                    text=t("status_clamp_soft").format(n=len(soft), idx=soft[0]["op_index"] + 1),
                    fg="#88aacc")
            else:
                self.lbl_info.config(text=t("status_ready"), fg="#ddd")

            # Modal popup ONLY for hard warnings (unless suppressed this session)
            if hard and not getattr(self, "_clamp_popup_suppressed", False):
                top = hard[0]["clamp_top_z"]
                ops = "\n".join(
                    "  • " + t("msg_clamp_warn_op").format(
                        idx=w["op_index"] + 1, type=w["op_type"], sz=round(w["start_z"], 1))
                    for w in hard)
                self._show_clamp_popup(
                    t("msg_clamp_warn_body").format(n=len(hard), top=round(top, 1), ops=ops))
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

    def refresh_flatness_status(self):
        """Surface the straight-line finishing flatness advisory after a path
        calculation. Reads path_gen.last_flatness_warnings (set by calculate_paths).
        Amber status-bar cue (clamp keeps priority on the single status line) + a modal
        ONLY for gouge-direction deviations (max_dev > 0 = surface bulges toward the
        tool → clearance loss). Away-direction (under-finish) is status/log only. Modal
        is session-suppressible like the clamp popup. Advisory only — no toolpath
        change. Called after a successful calc, alongside refresh_clamp_status."""
        try:
            fw = getattr(self.app.path_gen, "last_flatness_warnings", None) or []
            cw = getattr(self.app.path_gen, "last_clamp_warnings", None) or []
            # Status-bar cue: clamp warning (if any) keeps priority on the single line.
            if fw and not cw:
                self.lbl_info.config(
                    text=t("status_flatness_warn").format(n=len(fw), idx=fw[0]["op_index"] + 1),
                    fg="#ffb020")
            # Modal only for the gouge direction (toward the tool).
            gouge = [w for w in fw if w.get("max_dev", 0.0) > 0.0]
            if gouge and not getattr(self, "_flatness_popup_suppressed", False):
                ops = "\n".join(
                    "  • " + t("msg_flatness_warn_op").format(
                        idx=w["op_index"] + 1,
                        sz=round(w["start_z"], 1), ez=round(w["end_z"], 1),
                        dev=round(w["max_dev"], 2))
                    for w in gouge)
                self._show_flatness_popup(
                    t("msg_flatness_warn_body").format(
                        n=len(gouge), tol=round(gouge[0]["tol"], 2), ops=ops))
        except Exception:
            pass

    def _show_flatness_popup(self, body):
        """Modal straight-line flatness warning; Confirm (may reappear next calc) /
        Don't-show-again (suppress for the session). Mirrors _show_clamp_popup."""
        win = tk.Toplevel(self)
        win.title(t("msg_flatness_warn_title"))
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text="⚠", font=("Arial", 20), fg="#d08000").pack(anchor="w")
        tk.Label(frm, text=body, justify="left", wraplength=460).pack(anchor="w", pady=(4, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))

        def _dont_show():
            self._flatness_popup_suppressed = True
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

    def refresh_tool_change_status(self):
        """Surface the per-op tool-change swing advisory. Reads
        path_gen.last_tool_change_warnings (set by calculate_paths when a CUSTOM
        absolute/relative tool-change point sits near the turret swing envelope).
        Lowest-priority amber status cue (clamp/flatness keep the single status
        line if present) + a session-suppressible modal. Warn-only by design —
        the toolpath is never changed."""
        try:
            tw = getattr(self.app.path_gen, "last_tool_change_warnings", None) or []
            cw = getattr(self.app.path_gen, "last_clamp_warnings", None) or []
            fw = getattr(self.app.path_gen, "last_flatness_warnings", None) or []
            if tw and not cw and not fw:
                self.lbl_info.config(
                    text=t("status_tc_warn").format(n=len(tw), idx=tw[0]["op_index"] + 1),
                    fg="#ffb020")
            if tw and not getattr(self, "_tc_popup_suppressed", False):
                ops = "\n".join(
                    "  • " + t("msg_tc_warn_op").format(
                        idx=w["op_index"] + 1, mode=w["mode"],
                        x=round(w["x"], 1), z=round(w["z"], 1),
                        gap=round(w["gap"], 1),
                        pgap=round(w.get("path_gap", w["gap"]), 1))
                    for w in tw)
                self._show_tool_change_popup(t("msg_tc_warn_body").format(n=len(tw), ops=ops))
        except Exception:
            pass

    def _confirm_point_cap_warnings(self):
        """#99: tell the operator when a P2 fillet point cap could NOT be honoured.

        Returns True to carry on with the export, False to abort.

        Deliberately NOT suppressible, unlike the clamp / tool-change advisories.
        Those repeat on every recalculation and describe a standing condition; this
        one fires only at export, only when a cap was actually refused, and its
        whole purpose is to stop a silent "I set 6 points and the machine still
        stutters". A 'don't show again' would hide exactly the fact it exists to
        report.

        Note the program being exported is already SAFE — the cap was dropped, not
        the clearance. The choice offered is whether to ship a program that will not
        move as smoothly as asked, or go back and change the geometry first.
        """
        try:
            cw = getattr(self.app.path_gen, "last_point_cap_warnings", None) or []
            if not cw:
                return True
            ops = "\n".join(
                "  • " + t("msg_cap_warn_op").format(
                    op=w.get("op_name", "?"), req=w.get("requested", 0),
                    kept=w.get("kept", 0),
                    floor=f"{w.get('floor', 0.0):.2f}",
                    got=f"{w.get('clearance', 0.0):.2f}")
                for w in cw)
            return messagebox.askyesno(
                t("msg_cap_warn_title"),
                t("msg_cap_warn_body").format(n=len(cw), ops=ops),
                icon='warning')
        except Exception:
            return True     # never block an export on a reporting bug

    def _show_tool_change_popup(self, body):
        """Modal tool-change swing warning; Confirm (may reappear next calc) /
        Don't-show-again (suppress for the session). Mirrors _show_clamp_popup."""
        win = tk.Toplevel(self)
        win.title(t("msg_tc_warn_title"))
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text="⚠", font=("Arial", 20), fg="#d08000").pack(anchor="w")
        tk.Label(frm, text=body, justify="left", wraplength=460).pack(anchor="w", pady=(4, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))

        def _dont_show():
            self._tc_popup_suppressed = True
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
            # app_version is a BUILD constant (version.py), never carried from a saved file.
            _mkeys = set(MACHINE_PROFILE_KEYS) | {"machine_id", "machine_name", "app_version"}
            # Exclude underscore-prefixed keys — those are internal session state and
            # must not be carried over from a customer settings file (they would
            # overwrite _last_license_path / _last_settings_path with stale paths).
            clean = {k: v for k, v in settings.items()
                     if k not in _mkeys and not k.startswith("_")}
            self.app.params.update(clean)

        self.app.params.update(profile)

        # Retired cylinder enable/position → a program_start M40 custom command.
        # Runs here because cylinder_enabled arrives with the PROFILE, so this
        # must be after the update above. Writes the converted command back to
        # the profile so the conversion is permanent rather than per-session.
        try:
            from config_schema import migrate_cylinder_mcode
            _before = json.dumps(profile.get("custom_commands"), sort_keys=True)
            migrate_cylinder_mcode(self.app.params)
            for _k in ("custom_commands", "cylinder_enabled"):
                profile[_k] = self.app.params.get(_k)
            if json.dumps(profile.get("custom_commands"), sort_keys=True) != _before:
                self.app.autosave_machine_profile()
        except Exception as e:
            logger.error(f"Cylinder M-code migration failed: {e}")

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
        # No brand strip here (removed 2026-08-24). A 26px black bar repeated the
        # name and version that the OS title bar already shows, and the sidebar
        # shows the version a third time — three readings of the same number,
        # costing vertical space on every screen. Name+version now come from
        # self.title() at the top of __init__ and the sidebar label below.

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

        # 3D pane = action bar on top + the plotter frame below it.
        # plot_frame must stay a frame of its own and must contain NOTHING else:
        # embed_plotter reparents the PyVista HWND into it and drives it with
        # MoveWindow(0, 0, w, h), so any sibling widget placed inside would be
        # covered by the 3D view. Wrapping keeps that contract intact while
        # giving the bar its own space.
        view_pane = tk.Frame(self._paned, bg="#f0f0f0")
        self._paned.add(view_pane, minsize=300)

        # Calculate lives here, next to the 3D view, because it applies to the
        # whole program — it used to sit inside the Process tab, which meant the
        # Machine tab (M-codes, offsets, PLC) had no way to recalculate without
        # switching tabs first. Height locked like the status bar so a themed
        # button cannot grow the strip and squeeze the viewport.
        bar_view = tk.Frame(view_pane, bg="#e4e4e4", height=36)
        bar_view.pack(side="top", fill="x")
        bar_view.pack_propagate(False)

        self.btn_calc_global = tk.Button(
            bar_view, text=t("btn_calculate"), bg="orange", fg="black",
            font=("Arial", 9, "bold"), relief="raised", bd=2, padx=14,
            # Late binding: rebuild_all_tabs() replaces ui_program, so resolve
            # the attribute at click time rather than capturing it now.
            command=lambda: self.ui_program._start_async_calc())
        self.btn_calc_global.pack(side="left", padx=8, pady=4)
        self.helper.bind_tooltip(
            self.btn_calc_global,
            "Mevcut ayarlara göre tüm takım yollarını yeniden hesapla ve "
            "görünümü güncelle.\nHer sekmeden erişilebilir — Makine sekmesindeki "
            "M-code/offset/PLC değişiklikleri de buradan hesaplanır.")

        self.plot_frame = tk.Frame(view_pane, bg="white")
        self.plot_frame.pack(side="top", fill="both", expand=True)

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

                tk.Label(self.sidebar, text=f"V{APP_VERSION}", font=("Arial", 9, "bold"), fg="#555").place(relx=0.98, rely=0.01, anchor="ne")
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

            # #63: as the sim advances pass-by-pass, bend the deformed blank to the current
            # pass (only when it changes; the render below shows it).
            sp = self.app.sim_controller.current_pass_idx
            if sp >= 0 and sp != getattr(self, "_sim_last_blank_pass", -2):
                self._sim_last_blank_pass = sp
                self.app.active_editing_pass_idx = sp
                try: self.app.update_deformed_blank(render=False)
                except Exception: pass

            # Tool-change cue (banner + pulsing marker) while the worker dwells at a
            # change point. Updated every frame so the marker pulses; cleared as soon
            # as the dwell ends. The worker only sets the flags (main thread renders).
            sc = self.app.sim_controller
            self.app.update_tool_change_cue(
                getattr(sc, "tool_change_active", False),
                getattr(sc, "tool_change_pos", None),
                getattr(sc, "tool_change_from", ""),
                getattr(sc, "tool_change_to", ""))

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
            self._sim_last_blank_pass = -2   # #63: reset so the next sim run redraws fresh
            # Make sure the tool-change cue is gone when the sim ends/stops.
            try: self.app.update_tool_change_cue(False)
            except Exception: pass
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

    def _startup_tasks(self):
        """Auto-load the last STEP (no prompt), then show the changelog if it's a new version."""
        self._auto_load_step()
        self._maybe_show_changelog()

    def _auto_load_step(self):
        """Load the last-used STEP automatically if it still exists; only prompt if it's
        missing or none was ever set. Avoids asking for the file on every launch."""
        last = self.app.params.get("last_step_path", "")
        if last and os.path.isfile(last):
            try:
                self.app.load_step_file(last)
                logger.info(f"Auto-loaded last STEP: {last}")
                return
            except Exception as e:
                logger.warning(f"Auto-load of last STEP failed ({e}); prompting.")
        self.load_step_prompt()

    def _maybe_show_changelog(self):
        """Show the 'What's New' dialog once when the app version is newer than the last
        one the user acknowledged with 'Don't show again'."""
        try:
            from version import APP_VERSION
            import changelog
            sections = changelog.entries_since(
                self.app.params.get("changelog_seen_version", ""), APP_VERSION)
            if not sections:
                return
            from ui.dialogs.changelog_window import ChangelogWindow
            ChangelogWindow(self, APP_VERSION, sections, self._on_changelog_confirm)
        except Exception as e:
            logger.warning(f"Changelog window skipped: {e}")

    def _on_changelog_confirm(self, dont_show):
        """Persist the seen version only if the user ticked 'Don't show again'."""
        if dont_show:
            from version import APP_VERSION
            self.app.params["changelog_seen_version"] = APP_VERSION
            try:
                self.app.save_settings_json()
            except Exception as e:
                logger.warning(f"Could not save changelog_seen_version: {e}")

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
        try: self.ui_process.refresh_process_time()
        except Exception: pass
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

    def resolve_export_params(self):
        """params for an export, after settling any out-of-range pass triggers.

        Returns the dict to generate from, or None when the operator cancels —
        callers MUST treat None as "abort, write nothing".

        A "pass" trigger is pinned to a pass NUMBER, so editing the program list
        can leave a command aimed past the end, where the engine silently never
        fires it. Asking here is the last point before a file exists. The answer
        is applied to a COPY: the command table is never edited behind the user.
        """
        try:
            from recipe_explain import orphan_pass_commands, apply_orphan_action
            total = len(getattr(self.app.path_gen, 'last_calculated_paths', None) or [])
            orphans = orphan_pass_commands(self.app.params, total)
            if not orphans:
                return self.app.params
            from ui.dialogs.orphan_commands import OrphanCommandsDialog
            choice = OrphanCommandsDialog(self, orphans, total).result
            if choice is None:
                return None
            return apply_orphan_action(self.app.params, total, choice)
        except Exception as e:
            # A check must never be the reason an export fails: log and proceed
            # with exactly the old behaviour.
            logger.error(f"Orphan-command check failed, exporting unchanged: {e}")
            return self.app.params

    def _blocked_by_missing_tools(self):
        """Refuse to export when an operation uses a tool this computer doesn't have.

        The tool library is local (tools.json, never carried inside a .ssp), so a
        program written elsewhere can name a tool that isn't here. Every other
        tool value re-syncs from the library on each calculation; this one cannot,
        and the operation keeps the roller reach saved in the file — a reach
        calibrated on another machine. Reach is the clearance, so the quiet
        outcome is a gouge or a collision.

        Blocks like the turret/tool-table check does: say which tool, which
        operations, and stop. Returns True when the export must not proceed.
        """
        try:
            missing = self.app.missing_library_tools()
        except Exception as e:
            # A check must never be the reason an export fails.
            logger.error(f"Missing-tool check failed, exporting unchanged: {e}")
            return False
        if not missing:
            return False

        lines = []
        for m in missing:
            saved = m.get("r_tool")
            saved_txt = f"{float(saved):.3f} mm" if isinstance(saved, (int, float)) \
                else t("mt_no_reach")
            lines.append(t("mt_row").format(tool=m["tool_id"], reach=saved_txt,
                                            ops=", ".join(m["ops"])))
        messagebox.showerror(
            t("mt_title"),
            t("mt_body").format(n=len(missing), rows="\n".join(lines)))
        return True

    def save_gcode_logic(self):
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        if hasattr(self, 'ui_program'):
            self.ui_program._flush_entries()

        if not getattr(self.app.path_gen, 'last_calculated_paths', None):
            messagebox.showwarning(t("msg_no_paths_title"), t("msg_no_paths"))
            return

        # A tool this computer does not have means an un-syncable roller reach
        # in the toolpath — refuse before a file exists.
        if self._blocked_by_missing_tools():
            return

        _p = self.resolve_export_params()
        if _p is None:
            return

        path = filedialog.asksaveasfilename(
             defaultextension=".nc",
             filetypes=[(t("fd_gcode_files"), "*.nc"), (t("fd_all_files"), "*.*")],
             title=t("fd_save_gcode"),
             initialfile="EMS_Spinning.nc"
        )
        if path:
             self.app.save_gcode(True, filepath=path, params=_p)
             if messagebox.askyesno(t("msg_view_gcode_title"),
                                    t("msg_view_gcode").format(os.path.basename(path))):
                 webbrowser.open("https://ncviewer.com/")
                 try: os.startfile(path)
                 except: pass

    def open_recipe_audit(self):
        """Read-only list of values that did not come from the operation panel."""
        from ui.dialogs.recipe_audit import RecipeAuditDialog
        RecipeAuditDialog(self, self.app, getattr(self, "ui_program", None))

    def open_scl_inspector(self):
        """Read-only view of what PLC decimation does to the calculated paths."""
        if hasattr(self, 'ui_machine'):
            self.ui_machine.sync_params()
        if not getattr(self.app.path_gen, 'last_calculated_paths', None):
            messagebox.showwarning(t("msg_no_paths_title"), t("msg_no_paths"))
            return
        from ui.dialogs.scl_inspector import SclInspectorDialog
        SclInspectorDialog(self, self.app)

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
            # #88 — export-time parameter picker. Flat union of every param used by
            # the program's operations; the last choice is remembered globally
            # (settings.json) so a repeat export is just OK. Cancel aborts.
            from ui.dialogs.pdf_param_dialog import PdfParamDialog
            _skip = {"pass_edits", "pass_overrides", "zones", "type", "name", "enabled"}
            all_keys = sorted({k for op in self.app.params.get("operations", [])
                               if isinstance(op, dict) and op.get("enabled", True)
                               for k in op.keys() if k not in _skip})
            selection = None
            if all_keys:
                dlg = PdfParamDialog(self, all_keys,
                                     self.app.params.get("pdf_param_selection"))
                if dlg.result is None:
                    return   # user cancelled the export
                selection = dlg.result
                self.app.params["pdf_param_selection"] = selection
                try:
                    self.app.save_settings_json()
                except Exception:
                    pass
            paths = self.app.path_gen.last_calculated_paths
            success = ExportManager.export_pdf(self.app.params, paths, path, self.tool_library,
                                               mandrel_mgr=self.app.mandrel_mgr,
                                               tilt_angles=getattr(self.app.path_gen,
                                                                   "last_tilt_angles", None),
                                               param_selection=selection)
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

        # A tool this computer does not have means an un-syncable roller reach in
        # the recipe — refuse before the name/layout dialogs, like the turret check.
        if self._blocked_by_missing_tools():
            return

        # Settle out-of-range pass triggers BEFORE the first generate, so every
        # later step (line count, auto-tune, the written file) sees one and the
        # same program. _xp replaces self.app.params for the rest of this export.
        _xp = self.resolve_export_params()
        if _xp is None:
            return

        try:
            from recipe_to_scl import GCodeToSCLConverter
            gcode_str = self.app.path_gen.generate_gcode(params=_xp, for_recipe=True)
        except Exception as e:
            messagebox.showerror(t("msg_export_error_title"), t("msg_gcode_gen_error").format(e))
            return

        try:
            _pre_converter = GCodeToSCLConverter()
            _pre_converter.parse_gcode(gcode_str)
            _parsed_line_count = len(_pre_converter.lines)
        except ValueError as _pe:
            # A custom command's P will not fit the PLC Param byte. Say so now
            # rather than swallowing it and failing after the name dialogs — the
            # CAM never ships a P other than the one that was typed.
            _pe_msg = str(_pe)
            if _pe_msg.startswith("PARAM_RANGE:"):
                _, _mc, _pv = _pe_msg.split(":", 2)
                messagebox.showerror(
                    t("msg_export_error_title"),
                    f"{_mc} P{_pv}: P must be a whole number between 0 and 255 "
                    f"(the PLC Param field is one byte).\n\n"
                    f"Fix the custom command in the Machine tab.")
                return
            _parsed_line_count = None
        except Exception:
            _parsed_line_count = None

        # Fail fast on turret/tool-table problems (the PLC would reject the recipe
        # with 16#0311 / pre-scan) BEFORE bothering the operator with the name and
        # array-size dialogs.
        if _parsed_line_count is not None:
            try:
                _pre_converter._tool_table_scl(_xp)
            except ValueError as _tt:
                _tt_msg = str(_tt)
                if _tt_msg.startswith("TOOL_TABLE:"):
                    messagebox.showerror(t("msg_export_error_title"),
                                         _tt_msg[len("TOOL_TABLE:"):])
                    return
                raise

        db_name = simpledialog.askstring(
            t("dlg_db_name_title"),
            t("dlg_db_name_prompt"),
            initialvalue="DB_RecipeProgram1",
            parent=self
        )
        if not db_name:
            return

        # A distinct Header.sName per program, so the HMI can tell the operator
        # which recipe is loaded — seed the title from the DB's slot number rather
        # than shipping "SpinningCam Program" for all ten.
        _slot = "".join(ch for ch in db_name if ch.isdigit())
        _default_title = f"Program {_slot}" if _slot else "SpinningCam Program"
        program_title = simpledialog.askstring(
            t("dlg_prog_title_title"),
            t("dlg_prog_title_prompt"),
            initialvalue=_default_title,
            parent=self
        )
        if not program_title:
            program_title = _default_title

        auto = (bool(_xp.get("plc_auto_tune", False))
                and bool(_xp.get("plc_mode", False)))
        force_flag = False
        autofit_note = None

        def _fmt(v):
            if v is None or v in (float('inf'), float('-inf')):
                return "—"
            return f"{v:.2f}"

        if auto:
            # Auto-tune: pick the finest tolerance that fits the line budget while
            # staying at least as clear as the full-resolution path. Replaces the
            # array-size question entirely (target sizes the array: 350 -> [0..349]).
            pg = self.app.path_gen
            target = int(_xp.get("plc_target_lines", 1000) or 1000)
            floor_cl = pg.measure_min_clearance(pg.last_calculated_paths, _xp)
            result = ExportManager.auto_fit_plc_tolerance(pg, _xp, target, floor_cl)
            st = result.get("status")
            fit_tol   = result.get("tolerance")
            fit_lines = result.get("lines", 0)
            fit_cl    = result.get("min_clearance")

            # Show the fitted values so the operator can review before writing.
            man_tol = float(_xp.get("plc_tolerance", 0.5))
            before = _parsed_line_count if _parsed_line_count is not None else fit_lines
            preview = t("msg_autotune_preview").format(
                man=_fmt(man_tol), auto=_fmt(fit_tol),
                before=before, after=fit_lines, target=target,
                cl=_fmt(fit_cl), floor=_fmt(floor_cl))

            if st in ("clearance_limited", "infeasible_budget"):
                if st == "clearance_limited":
                    warn = t("msg_autotune_clearance").format(
                        lines=fit_lines, target=target, cl=_fmt(fit_cl), floor=_fmt(floor_cl))
                else:
                    warn = t("msg_autotune_infeasible").format(lines=fit_lines, target=target)
                if not messagebox.askyesno(
                        t("msg_autotune_title"), warn + "\n\n" + preview, icon='warning'):
                    return
                force_flag = fit_lines > 1000
            else:
                # Feasible & safe — still let the operator see and confirm the numbers.
                if not messagebox.askokcancel(t("msg_autotune_title"), preview):
                    return

            # Rebuild the SCL source with the fitted tolerance.
            p = dict(_xp)
            p["plc_mode"] = True
            p["plc_tolerance"] = fit_tol
            p["plc_exit_tolerance"] = fit_tol
            gcode_str = self.app.path_gen.generate_gcode(params=p, for_recipe=True)
            # Size the DB to the entered target (e.g. 350 -> 4 chunks of 100),
            # not a fixed 1000. chunk_geometry still grows the capacity if the
            # fitted line count exceeds the target, and rounds it up to whole
            # arrays so every chunk is the same length.
            custom_array_size = target
            autofit_note = t("msg_autotune_note").format(
                tol=_fmt(fit_tol), lines=fit_lines, cl=_fmt(fit_cl))
            _layout_line_count = fit_lines
        else:
            custom_array_size = None
            _layout_line_count = _parsed_line_count

        # Recipe DB layout: total capacity + lines per chunk array (Lines1..LinesN).
        # The PLC reads the recipe one declared array at a time, so both numbers
        # must match its loader — see letter_spinningcam_chunked_recipes.md.
        from recipe_to_scl import DEFAULT_CHUNK_SIZE
        chunk_size = int(_xp.get("scl_chunk_size", DEFAULT_CHUNK_SIZE) or 0)
        if _layout_line_count is not None:
            from ui.dialogs.scl_layout import SclLayoutDialog
            _dlg = SclLayoutDialog(
                self,
                line_count=_layout_line_count,
                capacity=(custom_array_size if custom_array_size is not None
                          else max(_layout_line_count, 1000)),
                chunk_size=chunk_size,
                capacity_locked=auto,
            )
            if _dlg.result is None:
                return
            chunk_size = _dlg.result["chunk_size"]
            if not auto:
                custom_array_size = _dlg.result["capacity"]
            # Remember the geometry: it is a property of the PLC on the other end,
            # not of this one program, so the next export should not re-ask blind.
            if chunk_size != int(_xp.get("scl_chunk_size", -1) or 0):
                _xp["scl_chunk_size"] = chunk_size
                try:
                    self.app.on_param_change("scl_chunk_size", chunk_size, "none")
                except Exception:
                    pass

        # #99: a refused fillet cap is reported BEFORE the save dialog — aborting
        # here costs the operator nothing, whereas after picking a filename it
        # reads as a failed export.
        if not self._confirm_point_cap_warnings():
            return

        default_name = db_name + ".scl"
        scl_path = filedialog.asksaveasfilename(
            defaultextension=".scl",
            filetypes=[(t("fd_scl_files"), "*.scl"), (t("fd_all_files"), "*.*")],
            title=t("fd_save_scl"),
            initialfile=default_name
        )
        if not scl_path:
            return

        # The DB name is what TIA imports, not the file name: saving program 5's
        # data in a block still called DB_RecipeProgram1 overwrites program 1.
        _db_slot = "".join(ch for ch in db_name if ch.isdigit())
        _file_slot = "".join(ch for ch in os.path.splitext(os.path.basename(scl_path))[0]
                             if ch.isdigit())
        if _db_slot and _file_slot and _db_slot != _file_slot:
            if not messagebox.askyesno(
                    t("msg_slot_mismatch_title"),
                    t("msg_slot_mismatch").format(
                        db=db_name, file=os.path.basename(scl_path),
                        dbnum=_db_slot, filenum=_file_slot),
                    icon='warning'):
                return

        success, stats = ExportManager.export_scl(
            scl_filepath=scl_path,
            db_name=db_name,
            program_title=program_title,
            force=force_flag,
            params=_xp,
            custom_array_size=custom_array_size,
            chunk_size=chunk_size,
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
                    params=_xp,
                    custom_array_size=custom_array_size,
                    chunk_size=chunk_size,
                    gcode_string=gcode_str
                )
            else:
                messagebox.showinfo(t("msg_cancelled_title"), t("msg_cancelled"))
                return

        # The generated file failed its own chunk-mapping self-check; nothing was
        # written (a scrambled recipe compiles cleanly in TIA, so it must not ship).
        if not success and stats.get('geometry_error'):
            messagebox.showerror(t("msg_export_error_title"),
                                 stats.get('message', t("msg_scl_error")))
            return

        # Turret/tool-table validation failed inside the writer (backstop — the
        # pre-check above normally catches this first).
        if not success and stats.get('tool_table_error'):
            messagebox.showerror(t("msg_export_error_title"),
                                 stats.get('message', t("msg_scl_error")))
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
            _geo = stats.get('geometry') or {}
            if _geo.get('chunked'):
                msg += "\n" + t("msg_scl_layout_line").format(
                    n=_geo['chunk_count'], m=_geo['chunk_size'])
            # Worth showing: it is the number the PLC will recompute and compare,
            # so it is what to quote when a load is refused with 16#0316.
            if stats.get('checksum') is not None:
                msg += "\n" + t("msg_scl_checksum_line").format(ck=stats['checksum'])
            if autofit_note:
                msg = f"{autofit_note}\n\n{msg}"
            messagebox.showinfo(t("msg_scl_complete_title"), msg)
            if messagebox.askyesno(t("msg_open_file_title"), t("msg_open_scl_file")):
                try: os.startfile(scl_path)
                except: pass
        else:
            messagebox.showerror(t("msg_export_error_title"), t("msg_scl_error"))
