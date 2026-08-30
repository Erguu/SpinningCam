# -*- coding: utf-8 -*-
"""Asked when a saved program (.ssp) disagrees with the machine's own settings.

A program file stores the whole params dict, machine settings included. Opening
one saved weeks ago used to silently restore that day's machine setup — program
start position, PLC/recipe settings, turret table — and the next Machine-tab edit
then wrote it permanently into the profile via autosave (field incident,
2026-08-14).

Now the loader keeps the machine in front of the operator and shows what the file
disagreed about. Every row starts on "Mine", so pressing OK without reading
changes nothing; the operator ticks only the rows they actually want from the
file. Geometry, operations and passes are never listed — those ARE the program.

``result`` is ``{key: value_from_file}`` for the accepted rows (``{}`` = keep all
of mine), or None if the load should be abandoned.
"""
import json
import tkinter as tk
from tkinter import ttk

from i18n import t

# Machine keys -> an existing UI label, so a row reads the way the Machine tab
# does. Keys not listed fall back to a prettified name (see _label).
_LABELS = {
    "home_x": "lbl_home_x",                 "home_z": "lbl_home_z",
    "end_x": "lbl_end_x",                   "end_z": "lbl_end_z",
    "retract_x": "lbl_retract_x",           "retract_z": "lbl_retract_z",
    "machine_origin_x": "lbl_machine_origin", "machine_origin_z": "lbl_machine_origin",
    "machine_gcode_offset_x": "lbl_x_offset", "machine_gcode_offset_z": "lbl_z_offset",
    "machine_invert_x": "cb_invert_x",      "machine_invert_z": "cb_invert_z",
    "output_mode": "frm_output_mode",
    "max_spin_rpm": "lbl_max_rpm",          "rapid_rate_mm_min": "lbl_rapid_rate",
    "gcode_header": "lbl_gcode_header",     "gcode_footer": "lbl_gcode_footer",
    "workspace_x_min": "lbl_ws_x_min",      "workspace_x_max": "lbl_ws_x_max",
    "workspace_z_min": "lbl_ws_z_min",      "workspace_z_max": "lbl_ws_z_max",
    "plc_mode": "cb_plc_enable",
    "plc_tolerance": "lbl_plc_tol",         "plc_exit_tolerance": "lbl_plc_exit_tol",
    "plc_auto_tune": "cb_plc_autotune",     "plc_target_lines": "lbl_plc_target",
    "scl_chunk_size": "dlg_layout_chunk",   "scl_capacity": "dlg_layout_capacity",
    "clamp_zone_baseline": "lbl_clamp_baseline",
    "turret_slots": "frm_turret",
}

# Keys whose value is a list/dict — showing the raw JSON would be noise, so the
# cell says how big it is instead.
_SUMMARY_KEYS = {"turret_slots", "custom_commands", "mcode_descriptions",
                 "calibration_view"}


def _label(key):
    lk = _LABELS.get(key)
    if lk:
        txt = t(lk)
        if txt and txt != lk:
            return txt.rstrip(":")
    return key.replace("_", " ").title()


def _fmt(key, val):
    """One short cell. Never longer than a glance."""
    if isinstance(val, bool):
        return t("diff_on") if val else t("diff_off")
    if isinstance(val, float):
        return f"{val:g}"
    if key in _SUMMARY_KEYS or isinstance(val, (list, dict)):
        try:
            n = len(val)
        except TypeError:
            n = 0
        return t("diff_items").format(n=n)
    s = str(val)
    if len(s) > 40:
        s = s[:37] + "..."
    return s.replace("\n", " ⏎ ")


class ProjectParamsDiffDialog(tk.Toplevel):

    def __init__(self, parent, conflicts, filename=""):
        super().__init__(parent)
        self.result = None
        self._conflicts = list(conflicts)
        # Row choice: True = take the file's value. Default False everywhere —
        # the machine in front of the operator wins unless they say otherwise.
        self._take = {c["key"]: False for c in self._conflicts}

        self.title(t("diff_title"))
        self.transient(parent)

        head = t("diff_head").format(n=len(self._conflicts))
        if filename:
            head = f"{filename}\n{head}"
        ttk.Label(self, text=head, wraplength=620, justify="left",
                  font=("Arial", 9, "bold")).pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(self, text=t("diff_info"), wraplength=620, justify="left",
                  foreground="#555").pack(fill="x", padx=12, pady=(0, 8))

        cols = ("setting", "mine", "file", "use")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=min(max(len(self._conflicts), 3), 12))
        for c, w, anchor in (("setting", 260, "w"), ("mine", 150, "center"),
                             ("file", 150, "center"), ("use", 130, "center")):
            self.tree.heading(c, text=t(f"diff_col_{c}"))
            self.tree.column(c, width=w, anchor=anchor)
        self.tree.pack(fill="both", expand=True, padx=12)
        self.tree.tag_configure("file", foreground="#a33")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())
        self.tree.bind("<Return>", lambda e: self._toggle_selected())

        ttk.Label(self, text=t("diff_hint"), foreground="#777",
                  font=("Arial", 8)).pack(anchor="w", padx=12, pady=(4, 0))

        fset = ttk.Frame(self)
        fset.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Button(fset, text=t("diff_all_mine"),
                   command=lambda: self._set_all(False)).pack(side="left")
        ttk.Button(fset, text=t("diff_all_file"),
                   command=lambda: self._set_all(True)).pack(side="left", padx=6)

        fok = ttk.Frame(self)
        fok.pack(fill="x", padx=12, pady=12)
        ttk.Button(fok, text=t("diff_cancel_load"),
                   command=self._cancel).pack(side="right")
        ttk.Button(fok, text=t("btn_ok"), command=self._ok).pack(side="right", padx=(0, 6))

        self._fill()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        try:
            self.grab_set()
        except Exception:
            pass
        self.tree.focus_set()
        self.wait_window(self)

    # -- rows ------------------------------------------------------------
    def _fill(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for c in self._conflicts:
            k = c["key"]
            take = self._take[k]
            self.tree.insert(
                "", "end", iid=k,
                values=(_label(k), _fmt(k, c["current"]), _fmt(k, c["loaded"]),
                        t("diff_use_file") if take else t("diff_use_mine")),
                tags=("file",) if take else ())
        for s in sel:
            if self.tree.exists(s):
                self.tree.selection_set(s)

    def _toggle(self, key):
        if key in self._take:
            self._take[key] = not self._take[key]
            self._fill()

    def _toggle_selected(self):
        for s in self.tree.selection():
            self._toggle(s)

    def _on_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row:
            self._toggle(row)

    def _set_all(self, take):
        for k in self._take:
            self._take[k] = take
        self._fill()

    # -- buttons ---------------------------------------------------------
    def _ok(self):
        self.result = {c["key"]: c["loaded"]
                       for c in self._conflicts if self._take[c["key"]]}
        self.destroy()

    def _cancel(self):
        self.result = None      # abandon the load entirely
        self.destroy()
