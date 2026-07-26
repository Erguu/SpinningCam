# Proposal — Curved exit tail after M ("straight to M, user-shaped curve to the end")

**Date:** 2026-07-25
**Status:** ✅ **PHASE 1 IMPLEMENTED 2026-07-25** — headless-verified
(`_test_exit_mid_curve.py`, 48/48, incl. a true byte-identical regression against
`git show HEAD:path_generator.py`). **GUI smoke PENDING · PHYSICAL VALIDATION PENDING ·
commit PENDING.** Phase 2 (`exit_mid_points`, user-drawn spline) NOT built.
Engine: `_tangent_arc` / `_make_curl_leg` / `_curl_penetration` / `CURL_SWEEP_CAP_DEG`
(`path_generator.py`); UI + registry (`ui/tabs/program_tab.py`); i18n ×3; help EN+TR;
changelog `LAST_CHANGES.md` 2026-07-25c. Original proposal below.

**One deliberate deviation from spec (§6.1):** FLATTEN (`exit_mid_trim=False`) gained a
TRIM **backstop**. Copying `exit_bow`'s CLAMP exactly would have inherited its hole —
shrinking curvature only undoes the violation the *curl* causes, so a leg whose own
direction already runs inside the clearance surface still gouges. The curl now holds the
clearance contract in BOTH modes. `exit_bow`'s own behaviour was left untouched.

**User decisions (2026-07-25):** shape = **flare**, endpoint free (§3) ✓ ·
dial = **signed radius in mm** ✓ · length = **remaining tail, no second field**, sweep
capped 90° (Q1) ✓ · **radius wins over `exit_mid_rotation`**, Rot greyed when radius is
set (Q2) ✓ · `exit_mid_t` = **chord fraction for the curl, point-array for the existing
rotation** (Q3) ✓ · clearance = **`exit_mid_trim`, same model as `exit_bow_trim`**
(Q4, §6.1) ✓ · **all passes of the op curl identically** (Q5) ✓.
Assumed unless corrected: reverse passes keep skipping (Q6), `linear_full` stays
excluded (Q7).
**Scope:** Roughing operations with `pass_shape == "linear_approach"` only
(the same gate the existing `exit_mid_*` fields use). Machine ID111 / ID112.
**Risk if built as specified:** Phase 1 low (opt-in, empty = byte-identical output).
Phase 2 medium — a user-drawn shape gives up the built-in no-gouge / no-fold
guarantees, so those must be re-established explicitly (§6).

---

## 1. Purpose — in the user's words

> *"we actually like the bow bias or pass angle. the problem with those is that we
> usually don't need spline in the first part after p2's radius. making it straight
> with only 2 points make our machine more smooth and fast. But we need a spline
> after some point while approaching to the blank edge. to curve the sides so it
> can be more strong."*

> *"after reach is auto calculated and mid exit t has a value, we are branching away
> from the following the blank dynamic in reality. blank follow was designed to try
> to keep the touch with the edge of the blank. when you are getting away from it in
> some point, there is no point of it. so we are more flexible about the x and z locks
> of p3. we are more interested in the curve between M and P3."*

> *"I couldn't decide how the shape must be after M. I want user should do whatever
> he wants it."*

Two separate wins are being asked for:

1. **Machine motion / line budget.** The stretch right after the P2 fillet should be
   dead straight. A straight run costs 2 lines after PLC RDP decimation no matter how
   long it is; `exit_bow` / `exit_arc_angle` spend curvature (and lines, and machine
   smoothness) over the *whole* T2→P3 leg, including the part that does not need it.
2. **Part strength.** Near the blank edge, a curved side is stiffer than a straight
   cone. That curvature is the actual forming work and is wanted only there.

`exit_mid_t` already marks a point along the exit leg, so it is the natural place to
split "straight" from "curved".

---

## 2. What exists today

### 2.1 Geometry of a `linear_approach` roughing pass

Built in `PathGenerator._create_and_store_pass`, `path_generator.py:1687-1747`:

```
ap_start ──straight arm──► T1 ⌒ fillet (p2_radius) ⌒ T2 ──── exit leg ────► P3
                                                              base shape =
                                                                exit_bow (mm, Bézier)   ← wins when set
                                                                else exit_arc_angle (°) tangent-chord arc
                                                                else straight line
```

| Piece | Builder | Ref |
|---|---|---|
| Approach arm | `np.linspace(ap_start, T1, …)` | `path_generator.py:1741` |
| P2 fillet | `_arc_fillet_at_p2` | `path_generator.py:1243` |
| Exit — arc | `_tangent_chord_arc` | `path_generator.py:1387` |
| Exit — bow | `_bezier_bow` / `_make_bow_leg` | `path_generator.py:1422` / `:1501` |
| Bow clearance guard | `_bow_penetration` | `path_generator.py:1478` |

### 2.2 The existing `exit_mid_*` fields

`path_generator.py:1715-1727`:

- `exit_mid_t` (0.05–0.95) → index `k = round(t·(N−1))` into the exit point array → **M**.
- `exit_mid_rotation` (°) → **rigid** rotation of every point after `k` about M in the
  XZ plane (`_apply_rotation`, `path_generator.py:2524`).
- Consequences: `T2→M` untouched; the `M→P3` tail keeps its exact shape and is merely
  swung; **P3 translates with the tail**; there is a **hard corner at M**.
- Skipped entirely in reverse-pass swap mode (`_swap_legs`, `path_generator.py:1683`)
  and in `linear_full`.
- UI: `ui/tabs/program_tab.py:2325-2336`, gated on `op_type == "roughing"` (`:2207`)
  **and** `pass_shape_val == "linear_approach"`. i18n `lbl_exit_mid_rot` /
  `lbl_exit_mid_t` (`i18n.py:849-850`).
- History: `LAST_CHANGES.md` 2026-06-16, TODO #13.

### 2.3 Point density — where the "2 points" actually happens

Worth being precise, because it determines how much of win #1 is already available:

- The **approach arm** is explicitly collapsed to 2 points at `path_generator.py:1911-1917`.
- The **exit leg is not.** It is downsampled by `gcode_resolution` (default 2 mm,
  `path_generator.py:1919-1934`), so a straight 100 mm exit still emits ~50 G-code points.
- The exit leg only collapses to 2 points in the **PLC/SCL export path**, where RDP
  decimation removes collinear points (`_decimate_path_for_plc`, `path_generator.py`
  ~1518; the exit section gets its own tolerance `plc_exit_tolerance`, split at T2 via
  `last_render_split_idx`, `path_generator.py:1944`).

**So the line-budget win is real and it is in the PLC export path:** with a full-leg
bow, RDP can collapse nothing; with straight-then-curve, the straight part collapses to
2 lines and the whole budget is left for the curve, under the 1000-line ceiling.

---

## 3. The geometric constraint that drives the design

With `exit_bow` / `exit_arc_angle` at 0, T2→P3 is one straight line. If T2→M stays
straight **on that line** and P3 is **pinned**, then any curve after M must bulge
sideways and return to P3 — a lens/S shape, not a flare. A curve that genuinely peels
away from the straight line **must move the end point**.

These are mutually exclusive; it is geometry, not preference:

```
(a) BULGE — P3 pinned                     (b) FLARE — end point moves
T2 ●━━━━━━━━━● M                          T2 ●━━━━━━━━━● M
             ╱‾‾╲                                       ╲
            ╱     ╲                                      ╲_
       ┈┈┈┈┈┈┈┈┈┈┈┈● P3 (unchanged)                        ╲__
                                                              ╲● end (moved)
                                                    ┈┈┈┈┈┈┈┈┈┈┈● P3 (planned)
```

**User decision (2026-07-25): (b) FLARE.** Justified in §1 — once the tail branches
away at M, follow-blank has nothing left to follow, so P3's X/Z locks are negotiable.
P3 demotes from *target* to at most a *length budget*.

---

## 4. Proposed design

Phased deliberately: the mechanism (and the machine win) ships and gets physically
validated first; the free-form editor, which is where the risk is, comes after.

### 4.1 Phase 1 — split at M + one shape control

**Mechanism.** In the exit-leg branch (`path_generator.py:1701-1713`, the non-swap
`else`), when the new field is set:

1. Build the straight run `T2 → M`, where M sits at `exit_mid_t` along the T2→P3 chord.
   (Note: `t` becomes a fraction of the **chord**, which equals the current
   array-index meaning when the base shape is a straight line. See open question Q3.)
2. Build the curved run `M → end` and concatenate.
3. Leave everything downstream — clearance loop, rotation, downsampling, decimation
   bookkeeping — untouched.

**Shape (user's pick, 2026-07-25): a circular arc, tangent to the straight leg at M.**

- `exit_mid_radius` (mm, signed) — the only new number. `+` curls outward (away from
  the spin axis), `−` curls inward. Empty/0 → feature off → **byte-identical output**.
- Tangency at M is automatic and exact, so **there is no corner** — this is what makes
  it better than today's rigid rotation for machine smoothness.
- Constant curvature is the most machine-friendly shape and decimates evenly.
- Reads like a drawing (*"R60 on the flange"*), which is why radius was preferred over
  a bow height or an angle.

> **⚠ CORRECTED 2026-07-26 after the first field test.** The rule below said the cap
> should grow the RADIUS to preserve length. That made every `|R|` below `arc_len·2/π`
> (~12 mm typically) collapse to one identical shape — only the sign of the field had any
> effect, which the user hit immediately. The radius is now authority and is never
> altered: the cap stops the ARC at 90° and the leftover length runs on as a straight
> tangent (`_curl_tail`). Both promises hold — exact radius AND preserved length.
> See `LAST_CHANGES.md` 2026-07-26.

**Length / stopping rule — recommended: arc length = the remaining `|M → P3|` distance.**
No second field. Reach keeps its meaning ("how far the pass runs"), radius adds
"how much it curls", and the end point falls where it falls — which §3 established is
acceptable. Sweep is then `length ÷ R`, **hard-capped at 90°**; hitting the cap logs a
warning rather than looping. That cap is not cosmetic: it is the exact failure mode
`exit_arc_angle` has above ~90° (the "funny movement" that `exit_bow` was created to
avoid — `LAST_CHANGES.md` 2026-07-08e).

**Clearance:** handled exactly like `exit_bow_trim` — per-op `exit_mid_trim`, default
ON. See §6.1.

**Alternative kept on the table:** if P3 must stay pinned after all, the same split can
instead run `_make_bow_leg(M, P3, …)` — i.e. the `exit_bow` + `exit_bow_bias` controls
the user already knows, applied only after M. That yields shape (a), reuses proven and
clearance-safe code, and needs no new geometry. Cheapest possible version of this
feature; rejected only because the user wants a flare.

### 4.1b MID PHASE — variable curvature (BUILT 2026-07-26b)

User request: *"can we have a mid phase where we have more parameters to control
automaticly the curve but not the full manual point definition like in phase 2"* — and
Phase 2 was explicitly shelved pending a physical test of this.

**One field: `exit_mid_radius_end` (mm).** Curvature interpolates linearly in arc length
from the start radius to this one — a clothoid, the standard road/rail transition curve.
Empty ⇒ the analytic constant-radius arc runs unchanged (byte-identical).

**Why this one and not the others.** The only thing Phase 1 structurally cannot do is
vary curvature along the tail. A constant-radius arc has a **curvature jump** at M:
heading is continuous (no corner) but curvature snaps 0 → 1/R in one step, so the tool
slams into the bend and the material absorbs it at a single spot. Setting only the END
radius leaves M perfectly straight and eases in, removing the jump entirely — the
recommended usage.

Considered and rejected for the mid phase: a curl-length override (fights reach's
decided authority over pass length, Q1); an editable turn limit (never hand out a knob
that can make the path fold); a curvature-peak bias (largely duplicates the end radius —
two knobs for one effect).

### 4.2 Phase 2 — user-drawn tail

Delivers *"user should do whatever he wants"* literally.

- New op key `exit_mid_points`: a list of `[dx, dz]` offsets **relative to M**, in mm.
- The tail is a spline through `M` + those points (Catmull-Rom or B-spline; the first
  segment's tangent locked to the straight T2→M direction so there is still no corner
  at M). The last point is where the pass ends.
- 2 points → a gentle bend; 5 → an S-curve; the operator decides.
- Editing: a small numeric table in the op editor, plus — ideally — drag-on-canvas
  reusing the 2D preview machinery from the v1.010 pass-table work
  (`ui/dialogs/pass_table.py`, `_draw` / `to_c`).
- Phase 1's arc becomes just a convenient generator that can seed the point list.

---

## 5. Parameters

| Key | Type | Default | Phase | Meaning |
|---|---|---|---|---|
| `exit_mid_t` | float 0.05–0.95 | 0.5 | — | **existing.** Where straight ends / curve begins. Curl reads it as a **chord** fraction, rotation as a **point-array** fraction (Q3) |
| `exit_mid_radius` | float, signed mm | `None` (off) | 1 | Curl radius after M. Sign = fixed handedness (`+` → `+Z`) |
| `exit_mid_radius_end` | float mm | `None` (constant) | mid | Radius at the tail END → curvature varies (clothoid). Magnitude only; empty = Phase 1 |
| `exit_mid_trim` | bool | `True` | 1 | Clearance handling, mirrors `exit_bow_trim`. ON = trim, OFF = flatten |
| `exit_mid_sweep_cap` | float ° | 90 (constant, not exposed) | 1 | Fold guard |
| `exit_mid_points` | list `[[dx,dz],…]` | `[]` (off) | 2 | User-drawn tail, relative to M, mm |
| `exit_mid_rotation` | float ° | 0 | — | **existing, unchanged.** See Q2 |

i18n keys needed (EN/TR/ES each, per the project rule): `lbl_exit_mid_radius`,
plus Phase 2 editor strings.

---

## 6. Guards that become mandatory

Every current exit shape is a formula the engine controls, which is *why* it can
promise things: `_make_bow_leg` guarantees clearance is never broken, `_bezier_bow`
guarantees the curve cannot fold. A curled or user-drawn tail forfeits both.

| Risk | Why it is new | Proposed guard |
|---|---|---|
| **Gouge** — a curled/drawn point inside the mandrel or blank | Free shape can point anywhere | **DECIDED (Q4): same model as `exit_bow_trim`** — reuse the `_bow_penetration` / `_make_bow_leg` trim-or-flatten pattern at the op's own clearance, never below `min_safety_gap`. See §6.1 |
| **Fold / loop-back** | Sweep > 90° with a small R | Hard sweep cap (§4.1) + `PARAM_DEBUG` warning |
| **Workspace exit** | Nothing checks the exit tail today because nothing could previously reach outside | Check tail against `workspace_x_max` / `workspace_z_min` / `workspace_z_max`; warn (advisory, consistent with `check_angled_clearance`) |
| **PLC line budget** | A busy curve eats the 1000-line ceiling | Already handled by `plc_exit_tolerance` + auto-tune (#86); straight-before-M *improves* the budget |
| **Tilt (ID112)** | B angle is derived from each point's Z | Deterministic — the curled Z values feed the same `_compute_tilt_for_path`. Verify reachability warnings still fire |

### 6.1 Clearance handling — `exit_mid_trim` (user decision, 2026-07-25)

> *"we can do it like we did for exit_bow_trim"*

Same two modes, same default (ON), same tooltip vocabulary — nothing new for the
operator to learn, and both branches already exist in `_make_bow_leg`
(`path_generator.py:1501-1546`):

| Mode | `exit_bow_trim` today | `exit_mid_trim` equivalent for the curl |
|---|---|---|
| **ON — TRIM** (default) | Full bow built; interior points crossing the clearance surface are pushed radially out to exactly that surface and ride the contour. Endpoints pinned. | Full `R` arc built; violating points pushed out to the clearance surface. **Endpoints are *not* pinned here** — the tail end is a free output (§3), so the last point may move too. Simpler than the bow case, with no pinned-endpoint conflict. |
| **OFF — FLATTEN** | Bow *amplitude* shrunk (×0.85, ≤14 iterations) until nothing violates — smaller but perfectly smooth. | An arc has no amplitude; its equivalent is **curvature**, so the radius is *grown* (×1.18, ≤14 iterations) until nothing violates — a gentler curl, still perfectly smooth, degenerating toward straight in the worst case. |

Two notes:

- Only an **inward** curl (`−R`) can gouge; `+R` moves away from the part, so the guard
  is normally inert. Same asymmetry `exit_bow` has.
- Under TRIM, "riding the clearance contour" means the tail hugs the part at the op's
  own clearance — for a flare that is often a *useful* forming move, not merely damage
  control. It is still logged via `PARAM_DEBUG` so it is never silent in the log.

**Separate key, not shared with `exit_bow_trim`:** a program can legitimately set both
an `exit_bow` and a curl, and they may want opposite handling. Default `True` matches
`exit_bow_trim`, so behaviour reads the same way in both places.

### Reporting accuracy

- ✅ **`Real End Z` is NOT affected.** It reads `contact_z` on the P2 side
  (`path_generator.py:737`), not the exit endpoint. *(This corrects a claim made
  earlier in the design discussion.)*
- ⚠️ **The pass table's endpoint column diverges.** `compute_pass_rows` computes
  `end_x/end_z` as `P2 + p3 offset` (`ui/dialogs/pass_table.py:214-221`) — the
  *planned* P3, not the curled end. Its 2D sketch also draws P1→P2→end as straight
  segments (`:431`). `compute_pass_rows` is documented as a mirror of the engine and
  must be kept in sync, so it needs updating or an explicit "curved tail" marker.

---

## 7. Touch points

| Area | File | Note |
|---|---|---|
| Exit-leg build | `path_generator.py:1701-1713` | Insert split; keep `_swap_legs` branch untouched |
| Existing exit-mid block | `path_generator.py:1715-1727` | Interaction with `exit_mid_rotation` — see Q2 |
| Decimation split bookkeeping | `path_generator.py:1907-1947` | T1/T2 indices must survive; consider a third split at M |
| Op editor fields | `ui/tabs/program_tab.py:2325-2336` | Same `linear_approach` gate. **Grey out `exit_mid_rotation` + note when a radius is set (Q2)** — needs a live trace on the radius entry, same pattern as `_reach_live_var` (`HANDOVER_2026-07-07`) |
| Param universe / labels / groups | `ui/tabs/program_tab.py:35, 91, 138, 173, 213` | Scalar keys only — see below |
| i18n | `i18n.py` | EN/TR/ES for every new string (project rule) |
| Help window | `help_window.py` `_C` dict | Required on every UI/feature change (project rule) |
| Changelog | `LAST_CHANGES.md` | Incl. rollback note |

### Non-scalar parameter warning (Phase 2 only)

Most op machinery here assumes scalars. `exit_mid_points` (a list) collides with:

- **View customizer / table columns** — `OP_PARAM_UNIVERSE` drives columns; a list has
  no sensible cell value (render as `"n pts"` or exclude).
- **Unite** (`_merge_ops` / `_unite_conflicts`) — offers first/last/average on
  conflicts; *average* is meaningless for a point list. Needs an explicit rule.
- **`OpUndoStack`** — snapshots values; must deep-copy the list, not alias it.
- **Split / copy / ops library** — copy op dicts wholesale; fine, but must deep-copy.

None of this is a blocker. It is the difference between "add a field" and "add a new
*kind* of field", and it is the main reason Phase 2 is separated from Phase 1.

---

## 8. Backward compatibility & rollback

- `exit_mid_radius` empty/`None` and `exit_mid_points` empty ⇒ the new branch never
  executes ⇒ **byte-identical toolpath and G-code** for every existing program.
- No existing key changes meaning, no default is altered.
- **Rollback:** delete the split branch in the exit-leg block; the leg reverts to a
  single `_tangent_chord_arc` / `_make_bow_leg` / `linspace` run. Remove the UI fields
  and i18n keys. Old `.ssp` files carrying the new keys stay loadable (unknown keys are
  ignored).

---

## 9. Open questions

- ~~**Q1 — Stopping rule.**~~ **RESOLVED 2026-07-25:** arc length = the remaining
  `|M → P3|` distance. **No second field.** Reach keeps setting how far the pass runs;
  `exit_mid_radius` sets only how hard it curls. Sweep = `length ÷ R`, hard-capped at
  90° (§4.1). Rejected: explicit sweep angle (decouples pass length from reach);
  stop-at-P3's-Z; stop-at-blank-OD (depends on the unverified flange-reach estimate,
  TODO #61 step 4).
- ~~**Q2 — Relationship to `exit_mid_rotation`.**~~ **RESOLVED 2026-07-25:** mutually
  exclusive, **radius wins**. `exit_mid_radius` empty ⇒ `exit_mid_rotation` behaves
  exactly as today. Radius set ⇒ the curl replaces the rigid rotation entirely and the
  Rot field is **greyed out in the editor with a note** (not silently ignored — see
  §7 UI note). One shape at a time, never both; no existing program can change.
- ~~**Q3 — Meaning of `exit_mid_t`.**~~ **RESOLVED 2026-07-25:** scoped per feature.
  The **curl** measures `t` as a fraction of the straight **T2→P3 chord** (predictable,
  independent of point density). The **existing rotation** keeps its current
  **point-array index** meaning. Existing output stays byte-identical, including
  programs that combine `exit_mid_rotation` with `exit_bow` / `exit_arc_angle`.
  ⚠️ Implementation note: one field, two readings — must be spelled out in the tooltip
  and the help window, and asserted in tests, or it will read as a bug later.
- ~~**Q4 — Gouge handling.**~~ **RESOLVED 2026-07-25 by the user:** *"we can do it like
  we did for exit_bow_trim"* → per-op `exit_mid_trim` toggle, default ON (trim), OFF
  flattens the curl instead. Full definition in §6.1.
- ~~**Q5 — Multi-pass.**~~ **RESOLVED 2026-07-25:** **all passes of the op curl at the
  same radius** — identical to how `exit_bow` / `exit_arc_angle` already behave per-op,
  so there is no new mental model. A curl confined to the last pass is still achievable
  by splitting the op (#64). Rejected for Phase 1: a `last_n` field; a
  start→end radius ramp across the fan (revisit only if the physical test asks for it).
- **Q6 — Reverse passes.** `exit_mid` is skipped in `_swap_legs` mode today
  (`path_generator.py:1681`). **Assumed: keep skipping** for Phase 1 — the curl would
  land on the leg that enters the mandrel, which #82 deliberately keeps straight.
  Stated for the record; say otherwise if wrong.
- **Q7 — `linear_full`.** Currently excluded from `exit_mid`. **Assumed: keep
  excluded** for Phase 1 (`linear_full` has no separate approach arm, so "straight
  before M" has a different meaning there and needs its own thinking).

---

## 10. Test plan

**Headless (`_test_exit_mid_curve.py`, new):**

1. Field absent / empty / 0 ⇒ path arrays byte-identical to current output (regression
   against a saved baseline for a representative roughing op).
2. Tangency: angle between the last straight segment and the first curved segment < 0.5°.
3. Radius accuracy: fitted circle radius on the curved run within 1% of `exit_mid_radius`.
4. Sign: `+R` increases X, `−R` decreases X.
5. Sweep cap: small R + long tail ⇒ sweep clamped at 90°, no self-intersection
   (segment-intersection check over the tail), warning logged.
6. Clearance, both modes (§6.1): with a deliberately gouging inward `−R`,
   `measure_min_clearance` on the full pass ≥ the op's clearance and never below
   `min_safety_gap` — with `exit_mid_trim` ON (points ride the contour, `PARAM_DEBUG`
   logs the count) **and** OFF (radius grown, curl smooth, no contour-riding points).
   Outward `+R` is untouched by either mode (guard inert).
7. Decimation: PLC RDP collapses the T2→M run to 2 points; total line count for
   straight-then-curve < full-leg bow at equal tolerance (the stated machine win).
8. Reverse pass (`_swap_legs`) and `linear_full` unchanged (Q6/Q7).
9. Q2 exclusivity: radius set + rotation set ⇒ output equals radius-only output
   (rotation provably ignored); radius empty + rotation set ⇒ equals today's output.
10. Q3 scoping: with `exit_bow` also set, M for the **rotation** sits at the same
    point-array index as today (byte-identical), while M for the **curl** sits at the
    chord fraction — asserted separately so the dual meaning cannot silently drift.

**GUI smoke:** field appears only for roughing + `linear_approach`; edit triggers
recalc; 3D preview shows straight-then-curve; PDF/SCL export runs; undo/redo;
split/unite carry the value.

**Physical:** required before trusting it — a curled tail changes where the roller
leaves the part, and per project history (`feedback_calibration_rtool`,
`project_finishing_zshift_debunked`) geometry that looks right headless is not
evidence it is right on the machine.

---

## 11. Recommendation

Build **Phase 1 only** — `exit_mid_radius` (one signed number, empty = off), arc length
= remaining tail, 90° sweep cap, and `exit_mid_trim` reusing the `exit_bow_trim` model
— validate it physically, then decide whether Phase 2's free-form editor is still
wanted. Phase 1 delivers both stated wins (the 2-point straight run and a curved,
stiffer side), adds no new safety machinery, and its rollback is a single deleted branch.

**Nothing is left open.** Q1–Q5 are decided (header + §9); Q6/Q7 are recorded as
"keep current behaviour" assumptions. Phase 1 is ready to build on the word go.

**Net operator-facing addition: two fields** — `exit_mid_radius` (signed mm, empty =
off) and `exit_mid_trim` (checkbox, default ON) — on roughing ops with Pass Shape =
`linear_approach`. `exit_mid_t` gains a second job it already looks like it does.
