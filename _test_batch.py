"""Headless verification for TODO #67 — batch edit core (_batch_compute + config)."""
from types import SimpleNamespace
from ui.tabs.program_tab import (ProgramTab, OP_PARAM_UNIVERSE, _default_cfg,
                                 _BATCH_ELIGIBLE, _DEFAULT_BATCH_KEYS)

f = ProgramTab._batch_compute
UNI = OP_PARAM_UNIVERSE  # full type->keys map is a fine universe for tests

ops = [
    {"type": "roughing",  "start_z": 10.0, "count": 3, "feed": 100.0},
    {"type": "finishing", "start_z": 25.0},
    {"type": "cutting",   "z_pos": 5.0},           # start_z n/a for cutting
    {"type": "roughing"},                            # no start_z -> default 10
]

# --- add: += 2 on start_z; cutting skipped n/a; missing value uses default ---
changes, skipped = f(ops, [0, 1, 2, 3], "start_z", "add", 2.0, UNI)
assert changes[0] == (10.0, 12.0) and changes[1] == (25.0, 27.0), changes
assert skipped == {2: "na"}, skipped
assert changes[3] == (10, 12.0), changes   # OP_PARAM_DEFAULTS start_z = 10
print("add mode + n/a skip + default fallback: OK")

# --- set: = 50 works even where no base value exists ---
changes, skipped = f(ops, [0, 1], "start_z", "set", 50.0, UNI)
assert changes[0] == (10.0, 50.0) and changes[1] == (25.0, 50.0)
assert not skipped
print("set mode: OK")

# --- scale: ×= 1.5 ---
changes, _ = f(ops, [0], "feed", "scale", 1.5, UNI)
assert changes[0] == (100.0, 150.0), changes
print("scale mode: OK")

# --- nobase: add/scale on a param with a NON-numeric default is skipped ---
changes, skipped = f(ops, [0], "feed_contact", "add", 5.0, UNI)  # default "= Feed"
assert changes == {} and skipped == {0: "nobase"}, (changes, skipped)
# ...but set-mode still applies it
changes, skipped = f(ops, [0], "feed_contact", "set", 80.0, UNI)
assert changes[0] == (None, 80.0) and not skipped
print("nobase skip (add) but set allowed: OK")

# --- count is integer-floored to 1 ---
changes, _ = f(ops, [0], "count", "add", 2.4, UNI)
assert changes[0] == (3, 5), changes                 # round(5.4) -> 5
changes, _ = f(ops, [0], "count", "add", -10.0, UNI)
assert changes[0] == (3, 1), changes                 # floored to 1
changes, _ = f(ops, [0], "count", "scale", 0.5, UNI)
assert changes[0] == (3, 2), changes                 # round(1.5) -> 2
print("count int rounding + floor 1: OK")

# --- bool values never treated as numeric bases ---
ops_b = [{"type": "roughing", "count": True}]        # pathological but safe
changes, _ = f(ops_b, [0], "count", "add", 1.0, UNI)
assert changes[0] == (1, 2), changes                 # falls back to default 1
print("bool never used as numeric base: OK")

# --- config: default batch list is universe ∩ curated ∩ eligible ---
for ot in ("roughing", "finishing", "cutting", "bending"):
    d = _default_cfg(ot)
    assert "batch" in d
    uni = set(OP_PARAM_UNIVERSE[ot])
    for k in d["batch"]:
        assert k in uni and k in _BATCH_ELIGIBLE and k in _DEFAULT_BATCH_KEYS, (ot, k)
assert "start_z" in _default_cfg("roughing")["batch"]
assert "z_pos" in _default_cfg("cutting")["batch"]
print("default cfg batch lists: OK")

# --- _view_cfg: old saved config without 'batch' falls back to defaults;
#     explicit [] is respected ---
fake = SimpleNamespace(app=SimpleNamespace(params={
    "op_view_config": {"roughing": {"columns": ["count"], "advanced": []}}}))
cfg = ProgramTab._view_cfg(fake, "roughing")
assert cfg["batch"] == _default_cfg("roughing")["batch"], cfg["batch"]
fake.app.params["op_view_config"]["roughing"]["batch"] = []
cfg = ProgramTab._view_cfg(fake, "roughing")
assert cfg["batch"] == [], cfg["batch"]
print("_view_cfg batch back-compat (missing->default, []->respected): OK")

# --- eligible set is numeric-only sanity: no known string/bool keys ---
for bad in ("tool_id", "direction", "pass_shape", "speed_mode", "feed_mode",
            "back_pass_enabled", "reach_follow_blank", "tilt_mode"):
    assert bad not in _BATCH_ELIGIBLE, bad
print("eligible set excludes string/bool params: OK")

print("ALL BATCH TESTS PASSED")
