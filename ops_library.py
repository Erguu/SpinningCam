"""Operation library (#71) — named, reusable operation presets.

Generalizes the one-slot-per-type ``op_presets`` (Save as Default): any number
of named entries per op type, stored app-level in ``ops_library.json`` next to
the exe (like tools.json — survives programs, user-generated at runtime, never
shipped; listed in packaging_manifest.NOT_SHIPPED). Sharing between PCs = copy
the file.

Pure module, no Tk — headless-tested by _test_op_library.py. The dialog
(ui/dialogs/op_library_dialog.py) and ProgramTab wrap it with UI.

⚠️ r_tool staleness: entries snapshot the op incl. tool_id/r_tool. The INSERT
path must re-sync r_tool from the live tool library (app.sync_operation_r_tools)
so an old entry cannot reintroduce a stale calibrated reach — the caller
(ProgramTab._insert_from_library) is responsible for that, not this module.
"""
import copy
import json
import os
from datetime import date

LIBRARY_FILE = "ops_library.json"


def _path(base_dir):
    return os.path.join(base_dir, LIBRARY_FILE)


def load_library(base_dir):
    """List of entry dicts; [] when the file is missing or unreadable (a corrupt
    library must never block the app — it is convenience data only)."""
    try:
        with open(_path(base_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def save_library(base_dir, entries):
    with open(_path(base_dir), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": entries}, f, indent=2, ensure_ascii=False)


def find_by_name(entries, name):
    """Index of the entry with this (exact) name, or -1."""
    for i, e in enumerate(entries):
        if e.get("name") == name:
            return i
    return -1


def add_entry(entries, name, op, machine=""):
    """Append (or overwrite same-name) entry snapshotting the op. Returns index."""
    entry = {
        "name": str(name),
        "type": op.get("type", "roughing"),
        "params": copy.deepcopy(dict(op)),
        "created": date.today().isoformat(),
        "machine": machine or "",
    }
    i = find_by_name(entries, entry["name"])
    if i >= 0:
        entries[i] = entry
        return i
    entries.append(entry)
    return len(entries) - 1


def remove_entry(entries, idx):
    if 0 <= idx < len(entries):
        entries.pop(idx)


def rename_entry(entries, idx, new_name):
    if 0 <= idx < len(entries):
        entries[idx]["name"] = str(new_name)


def make_op(entry):
    """A fresh op dict ready to insert into a program: deep copy (never shares
    state with the library), enabled, named after the entry."""
    op = copy.deepcopy(entry.get("params", {}))
    op["type"] = entry.get("type", op.get("type", "roughing"))
    op["enabled"] = True
    op["name"] = entry.get("name", "")
    return op
