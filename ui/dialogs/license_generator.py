import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date as _date

from i18n import t
import license_manager


class LicenseGenerator(tk.Toplevel):
    """Admin-only dialog for generating signed customer license files."""

    def __init__(self, parent, base_dir: str):
        super().__init__(parent)
        self.title(t("btn_generate_license"))
        self.resizable(False, False)
        self._base_dir = base_dir
        self._check_vars = {}   # machine_id → BooleanVar

        self._build()
        self.grab_set()

        self.update_idletasks()
        w, h = 500, 480
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build(self):
        PX = 14
        f = ttk.Frame(self, padding=PX)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        # ── Customer name ──
        ttk.Label(f, text=t("lbl_gen_customer") + ":").grid(
            row=0, column=0, sticky="w", pady=4)
        self._var_customer = tk.StringVar()
        ttk.Entry(f, textvariable=self._var_customer, width=36).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        # ── Expiry date ──
        ttk.Label(f, text=t("lbl_gen_expiry") + ":").grid(
            row=1, column=0, sticky="w", pady=4)
        self._var_expiry = tk.StringVar()
        ttk.Entry(f, textvariable=self._var_expiry, width=36).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        # ── Binding mode ──
        ttk.Label(f, text="Machine Binding:").grid(
            row=2, column=0, sticky="nw", pady=(8, 4))

        fr_bind = ttk.Frame(f)
        fr_bind.grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 4))

        self._bind_mode = tk.StringVar(value="strong")
        ttk.Radiobutton(fr_bind, text="None  (any machine)",
                        variable=self._bind_mode, value="none",
                        command=self._on_bind_change).pack(anchor="w")
        ttk.Radiobutton(fr_bind, text="MAC Address  (customer reads from ipconfig /all)",
                        variable=self._bind_mode, value="mac",
                        command=self._on_bind_change).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(fr_bind, text="Strong  (Windows GUID fingerprint)",
                        variable=self._bind_mode, value="strong",
                        command=self._on_bind_change).pack(anchor="w", pady=(4, 0))

        # ── Identifier entry (shown for mac / strong modes) ──
        self._fr_id = ttk.Frame(f)
        self._fr_id.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(2, 6))

        self._lbl_id = ttk.Label(self._fr_id, text="Value:")
        self._lbl_id.pack(side="left")
        self._var_id = tk.StringVar()
        self._entry_id = ttk.Entry(self._fr_id, textvariable=self._var_id, width=28)
        self._entry_id.pack(side="left", padx=(6, 6))
        self._btn_read = ttk.Button(self._fr_id, text="Read from THIS PC",
                                    command=self._read_identifier)
        self._btn_read.pack(side="left")

        self._on_bind_change()   # reflect the default binding mode (Strong)

        # ── Admin checkbox ──
        self._var_admin = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=t("lbl_gen_admin"),
                        variable=self._var_admin).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=4)

        # ── Machines list ──
        ttk.Label(f, text=t("lbl_gen_machines") + ":").grid(
            row=5, column=0, sticky="nw", pady=(8, 0))

        frm_machines = ttk.Frame(f, relief="sunken", padding=4)
        frm_machines.grid(row=5, column=1, columnspan=2, sticky="nsew",
                          padx=(8, 0), pady=(8, 0))
        f.rowconfigure(5, weight=1)

        self._load_machine_checkboxes(frm_machines)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=PX, pady=(6, 0))

        f_btn = ttk.Frame(self)
        f_btn.pack(fill="x", padx=PX, pady=(6, 12))
        ttk.Button(f_btn, text=t("btn_generate_license"),
                   command=self._generate).pack(side="right", padx=4)
        ttk.Button(f_btn, text="Cancel",
                   command=self.destroy).pack(side="right", padx=4)

    def _load_machine_checkboxes(self, parent):
        from machine_loader import list_machine_profiles
        profiles = list_machine_profiles(self._base_dir)
        if not profiles:
            ttk.Label(parent, text="No machine profiles found.",
                      foreground="#888").pack(anchor="w")
            return
        for p in profiles:
            mid = p.get("machine_id", "")
            name = p.get("machine_name", mid)
            if not mid:
                continue
            var = tk.BooleanVar(value=True)
            self._check_vars[mid] = var
            ttk.Checkbutton(parent, text=f"{mid}  —  {name}", variable=var).pack(anchor="w", pady=2)

    # ── Binding mode helpers ─────────────────────────────────────────────────

    def _on_bind_change(self):
        mode = self._bind_mode.get()
        if mode == "none":
            self._fr_id.grid_remove()
        else:
            self._fr_id.grid()
            if mode == "mac":
                self._lbl_id.config(text="MAC Address:")
            else:
                self._lbl_id.config(text="Fingerprint:")
            self._var_id.set("")

    def _read_identifier(self):
        mode = self._bind_mode.get()
        if mode == "mac":
            value = license_manager.get_mac_address()
        else:
            value = license_manager.get_machine_fingerprint()
        if not value:
            messagebox.showwarning(
                t("btn_generate_license"),
                "This PC's identifier could not be read reliably. "
                "Enter the customer's value manually.", parent=self)
        self._var_id.set(value)

    def _load_signing_key(self):
        """Load the EMS Ed25519 private key. Uses license_private_key.pem in the
        app dir if present, otherwise prompts. Returns the key or None."""
        default = os.path.join(self._base_dir, "license_private_key.pem")
        path = default if os.path.isfile(default) else filedialog.askopenfilename(
            parent=self,
            title="Select EMS Signing Key (private .pem)",
            filetypes=[("PEM private key", "*.pem"), ("All files", "*.*")],
        )
        if not path:
            return None
        try:
            return license_manager.load_private_key(path)
        except Exception as e:
            messagebox.showerror(t("btn_generate_license"),
                                 f"Cannot load signing key:\n{e}", parent=self)
            return None

    # ── Generate ─────────────────────────────────────────────────────────────

    def _generate(self):
        customer = self._var_customer.get().strip()
        if not customer:
            messagebox.showwarning(t("btn_generate_license"),
                                   "Customer name is required.", parent=self)
            return

        allowed = [mid for mid, var in self._check_vars.items() if var.get()]
        if not allowed and not self._var_admin.get():
            messagebox.showwarning(t("btn_generate_license"),
                                   "Select at least one machine.", parent=self)
            return

        expiry_raw = self._var_expiry.get().strip()
        expiry = expiry_raw if expiry_raw else None
        if expiry:
            try:
                _date.fromisoformat(expiry)
            except ValueError:
                messagebox.showwarning(t("btn_generate_license"),
                                       "Invalid expiry date format. Use YYYY-MM-DD.", parent=self)
                return

        mode = self._bind_mode.get()
        id_val = self._var_id.get().strip()
        mac_address = None
        machine_fingerprint = None

        if mode == "mac":
            if not id_val:
                messagebox.showwarning(t("btn_generate_license"),
                                       "Enter the customer's MAC address or click 'Read from THIS PC'.",
                                       parent=self)
                return
            if len(license_manager.normalize_mac(id_val)) != 12:
                messagebox.showwarning(t("btn_generate_license"),
                                       "MAC address must contain 12 hex digits "
                                       "(e.g. AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF).",
                                       parent=self)
                return
            mac_address = id_val
        elif mode == "strong":
            if not id_val:
                messagebox.showwarning(t("btn_generate_license"),
                                       "Enter the customer's fingerprint or click 'Read from THIS PC'.",
                                       parent=self)
                return
            if len(id_val) != 32 or any(c not in "0123456789abcdef" for c in id_val.lower()):
                messagebox.showwarning(t("btn_generate_license"),
                                       "Fingerprint must be exactly 32 hex characters "
                                       "(as shown by the Machine Info tool).",
                                       parent=self)
                return
            machine_fingerprint = id_val.lower()

        # Load the signing key up front — no point asking for a save path without it.
        private_key = self._load_signing_key()
        if private_key is None:
            return

        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save License File",
            defaultextension=".lic",
            filetypes=[("License files", "*.lic"), ("All files", "*.*")],
            initialfile=f"{customer.replace(' ', '_')}.lic",
        )
        if not save_path:
            return

        data = license_manager.generate_license(
            customer_name=customer,
            allowed_machines=allowed,
            private_key=private_key,
            admin=self._var_admin.get(),
            expiry=expiry,
            mac_address=mac_address,
            machine_fingerprint=machine_fingerprint,
        )
        license_manager.save_license(save_path, data)
        messagebox.showinfo(t("msg_lic_saved_title"), t("msg_lic_saved_body"), parent=self)
        self.destroy()
