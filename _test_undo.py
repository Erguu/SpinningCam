"""Headless verification for TODO #66 — OpUndoStack (snapshot undo/redo for op list)."""
from ui.tabs.program_tab import OpUndoStack

# --- basic undo: push before mutation, undo restores the pre-state ---
s = OpUndoStack()
ops = [{"type": "roughing", "count": 5, "start_z": 10.0}]
s.push("Split", ops, sel_idx=0)
# simulate the mutation (split into two chunk-ops)
ops_after = [{"type": "roughing", "count": 2, "start_z": 10.0},
             {"type": "roughing", "count": 3, "start_z": 30.0}]
res = s.undo(ops_after, current_sel=1)
assert res is not None
label, restored, sel = res
assert label == "Split" and sel == 0
assert restored == [{"type": "roughing", "count": 5, "start_z": 10.0}], restored
assert s.can_redo and not s.can_undo
print("undo restores pre-action snapshot: OK")

# --- redo: re-applies the undone state ---
res2 = s.redo(restored, current_sel=0)
label2, re_ops, sel2 = res2
assert label2 == "Split" and sel2 == 1
assert re_ops == ops_after, re_ops
assert s.can_undo and not s.can_redo
print("redo re-applies the undone state: OK")

# --- deep-copy isolation: mutating the live list must not corrupt snapshots ---
s2 = OpUndoStack()
live = [{"type": "roughing", "start_z": 10.0}]
s2.push("Delete", live)
live[0]["start_z"] = 999.0          # live edit after the snapshot
live.append({"type": "finishing"})
_, snap, _ = s2.undo(live)
assert snap == [{"type": "roughing", "start_z": 10.0}], snap
print("deep-copy isolation (live edits don't corrupt snapshots): OK")

# --- a new push clears the redo stack (standard editor semantics) ---
s3 = OpUndoStack()
s3.push("A", [{"n": 1}])
s3.undo([{"n": 2}])
assert s3.can_redo
s3.push("B", [{"n": 1}])            # new action after undo
assert not s3.can_redo and s3.can_undo
print("new action clears redo: OK")

# --- depth limit: oldest snapshot drops off silently at DEPTH ---
s4 = OpUndoStack()
for i in range(OpUndoStack.DEPTH + 5):
    s4.push(f"step{i}", [{"n": i}])
count = 0
cur = [{"n": "live"}]
while s4.can_undo:
    _, cur, _ = s4.undo(cur)
    count += 1
assert count == OpUndoStack.DEPTH, count
assert cur == [{"n": 5}], cur       # steps 0..4 were dropped; oldest kept = 5
print(f"depth limit {OpUndoStack.DEPTH}, oldest dropped: OK")

# --- empty stacks return None; clear() wipes both ---
s5 = OpUndoStack()
assert s5.undo([]) is None and s5.redo([]) is None
s5.push("X", [{"n": 1}])
s5.undo([{"n": 2}])
s5.clear()
assert not s5.can_undo and not s5.can_redo
print("empty-stack None + clear(): OK")

# --- interleaved: undo twice, redo once lands on the middle state ---
s6 = OpUndoStack()
v0, v1, v2 = [{"v": 0}], [{"v": 1}], [{"v": 2}]
s6.push("add1", v0)   # before v0 -> v1
s6.push("add2", v1)   # before v1 -> v2
_, back1, _ = s6.undo(v2)          # v2 -> v1
assert back1 == v1
_, back0, _ = s6.undo(back1)       # v1 -> v0
assert back0 == v0
_, fwd1, _ = s6.redo(back0)        # v0 -> v1
assert fwd1 == v1
assert s6.can_undo and s6.can_redo
print("interleaved undo/undo/redo sequence: OK")

print("ALL UNDO TESTS PASSED")
