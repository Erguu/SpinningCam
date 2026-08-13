# -*- coding: utf-8 -*-
"""Export must stop when an operation uses a tool this library does not have.

sync_operation_r_tools skips an operation whose tool it cannot find, so that
operation keeps the r_tool saved inside the .ssp — a reach calibrated on another
machine. Reach is the clearance, so it gouges or collides quietly. Everything
else about tooling self-corrects; this case cannot.

Run:  python _test_missing_tools.py
"""
import sys
import types

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


# missing_library_tools only touches self.tool_library and self.params, so bind
# the real unbound method to a stand-in rather than booting the whole app.
from main import SpinningApp

def app(tools, ops):
    a = types.SimpleNamespace(tool_library=tools, params={"operations": ops})
    a.missing_library_tools = SpinningApp.missing_library_tools.__get__(a, type(a))
    return a


LIB = [{"id": "T0101", "r_tool": 74.31, "radius": 74.0},
       {"id": "T0102", "r_tool": 77.53, "radius": 77.5}]


# ── 1. detection ─────────────────────────────────────────────────────────────
print("\n[1] detection")
check("all tools present -> nothing to report",
      app(LIB, [{"tool_id": "T0101"}, {"tool_id": "T0102"}]).missing_library_tools() == [])

m = app(LIB, [{"tool_id": "T0101"}, {"tool_id": "T0107", "r_tool": 91.4}]).missing_library_tools()
check("an unknown tool is reported", [x["tool_id"] for x in m] == ["T0107"], str(m))
check("carries the reach saved in the file", m[0]["r_tool"] == 91.4)

m = app(LIB, [{"tool_id": "T0107", "name": "Rough 1"},
              {"tool_id": "T0107", "type": "finishing"},
              {"tool_id": "T0109", "type": "roughing"}]).missing_library_tools()
check("groups the operations under one tool", len(m) == 2 and len(m[0]["ops"]) == 2, str(m))
check("uses the operation name when it has one", m[0]["ops"][0] == "Rough 1", str(m[0]["ops"]))
check("falls back to type + position", m[0]["ops"][1] == "finishing #2", str(m[0]["ops"]))
check("keeps first-appearance order", [x["tool_id"] for x in m] == ["T0107", "T0109"])

# ── 2. what must NOT block ───────────────────────────────────────────────────
print("\n[2] must not block")
check("a disabled operation is ignored",
      app(LIB, [{"tool_id": "T0107", "enabled": False}]).missing_library_tools() == [])
check("...but an enabled one beside it still blocks",
      len(app(LIB, [{"tool_id": "T0107", "enabled": False},
                    {"tool_id": "T0109"}]).missing_library_tools()) == 1)
check("an operation with no tool_id is ignored",
      app(LIB, [{"type": "cutting"}]).missing_library_tools() == [])
check("an empty tool library blocks nothing (never strand a user)",
      app([], [{"tool_id": "T0107"}]).missing_library_tools() == [])
check("no operations at all -> nothing",
      app(LIB, []).missing_library_tools() == [])
check("enabled defaults to True (older programs have no flag)",
      len(app(LIB, [{"tool_id": "T0107"}]).missing_library_tools()) == 1)


# ── 3. the message the operator sees ─────────────────────────────────────────
print("\n[3] message")
import i18n
for lang in ("EN", "TR", "ES"):
    i18n.set_language(lang)
    row = i18n.t("mt_row").format(tool="T0107", reach="91.400 mm", ops="Rough 1")
    body = i18n.t("mt_body").format(n=1, rows=row)
    ok = ("T0107" in body and "91.400" in body and "Rough 1" in body
          and i18n.t("mt_title") != "mt_title" and len(body) > 200)
    check(f"{lang}: message renders with the tool, reach and operations", ok)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
