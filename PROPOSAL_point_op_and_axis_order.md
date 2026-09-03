# PROPOSAL — "Point" operation + per-axis motion order

Status: **BOTH PARTS SHIPPED** (2026-09-03).

- **§3 Point operation — v1.027.** `LAST_CHANGES.md` 2026-09-03 (f),
  `CODE_NAVIGATION.md` §4e. Tests: `_test_point_op.py`, `_test_point_op_gui.py`.
- **§4 motion order on the pass retract — v1.028.** All three modes, warn-only on
  `z_first` at edit time AND after calculating. `LAST_CHANGES.md` 2026-09-03 (g),
  `CODE_NAVIGATION.md` §4f. Tests: `_test_retract_motion.py`,
  `_test_retract_motion_gui.py`.

Departures from the plan below, both deliberate:

- **One shared helper, not two.** `point_motion_waypoints` was generalised to
  `motion_waypoints` and `POINT_MOTION_MODES` to `AXIS_MOTION_MODES`, so the two
  features cannot describe the same shape differently.
- **Both axis words on every emitted leg**, rather than a single-axis word
  relying on modal X/Z. A recipe line carries absolute X and Z anyway, so it
  costs nothing and drops a dependency on line ordering.
- **Calm status note, no modal**, for the `z_first` advisory — see §4's warning
  discussion as amended.

§6 (the pass APPROACH) remains out of scope and unbuilt.

Scope confirmed by the user: **Point operation + pass retract**. The pass
*approach* is deliberately out of scope (see §6).

---

## 1. What was asked

> "Sometimes for some setpoints the operator would like not to have synchronized
> motion in both axes, but first X and then Z. And for every movement the operator
> can only move the axis with the passes — but sometimes you want to move the axis
> to a single point. Could we add a new operation type, 'Point'?"

Two features, related but separable:

- **A. Point operation** — an op that is just "go to this X/Z", no passes.
- **B. Motion order** — synchronized diagonal vs. one axis at a time.

---

## 2. Ground truth: how movement works today

### 2a. Retract is emitted AFTER the pass, never before

`path_generator.py:3518-3526`. The retract `G0` follows the last `G1` of the
pass, and its offsets are added to the pass's **last point**:

```python
raw_ret_x = last_pt[0] + retract_x_offset_real(ret_x_off, ret_side)
raw_ret_z = last_pt[2] + ret_z_off
```

Per-pass sequence in the .nc:

```
G0 X.. Z..     -> pass start          (single diagonal rapid, :3453)
G1 ...         -> cutting
G0 X.. Z..     -> end + retract x/z   (single diagonal rapid, :3526)
```

Consequences:

- **Nothing retracts before a pass.** The previous pass's retract is the only
  thing holding the roller off the part during the next approach. The sim
  comment at `:1419` says exactly this — *"X is already retracted"*.
- **Back passes skip the forward retract** (`:3514`) so the roller flows straight
  into the back pass; the back pass emits its own retract at `:3571`.
- At an op boundary with a tool change, the pass retract happens first, then the
  separate tool-change retract (`:3314-3333`).

### 2b. The 3D view and the .nc already disagree on rapid shape

- Simulation splits every rapid into three legs — X out, Z move, X in
  (`_safe_rapid_segments`, `:3597-3630`).
- The emitter writes **one diagonal `G0 X.. Z..`**.

So the screen already shows "X first, then Z" while the machine gets both axes
together. This is very likely what the operators have been reacting to.
**Confirm this on the machine before building on top of it** — if the PLC is
already doing something else with `CMD=0`, the premise changes.

### 2c. Split-axis motion is already proven

`:3323` — `tool_change_simultaneous`. Tool-change moves default to **two separate
single-axis `G0` lines** (`Z` then `X`, `:3332`), with a simultaneous diagonal as
the opt-in. So the machine already accepts single-axis rapids in production.
Feature B is not new machine behaviour, only a new place to ask for it.

---

## 3. Feature A — the Point operation

**Name.** Industry calls this a *positioning block* (Mastercam: "Manual Entry",
NX: "Positioning"). No term is common enough to be worth borrowing. Use
**Point** / `Nokta` / `Punto` — plainest for the operator.

**Model.** One target position. No passes, `count` ignored — the same shape as
the existing cutting/bending branch (`:742`), minus the second endpoint.

| Field | Type | Notes |
|---|---|---|
| `point_x`, `point_z` | float | The setpoint |
| `motion` | `synchronized` \| `x_first` \| `z_first` | Default `synchronized` |
| `feed` | float | Blank/0 -> rapid (`CMD=0`). A number -> feed move (`CMD=1`), integer 1-3000 |
| tool-change fields | — | Reuse `_add_tool_change_fields()`, already shared by every op type |

**Coordinate frame.** `point_x` is the **machine / DRO X** the operator reads off
the display — the same convention as cutting/bending `plunge_x`, *not* a part
radius. This must be stated in the field label, not just the docs.

**Retract: recommend NOT offering one.** A retract runs after the move, so it
would immediately undo the position the operator just asked for. If he wants to
leave a point in a controlled way, that is a second Point op — visible in the op
list instead of hidden in a field.

**Recipe cost.** 1 line synchronized, 2 lines split. Negligible against the
1000-line PLC cap.

**3D view.** Triangle marker at the setpoint. Also needs an entry in
`pass_colors.op_category()`, or the op list and the 3D picture will disagree.

---

## 4. Feature B — motion order on the pass retract

New per-op field `retract_motion`, default `synchronized` = **byte-identical
output for every existing program**.

Sites that must agree (the emitter/sim mirror hazard):

| Site | File:line | What changes |
|---|---|---|
| Forward pass retract (emit) | `path_generator.py:3518-3526` | 1 `G0` -> 1 or 2 `G0` |
| Back pass retract (emit) | `:3571-3574` | same |
| Forward pass retract (sim) | `:1456-1457` | 1 segment -> 2 segments |
| Back pass retract (sim) | `:1450` | same |
| Cut/bend retract (sim) | `:762` | same |

Factor a single `retract_segments(last_pt, dx, dz, motion)` helper used by both
sides, the same way `resolve_tool_change_point` keeps the tool-change sites
honest.

### The safety fork — Z-first on a retract is a gouge

- **X first** = pull the roller radially off the work, *then* move axially. Safe.
- **Z first** = drag the roller axially **while still in contact with the part**,
  then pull off. This is a scratch or a gouge along the whole Z offset.

Note the tool-change block uses Z-first (`:3332`) — that is safe only *because*
the pass retract already happened. The same order on the retract itself is not.

**Decision (user, 2026-09-03): offer all three, warn on `z_first`.** Not blocked —
the same warn-only stance already used for a custom tool-change position
(`PROPOSAL_per_op_tool_change_position.md` §5). Metal-spinning setups vary and an
operator who has measured his fixture may legitimately want it.

The warning must appear in **both** places, because each catches a different
moment:

- **Edit time** — in the op editor, next to the dropdown, the moment `z_first` is
  picked on a retract. This is where a mistake is cheap to undo.
- **Export time** — collected into `last_kinematic_warnings` (the existing list,
  `path_generator.py:3578`) so it reaches the export dialog even if the setting
  was inherited from an opened .ssp and nobody touched the dropdown this session.

Warning text should name the consequence, not the setting: *"Z first on a retract
moves the roller along the part before pulling it clear — this can scratch the
surface."* Not *"z_first selected"*.

### Line-count cost — this one is real

A split retract doubles retract lines. A program with 250 passes goes from 250 to
500 retract lines against a **hard 1000-line PLC cap**. Needs to be surfaced in
the SCL layout dialog capacity preview, not discovered at export time.

---

## 5. Where the work lands

1. `path_generator.py` — Point op branch (mirror of cutting/bending);
   `retract_segments()` helper; five call sites above.
2. `ui/tabs/program_tab.py` — `OP_PARAM_UNIVERSE` **and** `on_op_select` (both,
   or the column is selectable but not editable); `_factory_op`; op-type button
   via `adapter.get_available_op_types()`.
3. `ui/dialogs/pass_table.py` — `compute_pass_rows` mirrors the engine; it needs
   to know the new type or the pass table will contradict the recipe.
4. `pass_colors.py` — `op_category()` + `path_categories()`.
5. `pass_compare.py` — `_implied_default()` for the new fields.
6. `main.py update_scene` — triangle marker.
7. i18n EN/TR/ES, `help_window.py` `_C`, `changelog.py`, `LAST_CHANGES.md`.
8. `machine_adapter.get_available_op_types()` — decide per machine type.

## 6. Explicitly out of scope

- **The pass approach.** The approach move is what keeps the roller off the part
  (§2a). Letting the operator reshape it can drive into the work, and the
  clearance guard does not currently check rapids. Separate proposal if wanted.
- Changing the sim's `_safe_rapid_segments` 3-leg behaviour. §2b needs a machine
  answer first.

## 7. Test plan

`_test_point_op.py` + `_test_retract_motion.py`, headless first:

- `synchronized` retract -> output byte-identical to pre-change (regression lock).
- `x_first` -> two `G0` lines, X line first, both carrying the resolved offsets.
- `z_first` -> two `G0` lines, Z line first, **and** a warning present in
  `last_kinematic_warnings`; no warning for `synchronized` or `x_first`.
- Sim segments and emitted lines describe the same path (mirror check).
- Point op: rapid vs. feed branch; tool change on a Point op; `count` ignored.
- Point op X honours `roller_positive_x_side` mirroring (canonical vs machine
  frame — the classic silent bug on a positive-side machine).
- Line-count accounting matches what the SCL capacity preview predicts.

## 8. Effort / risk

- **Effort:** moderate. Point op is a small mirror of an existing branch. The
  retract change is five call sites plus one helper.
- **Risk:** low for programs that do not opt in (defaults reproduce today's
  output exactly). Real risks are (a) the emitter/sim mirror drifting, (b) the
  1000-line cap, (c) Z-first retract if it is offered at all.
- **Physical verification required** before field use, per §2b.
