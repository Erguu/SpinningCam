# -*- coding: utf-8 -*-
"""Recipe database layout picker, shown while exporting an SCL for TIA Portal.

Replaces the old bare "how many elements?" prompt. Two numbers decide the whole
DB layout and they are coupled, so they are asked together, with the resulting
declarations spelled out live:

    capacity  — total recipe elements the DB declares
    chunk     — recipe lines per declared array (Lines1..LinesN)

Chunking exists because READ_DBL silently returns short copies of a ~12 KB block
on the S7-1214C, so the PLC pulls the recipe one declared array at a time; its
VARIANT source resolves at compile time, so each transferable sub-range must be
its own declaration (letter_spinningcam_chunked_recipes.md, 2026-08-14).

The operator only has to recognise one sentence — "10 arrays x 100 lines" — and
it must equal what the PLC's loader was generated for. Getting the ARRAY COUNT
wrong is caught by the TIA compiler; getting the SIZE wrong is not, and
reassembles the recipe scrambled. Hence the warning line, not just the numbers.

``result`` is ``{'capacity': int, 'chunk_size': int}`` or None if cancelled.

TWO WAYS IN (2026-08-31). It used to open on every SCL export, which is a
question with the same answer every time — the layout describes the PLC on the
other end, not this program. Now:

* **Machine tab ▸ PLC ▸ Recipe DB layout…** — opened by hand, `line_count=None`.
  There is no measured recipe, so the declarations are still shown but the END
  marker position is not (it would be a position in a recipe that does not
  exist).
* **the SCL export** — only when the remembered layout cannot serve this recipe
  (nothing set yet, or the capacity is smaller than the line count). `reason`
  then says which, because a window that normally stays shut needs to explain
  why it did not.
"""
import tkinter as tk
from tkinter import ttk

from i18n import t
from recipe_to_scl import DEFAULT_CHUNK_SIZE, chunk_geometry


# The layout the PLC's chunked loader was generated for (letter, 2026-08-14).
# Anything else needs the PLC side regenerated to match, so it is flagged.
PLC_REFERENCE_GEOMETRY = (10, DEFAULT_CHUNK_SIZE)   # arrays x lines


class SclLayoutDialog(tk.Toplevel):

    def __init__(self, parent, line_count, capacity, chunk_size,
                 capacity_locked=False, reason=None):
        super().__init__(parent)
        self.result = None
        # None = opened from the Machine tab with no export running. Everything
        # downstream treats it as 0 lines (chunk_geometry already copes); only
        # the two places that would report a POSITION IN THE RECIPE change.
        self._has_recipe = line_count is not None
        self._line_count = int(line_count or 0)
        self._locked = bool(capacity_locked)

        self.title(t("dlg_layout_title"))
        self.transient(parent)
        self.resizable(False, False)

        ttk.Label(self,
                  text=(t("dlg_layout_lines").format(n=self._line_count)
                        if self._has_recipe else t("dlg_layout_no_recipe")),
                  font=("Arial", 9, "bold"), wraplength=430,
                  justify="left").pack(anchor="w", padx=12, pady=(12, 2))
        if reason:
            # Only the export sets this, and only when it had to break its own
            # rule about not asking.
            tk.Label(self, text=reason, wraplength=430, justify="left",
                     fg="#a33", font=("Arial", 8)).pack(anchor="w", padx=12,
                                                        pady=(0, 4))
        ttk.Label(self, text=t("dlg_layout_info"), wraplength=430, justify="left",
                  foreground="#555").pack(fill="x", padx=12, pady=(0, 8))

        grid = ttk.Frame(self)
        grid.pack(fill="x", padx=12)

        self.var_cap = tk.StringVar(value=str(int(capacity)))
        self.var_chunk = tk.StringVar(value=str(int(chunk_size or 0)))
        self.var_split = tk.BooleanVar(value=bool(chunk_size))

        ttk.Label(grid, text=t("dlg_layout_capacity")).grid(row=0, column=0, sticky="w", pady=3)
        self.e_cap = ttk.Entry(grid, textvariable=self.var_cap, width=10)
        self.e_cap.grid(row=0, column=1, sticky="w", padx=(8, 0))
        if self._locked:
            # Auto-tune already fixed the budget; showing it read-only beats
            # asking a question whose answer is ignored.
            self.e_cap.config(state="readonly")
            ttk.Label(grid, text=t("dlg_layout_locked"), foreground="#777",
                      font=("Arial", 8)).grid(row=0, column=2, sticky="w", padx=6)

        self.cb_split = ttk.Checkbutton(grid, text=t("dlg_layout_split"),
                                        variable=self.var_split, command=self._sync)
        self.cb_split.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(grid, text=t("dlg_layout_chunk")).grid(row=2, column=0, sticky="w", pady=3)
        self.e_chunk = ttk.Entry(grid, textvariable=self.var_chunk, width=10)
        self.e_chunk.grid(row=2, column=1, sticky="w", padx=(8, 0))

        self.lbl_preview = tk.Label(self, text="", justify="left", anchor="w",
                                    font=("Consolas", 9), fg="#0b5a2b")
        self.lbl_preview.pack(fill="x", padx=12, pady=(10, 0))
        self.lbl_warn = tk.Label(self, text="", justify="left", anchor="w",
                                 wraplength=430, font=("Arial", 8), fg="#a33")
        self.lbl_warn.pack(fill="x", padx=12, pady=(4, 0))

        fok = ttk.Frame(self)
        fok.pack(fill="x", padx=12, pady=12)
        self.btn_ok = ttk.Button(fok, text=t("btn_ok"), command=self._ok)
        self.btn_ok.pack(side="right", padx=(6, 0))
        ttk.Button(fok, text=t("btn_cancel"), command=self._cancel).pack(side="right")

        for v in (self.var_cap, self.var_chunk):
            v.trace_add("write", lambda *_: self._sync())
        self._sync()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        try:
            self.grab_set()
        except Exception:
            pass
        (self.e_chunk if self._locked else self.e_cap).focus_set()
        self.wait_window(self)

    # -- helpers ---------------------------------------------------------
    def _read(self):
        """Current (capacity, chunk_size) or None when a field is not a number."""
        try:
            cap = int(float(self.var_cap.get()))
        except (ValueError, TypeError):
            return None
        if not self.var_split.get():
            return cap, 0
        try:
            chunk = int(float(self.var_chunk.get()))
        except (ValueError, TypeError):
            return None
        if chunk <= 0:
            return None
        return cap, chunk

    def _sync(self, *_):
        self.e_chunk.config(state="normal" if self.var_split.get() else "disabled")
        vals = self._read()
        if vals is None:
            self.lbl_preview.config(text=t("dlg_layout_bad"))
            self.lbl_warn.config(text="")
            self.btn_ok.config(state="disabled")
            return
        cap, chunk = vals
        self.btn_ok.config(state="normal")
        geo = chunk_geometry(self._line_count, cap, chunk)

        if geo["chunked"]:
            preview = (t("dlg_layout_preview") if self._has_recipe
                       else t("dlg_layout_preview_nolines")).format(
                n=geo["chunk_count"], m=geo["chunk_size"],
                hi=geo["chunk_size"] - 1,
                last=geo["chunk_count"], cap=geo["capacity"],
                ea=geo["end_array"], ei=geo["end_index"])
        else:
            preview = (t("dlg_layout_preview_legacy") if self._has_recipe
                       else t("dlg_layout_preview_legacy_nolines")).format(
                hi=geo["capacity"] - 1, end=self._line_count - 1)
        self.lbl_preview.config(text=preview)

        warn = []
        if self._has_recipe and cap < self._line_count:
            warn.append(t("dlg_layout_warn_small").format(n=self._line_count))
        if geo["chunked"]:
            if geo["capacity"] != cap:
                warn.append(t("dlg_layout_warn_round").format(cap=geo["capacity"]))
            # The two mismatches fail in opposite ways, so they are said
            # separately: a wrong SIZE compiles and scrambles the recipe, a wrong
            # COUNT is caught by TIA (too few) or silently drops the tail (too many).
            if geo["chunk_size"] != PLC_REFERENCE_GEOMETRY[1]:
                warn.append(t("dlg_layout_warn_geo").format(
                    m=geo["chunk_size"], rm=PLC_REFERENCE_GEOMETRY[1]))
            if geo["chunk_count"] != PLC_REFERENCE_GEOMETRY[0]:
                warn.append(t("dlg_layout_warn_count").format(
                    n=geo["chunk_count"], rn=PLC_REFERENCE_GEOMETRY[0]))
        else:
            warn.append(t("dlg_layout_warn_legacy"))
        self.lbl_warn.config(text="\n".join(warn))

    # -- buttons ---------------------------------------------------------
    def _ok(self):
        vals = self._read()
        if vals is None:
            return
        cap, chunk = vals
        geo = chunk_geometry(self._line_count, cap, chunk)
        self.result = {"capacity": geo["capacity"], "chunk_size": chunk}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
