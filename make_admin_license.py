"""
EMS SoftSpinner — bootstrap the admin license.

The in-app license generator is only reachable once an admin license is loaded,
so the very first admin license must be created here. Requires the EMS private
key (license_private_key.pem) in this folder.

Usage:
    python make_admin_license.py
"""
import os
import license_manager as lm

BASE = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(BASE, "license_private_key.pem")
OUT_PATH = os.path.join(BASE, "admin.lic")

# Machine IDs the admin license may launch (admin also bypasses machine filtering).
ALLOWED_MACHINES = ["ID111-1"]


def main():
    if not os.path.isfile(KEY_PATH):
        raise SystemExit(
            f"Private key not found: {KEY_PATH}\n"
            "Generate one with license_manager.generate_keypair() and keep it safe."
        )
    key = lm.load_private_key(KEY_PATH)
    data = lm.generate_license(
        customer_name="EMS Admin",
        allowed_machines=ALLOWED_MACHINES,
        private_key=key,
        admin=True,
    )
    lm.save_license(OUT_PATH, data)
    print(f"Wrote admin license: {OUT_PATH}")


if __name__ == "__main__":
    main()
