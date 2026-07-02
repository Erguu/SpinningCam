import hashlib
import json
import os
import uuid
import winreg
from datetime import date

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

# ── Asymmetric licensing (Ed25519) ────────────────────────────────────────────
# The client ships ONLY this public key and can therefore verify but never sign.
# The matching private key is held off-machine by EMS (license_private_key.pem)
# and is required to generate new licenses. Extracting the public key from the
# binary gains an attacker nothing.
_PUBLIC_KEY_HEX = "3acce7d65fa816d33a15acb7dbbee0accfa9345fc114484cf265ed4d42ed5e9c"
_REQUIRED_FIELDS = ("customer_name", "allowed_machines", "issued_date")


def _canonical(data: dict) -> bytes:
    payload = {k: v for k, v in data.items() if k != "_sig"}
    return json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()


def _public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(_PUBLIC_KEY_HEX))


def generate_keypair() -> tuple[str, str]:
    """One-time setup helper. Returns (private_pem, public_hex).

    Store the private PEM somewhere safe and OFF the shipped client; paste the
    public hex into ``_PUBLIC_KEY_HEX`` above.
    """
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    return priv_pem, pub_hex


def load_private_key(path: str) -> Ed25519PrivateKey:
    """Load the EMS signing key (PEM) used by the license generator."""
    with open(path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Not an Ed25519 private key.")
    return key


def sign_license(data: dict, private_key: Ed25519PrivateKey) -> dict:
    payload = {k: v for k, v in data.items() if k != "_sig"}
    sig = private_key.sign(_canonical(payload)).hex()
    return {**payload, "_sig": sig}


def verify_license(data: dict) -> bool:
    sig = data.get("_sig", "")
    if not sig or not isinstance(sig, str):
        return False
    try:
        _public_key().verify(bytes.fromhex(sig), _canonical(data))
        return True
    except (InvalidSignature, ValueError):
        return False


def validate_license(data: dict) -> tuple[bool, str]:
    for field in _REQUIRED_FIELDS:
        if field not in data:
            return False, f"Missing field: {field}"
    if not isinstance(data["allowed_machines"], list):
        return False, "allowed_machines must be a list"
    if "_sig" not in data:
        return False, "no_sig"
    if not verify_license(data):
        return False, "tampered"
    expiry = data.get("expiry_date")
    if expiry:
        try:
            exp_date = date.fromisoformat(expiry)
            if exp_date < date.today():
                return False, f"License expired on {expiry}"
        except ValueError:
            return False, f"Invalid expiry_date format: {expiry}"
    return True, "ok"


def get_allowed_machines(data: dict):
    if data.get("admin", False):
        return None
    return data.get("allowed_machines", [])


def is_admin(data: dict) -> bool:
    return bool(data.get("admin", False))


def normalize_mac(mac: str) -> str:
    """Reduce a MAC to bare uppercase hex digits so that AA:BB:…, AA-BB:…
    (ipconfig /all uses dashes) and unseparated forms all compare equal."""
    return ''.join(c for c in mac.upper() if c in '0123456789ABCDEF')


def get_mac_address() -> str:
    """Return this machine's primary MAC as uppercase hex (AA:BB:CC:DD:EE:FF).

    Returns '' when the MAC is unreliable. ``uuid.getnode()`` sets the multicast
    bit (LSB of the first octet) when it cannot read a real hardware address and
    falls back to a random 48-bit value that differs on every call. Binding a
    license to such a number would lock out legitimate users, so we treat it as
    unavailable instead.
    """
    mac_int = uuid.getnode()
    if (mac_int >> 40) & 0x01:        # multicast bit set → random / unreliable
        return ""
    return ':'.join(('%012X' % mac_int)[i:i+2] for i in range(0, 12, 2))


def get_windows_guid() -> str:
    """Return the Windows Machine GUID from the registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception:
        return "unavailable"


def get_machine_fingerprint() -> str:
    """Return a 32-char SHA-256 hash of the Windows Machine GUID (strong binding).

    The MachineGuid survives reboots and network-adapter changes (VPNs, virtual
    NICs, docks) and only changes on OS reinstall, making it a far more stable
    anchor than the MAC address, which ``uuid.getnode()`` may randomize.

    Returns '' when the GUID cannot be read — hashing the 'unavailable' marker
    would give every broken machine the same fingerprint, so a license minted
    from it would validate anywhere the registry read fails.
    """
    guid = get_windows_guid()
    if guid == "unavailable":
        return ""
    return hashlib.sha256(guid.encode()).hexdigest()[:32]


def _legacy_fingerprint() -> str:
    """Old MAC+GUID combined fingerprint. Accepted for licenses issued before the
    GUID-only change, but only when a reliable MAC is available."""
    mac = get_mac_address()
    if not mac:
        return ""
    raw = f"{get_windows_guid()}|{mac}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def check_machine_binding(data: dict) -> tuple[bool, str]:
    """
    Check hardware binding. Priority: machine_fingerprint > mac_address > none.
    Returns (True, '') if allowed, (False, reason) if blocked.
    Admin licenses always pass.
    """
    if data.get("admin", False):
        return True, ""

    # Strong binding (fingerprint) — GUID-based, with legacy MAC+GUID fallback
    expected_fp = data.get("machine_fingerprint", "")
    if expected_fp:
        current_fp = get_machine_fingerprint()
        if current_fp and expected_fp == current_fp:
            return True, ""
        legacy_fp = _legacy_fingerprint()
        if legacy_fp and expected_fp == legacy_fp:
            return True, ""
        return False, f"machine_mismatch|{expected_fp}|{current_fp or 'UNAVAILABLE'}"

    # MAC binding
    expected_mac = data.get("mac_address", "")
    if expected_mac:
        current_mac = get_mac_address()
        if not current_mac:
            # MAC could not be read reliably — cannot verify a MAC-bound license.
            return False, f"machine_mismatch|{expected_mac.upper()}|UNAVAILABLE"
        if normalize_mac(current_mac) != normalize_mac(expected_mac):
            return False, f"machine_mismatch|{expected_mac.upper()}|{current_mac.upper()}"
        return True, ""

    return True, ""   # no binding field — allowed on any machine


def generate_license(customer_name: str, allowed_machines: list,
                     private_key: Ed25519PrivateKey,
                     admin: bool = False, expiry: str | None = None,
                     mac_address: str | None = None,
                     machine_fingerprint: str | None = None) -> dict:
    data = {
        "customer_name": customer_name,
        "allowed_machines": allowed_machines,
        "issued_date": date.today().isoformat(),
        "expiry_date": expiry or None,
        "admin": admin,
    }
    if machine_fingerprint:
        data["machine_fingerprint"] = machine_fingerprint.strip()
    elif mac_address:
        data["mac_address"] = mac_address.strip().upper()
    return sign_license(data, private_key)


def save_license(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_license(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_old_license(data: dict) -> dict:
    """Convert old {machine_id, ...} format to new {allowed_machines, ...} format (unsigned)."""
    mid = data.get("machine_id", "")
    result = {k: v for k, v in data.items() if k != "machine_id"}
    if "allowed_machines" not in result:
        result["allowed_machines"] = [mid] if mid else []
    if "issued_date" not in result:
        result["issued_date"] = date.today().isoformat()
    if "expiry_date" not in result:
        result["expiry_date"] = None
    return result


def regenerate_internal_license(base_path: str, private_key_path: str | None = None):
    """Regenerate license.lic at base_path with the Ed25519-signed format (dev/admin use).

    Requires the EMS private key (defaults to license_private_key.pem in base_path).
    """
    path = os.path.join(base_path, "license.lic")
    key_path = private_key_path or os.path.join(base_path, "license_private_key.pem")
    private_key = load_private_key(key_path)
    existing = {}
    if os.path.exists(path):
        try:
            existing = load_license(path)
        except Exception:
            pass
    if "machine_id" in existing and "allowed_machines" not in existing:
        existing = migrate_old_license(existing)
    data = generate_license(
        customer_name=existing.get("customer_name", "EMS Internal"),
        allowed_machines=existing.get("allowed_machines", ["ID111-1"]),
        private_key=private_key,
        admin=existing.get("admin", False),
        expiry=existing.get("expiry_date"),
    )
    save_license(path, data)
    return data
