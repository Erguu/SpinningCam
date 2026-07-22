"""Headless validation of the operation-reorder math shared by the ▲▼ buttons,
drag & drop, and 'Move to #…'. Mirrors _reorder_to / move_op / drag conversion
in ui/tabs/program_tab.py. Pure list logic — no Tk needed."""


def reorder(ops, targets, new_start):
    """Mirror of ProgramTab._reorder_to core (remaining-space new_start)."""
    targets = sorted(targets)
    n, k = len(ops), len(targets)
    new_start = max(0, min(new_start, n - k))
    tset = set(targets)
    remaining = [op for i, op in enumerate(ops) if i not in tset]
    sel = [ops[i] for i in targets]
    return remaining[:new_start] + sel + remaining[new_start:]


def move_op_new_start(ops, targets, d):
    """Mirror of move_op's new_start computation."""
    n, k = len(ops), len(targets)
    t = sorted(targets)
    return max(0, t[0] - 1) if d < 0 else min(n - k, t[0] + 1)


def drag_new_start(targets, pos):
    """Mirror of _on_drag_release: display insert index -> remaining-space start."""
    tset = set(targets)
    return sum(1 for i in range(pos) if i not in tset)


def moveto_new_start(ans):
    """Mirror of move_op_to_position: 1-based line -> new_start."""
    return ans - 1


L = ["A", "B", "C", "D", "E"]
fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got}, want {want}")


# ── ▲▼ single-row moves ────────────────────────────────────────────────────
check("up C", reorder(L, [2], move_op_new_start(L, [2], -1)), ["A", "C", "B", "D", "E"])
check("down C", reorder(L, [2], move_op_new_start(L, [2], 1)), ["A", "B", "D", "C", "E"])
check("up A (edge no-op)", reorder(L, [0], move_op_new_start(L, [0], -1)), L)
check("down E (edge no-op)", reorder(L, [4], move_op_new_start(L, [4], 1)), L)

# ── drag: 20th→2nd style (here E at idx4 dropped before B at idx1) ──────────
# pos=1 means "insert before display index 1".
check("drag E before B", reorder(L, [4], drag_new_start([4], 1)), ["A", "E", "B", "C", "D"])
# drag A to the very end: pos=5 (after last).
check("drag A to end", reorder(L, [0], drag_new_start([0], 5)), ["B", "C", "D", "E", "A"])
# drag C onto itself (pos within block) → no move.
check("drag C onto itself", reorder(L, [2], drag_new_start([2], 2)), L)
check("drag C just below itself", reorder(L, [2], drag_new_start([2], 3)), L)

# ── multi-row block drag (B,C move as a block before E) ────────────────────
check("drag block BC before E", reorder(L, [1, 2], drag_new_start([1, 2], 4)),
      ["A", "D", "B", "C", "E"])
# non-contiguous block (A,C) collapses and lands before E.
check("drag block A,C before E", reorder(L, [0, 2], drag_new_start([0, 2], 4)),
      ["B", "D", "A", "C", "E"])

# ── Move to #… (1-based target line) ───────────────────────────────────────
check("move C to line 1", reorder(L, [2], moveto_new_start(1)), ["C", "A", "B", "D", "E"])
check("move C to line 5", reorder(L, [2], moveto_new_start(5)), ["A", "B", "D", "E", "C"])
check("move C to line 2", reorder(L, [2], moveto_new_start(2)), ["A", "C", "B", "D", "E"])

# ── length preserved / no ops lost, always a permutation ───────────────────
import itertools
for tg in [[0], [4], [1, 2], [0, 2], [2, 3, 4]]:
    for ns in range(-1, 7):
        out = reorder(L, tg, ns)
        if sorted(out) != sorted(L):
            fails.append(f"perm broken: targets={tg} new_start={ns} -> {out}")

if fails:
    print("FAIL")
    for f in fails:
        print("  -", f)
    raise SystemExit(1)
print("ALL REORDER TESTS PASS")
