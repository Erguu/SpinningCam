# -*- coding: utf-8 -*-
"""Machine settings must not ride along inside a saved program (.ssp).

Field incident 2026-08-14: an operator opened an older program and got that day's
PLC line limit back; the next Machine-tab edit then wrote it permanently into the
machine profile via autosave. The loader now keeps the operator's machine
settings and asks about the differences.

Run:  python _test_project_machine_params.py
"""
import json
import sys

from machine_loader import (MACHINE_PROFILE_KEYS, diff_machine_params,
                            strip_machine_params, _same_value)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


# A machine as the operator has it now, and a program saved earlier.
NOW = {"plc_target_lines": 350, "plc_tolerance": 0.01, "home_x": -382.1,
       "plc_mode": True, "turret_slots": [{"code": 101, "angle": 0.0}],
       "blank_radius": 120.0, "operations": [{"type": "roughing"}]}
FILE = {"plc_target_lines": 1000, "plc_tolerance": 0.01, "home_x": -350.0,
        "plc_mode": True, "turret_slots": [{"code": 999, "angle": 0.0}],
        "blank_radius": 88.0, "operations": [{"type": "finishing"}]}


# ── 1. what counts as a difference ───────────────────────────────────────────
print("\n[1] diff_machine_params")
d = diff_machine_params(NOW, FILE)
keys = [c["key"] for c in d]
check("finds the changed machine settings",
      set(keys) == {"plc_target_lines", "home_x", "turret_slots"}, str(keys))
check("ignores identical values (plc_tolerance, plc_mode)",
      "plc_tolerance" not in keys and "plc_mode" not in keys)
check("never lists program content (blank_radius, operations)",
      "blank_radius" not in keys and "operations" not in keys)
check("order follows MACHINE_PROFILE_KEYS (stable across loads)",
      keys == [k for k in MACHINE_PROFILE_KEYS if k in keys])
check("reports both sides",
      d[0]["current"] != d[0]["loaded"] and "current" in d[0] and "loaded" in d[0])

# JSON round-trips must not invent differences.
rt = json.loads(json.dumps(NOW))
check("a JSON round-trip is not a difference", diff_machine_params(NOW, rt) == [],
      str(diff_machine_params(NOW, rt)))
check("1000 == 1000.0", _same_value(1000, 1000.0))
check("True != 1.0 (plc_mode is stored both ways in the wild)",
      not _same_value(True, 1.0))
check("list order matters", not _same_value([1, 2], [2, 1]))

# Old programs carry no machine keys at all -> nothing to ask about.
check("a program with no machine keys asks nothing",
      diff_machine_params(NOW, {"blank_radius": 5.0}) == [])
check("a key missing on OUR side is not a conflict",
      diff_machine_params({"blank_radius": 1.0}, FILE) == [])


# ── 2. the load policy ───────────────────────────────────────────────────────
print("\n[2] load policy")


def simulate_load(now, file_params, answer):
    """Mirrors main.py load_project: strip machine keys, re-apply accepted ones."""
    params = dict(now)
    conflicts = diff_machine_params(params, file_params)
    accepted = answer(conflicts) if conflicts else {}
    if accepted is None:
        return None                     # load abandoned
    params.update(strip_machine_params(file_params))
    params.update(accepted)
    return params


keep_mine = lambda c: {}
take_all = lambda c: {x["key"]: x["loaded"] for x in c}

p = simulate_load(NOW, FILE, keep_mine)
check("default keeps MY machine settings", p["plc_target_lines"] == 350
      and p["home_x"] == -382.1 and p["turret_slots"][0]["code"] == 101,
      f'target={p["plc_target_lines"]}')
check("...while the program's geometry IS applied",
      p["blank_radius"] == 88.0 and p["operations"][0]["type"] == "finishing")

p = simulate_load(NOW, FILE, take_all)
check("accepting every row takes the file's values", p["plc_target_lines"] == 1000
      and p["home_x"] == -350.0 and p["turret_slots"][0]["code"] == 999)
check("...and still applies the program's geometry", p["blank_radius"] == 88.0)

p = simulate_load(NOW, FILE, lambda c: {"home_x": -350.0})
check("a single accepted row moves only that setting",
      p["home_x"] == -350.0 and p["plc_target_lines"] == 350)

check("cancelling abandons the load", simulate_load(NOW, FILE, lambda c: None) is None)

# No prompt at all when nothing disagrees.
asked = []
simulate_load(NOW, json.loads(json.dumps(NOW)), lambda c: asked.append(c) or {})
check("identical settings never prompt", not asked)

# The old behaviour, for the record: an unfiltered update loses the machine.
old = dict(NOW)
old.update(FILE)
check("(regression guard) the OLD unfiltered merge did revert it",
      old["plc_target_lines"] == 1000)

# strip_machine_params must not touch program content.
s = strip_machine_params(FILE)
check("strip removes every machine key",
      not any(k in s for k in MACHINE_PROFILE_KEYS))
check("strip keeps program content", s["blank_radius"] == 88.0 and "operations" in s)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
