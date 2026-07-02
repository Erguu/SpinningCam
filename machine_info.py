"""
EMS SoftSpinner — Machine Info Tool
Run this on the customer's machine to get the identifiers needed for license generation.
"""
import tkinter as tk
from tkinter import ttk
import uuid
import winreg
import hashlib


def get_mac() -> str:
    mac_int = uuid.getnode()
    if (mac_int >> 40) & 0x01:        # multicast bit set → random / unreliable
        return "unavailable"
    return ':'.join(('%012X' % mac_int)[i:i+2] for i in range(0, 12, 2))


def get_guid() -> str:
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception:
        return "unavailable"


def get_fingerprint(guid: str) -> str:
    # GUID-only: stable across network-adapter changes (MAC is not part of it).
    if guid == "unavailable":
        return "unavailable"
    return hashlib.sha256(guid.encode()).hexdigest()[:32]


class MachineInfoWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EMS SoftSpinner — Machine Info")
        self.resizable(False, False)

        mac  = get_mac()
        guid = get_guid()
        fp   = get_fingerprint(guid)

        self._build(mac, guid, fp)

        self.update_idletasks()
        w, h = 520, 340
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build(self, mac, guid, fp):
        PX = 18
        f = ttk.Frame(self, padding=(PX, 14, PX, 14))
        f.pack(fill="both", expand=True)

        tk.Label(f, text="EMS SoftSpinner — Machine Identifier",
                 font=("Arial", 12, "bold")).pack(anchor="w")
        tk.Label(f, text="Send all three values to EMS to receive your license file.",
                 font=("Arial", 9), fg="#555").pack(anchor="w", pady=(2, 12))

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(0, 12))

        self._add_row(f, "MAC Address",       mac,  "Used for standard license binding.")
        self._add_row(f, "Windows GUID",      guid, "Used for strong license binding.")
        self._add_row(f, "Fingerprint", fp, "Hash of Windows GUID (for strong binding).")

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(12, 8))

        all_text = f"MAC Address:          {mac}\nWindows GUID:         {guid}\nFingerprint:          {fp}"
        ttk.Button(f, text="Copy All to Clipboard",
                   command=lambda: self._copy(all_text)).pack(anchor="e")

    def _add_row(self, parent, label: str, value: str, hint: str):
        frm = ttk.Frame(parent)
        frm.pack(fill="x", pady=3)

        tk.Label(frm, text=label + ":", font=("Arial", 9, "bold"),
                 width=22, anchor="w").pack(side="left")
        tk.Label(frm, text=value, font=("Courier", 9),
                 fg="#1a1a7a").pack(side="left", padx=(4, 8))
        ttk.Button(frm, text="Copy",
                   command=lambda v=value: self._copy(v)).pack(side="left")
        tk.Label(frm, text=hint, font=("Arial", 8), fg="#888").pack(side="left", padx=(10, 0))

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()


if __name__ == "__main__":
    MachineInfoWindow().mainloop()
