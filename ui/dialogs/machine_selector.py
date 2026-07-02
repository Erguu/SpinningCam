import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from machine_adapter import parse_machine_id, get_type_description
from i18n import t
import license_manager


class MachineSelector(tk.Toplevel):
    """
    Startup dialog — three steps in one window:
      1. Load license .lic file  (required — determines which machine types are shown)
      2. Pick machine type / ID  (filtered by license)
      3. Browse for customer settings  (optional)

    result dict on success:
      {
        "profile":  {...},   # machine profile dict (from machines/*.json)
        "license":  {...},   # parsed license dict
        "settings": {...} or None,
      }
    result is None if user closes without launching.
    """

    def __init__(self, parent, type_list: list, base_dir: str,
                 saved_license_path: str = "", saved_settings_path: str = ""):
        """
        type_list: [(type_code, sample_profile), ...]  from get_unique_types()
        base_dir:  app base path (used by find_or_create_profile)
        saved_license_path / saved_settings_path: remembered from last session
        """
        super().__init__(parent)
        self.title("EMS SoftSpinner — Machine & License")
        self.resizable(True, True)
        self.minsize(540, 480)
        self.result = None
        self._type_list = type_list
        self._base_dir = base_dir
        self._license_data = None
        self._settings_data = None
        self._license_path = ""
        self._settings_path = ""
        self._allowed_machines = None   # None = admin (all); list = restricted
        self._is_admin = False

        self._build()
        self.grab_set()

        self.update_idletasks()
        w, h = 620, 500
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-load saved paths — may trigger auto-launch
        if saved_license_path:
            self._auto_load(saved_license_path, saved_settings_path)

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build(self):
        PX = 16

        tk.Label(self, text="EMS SoftSpinner",
                 font=("Arial", 14, "bold"), fg="#222").pack(pady=(14, 0))
        tk.Label(self, text="Load your license file to see available machines.",
                 font=("Arial", 9), fg="#555").pack(pady=(0, 10))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=PX)

        # ── Step 1: license ──
        f1 = ttk.LabelFrame(self, text="  1 · License File  ")
        f1.pack(fill="x", padx=PX, pady=(10, 4))

        fr_lic = ttk.Frame(f1)
        fr_lic.pack(fill="x", padx=6, pady=6)
        ttk.Button(fr_lic, text="Browse License (.lic)…",
                   command=self._browse_license).pack(side="left")
        self._lic_label = tk.Label(fr_lic, text="—  No license loaded",
                                   fg="#888", font=("Arial", 9))
        self._lic_label.pack(side="left", padx=10)

        # ── Step 2: machine type tree ──
        f2 = ttk.LabelFrame(self, text="  2 · Machine Type  ")
        f2.pack(fill="x", padx=PX, pady=4)

        cols = ("machine_id", "type", "category", "process", "variant")
        self._tree = ttk.Treeview(f2, columns=cols, show="headings",
                                  height=4, selectmode="browse")
        self._tree.heading("machine_id", text="Machine ID")
        self._tree.heading("type",       text="Type")
        self._tree.heading("category",   text="Category")
        self._tree.heading("process",    text="Process")
        self._tree.heading("variant",    text="Variant")
        self._tree.column("machine_id", width=100, anchor="center")
        self._tree.column("type",       width=70,  anchor="center")
        self._tree.column("category",   width=90,  anchor="center")
        self._tree.column("process",    width=140, anchor="center")
        self._tree.column("variant",    width=160, anchor="center")
        self._tree.pack(fill="x", padx=6, pady=6)

        self._populate_tree(allowed=None)  # show all initially (grayed out until license loaded)

        # ── Step 3: settings (optional) ──
        f3 = ttk.LabelFrame(self, text="  3 · Customer Settings  (optional)  ")
        f3.pack(fill="x", padx=PX, pady=4)

        fr_set = ttk.Frame(f3)
        fr_set.pack(fill="x", padx=6, pady=6)
        ttk.Button(fr_set, text="Browse Settings (.json)…",
                   command=self._browse_settings).pack(side="left")
        self._set_label = tk.Label(fr_set, text="—  Using default settings",
                                   fg="#888", font=("Arial", 9))
        self._set_label.pack(side="left", padx=10)

        # ── Buttons ──
        f_btn = ttk.Frame(self)
        f_btn.pack(side="bottom", fill="x", padx=16, pady=(6, 14))
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x", padx=16)

        self._btn_launch = ttk.Button(f_btn, text="Launch", command=self._launch,
                                      state="disabled")
        self._btn_launch.pack(side="right", padx=4)
        ttk.Button(f_btn, text="Exit", command=self._on_close).pack(side="right", padx=4)

        self._btn_gen_lic = ttk.Button(f_btn, text=t("btn_generate_license"),
                                       command=self._open_license_generator)
        # hidden until admin license is loaded

    # ── Tree helpers ────────────────────────────────────────────────────────

    def _all_machine_entries(self):
        """Return [(machine_id, type_code), ...] for all profiles on disk."""
        from machine_loader import list_machine_profiles
        profiles = list_machine_profiles(self._base_dir)
        entries = []
        for p in profiles:
            mid = p.get("machine_id", "")
            if mid:
                tc, _ = parse_machine_id(mid)
                entries.append((mid, tc))
        return entries

    def _populate_tree(self, allowed):
        """Repopulate the treeview. allowed=None → show all; list → filter."""
        for item in self._tree.get_children():
            self._tree.delete(item)

        entries = self._all_machine_entries()
        shown = 0
        for mid, tc in entries:
            if allowed is not None and mid not in allowed:
                continue
            cat, proc, var = get_type_description(tc)
            self._tree.insert("", "end", iid=mid,
                              values=(mid, f"ID{tc}", cat, proc, var))
            shown += 1

        if shown > 0:
            children = self._tree.get_children()
            self._tree.selection_set(children[0])
            self._tree.focus(children[0])

        return shown

    # ── Actions ─────────────────────────────────────────────────────────────

    def _reset_license_state(self):
        """Clear everything a previously loaded license set up, so a failed
        re-load can't leave the admin generator button / machine filter behind."""
        self._license_data = None
        self._license_path = ""
        self._is_admin = False
        self._allowed_machines = None
        self._btn_gen_lic.pack_forget()
        self._btn_launch.config(state="disabled")
        self._populate_tree(allowed=None)

    def _browse_license(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select License File",
            filetypes=[("License files", "*.lic"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            lic = license_manager.load_license(path)
        except Exception as e:
            messagebox.showerror("License Error", f"Cannot read license file:\n{e}", parent=self)
            return

        # ── Backward compat: old format has machine_id instead of allowed_machines ──
        is_old_format = "machine_id" in lic and "allowed_machines" not in lic
        if is_old_format:
            lic = license_manager.migrate_old_license(lic)

        # ── Signature check ──
        ok, reason = license_manager.validate_license(lic)
        if not ok:
            self._reset_license_state()
            if reason == "no_sig" or is_old_format:
                # Unsigned / legacy licenses are rejected — signing is mandatory.
                messagebox.showwarning(t("msg_lic_tampered_title"),
                                       t("msg_lic_unsigned_body"), parent=self)
                self._lic_label.config(text=f"✗  {t('lbl_license_unsigned')}", fg="#cc0000")
            elif reason == "tampered":
                messagebox.showwarning(t("msg_lic_tampered_title"),
                                       t("msg_lic_tampered_body"), parent=self)
                self._lic_label.config(text=f"✗  {t('lbl_license_tampered')}", fg="#cc0000")
            else:
                self._lic_label.config(text=f"✗  {reason}", fg="#cc0000")
            return
        else:
            customer = lic.get("customer_name", "")
            admin_tag = "  [Admin]" if lic.get("admin") else ""
            expiry = lic.get("expiry_date")
            expiry_tag = f"  · exp {expiry}" if expiry else ""
            self._lic_label.config(
                text=f"✓  {t('lbl_license_valid')}  ·  {customer}{admin_tag}{expiry_tag}",
                fg="#1a7a1a",
            )

        # ── MAC address binding check ──
        mac_ok, mac_reason = license_manager.check_machine_binding(lic)
        if not mac_ok:
            parts = mac_reason.split("|")
            expected = parts[1] if len(parts) > 1 else "?"
            current  = parts[2] if len(parts) > 2 else "?"
            body = t("msg_mac_mismatch_body").format(expected=expected, current=current)
            self._reset_license_state()
            messagebox.showerror(t("msg_mac_mismatch_title"), body, parent=self)
            self._lic_label.config(text=f"✗  {t('msg_mac_mismatch_title')}", fg="#cc0000")
            return

        self._license_data = lic
        self._license_path = path
        self._is_admin = license_manager.is_admin(lic)
        self._allowed_machines = license_manager.get_allowed_machines(lic)

        # ── Filter / show generator ──
        shown = self._populate_tree(allowed=self._allowed_machines)

        if self._is_admin:
            self._btn_gen_lic.pack(side="left", padx=4)
        else:
            self._btn_gen_lic.pack_forget()

        if shown == 0 and not self._is_admin:
            self._lic_label.config(
                text=f"✗  {t('lbl_license_no_machines')}", fg="#cc0000"
            )
            self._btn_launch.config(state="disabled")
            return

        self._btn_launch.config(state="normal")

    def _browse_settings(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Customer Settings File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Settings file must be a JSON object.")
        except Exception as e:
            messagebox.showerror("Settings Error", f"Cannot read settings file:\n{e}", parent=self)
            return

        self._settings_data = data
        self._settings_path = path
        fname = os.path.basename(path)
        self._set_label.config(text=f"✓  {fname}", fg="#1a7a1a")

    def _launch(self):
        if not self._license_data:
            messagebox.showwarning("License Required",
                                   "Please load a license file first.", parent=self)
            return

        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Machine Selected",
                                   "Please select a machine from the list.", parent=self)
            return

        machine_id = sel[0]  # iid is the machine_id

        from machine_loader import find_or_create_profile
        try:
            profile = find_or_create_profile(machine_id, self._base_dir)
        except Exception as e:
            messagebox.showerror("Profile Error",
                                 f"Cannot load machine profile:\n{e}", parent=self)
            return

        self.result = {
            "profile":       profile,
            "license":       self._license_data,
            "settings":      self._settings_data,
            "license_path":  self._license_path,
            "settings_path": self._settings_path,
        }
        self.destroy()

    def _auto_load(self, license_path: str, settings_path: str):
        """Silently load saved paths. Auto-launches if license is valid and only one machine matches."""
        # ── License ──────────────────────────────────────────────────────────
        if not license_path or not os.path.isfile(license_path):
            return

        try:
            lic = license_manager.load_license(license_path)
        except Exception:
            return

        is_old_format = "machine_id" in lic and "allowed_machines" not in lic
        if is_old_format:
            lic = license_manager.migrate_old_license(lic)

        # Surface the reason in the label (no modal on the silent auto-load path)
        # so the user understands why a previously-working license stopped launching.
        ok, reason = license_manager.validate_license(lic)
        if is_old_format or reason == "no_sig":
            self._lic_label.config(text=f"✗  {t('lbl_license_unsigned')}", fg="#cc0000")
            return
        if not ok:
            if reason == "tampered":
                self._lic_label.config(text=f"✗  {t('lbl_license_tampered')}", fg="#cc0000")
            elif reason.startswith("License expired"):
                self._lic_label.config(text=f"✗  {t('lbl_license_expired')}", fg="#cc0000")
            else:
                self._lic_label.config(text=f"✗  {reason}", fg="#cc0000")
            return

        mac_ok, _ = license_manager.check_machine_binding(lic)
        if not mac_ok:
            self._lic_label.config(text=f"✗  {t('msg_mac_mismatch_title')}", fg="#cc0000")
            return  # wrong machine — don't auto-load, let user see the error manually

        # All checks passed — populate state exactly like _browse_license does
        self._license_data = lic
        self._license_path = license_path
        self._is_admin = license_manager.is_admin(lic)
        self._allowed_machines = license_manager.get_allowed_machines(lic)

        # Update label
        customer = lic.get("customer_name", "")
        admin_tag = "  [Admin]" if lic.get("admin") else ""
        expiry = lic.get("expiry_date")
        expiry_tag = f"  · exp {expiry}" if expiry else ""
        self._lic_label.config(
            text=f"✓  {t('lbl_license_valid')}  ·  {customer}{admin_tag}{expiry_tag}",
            fg="#1a7a1a",
        )

        shown = self._populate_tree(allowed=self._allowed_machines)
        if self._is_admin:
            self._btn_gen_lic.pack(side="left", padx=4)

        if shown == 0 and not self._is_admin:
            self._lic_label.config(text=f"✗  {t('lbl_license_no_machines')}", fg="#cc0000")
            return

        self._btn_launch.config(state="normal")

        # ── Settings ─────────────────────────────────────────────────────────
        if settings_path and os.path.isfile(settings_path):
            try:
                import json
                with open(settings_path, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                if isinstance(sdata, dict):
                    self._settings_data = sdata
                    self._settings_path = settings_path
                    self._set_label.config(
                        text=f"✓  {os.path.basename(settings_path)}", fg="#1a7a1a"
                    )
            except Exception:
                pass

        # ── Auto-launch if only one machine is available ──────────────────────
        if shown == 1 and not self._is_admin:
            # Select the single item and launch silently
            items = self._tree.get_children()
            if items:
                self._tree.selection_set(items[0])
                self._launch()

    def _open_license_generator(self):
        from ui.dialogs.license_generator import LicenseGenerator
        LicenseGenerator(self, base_dir=self._base_dir)

    def _on_close(self):
        self.result = None
        self.destroy()
