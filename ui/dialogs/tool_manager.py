import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from i18n import t
import tool_library_io
from logger_config import logger

class ToolManager(tk.Toplevel):
    # Curated palette for the tool "Color" dropdown (any PyVista/Tk color name or
    # hex string also works via the "…" picker). Represents the tool in simulation.
    _COLOR_CHOICES = ["orange", "red", "crimson", "gold", "limegreen",
                      "steelblue", "dodgerblue", "cyan", "purple", "dimgray"]

    def __init__(self, parent, ui_manager):
        super().__init__(parent)
        self.ui = ui_manager
        self.editing_id = None

        self.title(t("tm_title"))
        self.geometry("700x600")

        self._create_ui()

    def _create_ui(self):
        # Treeview
        cols = ("ID", "Name", "Radius", "Type", "Color")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80)
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.refresh()

        # Library-level share bundle (portable .zip = tools + their STEP geometry).
        f_io = ttk.Frame(self)
        f_io.pack(fill="x", padx=5)
        tk.Button(f_io, text=t("tm_export_btn"), command=self.export_library,
                  width=18).pack(side="right", padx=3)
        tk.Button(f_io, text=t("tm_import_btn"), command=self.import_library,
                  width=18).pack(side="right", padx=3)

        f_edit = ttk.LabelFrame(self, text=t("tm_frm_editor"))
        f_edit.pack(fill="x", padx=5, pady=5)

        f_entries = ttk.Frame(f_edit)
        f_entries.pack(fill="x", padx=5, pady=5)

        self.entries = {}
        for c in cols:
            f = ttk.Frame(f_entries)
            f.pack(side="left", padx=2)
            tk.Label(f, text=c, font=("Arial", 8)).pack(anchor="w")
            if c == "Color":
                # Curated named colors + a custom picker so the valid options are
                # discoverable. Combobox subclasses Entry, so get/insert/delete used
                # elsewhere still work. Any name PyVista accepts (or a hex like
                # #ff8800) is valid; the sim roller falls back to orange if invalid.
                row = ttk.Frame(f)
                row.pack()
                e = ttk.Combobox(row, width=9, values=self._COLOR_CHOICES)
                e.pack(side="left")
                tk.Button(row, text="…", width=2,
                          command=self._pick_color).pack(side="left")
            else:
                e = ttk.Entry(f, width=10)
                e.pack()
            self.entries[c] = e

        # r_tool row
        f_rt = ttk.Frame(f_edit)
        f_rt.pack(fill="x", padx=5, pady=(2, 0))
        tk.Label(f_rt, text=t("tm_rr_label"), font=("Arial", 8), width=16, anchor="w").pack(side="left")
        self.entry_r_tool = ttk.Entry(f_rt, width=10)
        self.entry_r_tool.pack(side="left")
        tk.Label(f_rt, text=t("tm_rr_hint"),
                 font=("Arial", 7), fg="gray").pack(side="left", padx=6)

        # Calc radius button
        f_calc = ttk.Frame(f_edit)
        f_calc.pack(fill="x", padx=5, pady=(0, 2))
        tk.Button(f_calc, text=t("btn_calc_step"), command=self._calc_radius_from_step,
                  bg="lightblue", width=22).pack(side="left")
        self.lbl_calc_result = tk.Label(f_calc, text="", font=("Arial", 8), fg="gray")
        self.lbl_calc_result.pack(side="left", padx=6)

        # STEP file row
        f_step = ttk.Frame(f_edit)
        f_step.pack(fill="x", padx=5, pady=(0, 2))

        tk.Label(f_step, text=t("lbl_step_file"), font=("Arial", 8), width=10, anchor="w").pack(side="left")
        self.entry_step = ttk.Entry(f_step, width=45)
        self.entry_step.pack(side="left", padx=(0, 4))
        tk.Button(f_step, text=t("btn_browse"), command=self._browse_step, width=10).pack(side="left")
        self.lbl_step_status = tk.Label(f_step, text="", font=("Arial", 8), width=12)
        self.lbl_step_status.pack(side="left", padx=4)

        # Shaft axis + tip offset row
        f_orient = ttk.Frame(f_edit)
        f_orient.pack(fill="x", padx=5, pady=(0, 4))

        tk.Label(f_orient, text=t("lbl_shaft_axis"), font=("Arial", 8)).pack(side="left")
        self.shaft_var = tk.StringVar(value="Z")
        ttk.OptionMenu(f_orient, self.shaft_var, "Z", "X", "Y", "Z").pack(side="left", padx=(0, 12))

        tk.Label(f_orient, text=t("lbl_tip_adj"), font=("Arial", 8)).pack(side="left")
        self.entry_tip_x = ttk.Entry(f_orient, width=7)
        self.entry_tip_x.insert(0, "0.0")
        self.entry_tip_x.pack(side="left", padx=(0, 4))

        tk.Label(f_orient, text="Y:", font=("Arial", 8)).pack(side="left")
        self.entry_tip_y = ttk.Entry(f_orient, width=7)
        self.entry_tip_y.insert(0, "0.0")
        self.entry_tip_y.pack(side="left", padx=(0, 4))

        tk.Label(f_orient, text="Z:", font=("Arial", 8)).pack(side="left")
        self.entry_tip_z = ttk.Entry(f_orient, width=7)
        self.entry_tip_z.insert(0, "0.0")
        self.entry_tip_z.pack(side="left")

        # Rotation row
        f_rot = ttk.Frame(f_edit)
        f_rot.pack(fill="x", padx=5, pady=(0, 4))

        tk.Label(f_rot, text=t("lbl_rotation_deg"), font=("Arial", 8)).pack(side="left")
        self.entry_rot_x = ttk.Entry(f_rot, width=7)
        self.entry_rot_x.insert(0, "0.0")
        self.entry_rot_x.pack(side="left", padx=(0, 4))

        tk.Label(f_rot, text="RY:", font=("Arial", 8)).pack(side="left")
        self.entry_rot_y = ttk.Entry(f_rot, width=7)
        self.entry_rot_y.insert(0, "0.0")
        self.entry_rot_y.pack(side="left", padx=(0, 4))

        tk.Label(f_rot, text="RZ:", font=("Arial", 8)).pack(side="left")
        self.entry_rot_z = ttk.Entry(f_rot, width=7)
        self.entry_rot_z.insert(0, "0.0")
        self.entry_rot_z.pack(side="left")

        # Buttons
        f_btns = ttk.Frame(f_edit)
        f_btns.pack(fill="x", pady=5)

        tk.Button(f_btns, text=t("btn_add_tool"), command=self.add_tool, bg="lightgreen", width=14).pack(side="left", padx=5)
        tk.Button(f_btns, text=t("btn_save_changes"), command=self.update_tool, bg="gold", width=14).pack(side="left", padx=5)
        tk.Button(f_btns, text=t("btn_clear_fields"), command=self.clear_fields, bg="lightgray", width=12).pack(side="left", padx=5)
        tk.Button(f_btns, text=t("btn_delete_selected"), command=self.del_tool, bg="lightcoral", width=14).pack(side="right", padx=5)

        self.lbl_status = tk.Label(f_edit, text=t("tm_status_hint"), fg="gray")
        self.lbl_status.pack(pady=2)

    def _calc_radius_from_step(self):
        step_file = self.entry_step.get().strip()
        if not step_file:
            messagebox.showinfo(t("tm_no_step_title"), t("tm_no_step_msg"))
            return
        def _fv(w):
            try: return float(w.get())
            except ValueError: return 0.0
        tool_draft = {
            "step_file": step_file,
            "shaft_axis": self.shaft_var.get(),
            "step_rotation": [_fv(self.entry_rot_x), _fv(self.entry_rot_y), _fv(self.entry_rot_z)],
            "tip_offset": [_fv(self.entry_tip_x), _fv(self.entry_tip_y), _fv(self.entry_tip_z)],
        }
        try:
            r = self.ui.app.tool_step_loader.get_contact_radius(tool_draft)
            if r is None:
                self.lbl_calc_result.config(text=t("tm_calc_failed"), fg="red")
                return
            self.entries["Radius"].delete(0, tk.END)
            self.entries["Radius"].insert(0, f"{r:.2f}")
            self.lbl_calc_result.config(text=f"→ {r:.2f} mm", fg="green")
        except Exception as e:
            self.lbl_calc_result.config(text="Error", fg="red")
            messagebox.showerror(t("tm_calc_error_title"), str(e))

    def _browse_step(self):
        path = filedialog.askopenfilename(
            title=t("tm_step_browse_title"),
            filetypes=[(t("tm_step_files"), "*.stp *.step *.STP *.STEP"), (t("fd_all_files"), "*.*")]
        )
        if path:
            self.entry_step.delete(0, tk.END)
            self.entry_step.insert(0, path)
            self._refresh_step_status(path)

    def _refresh_step_status(self, path: str):
        if not path:
            self.lbl_step_status.config(text="", fg="gray")
        elif os.path.isfile(path):
            self.lbl_step_status.config(text=t("tm_file_found"), fg="green")
        else:
            self.lbl_step_status.config(text=t("tm_file_not_found"), fg="red")

    def _read_step_fields(self) -> dict:
        step_file = self.entry_step.get().strip()
        shaft_axis = self.shaft_var.get()

        def _f(w):
            try: return float(w.get())
            except ValueError: return 0.0

        tx, ty, tz = _f(self.entry_tip_x), _f(self.entry_tip_y), _f(self.entry_tip_z)
        rx, ry, rz = _f(self.entry_rot_x), _f(self.entry_rot_y), _f(self.entry_rot_z)

        result = {}
        if step_file:
            result["step_file"] = step_file
            result["shaft_axis"] = shaft_axis
            result["tip_offset"] = [tx, ty, tz]
            result["step_rotation"] = [rx, ry, rz]
        return result

    def _populate_step_fields(self, tool: dict):
        self.entry_step.delete(0, tk.END)
        step_file = tool.get("step_file", "")
        if step_file:
            self.entry_step.insert(0, step_file)
        self._refresh_step_status(step_file)
        self.shaft_var.set(tool.get("shaft_axis", "Z"))
        tip = tool.get("tip_offset", [0.0, 0.0, 0.0])
        for widget, val in zip((self.entry_tip_x, self.entry_tip_y, self.entry_tip_z), tip):
            widget.delete(0, tk.END)
            widget.insert(0, str(val))
        rot = tool.get("step_rotation", [0.0, 0.0, 0.0])
        for widget, val in zip((self.entry_rot_x, self.entry_rot_y, self.entry_rot_z), rot):
            widget.delete(0, tk.END)
            widget.insert(0, str(val))
        self.entry_r_tool.delete(0, tk.END)
        rt = tool.get("r_tool")
        if rt is not None:
            self.entry_r_tool.insert(0, str(rt))

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for tool in self.ui.tool_library:
            self.tree.insert("", "end", values=(
                tool.get("id"), tool.get("name"), tool.get("radius"),
                tool.get("type"), tool.get("color")))

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0])["values"]
        if len(vals) < 5:
            return
        for key, val in zip(("ID", "Name", "Radius", "Type", "Color"), vals):
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, val)
        self.editing_id = vals[0]
        tool = next((tl for tl in self.ui.tool_library if str(tl.get("id")) == str(vals[0])), {})
        self._populate_step_fields(tool)
        self.lbl_status.config(text=t("tm_status_editing").format(vals[0]), fg="blue")

    def on_double_click(self, event):
        self.on_select(event)

    def clear_fields(self):
        for e in self.entries.values():
            e.delete(0, tk.END)
        self.entry_step.delete(0, tk.END)
        self.entry_r_tool.delete(0, tk.END)
        self.shaft_var.set("Z")
        for w in (self.entry_tip_x, self.entry_tip_y, self.entry_tip_z,
                  self.entry_rot_x, self.entry_rot_y, self.entry_rot_z):
            w.delete(0, tk.END)
            w.insert(0, "0.0")
        self._refresh_step_status("")
        self.editing_id = None
        self.lbl_status.config(text=t("tm_status_cleared"), fg="gray")

    def _pick_color(self):
        """Open the OS color chooser and write the chosen hex into the Color box."""
        from tkinter import colorchooser
        cur = self.entries["Color"].get().strip() or "orange"
        try:
            _rgb, hexval = colorchooser.askcolor(color=cur, parent=self,
                                                 title=t("tm_color_pick"))
        except tk.TclError:
            # Current value not a color Tk recognises → open without a seed.
            _rgb, hexval = colorchooser.askcolor(parent=self, title=t("tm_color_pick"))
        if hexval:
            self.entries["Color"].delete(0, tk.END)
            self.entries["Color"].insert(0, hexval)

    def _validate_tool_code(self, tool_id: str) -> bool:
        """The PLC tool code = the digits of the ID (T0201 -> 201). It must fit one
        byte (1-255); 0 is the reserved 'empty slot' sentinel. Block add/update with
        a clear message otherwise, so a too-big ID can't be silently clamped in the
        recipe. See CAM_TOOL_TABLE_HANDOVER.md."""
        from recipe_to_scl import tool_code_from_id
        code = tool_code_from_id(tool_id)
        if code <= 0 or code > 255:
            messagebox.showerror(
                t("tm_bad_code_title"),
                t("tm_bad_code_msg").format(id=tool_id, code=code),
                parent=self)
            return False
        return True

    def _build_tool_dict(self) -> dict:
        try:
            rad = float(self.entries["Radius"].get())
        except ValueError:
            rad = 0.0
        tool = {
            "id": self.entries["ID"].get(),
            "name": self.entries["Name"].get() or "Unnamed",
            "radius": rad,
            "type": self.entries["Type"].get() or "roller",
            "color": self.entries["Color"].get() or "red",
        }
        rt_str = self.entry_r_tool.get().strip()
        try:
            tool["r_tool"] = float(rt_str) if rt_str else None
        except ValueError:
            tool["r_tool"] = None
        tool.update(self._read_step_fields())
        return tool

    def add_tool(self):
        new_id = self.entries["ID"].get()
        if not new_id:
            messagebox.showwarning(t("tm_missing_id_title"), t("tm_missing_id_msg"))
            return
        for tl in self.ui.tool_library:
            if tl["id"] == new_id:
                messagebox.showwarning(t("tm_duplicate_id_title"), t("tm_duplicate_id_msg").format(new_id))
                return
        if not self._validate_tool_code(new_id):
            return
        tool = self._build_tool_dict()
        note = self._sync_geometry(tool)
        self.ui.tool_library.append(tool)
        self.ui.save_tools()
        self.refresh()
        self.clear_fields()
        msg = t("tm_status_added").format(new_id)
        if note:
            msg += "  ·  " + t("tm_geom_synced").format(note)
        self.lbl_status.config(text=msg, fg="green")

    def update_tool(self):
        if not self.editing_id:
            messagebox.showinfo(t("tm_select_tool_title"), t("tm_select_edit_msg"))
            return
        new_id = self.entries["ID"].get()
        if not new_id:
            messagebox.showwarning(t("tm_missing_id_title"), t("tm_missing_id_msg"))
            return
        if not self._validate_tool_code(new_id):
            return
        updated = self._build_tool_dict()
        note = self._sync_geometry(updated, old_id=self.editing_id)
        for i, tl in enumerate(self.ui.tool_library):
            if tl["id"] == self.editing_id:
                self.ui.tool_library[i] = updated
                break
        self.ui.save_tools()
        self.refresh()
        msg = t("tm_status_updated").format(new_id)
        if note:
            msg += "  ·  " + t("tm_geom_synced").format(note)
        self.lbl_status.config(text=msg, fg="green")
        self.editing_id = new_id

    def _sync_geometry(self, tool: dict, old_id: str = None) -> str:
        """Copy a browsed STEP into tool_geometry/<id> (and rename on ID change),
        then normalise step_file to the portable convention path. Never fatal."""
        try:
            return tool_library_io.sync_tool_geometry(
                self.ui.app.get_base_path(), tool, old_id=old_id)
        except Exception as e:  # noqa: BLE001 — geometry sync must not block save
            logger.warning(f"tool geometry sync failed: {e}")
            return ""

    def export_library(self):
        if not self.ui.tool_library:
            messagebox.showinfo(t("tm_export_empty_title"), t("tm_export_empty_msg"))
            return
        path = filedialog.asksaveasfilename(
            title=t("tm_export_title"), defaultextension=".zip",
            filetypes=[(t("tm_bundle_files"), "*.zip"), (t("fd_all_files"), "*.*")],
            initialfile="tool_library.zip")
        if not path:
            return
        try:
            n, g = tool_library_io.export_library(
                self.ui.app.get_base_path(), self.ui.tool_library, path)
            messagebox.showinfo(t("tm_export_done_title"),
                                t("tm_export_done_msg").format(n=n, g=g, path=path))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(t("tm_export_err_title"), str(e))

    def import_library(self):
        path = filedialog.askopenfilename(
            title=t("tm_import_title"),
            filetypes=[(t("tm_bundle_files"), "*.zip"), (t("fd_all_files"), "*.*")])
        if not path:
            return
        try:
            incoming = tool_library_io.import_library(self.ui.app.get_base_path(), path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(t("tm_import_err_title"), str(e))
            return
        if not incoming:
            messagebox.showinfo(t("tm_import_title"), t("tm_import_empty_msg"))
            return
        # Merge by ID. On any conflict, ask ONCE whether to overwrite the
        # existing tools or keep them (skip the incoming duplicates).
        existing = {str(tl.get("id")): i for i, tl in enumerate(self.ui.tool_library)}
        conflicts = [tl for tl in incoming if str(tl.get("id")) in existing]
        overwrite = True
        if conflicts:
            overwrite = messagebox.askyesno(
                t("tm_import_conflict_title"),
                t("tm_import_conflict_msg").format(
                    n=len(conflicts),
                    ids=", ".join(str(tl.get("id")) for tl in conflicts)))
        added = updated = skipped = 0
        for tl in incoming:
            tid = str(tl.get("id"))
            if tid in existing:
                if overwrite:
                    self.ui.tool_library[existing[tid]] = tl
                    updated += 1
                else:
                    skipped += 1
            else:
                self.ui.tool_library.append(tl)
                existing[tid] = len(self.ui.tool_library) - 1
                added += 1
        self.ui.save_tools()
        self.refresh()
        messagebox.showinfo(
            t("tm_import_done_title"),
            t("tm_import_done_msg").format(added=added, updated=updated, skipped=skipped))

    def del_tool(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(t("tm_select_tool_title"), t("tm_select_del_msg"))
            return
        tid = self.tree.item(sel[0])["values"][0]
        if messagebox.askyesno(t("tm_confirm_del_title"), t("tm_confirm_del_msg").format(tid)):
            self.ui.tool_library = [tl for tl in self.ui.tool_library if tl["id"] != tid]
            self.ui.save_tools()
            self.refresh()
            self.clear_fields()
            self.lbl_status.config(text=t("tm_status_deleted").format(tid), fg="red")
