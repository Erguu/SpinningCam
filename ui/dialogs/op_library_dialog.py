import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from i18n import t
import ops_library as ol

_TYPES = ("roughing", "finishing", "cutting", "bending")


class OpLibraryDialog(tk.Toplevel):
    """Operation library (#71).

    Named, reusable operation presets stored app-level (ops_library.json next
    to the exe) — any number per op type, unlike the single Save-as-Default
    slot. Save the op selected in the Program tab under a name; insert entries
    back into any program (the dialog stays open for multiple inserts).
    Inserting is undo-tracked and re-syncs r_tool via ProgramTab.
    """

    def __init__(self, parent, app, program_tab):
        super().__init__(parent)
        self.app = app
        self.pt = program_tab
        self.entries = ol.load_library(app.get_base_path())

        self.title(t("dlg_op_library"))
        self.geometry("560x420")
        self.transient(parent)
        self.focus_force()

        self._create_widgets()
        self._refresh_list()

    # ------------------------------------------------------------------
    def _create_widgets(self):
        f_top = ttk.Frame(self)
        f_top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(f_top, text=t("lbl_lib_filter")).pack(side="left")
        self.cmb_filter = ttk.Combobox(
            f_top, state="readonly", width=14,
            values=[t("lib_filter_all")] + list(_TYPES))
        self.cmb_filter.current(0)
        self.cmb_filter.pack(side="left", padx=(4, 0))
        self.cmb_filter.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        f_list = ttk.Frame(self)
        f_list.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("Name", "Type", "Created")
        self.tree = ttk.Treeview(f_list, columns=cols, show="headings", height=10)
        self.tree.heading("Name", text=t("lbl_op_name"));      self.tree.column("Name", width=220)
        self.tree.heading("Type", text=t("col_type"));         self.tree.column("Type", width=90, anchor="center")
        self.tree.heading("Created", text=t("col_lib_created")); self.tree.column("Created", width=90, anchor="center")
        sb = ttk.Scrollbar(f_list, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._insert())

        f_btn = ttk.Frame(self)
        f_btn.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(f_btn, text=t("btn_lib_add"),
                   command=self._add_from_selected).pack(side="left")
        ttk.Button(f_btn, text=t("btn_lib_insert"),
                   command=self._insert).pack(side="left", padx=(4, 0))
        ttk.Button(f_btn, text=t("vc_close"),
                   command=self.destroy).pack(side="right")
        ttk.Button(f_btn, text=t("btn_del_op"),
                   command=self._delete).pack(side="right", padx=(0, 4))
        ttk.Button(f_btn, text=t("ctx_rename"),
                   command=self._rename).pack(side="right", padx=(0, 4))

    # ------------------------------------------------------------------
    def _visible_entries(self):
        """[(library_index, entry)] matching the type filter, name-sorted."""
        i = self.cmb_filter.current()
        want = None if i <= 0 else _TYPES[i - 1]
        out = [(j, e) for j, e in enumerate(self.entries)
               if want is None or e.get("type") == want]
        return sorted(out, key=lambda p: str(p[1].get("name", "")).lower())

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for j, e in self._visible_entries():
            self.tree.insert("", "end", iid=str(j),
                             values=(e.get("name", "?"),
                                     e.get("type", "?").upper(),
                                     e.get("created", "")))

    def _sel_entry_idx(self):
        sel = self.tree.selection()
        try:
            return int(sel[0]) if sel else None
        except (ValueError, IndexError):
            return None

    def _save(self):
        ol.save_library(self.app.get_base_path(), self.entries)

    # ------------------------------------------------------------------
    def _add_from_selected(self):
        """Snapshot the Program tab's anchor-selected op under a name."""
        idx = self.pt._sel_op_idx()
        ops = self.app.params.get("operations", [])
        if idx is None or idx >= len(ops):
            messagebox.showinfo(t("dlg_op_library"), t("msg_lib_noselect"), parent=self)
            return
        self.pt._flush_entries()  # capture pending edits in the snapshot
        op = ops[idx]
        default = op.get("name") or op.get("type", "roughing")
        name = simpledialog.askstring(t("dlg_op_library"), t("msg_lib_name_prompt"),
                                      initialvalue=default, parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if ol.find_by_name(self.entries, name) >= 0:
            if not messagebox.askyesno(t("dlg_op_library"),
                                       t("msg_lib_exists").format(n=name), parent=self):
                return
        machine = str(self.app.params.get("machine_id", "") or "")
        ol.add_entry(self.entries, name, op, machine=machine)
        self._save()
        self._refresh_list()

    def _insert(self):
        j = self._sel_entry_idx()
        if j is None or j >= len(self.entries):
            messagebox.showinfo(t("dlg_op_library"), t("msg_lib_noentry"), parent=self)
            return
        # Dialog stays open — inserting several entries in a row is the point.
        self.pt._insert_from_library(self.entries[j])

    def _rename(self):
        j = self._sel_entry_idx()
        if j is None or j >= len(self.entries):
            return
        new = simpledialog.askstring(t("dlg_op_library"), t("msg_lib_name_prompt"),
                                     initialvalue=self.entries[j].get("name", ""),
                                     parent=self)
        if not new or not new.strip():
            return
        ol.rename_entry(self.entries, j, new.strip())
        self._save()
        self._refresh_list()

    def _delete(self):
        j = self._sel_entry_idx()
        if j is None or j >= len(self.entries):
            return
        if not messagebox.askyesno(t("dlg_op_library"),
                                   t("msg_lib_delete").format(
                                       n=self.entries[j].get("name", "?")), parent=self):
            return
        ol.remove_entry(self.entries, j)
        self._save()
        self._refresh_list()
