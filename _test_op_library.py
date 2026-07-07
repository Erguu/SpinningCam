"""Headless verification for TODO #71 — ops_library core (CRUD + isolation)."""
import json
import os
import tempfile

import ops_library as ol

tmp = tempfile.mkdtemp()

# --- empty/missing file -> [] ---
assert ol.load_library(tmp) == []
print("missing file -> empty library: OK")

# --- add + save + reload round-trip ---
entries = []
op = {"type": "roughing", "count": 5, "start_z": 10.0, "tool_id": "T0101",
      "r_tool": 74.31, "name": "wide flange"}
i = ol.add_entry(entries, "rough A", op, machine="ID111-1")
assert i == 0 and entries[0]["type"] == "roughing"
assert entries[0]["machine"] == "ID111-1" and entries[0]["created"]
ol.add_entry(entries, "rough B", {"type": "roughing", "count": 2})
ol.add_entry(entries, "finish std", {"type": "finishing", "count": 1})
ol.save_library(tmp, entries)
back = ol.load_library(tmp)
assert len(back) == 3 and back[0]["name"] == "rough A"
assert back[0]["params"]["start_z"] == 10.0
print("add + save + reload round-trip: OK")

# --- snapshot isolation: mutating the source op never touches the entry ---
op["start_z"] = 999.0
op["count"] = 1
assert entries[0]["params"]["start_z"] == 10.0, "entry shares state with source op"
print("snapshot deep-copy isolation: OK")

# --- same-name add overwrites in place ---
j = ol.add_entry(entries, "rough A", {"type": "roughing", "count": 9})
assert j == 0 and len(entries) == 3
assert entries[0]["params"]["count"] == 9
print("same-name overwrite in place: OK")

# --- find / rename / remove ---
assert ol.find_by_name(entries, "finish std") == 2
assert ol.find_by_name(entries, "nope") == -1
ol.rename_entry(entries, 2, "finish tight")
assert entries[2]["name"] == "finish tight"
ol.remove_entry(entries, 1)
assert len(entries) == 2 and ol.find_by_name(entries, "rough B") == -1
print("find/rename/remove: OK")

# --- make_op: fresh dict, enabled, named, never shares state ---
new_op = ol.make_op(entries[0])
assert new_op["enabled"] is True and new_op["name"] == "rough A"
assert new_op["type"] == "roughing" and new_op["count"] == 9
new_op["count"] = 77
assert entries[0]["params"]["count"] == 9, "make_op shares state with the library"
print("make_op fresh + isolated: OK")

# --- corrupt file -> [] (library must never block the app) ---
with open(os.path.join(tmp, ol.LIBRARY_FILE), "w") as f:
    f.write("{ not json !!!")
assert ol.load_library(tmp) == []
with open(os.path.join(tmp, ol.LIBRARY_FILE), "w") as f:
    json.dump({"version": 1, "entries": "not-a-list"}, f)
assert ol.load_library(tmp) == []
print("corrupt file -> empty, no crash: OK")

print("ALL OP LIBRARY TESTS PASSED")
