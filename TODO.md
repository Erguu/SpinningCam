# SpinningCam — TODO


---

## Features — 2026-07-07 (scoping, not started)

> Three Program-tab usability items raised by the user. **#68 is analysis-first:
> NO implementation without explicit user approval** (working program, don't break it).

### 66. Program tab — Undo / Revert for operation-list actions (undo SPLIT is a MUST)

**✅ IMPLEMENTED 2026-07-07 (headless-verified, GUI smoke PENDING, commit PENDING).**
`OpUndoStack` (pure, module-level in `program_tab.py`) + ↶/↷ toolbar buttons +
Ctrl+Z / Ctrl+Y (guarded: ignored when Program tab hidden or focus in a text
field). 9 actions tracked: add / del / move / toggle (incl. double-click) /
Continue ⤵ / Reach⟲ / Angle⟲ / Split / suggester-insert; push AFTER validation,
BEFORE mutation. 50-deep, redo cleared on new action, history cleared on project
load (`main_window`). Restore path clears entry-savers + rebuilds editor (#56
pattern) and fires debounced auto-calc. `_test_undo.py` (7 scenarios) +
continue/split regressions PASS. i18n ×3 + help EN/TR updated. See LAST_CHANGES
2026-07-07.

**Why (user, 2026-07-07):** the op-management actions (Split, Delete, Continue ⤵,
Reach⟲, Move, batch edits…) all mutate the `operations` list irreversibly. Splitting
an op (#64) replaces one parametric op with N chunk-ops and the original is simply
gone — the user explicitly wants **undo of a Split** as the minimum bar.

**Proposed scope (agent, to be confirmed):** a generic **snapshot-based undo stack**
rather than per-action inverse logic:
- Before every *mutating toolbar/structural action* (split, delete, move, add,
  continue-fill, Reach⟲/Angle fill, batch edit #67), push a deep-copy of
  `params["operations"]` (pure JSON dicts — cheap) onto an undo stack.
- **Undo button + Ctrl+Z** pops the stack, restores the list, rebuilds tree/editor,
  fires recalc (respecting async auto-calc).
- Advantage: one mechanism covers ALL current and future actions — no per-feature
  inverse math (a true "merge chunks back" inverse of split is not needed).

**DECIDED (user, 2026-07-07):**
- **Buttons/structural actions only** — per-field typing edits do NOT push undo
  steps for now (may add field-level later).
- A **batch edit (#67) = ONE undo step** — a single Ctrl+Z reverts the whole batch.
- **Redo included** (Ctrl+Y / Redo button): undone snapshots move to a redo stack;
  any NEW action clears the redo stack (standard editor semantics).
- **Depth = 50 undo levels** (snapshots are small JSON — memory trivial); when
  full, the OLDEST snapshot drops off silently. Redo depth is naturally bounded
  by undos performed — no separate limit.
- History is **per-session/per-project**: in-memory only, cleared on project load
  (agent default, implemented; flag if you want it persisted instead).
- ⚠️ Interaction to watch: `_active_entry_savers` positional-index writes (#56) —
  undo must clear/rebuild the editor exactly like `del_op` does, or stale savers
  will clobber the restored ops.

### 67. Program tab — multi-select operations + batch parameter adjust (add Δ to many ops at once)

**✅ IMPLEMENTED 2026-07-07 (headless-verified, GUI smoke PENDING, commit PENDING).**
☑ tick column (click toggles, eats the click; double-click guarded) + native
Shift/Ctrl multi-select (ticks win when set). "Toplu… (n)" button ≥2 targets →
`BatchEditDialog` (param dropdown / += = ×= / live old→new preview, greyed
skips, Apply-gated). Pure `_batch_compute` core: type-universe "na" skip,
"nobase" skip for +=/×= (set still works), numeric-default fallback, count
int≥1. Param list = third **"Batch"** checkbox in Customize View
(`op_view_config[type]["batch"]`, .ssp-saved; missing key → curated default,
explicit [] respected; numeric `_BATCH_ELIGIBLE` only). Whole batch = ONE #66
undo snapshot; editor rebuilt after apply (#56 guard); ticks cleared on
del/move/split/undo-redo/project-load. `_test_batch.py` (9 scenarios) +
extended `_test_program_tab_toolbar.py` (real-widget: ☑ column, undo/redo
buttons, batch enable/count, e2e apply + single-step undo) PASS. i18n ×3 +
help EN/TR. See LAST_CHANGES 2026-07-07b.

**Why (user, 2026-07-07):** tuning big programs means selecting each op one-by-one
and bumping the same parameter repeatedly. Wanted: select multiple ops (e.g. via
checkboxes), then apply **one adjustment to all of them** — e.g. add a constant to
every selected op's `start_z`, `end_z`, or reach factor.

**DECIDED (user, 2026-07-07):**
- **Selection = BOTH**: Shift/Ctrl-click extended selection AND a checkbox "select"
  column in the ops tree (☐/☑ per row, like the existing "On" column pattern).
  Note `on_op_select` currently assumes a single active op — multi-select must not
  break the property editor (e.g. editor shows the *anchor* op, or blanks out when
  >1 selected).
- **Undo reverts the whole batch** — one #66 snapshot per Apply, single Ctrl+Z.

**Dialog trigger & shape (agent proposal, user asked "how will it appear"):**
- A **"Batch…" toolbar button** on the Program tab, enabled only when ≥2 ops are
  selected (label shows the count, e.g. "Batch (4)…"). Clicking opens a small
  **modal Toplevel** centered over the ops tree:
  - Row 1: parameter dropdown + mode radio (**+= Δ** add / **= value** set /
    **×= factor** scale) + value entry.
  - Middle: **live preview table** — one row per selected op: `Op | old → new`,
    updating as the value is typed; ops where the param doesn't apply shown
    greyed "skipped".
  - Bottom: Apply (writes all + one undo snapshot + recalc) / Cancel (no change).
- Same per-field validation as the property editor (floats, ranges).
- Natural batch candidates beyond Δ: set same tool / clearance / feed on many ops,
  toggle On/Off for a selection, batch Reach⟲.

**DECIDED (user, 2026-07-07): batch-param list is chosen in Customize View (#59).**
The view-customizer dialog (per op type: Column / Advanced checkboxes) gets a THIRD
checkbox column, **"Batch"** — ticked params appear in the batch dialog's parameter
dropdown. Reuses the existing `op_view_config` storage (per-program, saved in .ssp)
+ `ui/dialogs/view_customizer.py` grid; default ON for a curated numeric subset
(start_z, end_z, reach, clearance, feed…), rest off. Resolves the old
"full universe vs curated" question — the user curates it himself.

**Open questions:**
- [ ] Depends-on: #66 (a batch edit without undo is scary) — build #66 first (agent
      recommendation, implied accepted by "undo reverts the batch").

### 68. ⚠️ APPROVAL-GATED — Simplify overlapping reach / pass-angle parameters (UX consolidation audit)

**Why (user, 2026-07-07):** the reach controls have accreted: **Reach⟲ button**
(`compute_reach_from_blank`, one-shot fill), **`reach`** field (manual exit
magnitude), **`reach_follow_blank`** checkbox (lock reach to flange — *overrides*
manual reach), **`reach_blank_factor`** (multiplier applied to Reach⟲ AND
follow-blank), **`progressive_reach_enabled` + `progressive_reach_end`** (per-pass
fan), plus raw **`p3_x`/`p3_z`** (direction/back-compat). Same pattern for angle:
**`pass_angle`**, **`progressive_angle_enabled` + `progressive_angle_end`**,
**Angle button** (`compute_angle_from_surface`). Some of these collide/override
each other and the precedence is invisible to the operator.

**Known overlaps to untangle (initial audit, 2026-07-07):**
- `reach_follow_blank` ON silently **overrides** the manual `reach` the user just
  typed — no visual indication on the field itself.
- **Reach⟲ button vs `reach_follow_blank`:** same flange model, one is one-shot,
  one is live — two entry points to one concept.
- `reach_blank_factor` only matters when Reach⟲/follow-blank are in play, but the
  field is always visible → looks like a general reach multiplier.
- `progressive_reach_end` vs `reach`: which one "wins" per pass depends on the fan
  checkbox + pass_angle being set — precedence chain not surfaced.
- `pass_angle` empty vs set flips P3 between raw-XZ and polar mode (#61), changing
  what `reach` even means mechanically — mode is implicit.

**Direction (user LIKED 2026-07-07, still approval-gated per proposal):**
- Single **"Reach source" selector** (Manual / From blank (live) / one-shot fill)
  instead of the button+checkbox+factor spread; grey-out/annotate overridden
  fields ("controlled by follow-blank"); progressive fan as a start→end pair UI
  shared by angle & reach; keep engine params untouched (UI-level consolidation)
  for zero toolpath risk + .ssp back-compat.
- **PLUS (user, 2026-07-07): simplify the naming and/or explanations** of these
  params — clearer labels, or better in-place explanation.
- **Explanations home = the Pass Diagram window** (`_show_pass_diagram`,
  program_tab.py:1777 — the canvas "which parameter affects which part of the
  pass" guide with the formula panel; user called it the "path shape informer").
  Extend it to cover the reach/angle family: reach source & precedence (manual vs
  follow-blank vs fan), what `reach_blank_factor` multiplies, polar-vs-raw P3 mode
  flip when `pass_angle` is set/empty. Diagram already draws P2/P3 + Pass Angle
  arc, so reach/fan annotations fit naturally.

**⛔ HARD CONSTRAINT (user, 2026-07-07):** this is a WORKING program.
Phase 1 = analysis + proposal document only. **Wait for explicit user approval
before changing ANY behavior.** Back-compat with existing .ssp files mandatory;
prefer view-layer changes over engine param changes.

---

## Research & Check Series — 2026-07-04 (scoping only, not started)

> Two operator-confidence topics raised by the user. Descriptions below are the
> agreed scope; **open questions** at the end of each need answers before design.
> Nothing implemented yet.

### 60. Tool reach/angle confidence — "Tested/Approved" flag + predicted touch point in the tool library

**Why:** Tool reach (`r_tool`) is the single riskiest number in the app — a too-small
value drives the roller into the part (gouge), and it has burned us repeatedly
(T0103 79.5 vs 74.31 saga; residual ~1 mm inter-tool gap → challenger axis-fit reach,
[[feedback-calibration-rtool]], TODO #58). Today the operator has no in-app way to
*prove* a tool's reach/angle before running it — he can measure, but there's no
capture-and-confirm workflow, and no record that a given tool was ever verified.

**Idea (user, 2026-07-04):** give each tool a **"Tested / Approved"** state and a
predicted **touch point** so the operator can jog to it, confirm the roller kisses
the part where the app says it will, and then mark the tool trusted.

**Proposed workflow:**
1. Operator calibrates `home_x` with a **baseline** tool he trusts (e.g. T0101),
   confirms the touch, and ticks **"Tested"** on that tool. This becomes the reference.
2. For another tool (e.g. T0103), the app **computes its reach** (from STEP: default
   chord/2 `get_contact_radius`, or the axis-fit challenger from #58) and shows the
   **predicted touch point** — the DRO X/Z the operator should see when the roller
   just contacts the part at a chosen Z (derived from the same
   `cam_x_contact = cx_man + side × (mandrel_R + blank + r_tool)` math the calibration
   dialog already uses, CODE_NAV §16).
3. Operator jogs to that point, verifies contact, and either **approves** (tick Tested,
   optionally write the confirmed `r_tool` to `tools.json`) or adjusts.

**DECIDED (user, 2026-07-04):**
- **Touch point = relative Δreach vs. the baseline (Tested) tool**, driven by #58's
  axis-fit `get_contact_radius_axis()` (tilt-independent, tool-to-tool consistent).
  After calibrating with the trusted baseline, each other tool is shown as *how much
  farther/closer* its contact sits — the operator verifies that delta, not an absolute.
- **On approve, WRITE the confirmed reach to `tools.json`** (`r_tool`). This is a
  deliberate exception to #58's read-only stance: approval is the moment the operator
  commits the verified value. ⚠️ Because `r_tool` is the gouge-risk number, gate the
  write behind the explicit Tested/Approve action and keep the gouge guard
  (`r_tool < radius` refused).
- **Fix-in-window when the guess is wrong (user, 2026-07-04):** the computed reach /
  touch point for a non-tested tool is only an estimate and may come out false. The same
  window must let the operator **edit the calculated reach value in place** and re-check
  before approving — i.e. the predicted-reach field is editable (seeded from the STEP
  guess), the touch point recomputes live from the edited value, and Approve writes the
  operator's corrected value. So the flow is: guess → operator jogs & sees it's off →
  edit the number here → touch matches → Approve (writes to tools.json).

**DECIDED (user, 2026-07-04):**
- **Tested state is per (tool, machine profile)** — reach is machine-calibrated, so a tool
  verified on ID111-1 is trusted only there; untested elsewhere until re-verified. Store
  keyed by machine (e.g. `tools.json` `tested: {"ID111-1": {date, reach}}`, or in the
  machine profile) rather than a single global flag.
- **Angle to confirm (phase 1) = the disc tilt baked into reach (ID111)** — on the 2-axis
  machine the fixed disc tilt is already inside `r_tool`, so verifying reach covers it.
  Design so **ID112 B-axis tilt verification can slot in later** (it's a real per-pass
  commanded angle, a separate check).
- **Untested tool = warn but allow.** Clear "this tool is not verified" warning at
  export/run; operator may proceed (respects operator judgement, doesn't block quick trials).

### 61. Program-tab operation authoring — reorder + "continue from previous op's end-state" + hold-reach / hold-clear helpers

**Why:** Big programs are hard to maintain because everything is manual. Spinning is
trial-and-error, so the user wants many small operations of different pass types stacked
and re-tried, not one big op. The real pain isn't a single op with many passes (that's
already easy) — it's making a **new op start exactly where the previous op's last pass
ended**, which today requires hand-calculating that pass's end position, angle, and reach.

**User's concrete scenarios (2026-07-04):**
- "5 forward linear-approach passes, 2 mm clear, angle sweeping 95° → 101°. Then **1
  reverse pass at the same position/angle as the *last* pass of the previous op**." →
  today he must manually work out what the 5th pass's position/angle actually were.
- Added **"Real End Z"** column (`last_op_end_z`, CODE_NAV §5) to see the last contact Z
  — but **angle and reach of that end pass are still invisible / hand-derived**.
- "I want a **larger clear but the same reach** as the previous pass" → he must hand-solve
  the P3 X/Z to hold the contact point fixed while pushing the standoff out.

**Two separable pieces:**

**(A) Reordering / duplication ergonomics.** There's Save-as-default + copy + Move
Up/Down, but no drag-and-drop and copies still need manual shift/tilt. Scope:
- Drag-and-drop reorder in the ops tree (replaces/augments Move Up/Down).
- "Duplicate op" that clones in place, ready to edit (already partially there via default).

**(B) Derived / linked pass authoring — the real request.** Let a pass or op inherit
computed end-state from the previous op's last pass, instead of re-deriving it by hand:
- **"Continue from previous op"** — new op's start position/angle/reach auto-fill from
  the previous op's **last-pass end-state** (the same values behind Real End Z, extended
  to include end angle θ and end reach). Enables the "reverse pass matching the last
  forward pass" case directly.
- **"Hold reach, change clear"** helper — given a target clearance change, solve the new
  P3 X/Z (or P2 offset) so the **contact point stays put** while standoff grows. This is
  the "larger clear, same reach" case; math sits on top of the existing
  `total_off = r_tool + blank + clearance` and the polar P3 (`_L3` × θ_B, #57 fan).
- Expose the **end-state readout** per op (end Z **and** end angle **and** end reach),
  since Real End Z alone isn't enough — the user explicitly said "angle and reach are
  another topic."

**DECIDED (user, 2026-07-04): one-shot fill.** A "Continue from previous" button copies
the previous op's last-pass end-state into the new op **once**, then the new op is
independent. No live dependency graph — safer given the #56 delete/reorder history.
(User confirmed 2026-07-05: likes the single-button approach over parameter fiddling.)

**⛔ ATTEMPTED & REMOVED (2026-07-05e).** Built P3-handle drag → per-pass override
(`pass_overrides`) via VTK `add_sphere_widget`; the engine override layer was headless-tested
and solid, but the **VTK widget interaction never stabilized** (small drag → huge angle/reach
jumps, period-2 long/short oscillation, crashes). Untestable in the headless dev env. Fully
reverted (UI + engine override) — see LAST_CHANGES 2026-07-05e. **Future retry: do NOT use a
sphere-widget; consider point-picking + a constrained-to-XZ handle, or an entry-field / numeric
nudge UI instead of free 3D drag.** The engine per-pass-override design is in git history.

**NEW (user, 2026-07-05) — interactive 3D drag editing (the real "drag" request).** The
user doesn't want to drag rows in a list — he wants to **grab a pass in the 3D view, drag
it, then hit Calculate** to re-run with the modified parameters. Feasible: the view is
VTK/PyVista, which supports draggable handle widgets + point picking.
- **Realistic shape:** put grab-handles on an operation's **defining control points** — its
  contact point (P2) and its exit (P3) — not on arbitrary generated middle passes. Drag P3
  → back-compute `reach`/`angle` (or `p3_x`/`p3_z`); drag P2 → `start_x`/`start_z`/clearance.
  Then Calculate (or live-preview) with the new params.
- **Why endpoints only:** passes are *generated* from the op's start→end sweep (count,
  progressive angle/reach), so a middle pass has no stored params of its own. The draggable
  points are the op's endpoints, which is exactly what the single-reach model (below) needs.
- **Pairs with the single-reach reframe:** dragging the exit handle *is* the visual way to
  set the one `reach` value — direct-manipulation front-end for the same parameter.
- **Effort/risk:** medium–high. Needs handle placement on the selected op, drag→inverse-
  param mapping, and a recalc trigger. Additive to the 3D scene (`main.py update_scene`).
  Scope as its own phase after the single-reach param exists (it depends on it).

**NEW (user, 2026-07-05) — "Customize mode": drag each individual pass, revert, or save.**
Extends the 3D-drag idea to *every* pass in an op, not just the endpoints. A toggled mode
where the op's generated passes become individually draggable; the operator nudges any
pass, can **Return to original** (discard edits) at any time, and when happy clicks **Save**
to make the edited passes the op's **final version**.
- **Why this is a real model change:** passes today are *generated* from `count` + params,
  so a single pass has no stored geometry to drag. Customize mode must **explode** the op's
  passes into an editable per-pass layer.
- **DECIDED (user, 2026-07-05): override layer — op stays parametric.** Save keeps the op's
  `count`/angle/etc. and stores the operator's drags as an **override layer on top**
  (`pass_overrides[i] = {reach, angle, start_x, start_z, …}`). Non-dragged passes still
  regenerate from params; changing count/angle later still works and edits stick where they
  apply. (Rejected the "freeze to fixed passes" alternative.)
  - **Regeneration rule to define:** what happens to `pass_overrides[3]` if the operator
    later drops the op from 5 passes to 3? (Likely: keep overrides for surviving indices,
    drop/stash the rest — confirm at design time.)
- **Revert** needs the pre-edit state kept in memory while in customize mode (snapshot on
  enter). **Save** commits per the chosen storage model above.
- **Effort/risk:** high — new UI mode, per-pass 3D handles, storage-model change,
  regeneration rules, and .ssp persistence. The heaviest piece in #61; do it last.

**FOUNDATIONAL REFRAME (user, 2026-07-04) — collapse P3 into a single "reach" parameter.**
The user's mental model of a pass = **start_x, start_z, reach, angle**. Today the exit is
stored as the coupled pair `p3_x` / `p3_z`, and "reach" scales that X/Z combination *at a
different scale* — so a pass showing `p3_x = 50` does **not** have reach = 50. This
coupling is exactly what forces the hand-calculation. **The fix underneath everything
else in #61 is to express the exit as ONE reach value along the pass angle** (polar:
reach = stroke length, angle = direction), and show that single number in the editor —
instead of two coupled offsets the operator has to reverse-engineer.
- This already exists *partly*: when `pass_angle` is set, P3 is polar (`_L3` × θ_B, #57).
  When `pass_angle` is empty, P3 is raw `p3_x`/`p3_z`. Unify so **reach is always the
  single authoritative exit parameter** (derive p3_x/p3_z from reach+angle for the engine;
  keep raw-XZ as an advanced/back-compat fallback).
- **REFINED (user, 2026-07-04) — keep `p3_x`/`p3_z`, let reach scale them proportionally.**
  Don't remove the exit-X/Z fields. Instead: `p3_x` / `p3_z` define the exit **direction
  (their X/Z ratio)**, and **reach scales that vector's length without breaking the ratio**.
  Left at default, `reach` simply makes the exit longer along the same angle. So reach =
  the vector magnitude, `p3_x`/`p3_z` = the direction — a two-way bound polar/cartesian
  view (edit reach → rescale p3_x/p3_z keeping ratio; edit p3_x/p3_z → reach display
  updates). "Show that single number" = expose the magnitude, keep XZ as the advanced view.
- Once reach is a single number, "continue from previous" and "hold reach, change clear"
  become trivial: copy/hold one value instead of solving an X/Z pair.

**Build order (user-guided):**
1. **Single reach parameter** — unify P3 to (angle, reach); surface `reach` in the editor
   and as a readout (extends Real End Z with end-angle + end-reach). *Prerequisite.*
   **⏳ IMPLEMENTED 2026-07-05 (headless-verified, GUI smoke + commit PENDING).** Engine:
   per-op `reach` = exit magnitude, overrides `_L3` in pass-angle mode / scales p3_x/p3_z
   (ratio preserved) in raw mode; unset=identical (backward-compat verified + e2e regression).
   `last_op_reach`/`last_op_end_angle` recorded. UI: `reach` editor field + End Reach / End
   Angle columns. **Reach is CLEARANCE-INDEPENDENT** (user 2026-07-05): same reach + diff
   clearance ⇒ same absolute END (P3 anchored to zero-clearance contact; caveats: exact only
   for base_rot=0, safety-floor may override at low clearance). See LAST_CHANGES 2026-07-05.
   **Deferred:** two-way live bind (reach ↔ p3_x/p3_z boxes) — reach currently written
   independently, direction read from p3.
2. **Continue from previous op** — one-shot button filling start_x/start_z/angle/reach
   from the prior op's last-pass end-state. Enables the "reverse pass = last forward pass"
   case directly. **✅ GUI CONFIRMED 2026-07-05 (user) — commit PENDING.** "Continue ⤵"
   toolbar button → `continue_from_previous()` +
   testable `_continue_fill_values()`. Copies Start Z (prev end), angle (pass_angle / fan
   end / raw p3 ratio), reach, clearance; tool NOT copied; then op is independent. Uses
   computed `last_op_end_z`/`last_op_reach`, param fallback if uncalculated. `_test_continue.py`
   passes. See LAST_CHANGES 2026-07-05.
3. **Hold reach, change clear** — ✅ EFFECTIVELY DELIVERED by step 1 (2026-07-05). Because
   reach is now CLEARANCE-INDEPENDENT, changing an op's clearance already keeps the exit end
   fixed — no separate helper needed. (Low-clearance gouge still safety-corrected.)
4. **Auto-calculate reach from blank radius (user, 2026-07-04) — the "fixes all reaching
   problems" button.** The blank radius is already known. For a pass at target Z, compute
   the **remaining (unformed) blank/flange size at that Z** and set `reach` so the exit
   lands on the flange edge automatically — no hand-tuning. Revives the idea deferred in
   **#57** ("auto-fill start reach from blank radius … physics-exact flange model deferred").
   **DECIDED (user, 2026-07-04):**
   - **Model = simple geometric estimate first** (no thinning / material-flow). Physics-
     exact material conservation stays deferred.
   - **Remaining flange = blank radius − (material formed up to the pass's Z)**, measured
     from the **clamp-zone top Z** (see #62), not the raw mandrel base. Reach = distance
     from the contact point out to the flange edge, **directed along the profile tangent
     at that Z** (user, 2026-07-04 — more accurate on angled/curved mandrel ends than a
     purely radial flange).
   - **Model: area equivalence, not raw arc length (agent recommendation; user deferred
     "never used it").** Use the existing surface-of-revolution math in
     `analyze_profile` (`blank_r = sqrt(r_min² + 2·Σ r_mid·ds)`) rather than plain arc
     length — physically correct for a shrinking disc and already coded. Revisit only if
     it misbehaves in practice.
   - **Per pass** — each pass computes its own reach from the remaining blank at *its own*
     target Z (naturally shrinks as passes climb toward the flange; dovetails with #57
     progressive reach).
   - **✅ IMPLEMENTED v1 2026-07-05 (opt-in, headless-verified, PHYSICAL validation + GUI
     smoke PENDING).** Model confirmed with user: accounting ALWAYS from the clamped base
     (min-Z), CLOSED flat bottom → `Rc(Z)²=r_base²+2Σ(base..Z)r·ds`; flange overhang
     `√(r(Z)²+R_blank²−Rc²)−r(Z)`; **RADIAL** measure (user chose radial v1; tangent deferred
     for steep walls). Orientation-proof (user: "varies by part").
     `process_planner.estimate_flange_reach()` + opt-in **Reach⟲** toolbar button
     (`compute_reach_from_blank`) that FILLS `reach` (and fans `progressive_reach_end` for
     progressive-angle multi-pass ops) — never silent, labeled ESTIMATE. `_test_flange_reach.py`
     (top→0, base=R−r_base, monotonic). See LAST_CHANGES 2026-07-05.
   - Implementation hook: **`process_planner.analyze_profile()` already computes** the
     profile arc-length segments (`ds`), `surface_len`, and a `blank_radius_suggested`.
     And `blank_radius` is a real param (`main.py:89`, auto-set to mandrel base ×1.1 on
     STEP load, `main.py:1439`) — so both inputs exist; reach-from-blank is mostly wiring.
   - **Anchor (origin) for the material-formed measurement = the clamp-zone top Z (#62).**
     That's where free forming actually begins, so it's the correct zero for accumulating
     formed material. If #62 isn't built yet, fall back to the **lowest program-start Z
     across ops** (or a manual offset) as the anchor.
5. **Drag-and-drop reorder + duplicate** — ergonomics, lower priority (Move Up/Down + copy
   already exist).

**Still open (need answers before design):**
- **DECIDED (user, 2026-07-04): end-state readout = new tree columns** (end Z / end angle /
  end reach) next to the existing Real End Z, via the Customize-View column system (§21) —
  so all ops are comparable at a glance.
- **DECIDED (user, 2026-07-05): reach is CLEARANCE-INDEPENDENT** — "same reach + different
  clearance ⇒ same absolute END position." Implemented in step 1: the exit P3 is anchored to
  the zero-clearance contact reference (clearance component subtracted from the P3 offset), so
  clearance moves only the contact/approach, not the endpoint. Exact for base_rot=0 (linear
  approach / rotation off); approximate for auto-rotated splines; at low clearance the safety-
  floor may override the anchor to avoid a gouge (safety wins). This resolves the old "hold
  reach, change clear" invariant question → the invariant is the absolute END point.
- Still open — migration: existing programs store `p3_x`/`p3_z`. Convert to reach+angle on
  load, or keep both and prefer reach? (Back-compat + .ssp files.)

### 62. Counter-press / clamp-zone exclusion — the base fillet must not be machined (fix FIRST)

**⏳ PHASE 1 IMPLEMENTED (2026-07-05) — headless-verified, GUI smoke + commit PENDING.**
Params (`clamp_zone_length` per-part + `clamp_zone_baseline` machine),
`effective_clamp_length()`, `calculate_paths` warning (`last_clamp_warnings`), 3D red band
in `update_scene`, Process/Machine UI, i18n, help. `_test_clamp_zone.py` passes. Phase 2
(hard clip so the manual `start_z` hack is dropped) NOT started. See LAST_CHANGES 2026-07-05.


**Bug (user, 2026-07-04):** the mandrel has a **radius/fillet at its base**, and the
program tries to machine that region too. In reality that part of the blank is **clamped
between the counter-press (tailstock holder) and the mandrel** — it never gets formed, so
it must be **excluded from all toolpaths**. Today the operator works around it by manually
setting the first op's `start_z` to an offset like `10`. The user wants this fixed
**before** auto-reach (#61 step 4), because the clamp-zone top is also the correct anchor
for the blank/flange calculation.

**Agent's take (what I think — user asked):** replace the per-op manual `start_z` hack
with **one part/machine-level "clamp zone" parameter** — the Z below which nothing is
machined (the counter-press region). Benefits:
- **Fixes the bug at the source:** every op's effective start is clamped to
  `max(clamp_top_z, op.start_z)`; no need to remember a magic `start_z=10` on op 1, and no
  risk of a later op accidentally dipping into the clamped fillet.
- **Becomes the single anchor** for #61's blank/flange calc (arc-length/area origin) and a
  sensible default first-pass start.
- **Fits the geometry we already have:** mandrel `props["min_z"]` is the raw base; the
  clamp zone is `min_z → clamp_top_z`. Path-gen already reads `op.start_z`
  (`path_generator.py:224`) and `min_z` (`:335`), so this is a small clamp added there.

**DECIDED (user, 2026-07-04):**
- **Specified as a LENGTH from the mandrel base** (e.g. `clamp_zone_length` = "bottom
  12 mm is clamped"), not an absolute Z — portable across parts, matches how the
  counter-press grips a fixed depth. Effective top Z = `min_z + clamp_zone_length`.
- **Machine default + per-part override.** Machine profile carries a baseline (counter-
  press is hardware); each program/.ssp can override it (fillet height is part geometry).
- **Warning-only first**, hard clip later. Phase 1: draw the excluded band in 3D + warn if
  an op enters the clamp zone, but still generate. Phase 2: actually clamp/clip toolpaths
  so the manual `start_z=10` hack is no longer needed. ⚠️ Note: until phase 2 ships, the
  operator still hand-sets `start_z`; the warning just makes the zone visible.
- **Operator enters the clamped height** (knows the counter-press grip depth). Auto-detect
  of the base fillet from STEP is a later nicety, not phase 1.

**Implementation sketch:** new `clamp_zone_length` param (machine-profile default in
`MACHINE_PROFILE_KEYS`, per-part override in `params`/.ssp); compute `clamp_top_z =
mandrel min_z + clamp_zone_length`; phase-1 warn in `calculate_paths` when an op's
`start_z < clamp_top_z` (path_gen already reads both, `:224`/`:335`); 3D band in
`update_scene`; phase-2 clamp each op/pass start to `max(clamp_top_z, start_z)`. Feeds
#61 step 4 as the blank-calc anchor.

### 63. Deformed-blank preview — faded-blue overlay of the formed sheet (from the reach calc)

**Idea (user, 2026-07-05):** show the **predicted deformed blank** in the 3D view as a
**semi-transparent ("faded") blue** surface, built from the same reach/flange math as
#61 step 4. Lets the operator *see* how far the sheet is formed and whether the reaching
looks right — and doubles as a visual sanity check on the blank/flange model itself.

**Shape of the surface:** a surface of revolution = **formed region** (sheet lies on the
mandrel, offset by blank thickness) from the clamp-zone top up to the last-formed Z, then
the **unformed flange** sticking out from that height along the profile tangent (the
remaining-blank length from the area/arc model). As forming progresses the formed height
advances and the flange shrinks.

**DECIDED (user, 2026-07-05b): PER-PASS, not per-op.** The overlay should show the formed
shape after each individual **pass**, driven by a **"formed-up-to Z" = running max contact
Z through pass k** (robust to reverse passes). Supersedes the earlier per-op end-state
decision. Two access modes:
- **Static scrubber** — a pass slider/spinner to preview any pass without playing (needed
  because the ops tree selects OPERATIONS, not passes — this is the main *new* UI work).
- **Simulation animation (user wants this)** — as the sim plays pass-by-pass, the blue
  blank deforms in step (formed height climbs, flange shrinks). Per-pass + animation are
  effectively the same feature.

**Build order (incremental, all visual):**
1. Faded-blue surface-of-revolution overlay driven by a single "formed Z" (works per-op
   immediately from `last_op_end_z`). **✅ PHASE 1 IMPLEMENTED 2026-07-05b (headless-verified,
   GUI smoke PENDING).** `main.update_deformed_blank()` builds the formed wall (mandrel r +
   blank thickness, clamp-top→formed Z) + flat flange annulus (`estimate_flange_reach`)
   revolved via pyvista `extrude_rotate`; faded blue opacity 0.30. Driven by
   `_deformed_op_idx` (set in `program_tab.on_op_select`), formed Z read fresh from
   `last_op_end_z` each draw. Toggle param `show_deformed_blank` (default on). Called from
   `_update_scene_impl` + on op-select. `_test_deformed_blank.py` passes (valid mesh, spans
   base→formed, flange present, tracks formed height). NO toolpath/G-code impact.
2. Per-pass running-max formed-Z (small `path_generator` addition where passes are already
   generated) + pass scrubber → per-pass static preview.
3. Drive the current pass from `simulation_controller` → the deforming animation.
   **✅ DONE 2026-07-05c (user confirmed "you made it right").** FINAL MODEL = toolpath-based:
   revolve the selected pass's own toolpath (P2→P3) pulled in by r_tool → follows the pass's
   angle+reach exactly (the mandrel-profile/flange-area models were scrapped). Sim: controller
   `current_pass_idx` → `check_sim_loop` bends the blank pass-by-pass while playing.
   `deformed_blank_offset` param tunes radial position. GUI smoke on the sim PENDING.

**FUTURE (user, 2026-07-05b): material spring-back.** After forming, the surface relaxes
slightly (radius grows / angle opens) by a material-dependent factor. Add a `springback`
coefficient to `materials.json`; the overlay shows the relaxed shape. Purely geometric on
the overlay — NO toolpath/G-code impact. Later refinement, not phase 1.

**Implementation notes:**
- Additive to `main.py update_scene`. The view already renders a flat blank disc
  (`main.py:666`) and shell meshes (`mandrel_analyzer.generate_shell_mesh`) — reuse that
  machinery to build the deformed surface; set low opacity (~0.3) + blue.
- Inputs already exist: `blank_radius`, the profile arc-length/area model
  (`process_planner.analyze_profile`), per-op end Z (`last_op_end_z`); per-pass needs the
  new running-max contact-Z array. Flange math = `process_planner.estimate_flange_reach`.
- Depends on #61 step 4 (flange model ✅ done) and #62 (clamp-zone anchor ✅ phase 1 done)
  — prerequisites now in place, buildable.
- **Risk:** low–medium, purely visual; no toolpath/G-code impact.

### 64. Split operation into pass-chunks (→ reorder to interleave reverse passes)

**Idea (user, 2026-07-05):** author one parametric multi-pass op (e.g. 20 rough passes,
Z 10→60, angle 90→180), then **split it into contiguous chunks** — e.g. `1·1·5·5·3·2·2`
(=20). Each chunk becomes its own normal operation in the op-management list,
independently editable. Then drop reverse operations *between* the chunks (reorder via
Move Up/Down or the planned drag). Reordering only — passes are preserved, not recreated.

**Why it works (exact reproduction):** the op progresses LINEARLY in Z, angle
(`pass_angle`→`progressive_angle_end`) and reach across its passes. So a chunk covering
passes [a..b] becomes an op with `count=b-a+1` whose `start_z`/`end_z`,
`pass_angle`/`progressive_angle_end`, and `reach`/`progressive_reach_end` are the sub-range
values at passes a and b. Because the progression is linear, the sub-op's own fan
reproduces those passes exactly; the union of chunks == the original op. Single-pass chunks
→ fixed angle/reach (count=1, no fan). Verify exactness in a headless test on split.

**This replaces the earlier per-op "reverse every N" and "sequence-layer" ideas** — the
user prefers splitting the parametric op into editable chunk-ops + reordering ops, because
the chunks stay first-class, independently tunable operations (not a hidden override).

**Reduces to two primitives:**
- **Split op** — the new piece. Select an op → specify the split → replace it with N
  contiguous chunk-ops that reproduce it. (Engine already supports each chunk as a normal
  op; this is a UI + param-slicing operation, no path-gen change.)
- **Reorder ops** — Move Up/Down exists; drag-reorder is #61(A). Used to place reverse
  ops (defined separately, e.g. a 5-pass reverse op split to singles) between chunks.

**DECIDED (user, 2026-07-05): visual window with dividers** — a dialog lists the op's
passes; click between passes to drop dividers → chunks.
**✅ GUI CONFIRMED 2026-07-05 (user) — commit PENDING.**
`_split_op(op, sizes, end_z_fallback)` (pure, exact) + `_pass_previews` + `open_split_op` +
`SplitOpDialog` (ui/dialogs/split_op_dialog.py) + `btn_split` toolbar + i18n. `_test_split.py`
proves union of chunks == original forming toolpaths (prog angle+reach, constant, raw p3,
open-ended). Chunks are first-class ops → reorder (Move Up/Down / #61(A) drag) to interleave
reverse ops. See LAST_CHANGES 2026-07-05.

**Caveats:** after splitting you have N ops instead of 1 (tuning the whole sweep as one is
gone — that's the trade for per-chunk flexibility). Clearance safety-correction is per-pass
so it reproduces; only inter-op rapids differ (expected). Not started.

### 65. Simulation mode — future improvements (backlog, opened 2026-07-05c)

**Context:** the sim now drives the deformed-blank overlay pass-by-pass (#63 phase 3, done).
This item collects ideas to make simulation richer/more useful later. None started.

- **Deformed-blank in sim polish:** smooth the blank between passes (currently snaps per pass),
  optionally accumulate the formed shape across passes rather than showing only the current
  pass; restore the pre-sim selected pass when the sim ends (currently leaves it on the last).
- **Spring-back overlay during sim** (ties to #63 future): show material relax as it forms.
- **Scrubbable timeline / seek:** jump to a pass or % of the program, not just play/step.
- **Speed + per-op feed-true timing:** play at real cycle-time proportions (feed/speed aware),
  live cycle-time readout synced to the roller position.
- **Collision / clamp-zone / workspace-limit flags surfaced live** while playing.
- **Record / export a sim clip** (screenshots or video) for operator hand-off (ties to #53
  teach mode / dry-run).
- **Multi-view or section view** during sim so the operator sees roller vs. wall clearance.

---

## Features — 2026-07-04

### 59. ✅ GUI CONFIRMED (2026-07-04, user) — Program tab "Customize View" (columns + Basic/Advanced)
**What:** Program tab now has a "Customize…" button + global "Advanced" checkbox.
Per op type, tick **Column** (adds the param as a column in the ops table) and/or
**Advanced** (hides it from the property editor while Advanced is off). Settings are
per-program (`params["op_view_config"]`, saved in .ssp); the Advanced switch is a
global app pref (`op_view_show_advanced`), **default OFF = Basic view on first run**.
**Why:** Big programs expose dozens of params; this declutters the editor and lets you
compare operations at a glance. Industry pattern: progressive disclosure + custom columns.
**Files:** `ui/tabs/program_tab.py` (`OP_PARAM_UNIVERSE`/`OP_PARAM_LABELS`/`GROUP_DEPS`/
`SECTION_KEYS`/`_DEFAULT_*`/`_default_cfg`, `_view_cfg`/`_hidden_keys`/`_apply_field_visibility`/
`rebuild_tree_columns`/`_cell_value`, `_pkey`/`_section` tags, toolbar), new
`ui/dialogs/view_customizer.py`, `main.py` load_project fix, `i18n.py`, `help_window.py`.
**Safety:** view-only — hiding a field never changes its value or the toolpath.
**Status:** headless logic tests 9/9 pass, all files compile, GUI verified by user
("looks nice"). **NOT committed yet** (awaiting user go-ahead to commit).
**Maintenance:** `OP_PARAM_UNIVERSE` is hand-kept in sync with `on_op_select` — update it
when adding/removing an op field. See CODE_NAVIGATION §21.

### 58. ⏳ AWAITING PHYSICAL A/B TEST (2026-07-04) — Calibration "Challenger Rr" (axis-fit reach)
**Problem:** Calibrate `home_x` with tool A (T0101), then run tool B (T0103) → roller
sits ~1 mm off (an earlier fix already cut this from ~5 mm). Root cause: the default
reach `get_contact_radius = max|XZ|/2` mixes disc radius with disc tilt, so it differs
tool-to-tool by ~0.5–1 mm. That inter-tool inconsistency is the residual gap.

**What was added (non-destructive, opt-in):**
- `tool_step_loader.get_contact_radius_axis()` — NEW; fits the disc rotation axis and
  returns max rim radius about it (tilt-independent). Default `get_contact_radius`
  UNCHANGED and still used everywhere else.
- Calibration dialog: read-only "Challenger Rr (axis)" label + Δ + "Use ▸" button that
  loads the value into the editable Rr field ONLY. `_refresh_challenger()`,
  `_use_challenger_rt()`.

**Verified headless (spinning_cam env):** T0101 73.79→74.91, T0102 77.53→77.53,
T0103 74.31→74.91. Relative reach T0103−T0101: current +0.52 mm, challenger ≈0.00 mm.

**Safety (verified):** button never saves a tool value; dialog never writes tools.json
(read-only); no Apply button touches r_tool. Only home_x/offset/blank/etc. change.

- [ ] **NEXT: physical A/B test** — calibrate with T0101 (Use ▸), then T0103 (Use ▸),
      compare Delta X. ~0 → challenger wins.
- [ ] If it wins: update `tools.json` r_tool values + optionally flag path-gen onto the
      axis-fit reach. If ~1 mm persists → try tilt-projected reach (project contact
      point onto machine-X at the disc's real tilt), not just axis-fit.
- [ ] GUI smoke test (label/Δ/Use ▸ appear and populate Rr on real window).

See LAST_CHANGES 2026-07-04, CODE_NAVIGATION §14/§16.

### 57. ✅ DONE (2026-07-04) — Progressive Reach (per-pass P3 exit stroke length)
Opt-in per-pass sweep of the P2→P3 stroke length (`L3`), sibling to the existing
Progressive Angle fan. Angle sweeps the exit **direction** (θ_B), reach sweeps the
exit **length** — orthogonal, can run together (P3 is polar: length × direction).
First pass keeps current reach, last pass reaches `progressive_reach_end` (mm);
shorten it to keep the exit near the shrinking flange as passes climb the mandrel.
Only active when `pass_angle` is set. New op fields: `progressive_reach_enabled`,
`progressive_reach_end`. See LAST_CHANGES 2026-07-04.

Gated on **Pass Angle having a value** (not the fan checkbox) — that's the only mode
where P3 is polar (`_L3` × θ_B). With Pass Angle empty, P3 is raw p3_x/p3_z offsets and
there's no length to progress.

- [x] Engine interp (`path_generator.py` ~265), UI row, i18n, help, test
- [ ] GUI smoke test (checkbox appears with Pass Angle set; field toggles)
- [ ] DEFERRED (user, 2026-07-04): reach when Pass Angle is fully OFF (pure P3 X/Z) —
      scale p3_x/p3_z proportionally. Add only if needed.
- [ ] Optional follow-up: auto-fill start reach from blank radius (needs a Compute
      button; physics-exact flange model deliberately deferred)

---

## Bug Fixes — 2026-07-04

### 56. ✅ FIXED (2026-07-04) — Deleting an op reverts the next set to defaults (Program tab)
**Symptom:** With two+ rough/finish sets (second created from default, then edited),
deleting the first set silently reverted the second to default values.

**Root cause:** Property-editor entry-savers (and widget FocusOut/Return bindings)
write to `operations[op_idx]` by **positional index** (`program_tab.py:1194`).
`del_op()` popped the op but left `_active_entry_savers` and the editor widgets in
place; those stale savers stayed bound to index 0 while still holding the deleted
op's (usually default) values, and the next `_flush_entries()` wrote them into the
op that shifted into index 0.

**Fix (`ui/tabs/program_tab.py`):** `del_op()` clears `_active_entry_savers`,
resets `_active_op_idx`, and destroys the editor widgets before popping, then
rebuilds the editor for the new selection. `move_op()` had the same latent bug
(swap-then-flush clobbered the swapped-in op) and now flushes+clears savers before
the swap. See LAST_CHANGES 2026-07-04.

- [x] Fix `del_op` / `move_op`
- [ ] GUI smoke test in a real window (headless suites don't cover editor widget state)

---

## Operation Suggester Roadmap — 2026-07-03

**Context:** v1+v2 done (rule-based advisory suggester, `process_planner.py` +
`materials.json` + `OpSuggesterDialog`; WHY notes, back-pass rule, On/Off compare).
See LAST_CHANGES 2026-07-03/-03b, CODE_NAVIGATION §20.

### 54. Suggester — cover more parameters, each with a WHY explanation
Every value the suggester emits should carry a one-line rationale (current
`notes` mechanism, i18n `sug_note_*`). Candidates not yet suggested:
- [ ] speed zones (`zones`) — e.g. slower RPM near the large diameter / flange edge
- [ ] contact-zone feed (`contact_zone_mm`, `feed_contact`, `feed_contact_end`)
- [ ] reverse direction strategy (when tip→root traversal helps)
- [ ] `p2_z_extend`, exit arc angle, back-pass arc X/Z shape values
- [ ] conformal flag on angled mandrels (ties into the angled-clearance advisory)
- [ ] ID112: tilt_mode / tilt_start / tilt_end suggestion from surface normals
- [ ] multi-stage roughing (2 ops with intermediate anneal note) when spinning
      ratio exceeds the material limit — today it only warns

### 55. Suggester — ask more inputs for more accurate suggestions
Optional second step in the dialog ("More detail…"): each answer tightens the
heuristics; blank/skip keeps the current defaults.
- [ ] material temper/condition (annealed / H14 / work-hardened) → scales angle-per-pass
- [ ] part tolerance / surface-quality target → finishing pass count + finer feeds
- [ ] machine rigidity / max forming force class → feed ceiling
- [ ] whether intermediate annealing is possible in-house → multi-stage planning
- [ ] roller profile (round-nose vs flat) → clearance + back-pass defaults
- [ ] production volume (one-off vs series) → bias cycle time vs safety margin

---

## Machine #2 — Hot Spinning (ID112) Roadmap — 2026-07-02

**Context:** Phase 0 (infrastructure) is DONE — `HotTiltArmSpinningAdapter` (type 112),
`machines/ID112-1.json`, adapter-driven op buttons / machine-tab sections / export menu.
Machine #2: hot spinning lathe, Z linear + X slide on a rotary (B) arm, CODESYS-based
IPC (Delta or Inovance). See LAST_CHANGES 2026-07-02c. Phases below are NOT started.

---

### 50. Phase 1 — Tilt-arm kinematics (ID112) — ✅ DONE 2026-07-02

- [x] Profile keys `tilt_pivot_x/z`, `tilt_b_min/max/home/sign` → `MACHINE_PROFILE_KEYS`,
  `MachineProfileSchema`, `machines/ID112-1.json` (placeholder values until drawings).
- [x] New `kinematics.py`: `TiltArmKinematics` — forward/inverse tip XZ ⇄ (B, X_arm, Z_car),
  side-aware (`roller_positive_x_side`), singularity + B-range + arm<0 checks; factory
  `get_kinematics(params)`.
- [x] Per-point tilt: `path_generator` builds `last_tilt_angles` (per-op `tilt_mode` =
  `normal` yüzey normali + `tilt_offset`, veya `interp`). Deterministic from
  geometry → decimation-safe.
  **2026-07-03 redesign (commit c55cc58):** interp artık Z-BAZLI — açı yüzey
  konumunun fonksiyonu: `tilt_start` op Start Z'de, `tilt_end` op End Z'de,
  arada Z'ye göre doğrusal, bölge dışı kırpılır. Yön-bağımsız → geri-pas
  uç-ters-çevirme (`reverse=True`) kaldırıldı. Detay: `LAST_CHANGES.md`
  2026-07-03 girişi + `CODE_NAVIGATION.md` §19.
  ⚠️ Matematik headless doğrulandı; FİZİKSEL doğruluk sahada ONAYSIZ
  (kullanıcı GUI'de hareketi gördü, doğruluğundan emin değil; makine
  geometrisi hâlâ placeholder — çizimler bekleniyor).
- [x] G-code: B word on every G1 + pass-start G0 (rapids hold last B — "both-ready core":
  Cartesian tip + angle canonical until Phase 3 controller spec). `check_reachable` →
  `last_kinematic_warnings`. ID111 output byte-identical (regression-verified).
- [x] Visualization: static roller + simulation tilt (SetOrientation, zero-alloc),
  live monitor B display.
- [x] UI: op editor tilt fields (tilt-arm-gated), machine tab "Tilt Arm (B Axis)" section,
  pass-info per-pass "B start → end" operator reference, PDF per-pass B table,
  i18n EN/TR/ES, help window EN/TR.
- **Open questions (Phase 3 / drawings needed):**
  - Exact arm geometry (pivot position, arm zero-offset) — placeholders in profile.
  - **Arm direction sign:** does the slide extend outboard or inboard of the pivot?
    Current model assumes x_arm ≥ 0 outboard; if inboard, flip in `kinematics.forward/inverse`.
  - Controller IK question for Delta/Inovance: *"Does the motion package support
    user-defined kinematic transformations, or only synchronized multi-axis point
    interpolation?"* → decides Phase 3 export format (machine axes vs tip+angle).
- **Deferred refinements (noted, not scheduled):**
  - Contact-point migration on the curved roller profile at large tilt (tip currently
    assumed to rotate about itself).
  - Touch calibration tilt-aware variant — for now calibrate at B=0 (ID111-equivalent).
  - Tool-body-vs-mandrel collision check at tilt.

### 51. Phase 2 — Hot process features (ID112)

- New op types via `adapter.get_available_op_types()` (e.g. preheat, hot preform,
  necking — define with customer). `program_tab._op_buttons` map gets new entries.
- Per-op/pass heating params: heater on/off, temperature setpoint, wait-for-temperature
  dwell, pyrometer tolerance band.
- Program model: heating steps interleaved with motion (G-code comments, time estimate,
  simulation). UI fields gated by `adapter.supports_heating()`.

### Packaging / release policy — machine types vs exe size (2026-07-02)

**Decision:** ONE universal exe for all machine types. Exe size is dominated by
libraries (VTK/PyVista, numpy/MKL, pythonocc, cryptography) — all adapter/machine
code together is <1 MB, so machine types add essentially nothing. License
(`allowed_machines`) gates what a customer can open.

**Per-customer packaging rule:** when preparing a customer package, ship ONLY that
customer's `machines/*.json` profiles. Selector + license generator list from disk,
so absent profiles never appear, and other customers' machine names/params stay private.
Zero code change — just a release-procedure step.

**Code rule:** machine-specific heavy code stays behind lazy imports inside adapter
methods (pattern: `get_path_generator_class()`). At runtime only the selected
machine's modules are imported; the rest sit unused on disk.

**Revisit single-exe policy only if:** (a) a machine type drags in a heavy new
dependency (e.g. OPC-UA client for CODESYS transfer) — then decide per-build
inclusion via PyInstaller `excludes`; or (b) a machine type's process know-how
becomes IP-sensitive — then per-machine-type builds (same codebase, build flag).
Not worth it at 2 machine types.

### ✅ Done — Builder drift protection: manifest + auto-check + exe self-test (2026-07-04)

**Problem:** the exe builder had silently fallen behind the app. Three divergent
build recipes existed (`build_exe.py` run by the `.bat`, plus `SpinningCam.spec`
and `EMS_SoftSpinner.spec`); only the `.spec` bundled `cryptography` (license
backend) while the recipe actually run did not; new data files (`materials.json`,
`machines/ID112-1.json`) were never shipped; and `--add-data` put files in
`_internal/` which the app never reads (`get_base_path()` == exe folder). Failures
were silent — a subtly incomplete exe, no error.

**Fix (single source of truth + fail-loud):**
- `packaging_manifest.py` — the ONE list of what must ship next to the exe
  (`SHIP_NEXT_TO_EXE`), what must NEVER ship (`MUST_NOT_SHIP`: private key,
  admin.lic), what is intentionally excluded (`NOT_SHIPPED`), and the
  `CRITICAL_MODULES` that must import. Also hosts `run_selfcheck()`.
- `main_tk.py --selfcheck` — proves a frozen build without opening the GUI:
  imports every critical module, builds the license public key (forces the
  cryptography backend to load), resolves every required data file next to the exe.
- `check_packaging.py` — static checks (source exists, modules import, and a
  SOURCE SCAN that WARNS about any data file read in code but not in the manifest)
  + `--post-build` checks (files sit next to the exe, no secret leaked, exe
  `--selfcheck` exits 0).
- `build_exe.py` — now the ONLY recipe. Added `--collect-all=cryptography`,
  dropped the unused `images/` (dev screenshots, never read by the app), copies
  the manifest next to the exe after build, then runs `check_packaging --post-build`
  and fails the build if the check fails. `.spec` files retired (git history keeps them).

**Maintenance rule going forward:** add a new data file read at runtime → add it to
`SHIP_NEXT_TO_EXE`. The source scanner warns if you forget. Run in the
`spinning_cam` conda env (OCC/fpdf/cryptography live there; system python fails imports).

**Status:** DONE and proven. Real frozen rebuild via `build_exe.bat` (2026-07-04)
ended `BUILD SUCCESSFUL and VERIFIED` — the built exe's own `--selfcheck` reported
all critical modules imported, license crypto loaded, and data files present next to
the exe. Verifies completeness/launchability, NOT GUI render or license-logic correctness.

### 52. Phase 3 — CODESYS post-processor (Delta / Inovance IPC)

- Obtain recipe/interface spec from controller side (array/struct layout, transfer
  mechanism — file? OPC-UA?).
- New converter module (parallel to `recipe_to_scl.py`) + `export_manager` entry;
  enable via `get_export_formats()` for 112 (currently gcode/pdf/stl only).
- Heating + B-axis commands in the recipe row format; new `CAM_INTERFACE_SPEC`-style
  document for machine #2.

### 53. Operator pre-run reference / teach mode (backlog — user liked the idea 2026-07-02)

Bigger version of the Phase-1 pass-info "B start → end" line. Ideas to scope with user:
- Printable per-pass setup card: start/end XZ+B, contact zone, feed/speed, tool — beyond
  the current PDF table (diagrams per pass, jog-to positions).
- "Teach" flow: operator jogs machine to key positions, software captures them as
  references (dovetails with tilt-aware calibration).
- Dry-run mode: export a slowed/no-contact variant of the program for first-article runs.

---

## Licensing System — Review & Security Audit — 2026-07-01

**Status:** REVIEW ONLY — no code changed yet. Awaiting user approval before any fix.

**Files reviewed:** `license_manager.py`, `ui/dialogs/license_generator.py`,
`ui/dialogs/machine_selector.py`, `machine_info.py`, `ui/main_window.py:181-233`.

**How it works today:** license = signed JSON (`.lic`). `license_manager.sign_license`
computes an **HMAC-SHA256** over the canonical JSON using a secret hardcoded in the app
(`_SECRET`). `MachineSelector` loads the file, calls `validate_license` (fields + sig +
expiry) then `check_machine_binding` (fingerprint → MAC → none). Admin licenses show the
in-app **license generator** and bypass machine filtering. Binding = MAC (`uuid.getnode()`)
and/or "strong" fingerprint = `sha256(WindowsGUID | MAC)[:32]`.

Overall the crypto primitives are used correctly (`hmac.compare_digest`, canonical JSON with
`sort_keys`), but there are functional bugs and one architectural weakness that together make
the protection bypassable.

---

### L1. ✅ FIXED (2026-07-01) — Unsigned / "old-format" licenses are accepted (full bypass + admin escalation)

**Fix:** Chose option (a) — signing is now mandatory. `machine_selector._browse_license` shows an
error and disables Launch on `no_sig`/old-format (was: amber warning + fall-through). `_auto_load`
now returns on `is_old_format or not ok` (was: allowed `no_sig` through). New i18n keys
`lbl_license_unsigned` / `msg_lic_unsigned_body` (EN/TR/ES). Any genuinely-issued unsigned `.lic`
must be reissued signed.



**Files:** `machine_selector.py:191-215` (`_browse_license`) and `:322-357` (`_auto_load`).

`validate_license` returns `(False, "no_sig")` when a license has no `_sig`. But the caller
treats `no_sig`/old-format as a **warning, not a rejection** — it shows an amber "old format"
label and then **falls through and enables Launch**:

```python
ok, reason = license_manager.validate_license(lic)
if not ok:
    if reason == "no_sig" or is_old_format:
        self._lic_label.config(text="⚠ old format")   # ← no return; keeps going
    elif reason == "tampered": ... return
    else: ... return
# ...falls through, sets self._license_data, enables Launch
```

**Impact:** Anyone can bypass licensing completely by writing a plain JSON file with **no
signature**:
```json
{"customer_name":"x","allowed_machines":["ID111-1"],"issued_date":"2026-01-01","admin":true}
```
This runs on any machine, ignores expiry (the `no_sig` check returns before the expiry check
in `validate_license`), and — because `admin:true` is honored — unlocks the **license
generator** so the user can mint signed licenses for anyone. The HMAC signing is effectively
optional and therefore provides no protection.

**Options to fix (need decision):**
- (a) Reject unsigned licenses outright (`no_sig` → hard fail, disable Launch). Cleanest, but
  breaks any genuinely-issued legacy unsigned `.lic` files still in the field.
- (b) Keep a grace path for unsigned *only if* `admin:false` AND binding present, and never
  honor `admin:true` from an unsigned file. Weaker but backward-compatible.
- Recommendation: (a), after confirming no unsigned licenses were ever shipped to customers.

---

### L2. ✅ FIXED (2026-07-01) — Symmetric secret embedded in client → moved to Ed25519 asymmetric signing (clean break)

**Fix (clean break — HMAC fully removed):**
- `license_manager.py` now signs/verifies with **Ed25519** (`cryptography`, already installed).
  Client embeds only the **public** key (`_PUBLIC_KEY_HEX`); it can verify but never sign.
- The **private** key lives in `license_private_key.pem`, kept off the shipped client
  (gitignored). `sign_license`/`generate_license` now require a `private_key`; the generator
  dialog loads it via `_load_signing_key()` (auto-uses `license_private_key.pem` in the app dir,
  else prompts). `regenerate_internal_license` takes a key path.
- Helpers added: `generate_keypair()` (one-time setup), `load_private_key()`.
- **All existing HMAC licenses are now invalid and must be reissued** (chosen: clean break).
  Bootstrap: `make_admin_license.py` mints the first admin `.lic` (generator UI needs an admin
  license to open). New `.gitignore` excludes `*.pem` / `*.lic`. `SpinningCam.spec` bundles
  `cryptography`.
- Verified headless: sign→verify OK, tamper rejected, old HMAC-style sig rejected, unsigned
  rejected, admin.lic valid.

**Residual risk (unchanged, accept):** the app is bundled Python — an attacker can still
decompile and patch `verify_license` to `return True`. Ed25519 removes the trivial
key-extraction forgery; patching the binary remains possible for any pure-software scheme.

**OLD NOTES (kept for context):**

**File:** `license_manager.py:9` — `_SECRET = b"EMS_SPINNINGCAM_2026_HMAC_KEY_v1"`.

The **same** secret both **signs** (admin generator) and **verifies** (every customer copy).
HMAC only protects against parties who don't know the key — but the key ships inside every
`.exe`. A customer can recover it with `strings EMS_SoftSpinner.exe` (or by reading the
bundled `license_manager.pyc`) and then forge unlimited valid licenses (any machine, admin,
no expiry). Even with L1 fixed, this remains the ceiling on the whole scheme's strength.

**Proper fix:** switch to **asymmetric signatures** (Ed25519 via `cryptography`/`pynacl`, or
RSA). Vendor keeps the **private** key offline (only the license-generator machine has it);
each client ships only the **public** key, which can verify but not sign. Extracting the
public key gains an attacker nothing.

**Note:** because the app is Python bundled with PyInstaller, a determined attacker can still
patch `verify_license` to `return True` in the decompiled bytecode. No pure-software scheme
stops that; asymmetric signing raises the bar from "read one string" to "decompile + patch +
rebuild", which is the realistic goal here. Flag as accepted residual risk.

---

### L3. ✅ FIXED (2026-07-01) — `uuid.getnode()` MAC is unreliable → false lockouts + easy spoofing

**Fix:** `get_mac_address()` now returns `""` when the multicast bit is set (random/unreliable MAC).
`get_machine_fingerprint()` is now **GUID-only** (`sha256(MachineGuid)[:32]`) — stable across
adapter/VPN changes. `check_machine_binding` accepts the new GUID-only fingerprint and, via
`_legacy_fingerprint()`, still honors the old MAC+GUID combined fingerprint when a reliable MAC is
present (backward compat); MAC-mode binding with an unavailable MAC reports mismatch (fail-closed).
`machine_info.py` updated to report the GUID-only fingerprint + flag unreliable MAC. Verified
headless: GUID-only match, wrong-fp mismatch, legacy-fp still accepted, unsigned rejected.



**File:** `license_manager.py:62-65` (`get_mac_address`), also feeds the "strong" fingerprint.

`uuid.getnode()` returns the MAC of *an arbitrary* interface, and if it can't read a hardware
MAC it returns a **random 48-bit value with the multicast bit set** (different every run).
On real customer PCs the result changes when a VPN/virtual adapter (VMware, VirtualBox,
Hyper-V, Docker, WSL) is installed or the adapter enumeration order changes → a legitimate,
correctly-licensed customer gets locked out with a "machine mismatch" error. It is also
trivially spoofable (registry `NetworkAddress` override / adapter setting).

**Fix options:**
- Detect the random/multicast case: `if (uuid.getnode() >> 40) & 0x01: <unreliable>` and fall
  back to the Windows MachineGuid alone.
- Prefer the **Windows MachineGuid** (registry, already read in `get_windows_guid`) as the
  primary stable identifier; treat MAC as secondary/optional. GUID survives reboots and
  adapter changes; it changes only on OS reinstall (acceptable re-activation trigger).

---

### L4. ✅ FIXED (2026-07-01) — `_auto_load` silently swallows expired / tampered / wrong-machine

**Fix:** `machine_selector._auto_load` now sets `_lic_label` with the specific reason
(unsigned / invalid signature / expired / wrong machine) before returning, so the user sees why a
previously-working license stopped auto-launching. No modal on the silent path — label only.

**Original note:**

**File:** `machine_selector.py:322-328`.

On auto-load, an expired/tampered license (`not ok and reason not in ("no_sig",)`) or a
machine mismatch just `return`s with no message — the dialog opens blank and the user has no
idea why their previously-working license stopped launching. Manual re-browse *does* show the
real error, but the silent path is confusing. Surface the reason in `_lic_label` even on the
auto-load path.

---

### L5. ⏸ DEFERRED (2026-07-01) — Local clock is trusted for expiry (rollback bypass)

**Decision:** Skipped by choice. Low value for offline/honest industrial customers and it risks
locking out users whose system clock is simply wrong. Left as-is; revisit only if expiry becomes
a real commercial lever. Original note below.

**File:** `license_manager.py:41-48` — `date.today()` vs `expiry_date`.

A user can set an expiring license to never expire by rolling the system clock back. Low
priority for this product (offline industrial PCs, honest customers), but note it. Mitigation
if ever needed: store a "last launched" date in the registry/settings and refuse to run if the
current date is earlier (anti-rollback). Not worth doing unless expiry becomes a real lever.

---

### L6. ✅ FIXED (2026-07-01) — binding defaults to "none"; generator "Read from this machine" reads the admin's PC

**Fix:** `license_generator.py` binding mode now defaults to **Strong** (GUID fingerprint) and the
identifier row shows on open (`_on_bind_change()` called at build). The read button is relabelled
**"Read from THIS PC"** (and matching warning text) to make clear it reads the admin's own machine,
not the customer's.

**Original note:**

- `license_generator.py:57` defaults binding mode to **None** (runs on any machine). Consider
  defaulting to MAC/strong so an admin doesn't accidentally issue an unbound license.
- `_read_identifier` (`:138-143`) reads the **admin's** MAC/fingerprint, correct only when
  generating on the customer's own PC. The intended flow (customer runs `machine_info.py`,
  sends values, admin pastes) is fine — just confirm the button label can't mislead the admin
  into binding a customer license to the admin machine.

---

**Suggested fix order (if approved):** L1 (close the bypass) → L3 (stop false lockouts) →
L2 (asymmetric signing, the real fix) → L4 → L5/L6. L1, L3, L4 are small, contained changes;
L2 is a larger crypto migration that changes the `.lic` format and the generator.

---

## High Priority Features — 2026-06-22

---

### 45. ✅ Help window — in-app user guide for customers

**Why:** Customers have no prior knowledge of the program. Currently there is no in-app documentation. Without guidance they cannot set up operations, understand calibration, or export correctly.

**Scope:**
- A "Help" dialog (or side panel) accessible from the menu bar (`Help → User Guide`)
- Organized into sections matching the tab structure:
  1. **Getting started** — load STEP model, what the 3D view shows
  2. **Process tab** — visual settings, geometry settings, what each parameter does
  3. **Program tab** — adding/editing operations, operation types (roughing/finishing/cutting/bending), back pass, Calculate button
  4. **Machine tab** — home position, workspace limits, cylinder feature, G-code offset
  5. **Calibration** — touch point calibration walkthrough
  6. **Exporting** — save G-code, export SCL for TIA Portal, export recipe CSV
- Text should go through `t()` so TR/ES translations can be added
- Keep it simple: sections with short paragraphs + parameter name references. No images required for MVP.

**Implementation:** Simple `tk.Toplevel` with a `ttk.Notebook` (one tab per section), scrollable `tk.Text` widgets for content. Content stored as i18n strings or a separate `help_content.py` dict.

**Risk:** Low. Purely additive, no existing code touched.

---

### 46. ✅ License / activation system — lock program to customer PC

**Why:** The compiled `.exe` can currently be copied and run on any machine. The customer needs to be given a specific ID and password that only works on their hardware.

**Design:**
- **Hardware fingerprint** — combine CPU ID + motherboard serial + MAC address into a stable machine ID (survives reboots, not OS reinstall). Use `wmic` or `platform`/`uuid` + registry reads via `winreg`.
- **License file** — a small `license.lic` file (JSON encrypted with a symmetric key hardcoded in the exe) containing: `machine_id`, `customer_name`, `expiry_date` (optional), `admin: false`.
- **Admin license** — same format but `admin: true`. Admin mode unlocks: generating new license files for customers (license generator dialog), viewing all parameters without restriction, any future admin-only features.
- **Activation flow (customer):**
  1. First launch: show "Activate" dialog with machine ID displayed (customer sends this to you)
  2. You generate a `license.lic` for that machine ID and send it back
  3. Customer places `license.lic` next to the `.exe` — program starts normally from then on
- **Activation flow (admin):**
  1. Launch with a special admin `license.lic` (`admin: true`) — full access + license generator
- **On invalid/missing license:** show a dialog with the machine ID and instructions, then exit.

**Implementation files:**
- New `license_manager.py` — fingerprint generation, license read/write/verify
- New `ui/dialogs/activation_dialog.py` — "Not activated" screen
- New `ui/dialogs/license_generator.py` — admin-only dialog to generate customer licenses
- `main.py` or `main_window.py` — check license at startup before building the UI

**Risk:** Medium. Startup flow changes. Must handle edge cases: VM fingerprint instability, OS reinstall, hardware swap (→ re-activation).

---

### 47. ✅ PDF export — add 2D path diagram page

**Why:** The existing PDF operation sheet is useful but doesn't show what the toolpath looks like. A 2D XZ diagram (mandrel profile in gray + toolpaths in color) gives the customer and operator a visual reference on paper.

**Scope:**
- New page appended after the existing operation table in the PDF
- XZ diagram: mandrel profile outline (gray), each operation's path (color-cycled), axis labels, scale bar
- Optionally: home position marker, workspace boundary box
- Use `matplotlib` (already available) to render the diagram, save as image, embed in PDF via `reportlab`

**Risk:** Low. Additive — existing PDF pages untouched.

---

### 48. 🟡 Multi-machine support — machine profiles + startup selector

**Machine ID format:** `ID{3-digit type code}-{serial}`
- Digit 1: Category (1 = lathe)
- Digit 2: Process (1 = spinning)
- Digit 3: Variant (1 = two-axis basic)
- Serial: variable length (1, 2, … 100, …)
- Example: `ID111-1` (current machine)

**Phase 1 — Implemented 2026-06-23:**
- `machine_adapter.py` — `MachineAdapter` base + `StandardTwoAxisSpinningAdapter` (type 111); `ADAPTERS` dict routes type code → class; `parse_machine_id()` + `get_adapter()` helpers
- `machine_loader.py` — `MACHINE_PROFILE_KEYS` list; `list_machine_profiles()`, `load_machine_profile()`, `save_machine_profile()`, `migrate_from_settings()`
- `machines/ID111-1.json` — first profile (all machine params extracted from old settings.json)
- `ui/dialogs/machine_selector.py` — startup dialog (auto-skips if only 1 profile and `show_machine_selector` is false)
- `main.py` — `active_machine_profile` + `active_adapter` attributes; `save_settings_json` now excludes machine keys
- `main_window.py` — `_load_machine_profile()` called at startup before `_setup_layout()`
- `machine_tab.py` — active machine header + "Save Machine Profile" button
- `settings.json` — machine keys removed (now in `machines/*.json`)
- `config_schema.py` — `MachineProfileSchema` + `validate_machine_profile()`
- `i18n.py` — `btn_save_profile` key added

**Phase 2 — ✅ Done (extends #46):**
- `license_manager.py` — `license.lic` has `allowed_machines` list
- `MachineSelector` filters profiles by `license.allowed_machines`
- Admin license shows all machines + license generator button

---

### 49. ✅ Done — Pass Direction (Forward / Reverse) — per-op, roughing & finishing

Implemented: per-op `direction` field (combobox in `program_tab.py`, default `forward`). When `reverse`, `path_generator.py` reverses each pass's stored point array (plus its projections/deviations) right after generation and drops the now-invalid split index so rendering/PLC fall back to corner detection. Cut-direction-only — pass-to-pass order unchanged; mirror back pass kept (composes via the whole-path-mirror branch). i18n keys `lbl_direction`/`opt_forward`/`opt_reverse` (EN/TR/ES). Verified headless: each pass exactly reversed, identical geometry, valid G-code.

**Why:** The only inverse stroke available today is the mirror back-pass add-on (`back_pass_enabled`, `path_generator.py:331-385`), which is derived from a forward pass and can't stand alone. The user wants any roughing/finishing op to optionally run in the **inverse direction** (top→root) via a simple per-op selector — composing with pass count, shapes, and angles, with no geometry change.

**Scope:**
- New per-op field `direction` (`"forward"` default | `"reverse"`), applies to `roughing` and `finishing` ops.
- **Reverse = cut direction only:** generate each pass exactly as today, then **reverse the stored point order** of each pass. Pass-to-pass progression order is unchanged (a 6-pass op still steps in the same radial/Z order; only each pass's traversal flips).
- Swap which end gets the **rapid approach vs retract** so the rapids still bracket the (now reversed) cut correctly.
- **Keep** the existing mirror `back_pass_enabled` feature — the two compose (a reverse-direction op may still get a mirror back pass; note this interaction).
- No new path-shape math; geometry is untouched.

**Implementation hooks (confirm at build time):**
- `program_tab.py` — add a **Direction** combobox (Forward/Reverse) in the property editor (`~510+`) for roughing/finishing only; persist `op["direction"]`.
- `path_generator.py` — after a pass is generated and appended (the `len(toolpaths) > prev_paths_len` block, `~322`), if `op["direction"] == "reverse"`: reverse the pass point array (and its `projections`/`deviations`), and build the rapid approach to the new start / retract from the new end. Keep clearance correction as-is (order-independent).
- G-code/SCL: emitted naturally from the reversed point order — verify pass-label comments still read correctly.
- `i18n.py` — `lbl_direction`, `opt_forward`, `opt_reverse` (EN/TR/ES).
- Optional: a distinct color/line-style for reversed passes in `recolor_paths()` / `update_scene()` (otherwise they color by their op type as normal).

**Open question for implementation:**
- Reverse interaction with a mirror back pass on the same op (back pass mirrors the already-reversed forward pass → returns to forward direction). Confirm that's acceptable or gate it.

**Risk:** Low–Medium. Additive per-op field; reuses existing geometry. Main care points: rapid approach/retract ends and projection/deviation array reversal staying in sync with the path.

---

## Code Review Findings — 2026-06-22

Sorted **easy → hard / risky**. Severity legend: 🔴 functional bug · 🟡 UX / quality · 🟠 performance · ⚪ code hygiene

---

### 28. ✅ Done — Move `import datetime` to module level in `path_generator.py`

**File:** `path_generator.py` — inside `generate_gcode()`, line ~1218

**Problem:**
```python
def generate_gcode(...):
    ...
    import datetime          # ← inside the function body
    gen_time = datetime.datetime.now().strftime(...)
```

`import` inside a function body re-runs the module lookup machinery on every call. For G-code export (called every time the user saves), this is a tiny but unnecessary cost. It also makes the dependency invisible at the top of the file.

**Fix:** Move `import datetime` to the module-level imports at the top of `path_generator.py`, alongside the existing `import numpy`, `import math`, etc.

**Risk:** None. Pure hygiene change.

---

### 29. ✅ Done — Version label hardcoded in `_init_logo()` — won't update when `app_version` changes

**File:** `ui/main_window.py` line ~292

**Problem:**
```python
tk.Label(self.sidebar, text="V1.002", ...).place(...)   # hardcoded
```

The title bar correctly reads from `self.app.params.get('app_version', '?')`. This overlay label in the logo area is static — bumping the version in `settings.json` leaves it at "V1.002" forever.

**Fix:**
```python
tk.Label(self.sidebar, text=f"V{self.app.params.get('app_version', '?')}", ...).place(...)
```

**Risk:** None.

---

### 30. ✅ Done — Remove hardcoded personal path from `run()` method in `main.py`

**File:** `main.py` line ~1201

**Problem:**
```python
default_step = "C:/Users/PC/Documents/CAD_Files/deneme_mandrel.step"
```

This is leftover development scaffolding that silently fails with a FileNotFoundError on any machine that isn't the developer's. The `run()` method is the CLI/headless entry point (`if __name__ == "__main__"`); the GUI never calls it. Still, if someone runs `python main.py` directly they get an immediate crash.

**Fix:** Remove the default path so the prompt has no pre-filled value, or use `os.getcwd()` as the initial directory suggestion. The method body also uses `input()` which is a blocking console call — confirm this is intended for CLI-only use.

**Risk:** None. This path is not called by the GUI.

---

### 31. ✅ Done — `load_tools()` / `save_tools()` use relative path — breaks in frozen `.exe`

**File:** `ui/main_window.py` lines ~410, ~417

**Problem:**
```python
def load_tools(self):
    with open("tools.json", "r") as f:   # relative to CWD, not app dir

def save_tools(self):
    with open("tools.json", "w") as f:   # same issue
```

`save_settings_json()` in `main.py` correctly uses `get_base_path()` to resolve the app directory. `load_tools` / `save_tools` do not — they rely on the process's current working directory being the app folder. When launched via the `.bat` shortcut or as a frozen `.exe` from a different directory, `tools.json` is silently not found, so the tool library loads empty every session.

**Fix:**
```python
def load_tools(self):
    path = os.path.join(self.app.get_base_path(), "tools.json")
    try:
        with open(path, "r") as f:
            self.tool_library = json.load(f)
    except:
        self.tool_library = []
    self.app.tool_library = self.tool_library

def save_tools(self):
    path = os.path.join(self.app.get_base_path(), "tools.json")
    with open(path, "w") as f:
        json.dump(self.tool_library, f, indent=4)
    self.app.tool_library = self.tool_library
    self.app.tool_step_loader.invalidate()
```

**Risk:** Low. Pure path fix, no logic change.

---

### 32. ✅ Done — `load_step_prompt` calls `update_scene("all")` twice after STEP load

**File:** `ui/main_window.py` lines ~377-379

**Problem:**
```python
if path:
    self.app.load_step_file(path)   # already calls update_scene("all", force_path_calc=True)
    self.app.update_scene("all")    # redundant second full rebuild
```

`load_step_file()` internally calls `update_scene("all", force_path_calc=True)` at its last line. The second call in `load_step_prompt` runs path calculation and full scene render again for no reason. On a complex STEP file with many operations this can add 1-3 seconds of delay after every model load.

**Fix:** Delete the redundant line. The focus/lift calls that follow are unrelated and can stay:
```python
if path:
    self.app.load_step_file(path)
    # update_scene("all") ← remove this line
    self.attributes('-topmost', True)
    ...
```

**Risk:** None. `load_step_file` already performs the complete update.

---

### 33. ✅ Done — `recolor_paths()` builds `op_types` without back-pass entries — back passes stay blue

**File:** `main.py` lines ~1088-1097

**Problem:**
`recolor_paths()` is the fast path called when the user changes the active pass (no full recalculate). It builds `op_types` to map actor index → pass color. But it only appends one entry per *forward* pass, without inserting "back" entries for operations that have `back_pass_enabled=True`. Since `actors["paths"]` contains interleaved forward+back entries (F1, B1, F2, B2, …), the actor-to-type mapping shifts out of phase as soon as a back pass exists.

Result: back-pass actors always get the color of the *next* forward pass's type (usually blue/roughing) instead of their own teal color. The bug only manifests in the `recolor_paths()` fast path — `update_scene()` uses a separate correctly-built `op_types` list.

```python
# CURRENT — missing back entries
for op in ops:
    if not op.get("enabled", True): continue
    for _ in range(int(op.get("count", 1))):
        op_types.append(op.get("type", "roughing"))   # never inserts "back"
```

**Fix:** Mirror the logic from `update_scene` that already handles this correctly:
```python
for op in ops:
    if not op.get("enabled", True): continue
    op_type = op.get("type", "roughing")
    is_cb = op_type in ("cutting", "bending")
    count = 1 if is_cb else int(op.get("count", 1))
    has_back = not is_cb and op.get("back_pass_enabled", False)
    for _ in range(count):
        op_types.append(op_type)
        if has_back:
            op_types.append("back")

# Also add the "back" color branch:
elif op_types[i] == "back":
    prop.SetColor(0.0, 0.5, 0.5)   # teal
    prop.SetLineWidth(5)
```

**Risk:** Low. Self-contained in one method.

---

### 34. ✅ Done — Duplicate `MandrelManager` / `PathGenerator` instantiation in `SpinningApp.__init__`

**File:** `main.py` lines ~18-19 and ~55-56

**Problem:**
```python
def __init__(self, ...):
    # Block 1 — Initialize Managers
    self.mandrel_mgr = MandrelManager()   # line 18 — created, then immediately discarded
    self.path_gen = PathGenerator()       # line 19 — same

    self.params = self.load_settings()
    ...

    # Block 2 — Setup Plotter & UI  (line 54–57)
    self.mandrel_mgr = MandrelManager()   # ← replaces the one from line 18
    self.path_gen = PathGenerator()       # ← replaces the one from line 19
```

The first pair is created and then overwritten 35 lines later. This wastes allocation and is confusing — a reader assumes each manager is initialized once. If any future code between lines 18 and 55 writes to `self.mandrel_mgr`, that write is silently discarded.

**Fix:** Delete lines 18-19 (the first `MandrelManager()` and `PathGenerator()` assignments). Keep only the ones at lines 55-56.

**Risk:** None. The second instantiation already fully initializes both managers.

---

### 35. ✅ Done — `_create_sweeping_pass` appends raw Python lists — type inconsistency with rest of system

**File:** `path_generator.py` lines ~1758-1761

**Problem:**
Every other pass generator wraps results in `np.array()` before appending to the shared lists:
```python
# _create_adaptive_pass:
t_list.append(pts_arr)             # np.array
p_list.append(np.array(proj_pts))  # np.array
d_list.append(np.array(devs))      # np.array

# _create_and_store_pass:
t_list.append(np.array(final_points))
```

`_create_sweeping_pass` instead appends raw Python lists:
```python
t_list.append(path_pts)   # list of [float, float, float] — NOT np.array
p_list.append(projs)      # list
c_list.append([])         # bare list, not np.array([])
d_list.append(devs)       # list, not np.array(devs)
```

Downstream code that does `pts[:, 0]` on `paths[i]` succeeds for numpy arrays but raises `TypeError: list indices must be integers` on Python lists. Currently `update_scene` does `np.array(p, dtype=float)` at use time which auto-converts, but other callsites (e.g. `_correct_clearance_uniform`, PLC decimate) iterate with numpy idioms and may fail silently or incorrectly on a plain list.

**Fix:**
```python
t_list.append(np.array(path_pts, dtype=float))
p_list.append(np.array(projs,    dtype=float))
c_list.append(np.array([],       dtype=float))
d_list.append(np.array(devs,     dtype=float))
```

**Risk:** Low. Behavior is identical; only the type changes.

---

### 36. ✅ G-code export silently produces empty `.nc` file when paths are not yet calculated

**File:** `ui/main_window.py` → `save_gcode_logic()` + `path_generator.py` → `generate_gcode()`

**Problem:**
```python
def generate_gcode(...):
    if not self.last_calculated_paths: return ""   # silent empty string
```

If the user opens the app, skips clicking "Calculate", and immediately does File → Save G-code, they get a zero-byte (or header-only) `.nc` file with no warning. The file dialog succeeds, the status bar says nothing, and the `.nc` file looks valid but contains no toolpath moves. On a real CNC machine this would send the spindle home and stop immediately.

**Fix:** Add a guard at the top of `save_gcode_logic()`:
```python
def save_gcode_logic(self):
    if not self.app.path_gen.last_calculated_paths:
        messagebox.showwarning(
            t("msg_no_paths_title"),
            t("msg_no_paths")
        )
        return
    ...
```

Also add the keys `msg_no_paths_title` and `msg_no_paths` to `i18n.py` (EN/TR/ES).

**Risk:** None. Purely additive guard.

---

### 37. ✅ `_create_adaptive_pass` calls `get_radius_fast()` twice for every z-value

**File:** `path_generator.py` lines ~534-565

**Problem:**
The adaptive finishing pass iterates `z_vals` twice: once to build the roller path (calls `get_radius_fast(z)` + `get_normal_at_z(z)`), and again to build the projection line (calls `get_radius_fast(z)` a second time). For a 300 mm mandrel at 0.5 mm resolution that is 600 mandrel lookups instead of 300.

```python
for z in z_vals:          # PASS 1
    m_rad = mandrel_mgr.get_radius_fast(z)      # lookup 1
    nx, nz = mandrel_mgr.get_normal_at_z(z)
    ...

for z in z_vals:          # PASS 2
    m_rad = mandrel_mgr.get_radius_fast(z)      # redundant lookup 2
    px = center_x + m_rad + shell_offset + blank_thick
```

**Fix:** Cache the radii during the first pass and reuse:
```python
cached_radii = []
for z in z_vals:
    m_rad = mandrel_mgr.get_radius_fast(z)
    cached_radii.append(m_rad)
    ...  # use m_rad for path_points

for z, m_rad in zip(z_vals, cached_radii):   # reuse cached value
    px = center_x + m_rad + shell_offset + blank_thick
    proj_pts.append([px, 0, z])
```

**Risk:** None. `get_radius_fast` is a pure function with no side effects.

---

### 38. ✅ Cache repeated `get_radius_fast(rz_tip)` calls in `update_scene()`

**File:** `main.py` — multiple locations in `update_scene()`

**Problem:**
`update_scene()` calls `get_radius_fast(rz_tip)` and `get_normal_at_z(rz_tip)` / similar at lines ~354, ~795, ~845-847 — in some cases with the same `rz_tip` value but with separate lookups. Each call does a binary search through the mandrel profile array. Caching the result at the start of the function avoids redundant searches on every visual update.

**Fix:** At the top of `update_scene()`, after `rz_tip` is defined:
```python
# Cache once — used by gap indicator, tip-distance display, ref-point display
_clamped_z = max(self.mandrel_mgr.props.get("min_z", rz_tip),
                 min(self.mandrel_mgr.props.get("top_z", rz_tip), rz_tip))
_clamped_r  = self.mandrel_mgr.get_radius_fast(_clamped_z)
m_edge_x    = self.params.get("mandrel_pos_x_offset", 0.0) + _side * _clamped_r
```

Then replace the three separate `get_radius_fast` calls in the gap indicator and tip-distance sections with `_clamped_r` / `m_edge_x`.

**Risk:** Low. Local refactor within `update_scene`.

---

### 39. ❌ Discarded — Vectorize `_create_sweeping_pass` inner loop

---

### 40. ✅ `adaptive_bow_height` parabola formula is inverted — bows path inward at midpoint

**File:** `path_generator.py` line ~539

**Problem:**
```python
t = (z - z_min) / z_len
parabolic_offset = bow_height * 4 * ((t - 0.5)**2)
```

`4*(t − 0.5)²` evaluates to **1.0 at t=0 and t=1**, and **0.0 at t=0.5**. This is a W-shape (maximum at the endpoints, minimum at the center). With `bow_height > 0`, the path is pushed furthest from the mandrel at the start and end of the pass, and closest to the mandrel in the middle — a concave "pinch" rather than the convex bow the parameter name implies.

The intended behavior of a "bow height" in metal spinning is an arch: the roller lifts away from the surface in the middle of the pass and contacts at both ends. That is the standard arch formula:

```python
parabolic_offset = bow_height * 4 * t * (1.0 - t)
# t=0 → 0, t=0.5 → 1.0 (max), t=1 → 0
```

**Fix:** Replace the formula on line ~539 with the arch version.

**Impact:** Any saved program that uses `adaptive_bow_height > 0` currently gets the opposite of intended behavior. After the fix, existing non-zero bow_height values will behave correctly. Zero (the default) is unaffected.

**Risk:** Medium — changes path geometry for anyone using this parameter. Verify with a test mandrel before deploying.

---

### 41. ✅ No busy indicator during path calculation — UI appears frozen on complex geometry

**File:** `ui/main_window.py` — the "Calculate" button handler and `on_param_change` trigger path

**Problem:**
When path calculation runs (e.g. after clicking "Calculate" or toggling "Auto-Calculate"), the UI freezes silently for however long the calculation takes (can be 2-5+ seconds on dense mandrels with many operations and tight `collision_resolution`). The user has no feedback — no cursor change, no status bar message, no progress indication. On first use this looks like a crash.

**Fix (minimal):**
```python
def _run_calculate(self):
    self.config(cursor="watch")
    self.lbl_info.config(text=t("status_calculating"))
    self.update_idletasks()
    try:
        self.app.update_scene("paths", force_path_calc=True)
    finally:
        self.config(cursor="")
        self.lbl_info.config(text=t("status_ready"))
```

Add `"status_calculating"` to `i18n.py` (e.g. EN: `"Calculating paths…"`, TR: `"Yollar hesaplanıyor…"`).

**Note:** Tkinter is single-threaded. A true non-blocking progress bar would require running `calculate_paths` in a background thread, which is a larger change. The cursor + status update is a practical minimum that requires only 4 lines.

**Risk:** Low for the minimal version. Medium if threading is added.

---

### 42. ✅ Export success messages bypass i18n — hardcoded English strings in SCL and Recipe dialogs

**File:** `ui/main_window.py` — `export_recipe_action()` lines ~519-529, `export_scl_action()` lines ~639-655

**Problem:**
The success `messagebox.showinfo()` calls in both export actions contain hardcoded multi-line English strings with emoji, bypassing the `t()` i18n system entirely:
```python
msg = (
    f"Recipe converted successfully!\n\n"
    f"📊 Statistics:\n"
    f"   Total Lines: {stats.get('total_lines', 0)}\n"
    ...
)
messagebox.showinfo("Export Complete", msg)
```

Turkish and Spanish users see English-only output for these dialogs despite the rest of the UI being translated.

**Fix:** Extract the static portions into `i18n.py` keys, keep the dynamic statistics values as format arguments:
```python
# i18n.py — add keys:
# "msg_recipe_success": {"EN": "Recipe converted successfully!", "TR": "Reçete başarıyla dönüştürüldü!", "ES": "..."}
# "msg_stats_total_lines": {"EN": "Total Lines", ...}
# etc.

# main_window.py:
msg = (
    f"{t('msg_recipe_success')}\n\n"
    f"{t('msg_stats_header')}\n"
    f"   {t('msg_stats_total_lines')}: {stats.get('total_lines', 0)}\n"
    ...
)
```

**Risk:** Low. Purely cosmetic, no logic changes. Only touches `messagebox` content.

---

### 43. ✅ `on_param_change` converts bool parameters to `float` — subtle serialization hazard

**File:** `main.py` lines ~931-934

**Problem:**
```python
def convert(v):
    try: return float(v)   # True → 1.0, False → 0.0
    except: return v
real_val = convert(val)
self.params[key] = real_val
```

Boolean UI values (checkboxes like `cylinder_enabled`, `back_pass_enabled`, `plc_mode`, etc.) are passed as Python `bool` but come out as `float` (1.0 or 0.0) after `convert()`. At runtime `if 1.0:` works like `if True:`, so the logic is correct. However:
- `json.dump` serializes `True` as `true` but `1.0` as `1.0` — the saved `settings.json` slowly accumulates `1.0`/`0.0` where it should have `true`/`false`, making the file harder to read and potentially confusing any external tool that parses it strictly.
- `val == True` comparisons (some checkboxes) work for `bool(True)` but not for `float(1.0)` in strict mode.

**Fix:** Detect original type from the existing default value and preserve it:
```python
def convert(v):
    existing = self.params.get(key)
    if isinstance(existing, bool):
        # Checkboxes pass BooleanVar.get() which is already bool; strings "True"/"False" also handled
        if isinstance(v, bool): return v
        return bool(v)
    try: return float(v)
    except: return v
```

Or more simply, let tkinter `BooleanVar` values pass through as-is since `isinstance(True, int)` already handles them in most Python contexts — just guard against `bool` before the `float()` attempt:
```python
def convert(v):
    if isinstance(v, bool): return v
    try: return float(v)
    except: return v
```

**Risk:** Low. Functional behavior unchanged; only affects JSON serialization type.

---

### 44. ✅ `_rdp_decimate` recursive implementation risks Python stack overflow on dense paths

**File:** `path_generator.py` lines ~1538-1564

**Problem:**
The Ramer-Douglas-Peucker implementation is recursive:
```python
def _rdp_recursive(start, end, indices):
    if end - start <= 1: return
    # find max-deviation point
    if max_dist > tolerance:
        indices.add(max_idx)
        _rdp_recursive(start, max_idx, indices)   # recursive call
        _rdp_recursive(max_idx, end, indices)     # recursive call
```

For a balanced binary split, recursion depth = log₂(N). Python's default limit is 1000. That means paths with more than ~2^1000 points are safe — in practice fine. However, in the **worst case** (already-sorted data where each recursive call peels off only one point), depth = N−1. A sweeping finishing pass at 0.5 mm resolution over a 300 mm mandrel produces ~600 points. `600 > stack limit / 2` is not a problem today, but at finer resolution or longer mandrels (e.g. 1500 mm automotive parts at 0.1 mm resolution → 15 000 points) a `RecursionError` will occur with no graceful fallback.

**Fix:** Replace with an explicit stack (iterative DFS):
```python
def _rdp_decimate(self, points, tolerance):
    if len(points) <= 2:
        return list(range(len(points)))
    kept = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start <= 1:
            continue
        seg_vec = points[end] - points[start]
        seg_len = np.linalg.norm(seg_vec)
        max_dist, max_idx = 0.0, start + 1
        for i in range(start + 1, end):
            d = (np.linalg.norm(points[i] - points[start])
                 if seg_len < 1e-9
                 else np.linalg.norm(points[i] - points[start]
                      - np.dot(points[i] - points[start], seg_vec) / seg_len**2 * seg_vec))
            if d > max_dist:
                max_dist, max_idx = d, i
        if max_dist > tolerance:
            kept.add(max_idx)
            stack.append((start, max_idx))
            stack.append((max_idx, end))
    return sorted(kept)
```

**Risk:** Medium. The algorithm is well-defined but the iterative rewrite requires careful testing that it produces identical results to the recursive version. Test on known paths (straight line, tight arc, zig-zag) before deploying.

---

## Completed
- [x] **UI Internationalization (TR/EN/ES)** — `i18n.py` module with `t()` helper; 638 string keys across all tabs/dialogs; language selector in menu bar; persists to `settings.json`. *(2026-06-22)*
- [x] **Touch Point Calibration v3** — `ui/dialogs/touch_calibration.py` full rewrite. XZ canvas: mandrel profile, blank ring, roller circle, delta arrows, dimension brackets, machine-origin reference lines, zoom+pan. Z-axis calibration (mandrel root/top/custom reference → Program Start Z or G-code Z Offset). 5 apply buttons with ★ recommendation based on `origin_use_home`. *(2026-06-19)*
- [x] **Simulation speed control** — Slider in Program Tab action bar (1–20 → 0.25x–5.0x). `SimulationController.speed_multiplier` applied to all sleep delays. *(2026-05-24)*
- [x] **Program parameter presets / save per type** — "Save as Default" button in operation editor saves params to `op_presets[type]` in settings.json. `add_op()` loads preset automatically when available. *(2026-05-24)*
- [x] **PDF: 2D path diagram** — New page in PDF export with XZ-plane diagram: mandrel profile (gray), toolpaths (color-cycled), grid, tick labels, axis titles, stats line *(2026-05-24)*
- [x] **Pass shape mode per operation** — New `pass_shape` field per operation (`spline` / `linear_approach` / `linear_full`) *(2026-05-22)*
- [x] **G-code / SCL pass label in comments** — Every G0/G1 line ends with `(Op1 P2)`; every SCL line ends with `// ... [Op1 P2]` *(2026-05-22)*
- [x] **Pass shape & feed progression** — `p3_x` independent exit arm, `_end` progression params for all shape/feed values, contact zone slow feed *(2026-05-21)*
- [x] **Recipe CSV export** — `export_recipe_action` outputs CSV recipe via `gcode_to_recipe.py`; menu item in File menu
- [x] **Cylinder feature (CMD=40)** — Machine Tab cylinder section, scene visualization, GCode `M40 P{mm}`, SCL export *(2026-05-13)*
- [x] **GCode/SCL config header** — Machine origin, axis direction, blank, mandrel, and operation summary written as comments at the top of `.nc` and `.scl` files
- [x] **Working Area (Workspace) visualization** — Machine Tab workspace section (Max X, Min Z, Max Z) with show/hide toggle; semi-transparent box in 3D scene

---

## To-Do

### 27. UI Internationalization (TR / EN Language Switch) ✅ Done

**Goal:** All UI strings obey a selected language (Turkish or English). Language saved to `settings.json`, persists across sessions.

**Approach:** Lightweight `i18n.py` module — no external dependencies.
- `STRINGS` dict: `{key: {"EN": "...", "TR": "..."}}` for every label, button, menu item, messagebox string.
- `t(key)` helper function: returns `STRINGS[key][current_lang]` (falls back to EN if key missing).
- Language selector: combobox or flag button in the menu bar / Machine Tab header.
- On language switch: save new lang to `settings.json`, rebuild all tab widgets (destroy + recreate via existing `_create_widgets` pattern).

**Files to touch:**
- New: `i18n.py` — string dictionary + `t()` function + `set_language()` + `get_language()`
- `ui/main_window.py` — menu labels, messagebox strings, tab titles, language selector widget
- `ui/tabs/process_tab.py` — all label/button `text=` → `text=t("key")`
- `ui/tabs/program_tab.py` — same
- `ui/tabs/machine_tab.py` — same
- `ui/dialogs/tool_manager.py` — same
- `ui/dialogs/touch_calibration.py` — same (large dialog, ~50 strings)
- `main.py` — any UI-facing strings (load_step_prompt dialog, etc.)
- `settings.json` — add `"language": "TR"` default

**Language pairs:** Turkish (TR), English (EN), Spanish (ES) at launch. Expanding to 5 languages later is just adding keys to the dict — no structural change needed.

**Scope:** ~200 string keys, ~150 `text=` widget replacements + ~50 messagebox strings. Mechanical but large sweep.

### 24. Simulation Roller — Use STEP Mesh Instead of Sphere ✅ Done

**Problem:** During simulation (`SimulationController`) the animated roller is still drawn as a sphere (`pv.Sphere`), ignoring the STEP mesh assigned to the active tool.

**Where:** `simulation_controller.py` — the block that creates/moves the animated roller actor (`self.actors["anim_roller"]`). Currently calls `pv.Sphere(radius=r_rad, center=pos)`.

**Goal:** Replace that sphere with `ToolStepLoader.get_roller_mesh(tool_entry, side, rx_tip, rz_tip)` using the tip position derived from the current simulation point. Sphere fallback if no STEP file.

**Implementation notes:**
- `SimulationController` needs access to `tool_step_loader` and `tool_library` — pass them in, or read from `SpinningApp` (already owns both after the STEP feature is added).
- The simulation ticks every ~20 ms. `get_roller_mesh()` should be fast (canonical mesh is cached; only `_position_mesh` runs per tick — a `.copy()` + array ops on a small mesh).
- The roller mesh is removed/re-added each tick: preserve the `remove_actor` / `add_mesh` pattern.
- `r_rad` is still needed for the gap indicator even when using STEP.

---

### 25. Roller Contact Point — Tip Indicator in 3D View ✅ Done

**Problem:** There is no visual marker for the roller's actual contact tip. When a STEP mesh is shown, the tip (the point that drives the path) is invisible unless the user already knows where it is.

**Goal:** Render a small bright-green sphere (radius ~2 mm) or a crosshair glyph at the tip position `(rx_tip, 0, rz_tip)` — the exact point path generation addresses — both in the static view and during simulation.

**Implementation notes:**
- Add `"roller_tip"` to `self.actors` dict (init as `None`).
- In `update_scene()` section 4, after the roller mesh is placed, add/remove the tip marker:
  ```python
  tip_mesh = pv.Sphere(radius=2.0, center=(rx_tip, 0, rz_tip))
  self.actors["roller_tip"] = self.plotter.add_mesh(tip_mesh, color='lime', smooth_shading=True)
  ```
- During simulation: same position update logic as the roller itself.
- Make it toggleable (checkbox in Process Tab, param `show_roller_tip`, default ON when a STEP is loaded, OFF otherwise).

---

### 26. Roller Radius — Auto-Calculate from STEP File ✅ Done

**Problem:** The user must manually enter `radius` (mm) in the Tool Manager even when a STEP file is assigned. The radius is geometrically derivable from the STEP: it is the maximum distance from the shaft axis to any surface point, measured after shaft alignment.

**Goal:** Add an "Auto from STEP" button in the Tool Manager that loads the STEP (using `ToolStepLoader._get_canonical`), computes the bounding radius in the XZ plane (after shaft axis is mapped to Y), and fills in the Radius field automatically.

**Implementation notes:**
- After `_build_canonical()`, shaft is along Y. The XZ-plane radius at each vertex = `sqrt(x² + z²)`. Max of all vertices = the contact radius.
- The calculated radius should be the **maximum XZ distance from the shaft axis** (Y axis), not the 3D bounding sphere.
- `ToolStepLoader` should expose a helper:
  ```python
  def get_contact_radius(self, tool_entry) -> float | None:
      path = _resolve_step_path(tool_entry, self.base_dir)
      mesh = self._get_canonical(tool_entry, path)
      if mesh is None: return None
      pts = mesh.points  # tip at origin, shaft along Y
      return float(np.sqrt((pts[:, 0]**2 + pts[:, 2]**2)).max())
  ```
- Button in Tool Manager: "Calc from STEP" next to the Radius entry — calls this, rounds to 0.01 mm, fills the entry.
- After saving, radius propagates to any operation that uses this tool_id (same mechanism as manual radius change).

---

### 23. ✅ Done — Mandrel Scan: adaptive 2-pass (18-ray coarse + 72-ray refinement at outliers). ~4× faster on smooth mandrels.

**Problem:** Multi-ray azimuthal scan (72 rays × all Z slices) makes STEP loading noticeably slower than the original single-ray approach.

**Current state:** `_cache_mandrel_profile` in `mandrel_analyzer.py` fires 72 rays per Z slice (every 5°) to avoid the chord-underestimate that caused R_max to read smaller than the true CAD value. Accuracy is now correct.

**Candidate fixes:**
- Adaptive approach: do a coarse 8-ray scan first; only densify to 72 rays at Z slices where the coarse max differs from neighbours by > threshold (indicates a feature/edge).
- Use OCC BRep directly (`BRepExtrema_DistShapeShape` or section curves) instead of mesh ray-tracing — exact result, no multi-ray needed.
- Reduce to 36 rays (10° step) if 0.5 mm absolute error at R_max is acceptable for the mandrel sizes in use.

**Files:** `mandrel_analyzer.py` → `_cache_mandrel_profile`, `_SCAN_ANGLES`

---

### 10. Linear Approach — Forward Pass Geometry Fix ✅ Done

**Problem:** In `linear_approach` mode the P1→P2 segment is not rendering as a straight horizontal line. The path looks broken/curved where it should be linear.

**Expected geometry:**
1. **P1→P2 (approach arm):** Pure horizontal straight line at P2's radial X position. Z-only movement. No curve, no spline interpolation. `p1_x` is irrelevant — only `p1_z` controls arm length.
2. **P2→P3 (exit curve):** Smooth quadratic Bézier curve. Controlled by `exit_curve_tension` (control point height as fraction of P2→P3 chord) and `corner_blend` (fillet radius at P2 corner for G1 continuity between the straight arm and the exit curve).

**Pass Angle behaviour:** `pass_angle` must only rotate the P3 direction — it changes where P3 ends up (angle between P1→P2 and P2→P3 lines at P2). It does NOT change the straight approach arm or P2 position. Implementation: keep `θ_A = -90°` (approach is always -Z), set `θ_B = θ_A + pass_angle`, recompute `p3_x = L3 * cos(θ_B)` and `p3_z = L3 * sin(θ_B)` while preserving `L3 = sqrt(p3_x² + p3_z²)`.

**Current bugs to check:**
- The stored path contains the full quadratic Bézier (approach + exit merged). Rendering uses `pv.Spline` on the entire point array — this re-interpolates across the P2 corner and introduces curvature into the straight arm.
- `split_idx` (sharp-corner detection in `main.py`) should catch P2 and split there: render approach arm as a straight line (`lines_from_points`) and exit curve as `pv.Spline` separately. Verify that `split_idx` is actually triggered correctly for all cases (corner_blend > 0 softens the corner so dot product may not go negative → split_idx = None → whole path fed into Spline).
- When `corner_blend = 0`: dot at P2 should be very negative (180°+ bend) → split_idx fires. When `corner_blend > 0`: fillet smooths the corner → dot may not reach < 0 threshold → split not triggered → Spline overshoots/oscillates through the approach arm.

**Fix approach:**
- Track `_ap_split` index (already computed in `_create_and_store_pass`) through to `main.py` so rendering always knows where the approach arm ends, regardless of corner angle.
- Render `path[:ap_split+1]` as `lines_from_points` (straight), `path[ap_split:]` as `pv.Spline` (exit curve).
- Alternatively: store approach and exit as separate path segments in `toolpaths`.

---

### 11. Linear Approach — Back Pass Geometry Fix ✅ Done

**Dependency:** Implement TODO #10 (forward pass geometry) first.

**Expected back pass geometry (linear_approach mode):**
- Exact mirror of the forward exit curve: travels P3→P2 along the same Bézier arc as the forward P2→P3 exit, then follows the straight approach arm P2→P1 (horizontal -Z direction).
- With `bp_arc_x = 0, bp_arc_z = 0`: back pass traces the forward exit curve in reverse, then the straight arm in reverse. Zero asymmetry = perfect overlap with forward path.
- `bp_arc_x / bp_arc_z` offsets the Bézier control point relative to the forward exit control point for asymmetric shaping.
- Corner blend at P2 on the back pass: same fillet radius as forward, applied symmetrically.

**Current bugs to check:**
- Back pass Bézier control point base (`ctrl_base_bp`) uses `p2_z + bp_exit_ten * p2p3_len`. Verify this matches the forward exit control point exactly when `bp_arc_x = bp_arc_z = 0`.
- Back pass approach arm (P2→ap_start) must be straight, not curved — same constraint as forward arm.
- Rendering: same split-at-P2 logic needed for back pass paths.

---

### 12. Back Pass — Ironing / Surface-Conformal Return ❌ Discarded (prototype reverted)

**Idea:** The `mirror` back pass inherits the forward exit shape, driven by `pass_angle`,
so the return-stroke shape wobbles per pass with no clear physical meaning. In real metal
spinning the return is usually an **ironing / planishing** pass that rides the already-formed
contour at tight standoff, independent of the forward attack angle.

**Why discarded (2026-06-16):** the prototype (`back_pass_mode="ironing"`, contour trace via
surface-normal offset, `back_pass_allowance` standoff) produced "thrash" on the real mandrel
— passes diving in and out of the surface. Likely two causes: (a) normal-vector noise from
the ray-traced profile makes the per-z normal offset jitter radially; (b) the span was
`[contact_z → forward P3.z]`, whose length still follows `pass_angle` via P3. All of it
(`_build_ironing_back_pass`, `back_pass_mode`, `back_pass_allowance`, the UI Mode combo +
Back Allowance entry) was reverted.

**If revisited, fix first:**
1. **Smooth/denoise the contour normal** before offsetting (the forward pass dodges this by
   placing a single P2 point + spline; a per-z trace exposes the jitter).
2. **`pass_angle`-independent span** — base it on the pass stepover `(end_z-start_z)/(count-1)`
   or the forward approach span `[contact_z - p1_z, contact_z]`, not P3.z.
3. **Overshoot** slightly past the formed region at the flange end to clear piled-up material
   (original TODO #4 note).
4. **Swap interaction** — `back_pass_swapped` is mirror-only; gate it if ironing returns.

**Current state:** `mirror` is the only back-pass style. It reverses the forward forming
portion verbatim (follows `p2_radius` + exit curve), with `bp_arc_x/z` as a parabolic bow.

---

### 13. Forward Pass — Rotate the Exit Tail After a Mid Point ✅ Implemented (simplified)

Started as a full two-Bézier "mid anchor with locked T2→M" (over-engineered per user). Reduced
to the actual need: **pick a point M along the P2→P3 exit and rotate everything after it about
M by a few degrees.**

**Done (`path_generator.py` exit-curve block, `linear_approach`):** the exit is the original
single quadratic T2→P3, then if `exit_mid_rotation` (deg) ≠ 0:
- M = point at `exit_mid_t` fraction along the exit (default 0.5, clamped 0.05–0.95).
- Everything after M is rotated about M by `exit_mid_rotation` degrees (Y-axis, XZ plane, via
  `_apply_rotation`). T2→M is untouched; P3 rides along with the tail.
- `exit_mid_rotation = 0` / absent → identity (verified bit-exact == no param → backward
  compatible).

**UI (`program_tab.py`):** two entries — `Exit Mid Rot (deg)` and `Exit Mid t`. (Old
`exit_mid_enabled` / `exit_mid_x/z` / `exit_curve_tension_2` removed.)

**Verified:** `rot=20°` swings the tail (P3 moves ~6mm, rigid — point count unchanged);
clearance correction still applies (rot −30° toward the mandrel → worst clearance 0.500); back
pass automatically follows (reverses the whole forming portion).

**Follow-up:** interactive dragging of P2/P3/the exit — TODO #8.

---

## Research Findings — 2026-06-16 (audit, not yet actioned)

Severity: 🔴 functional · 🟡 cosmetic/visual · ⚪ dead code/smell

### 14. ✅ Done — `safety_clearance_roller_to_part` exposed in Process Tab as "Safety Standoff (mm)"
`process_tab` exposes `target_clearance` / `collision_resolution` / `gcode_resolution` but
NOT `safety_clearance_roller_to_part`, which `calculate_paths` bakes into P2 placement:
`total_off = r_tool + blank_thick + safety_clearance(0.5) + allowance`, while the correction
separately enforces `target_clearance(0.5)`. **Two clearance knobs, both default 0.5, stack** —
one settable, one hidden. User adjusting Target Clearance doesn't see the other 0.5 mm in the
nominal standoff.
**Action:** surface `safety_clearance_roller_to_part` in process_tab Safety section, OR merge
the two concepts into one clearance param. Decide which is the "real" standoff.

### 15. ✅ Done — Dead code removed: gui_manager import/branch in main.py, auto_align_rotation dead read in path_generator.py. Files gui_manager.py / ui_sidebar.py remain on disk as orphans.
Live app is `SpinningApp(headless=True)` → Tkinter tabs (`ui/`). Dead/duplicate GUIs still in
the tree:
- `gui_manager.py` (PyVista sliders) — instantiated only when `not headless` (`main.py:56`),
  never in the live `main_tk.py` path.
- `ui_sidebar.py` (Qt) — only used by alternate entry `main_qt.py`.
Their param wiring duplicates the tabs. This is the source of the **`auto_align_rotation` vs
`auto_calc_angle` duplicate** (two params, one concept; see #16).
**Action:** confirm `main_qt.py` / non-headless mode are abandoned, then delete `gui_manager.py`,
`ui_sidebar.py`, `main_qt.py` (and the `not headless` branch in `main.py`). Keep a backup.

### 16. ❌ Discarded — `auto_align` dead read (`path_generator.py:76`)

### 17. ✅ Done — Pass coloring fixed: op_types list replaces legacy num_rough index. Back passes = teal.
`num_rough = int(params["num_sweeping_passes"])` (legacy global) compared against `i`
(toolpath index) via `is_finish_pass = (i >= num_rough)`. With the operations dict, finishing
ops, or `back_pass_enabled` (doubles entries), blue/orange coloring is unreliable. The
`op_feeds` list just above (`:396‑409`) already mirrors the real toolpath order — build
`is_finish`/`is_back` the same way (or reuse `program_tab._get_pass_type_list`). G-code/paths
unaffected; 3D color only.

### 18. ✅ Done — Back-pass projections/deviations recomputed from actual back-pass path via _compute_proj_and_devs()
Mirror back pass uses `_bp_proj = projections[-1][::-1]` / `_bp_devs = deviations[-1][::-1]`
(the FULL forward arrays) while it now stores only the forming portion (shorter). Cyan
projection lines / heatmap for back passes are misaligned. Rebuild proj/devs from the actual
back-pass points (or slice to the forming portion).

### 19. ✅ Done — `visual_shell_offset` removed (`path_generator.py`)
`visual_shell_offset = shell_offset + (1.0 if is_finish else 0.0)` is passed as the real
`shell_offset` into the clearance math, so finishing passes silently get +1 mm standoff. Either
intended (rename to e.g. `finish_extra_standoff` and expose) or a viz tweak leaking into
geometry — decide and rename.

### 20. ✅ Done — Dead code removed (`path_generator.py`)
- `safety_tolerance = 0.05` (`:739`) — never used.
- `_calculate_adaptive_z_distribution()` (`:573`) — returns `[]`, deprecated stub.
- `approx_len` / `num_points` computed every clearance iteration but only used by the `spline`
  branch.
- `p3_z` sign convention: UI asks for negative, `calculate_paths` does `p3_z = abs(p3_z)` and
  treats it as +Z forward unless `pass_angle` is set — tooltip vs behavior mismatch (clarify
  the convention or honor the sign).

### 21. ✅ Done — `last_pass_extension_z` removed from path_generator, main, constants, settings
- `last_pass_extension_z` — extends last roughing pass past mandrel top (`end_h = top_z +
  last_pass_ext`); meaningful, not surfaced (default 0). Consider exposing per-op or in process.
- `feed_rate_mm_min`, `surface_speed_m_min`, `spindle_speed_limit_rpm` — fallback defaults only;
  per-op values are used instead. Harmless; remove or wire intentionally.

### 22. ✅ Done — `adaptive_rough_mode` → `conformal_clearance_all_operations`, `conformal_clearance` → `conformal_clearance_operation_specific`
- `conformal_clearance` (per-op) falls back to `adaptive_rough_mode` (global) — two controls for
  "place P2 along the surface normal." Confirm both are wanted.
- `cylinder_show` (visual) vs `cylinder_enabled` (emits M40) — similar names, different jobs;
  fine but easy to confuse.

---

### 1. Tool Radius — Auto-sync from Tool Library ✅ Done
Removed the editable `r_tool` entry from operation settings. Replaced with a read-only label that shows radius from tool library. Selecting a different tool updates both params and the label live. Cutting/bending block also updated to sync `r_tool` from library on tool change.

### 2. Finishing Pass — Straight Line Unchecked + Count > 1 Still Single Line ❌ Discarded
**Root cause found:** `calculate_paths` (path_generator.py:267–268):
```python
else:
    self._create_sweeping_pass(start_h, end_h, ...)  # inside for i in range(count)
```
`start_h` / `end_h` do not change with pass index `i` → count=3 produces 3 identical overlapping sweeping paths → appears as one line.
Roughing has `target_z = start_h + (i / (count-1)) * (end_h - start_h)` stepover logic; finishing sweeping mode does not.
**Action:** For each pass in sweeping mode, apply a different radial offset (e.g. `finish_allowance` stepping down per pass) or vary Z range per pass.

### 2b. Conformal Clearance for Roughing ✅ Done
Added per-operation `conformal_clearance` checkbox to roughing UI. When enabled: P2 contact point is placed along surface normal (`nx * total_off`, `nz * total_off`) — identical to finishing behavior. Falls back to global `adaptive_rough_mode` if not set. Both X and Z of P2 are now corrected (previously only X was corrected).

### 4b. Back Movement / Reverse Pass ✅ Done
- `calculate_paths`: exact reversal of the forward path stored as back pass. `self.last_back_pass_meta[idx] = {"feed": bp_feed}`.
- `generate_gcode`: after each forward pass block, checks `last_back_pass_meta` and consumes the back pass path with its own `G1 F{bp_feed}`, separate G0 approach/retract.
- UI (roughing section): Enable checkbox + Back Feed. In `linear_approach` mode: Bézier arc from P3→P2 with Back Arc X / Back Arc Z midpoint offsets (0 = straight line). Non-linear_approach: plain reversal.

### 5. Back Pass Arc Customization ✅ Done
Quadratic Bézier arc for back pass entry (P3→P2) in `linear_approach` mode.
- `back_pass_arc_x`: pushes arc midpoint outward (+) or inward (−) in X. Default 0.
- `back_pass_arc_z`: pushes arc midpoint toward P3 (+) or P2 (−) in Z. Default 0.
- P2 and P3 positions are always identical to forward pass — only the arc shape between them changes.
- `spline` / `linear_full` modes: fall back to plain reversal.

### 6. Back Pass & Forward Approach Point Count Fix ✅ Done
- Forward `linear_approach`: approach arm reduced to 2 points (start + P2) before `gcode_resolution` downsampling. Dense linspace was only needed for collision checking, not for storage.
- Back pass Bézier arc: downsampled with `gcode_resolution` (same as forward path). Was stored at raw `check_res` density (4× more points than forward).
- Back pass approach arm: stored as 2 points only (straight Z line).

### 7. P2 Z Extend (Roughing Gap Fill) ✅ Done
New per-operation `p2_z_extend` parameter for roughing. Extends each pass's contact point in +Z without shifting the approach arm start:
- Approach arm start: `target_z − p1_z` (unchanged)
- Approach arm end (P2): `target_z + p2_z_extend` (extended)
- Implemented by passing `effective_p1_z = p1_z + p2_z_extend` to `_create_and_store_pass`.
- Gap-fill formula: `p2_z_extend = spacing − p1_z` where `spacing = (end_z − start_z) / (count − 1)`.

### 9. Pass Angle + Progressive Angle Across Passes ✅ Done

**Pass Angle** — yeni per-op parametre (`pass_angle`, derece). P2'deki iç açıyı tanımlar:
- A = P2→P1 = (p1_x, -p1_z) in XZ, B = P2→P3 = (p3_x, +|p3_z|) in XZ
- `pass_angle = acos(dot(A_norm, B_norm))` — 180° = düz geçiş, küçük açı = sivri dönüş
- **Option B:** `L3 = sqrt(p3_x² + |p3_z|²)` sabit (P2→P3 kolu uzunluğu korunur), sadece yön değişir

**Matematik:**
```
θ_A  = atan2(-p1_z, p1_x)          # P2→P1 vektörünün +X'ten açısı
                                    # linear_approach'ta sabit = -90°
θ_B  = θ_A + pass_angle             # P2→P3 hedef yönü
L3   = sqrt(p3_x² + |p3_z|²)       # sabit kol uzunluğu
p3_x_new  = L3 * cos(θ_B)
p3_z_new  = L3 * sin(θ_B)          # pozitif = P3 P2'nin Z üstünde (ilerisi)
```
- 180°'de: θ_B = θ_A + 180° → B, A'nın tam tersi → düz geçiş ✓
- `linear_approach`'ta θ_A = -90° sabit; 180°'de p3_x=0, saf +Z çıkış
- p3_x_new < 0 olursa (θ_B > 90°) mandrel tarafına geçer — collision check bunu yakalar

**Progressive Angle** — checkbox (`progressive_angle_enabled`):
- Etkin olduğunda birinci pas `pass_angle`'ı kullanır, son pas 180°'ye ulaşır
- Lineer interpolasyon: `angle_i = pass_angle + i * (180 - pass_angle) / (count - 1)`
- L3 tüm paslarda aynı kalır; sadece θ_B değişir → P3'ün yönü açılır
- Fiziksel anlam: ilk paslarda rulo sivri döner (malzemeyi iter), son paslarda düz geçer (ütüler)

**Implementation:**
- `calculate_paths` döngüsünde `i` indeksine göre `effective_angle` hesapla
- `_create_and_store_pass`'a `pass_angle` override olarak geç; içinde `p3_x_offset / p3_z_offset` L3+θ_B'den yeniden hesaplanır
- `pass_angle` boşsa (None) mevcut p3_x / p3_z doğrudan kullanılır — geriye dönük uyumlu
- UI: Path Shape bölümüne `Pass Angle (deg)` entry + `Progressive Angle` checkbox ekle

### 8. ❌ Discarded — Interactive Control Point Editing (P1 / P2 / P3 + Spline)

### 3. Roughing Clearance — Surface Angle Not Accounted For ✅ Done
**Root cause found:** `calculate_paths` (path_generator.py:236–237):
```python
adaptive_rough = params.get("adaptive_rough_mode", False)
p2_x = center_x + r_contact + (nx * total_off if adaptive_rough else total_off)
```
With `adaptive_rough_mode=False` (default), P2 contact point is placed with a purely radial offset — surface normal is ignored. On a slanted mandrel surface the actual perpendicular clearance is `total_off * cos(angle)` < `total_off`.
Finishing `_create_sweeping_pass` (line 1220–1221) always applies `nx * total_off` + `nz * total_off` → clearance is always perpendicular to surface.
**Action:** Expose `adaptive_rough_mode` as a visible checkbox in Process Tab, or apply normal-based offset to roughing P2 unconditionally (the way sweeping/finishing already does).

### 4. Back Movement (Reverse Pass / Ironing Pass) Feature
**Metal spinning context:** A back pass is NOT a simple reversal of the forward path. Key characteristics:
- Traces the **mandrel contour surface** at tight clearance (r_tool + part_thickness), like a sweeping/finishing pass — not the same intermediate offset as the forward roughing pass
- Acts as an **ironing stroke** — smooths and work-hardens material, redistributes thinned areas
- Has its **own feed rate** (typically slower) and its own **radial allowance** (`back_pass_allowance`, default 0 = mandrel surface)
- Direction: end_z → start_z (flange direction)
- May extend slightly beyond the forward pass Z range at flange end to clear piled-up material
**Action:**
- Add `back_pass_enabled` checkbox per operation (roughing primarily, finishing optionally)
- Add `back_pass_allowance` (mm, default 0.0) and `back_pass_feed` (mm/min) per-op params
- Implementation: after each forward pass in `calculate_paths` loop, if `back_pass_enabled`: call `_create_sweeping_pass(end_h, start_h, mandrel_mgr, center_x, r_tool, blank_thick, back_pass_allowance, ...)` — NOT the forward spline reversed
