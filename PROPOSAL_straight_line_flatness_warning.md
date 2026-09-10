# Proposal — Straight-Line Finishing "Non-Constant-Angle Surface" Warning

**Date:** 2026-07-14
**Status:** ✅ IMPLEMENTED 2026-07-14 (headless-verified; **GUI smoke PENDING; commit PENDING**).
Engine metric `PathGenerator._straight_line_flatness_dev` + per-op check populating
`last_flatness_warnings` (`path_generator.py`), params `straight_line_flatness_warn` /
`straight_line_flatness_tol` (`main.py`), UI `refresh_flatness_status` /
`_show_flatness_popup` (`ui/main_window.py`) called from `ui/tabs/program_tab.py`
after a successful calc, i18n ×4 (EN/TR/ES), help note, `_test_straight_line_flatness.py`
(all pass) + clamp-zone regression PASS. Original proposal below.
**Scope:** Machine ID-111 (and any XZ machine using `straight_line_mode` finishing).
**Risk:** Minimal — advisory only, mode-scoped, no toolpath/G-code change.

---

## 1. Purpose

Straight-line finishing (`straight_line_mode`) emits a 2-point line that is only
clearance-correct when the mandrel surface between `start_z` and `end_z` is a
**straight (constant-angle) profile**. On a curved / bulged / slope-changing region
the line drifts off the surface and the mid-line clearance varies — a silent gouge
(or under-finish) risk. This feature **detects and warns** when that precondition is
violated. **Advisory only — the toolpath and G-code are unchanged.**

Background: the 2-point design is intentional and correct on constant-angle surfaces
(a cone has a constant normal, so offsetting both endpoints along the normal produces
a line parallel to the surface at constant perpendicular distance = the clearance).
This warning simply guards the assumption that the region is actually conical.

---

## 2. Detection metric (cheap, no normals needed)

For each enabled op with `type == "finishing"`, `straight_line_mode == True`, and
adaptive mode off:

1. Let `s = start_z`, `e = end_z`. Skip if `|e - s| < 1e-3`.
2. Sample the profile radius at N interior points:
   `z_i = linspace(s, e, N)`, `r_i = mandrel_mgr.get_radius_fast(z_i) + shell_offset`
   with `N = clamp(int(|e - s|) + 1, 8, 65)` (~1 sample/mm, capped).
3. Linear reference (what a true cone would be):
   `r_chord(z_i) = r_s + (r_e - r_s) * (z_i - s) / (e - s)`
4. Radial deviation: `dev_i = r_i - r_chord(z_i)`.
   - `dev_max_pos = max(dev_i)` -> surface bulges **toward** the tool -> **reduced
     clearance (gouge risk)**.
   - `dev_max_neg = min(dev_i)` -> surface dips **away** -> clearance grows
     (**under-finished band**).
5. `dev = the extreme of largest magnitude`; warn if `|dev| > tol`.

Notes:
- Radial deviation slightly **overstates** the true perpendicular clearance error
  (by `1/cos(slope)`), so it is conservative for a safety advisory — good.
- Sign is meaningful for severity (see section 5).
- A true cone gives `dev ~= 0` -> never warns. A cylinder -> `dev = 0`. This matches
  the design intent exactly.

---

## 3. Parameters (params-level, global v1)

| Key | Default | Meaning |
|---|---|---|
| `straight_line_flatness_warn` | `True` | Enable the advisory |
| `straight_line_flatness_tol` | `0.15` (mm) | Deviation threshold to warn |

Add defaults in `main.py load_settings()`. NOT a `MACHINE_PROFILE_KEY` (it is
geometry/quality, not machine hardware). Per-op override can come later; v1 is global.

---

## 4. Engine hook (`path_generator.py`)

- **Init:** near line 100 (beside `self.last_clamp_warnings = []`), add
  `self.last_flatness_warnings = []` (reset every `calculate_paths`).
- **Populate:** inside the straight-line branch (~`:507-518`), where `start_h`,
  `end_h`, `mandrel_mgr`, `shell_offset` are already in scope. Gate on
  `params.get("straight_line_flatness_warn", True)`. On violation append:
  ```python
  {"op_index": op_index, "op_type": "finishing",
   "start_z": start_h, "end_z": end_h,
   "max_dev": dev, "tol": tol}     # max_dev signed: + = toward tool
  ```
- **Log** (mirror the `:756` clamp line): if the list is non-empty, one
  `logger.warning("[FLATNESS] ...")` with count + first op. Headless-visible.

This is a pure read of geometry already loaded — no dependency on toolpath order,
mirroring/side, or PLC mode.

---

## 5. UI surfacing (`ui/main_window.py`) — mirror `refresh_clamp_status()`

New `refresh_flatness_status()`, called from the **same two places** the clamp refresh
is (async poller + synchronous Calculate), reading `path_gen.last_flatness_warnings`:

- **Status bar (always):** amber indicator when non-empty, e.g. `status_flatness_warn`
  -> "N op(s): straight-line finish on curved surface".
- **Modal (tiered by severity):**
  - `max_dev > 0` (toward tool -> **gouge**): pop the modal (Confirm /
    Don't-show-again, session suppress flag `_flatness_popup_suppressed`), same shape
    as `_show_clamp_popup`.
  - `max_dev < 0` (away -> under-finish, quality only): status-bar + log only,
    **no modal** (do not nag on a non-safety case).
- To avoid two popups colliding with the clamp advisory in one calc, show clamp first,
  then flatness; or concatenate into one advisory dialog. Simplest v1: independent,
  clamp then flatness.

---

## 6. i18n (`i18n.py`) — EN / TR / ES all three (per project rule)

- `status_flatness_warn` — status-bar text, `{n}`, `{idx}`.
- `msg_flatness_warn_op` — per-op line, `{idx} {sz} {ez} {dev}`.
- `msg_flatness_warn_body` — modal body, `{n} {tol}` + ops block.

Example EN body: *"{n} straight-line finishing op(s) run over a non-constant-angle
surface (deviation > {tol} mm). The 2-point line assumes a straight profile; here the
surface bows away from it, so the clearance is not held along the whole pass. Verify or
switch these to sweeping/adaptive finishing."*

---

## 7. Help text

Update the `_C` dict in `help_window.py` (per standing policy) — add a note under the
finishing section explaining the straight-line precondition and this warning.

---

## 8. Test (`_test_straight_line_flatness.py`, headless, mirror `_test_clamp_zone.py`)

Build synthetic profiles (or stub `get_radius_fast`) and assert `last_flatness_warnings`:

- **Cone** (linear r vs z) -> 0 warnings.
- **Cylinder** (constant r) -> 0 warnings.
- **Barrel/convex** (mid-bulge) -> 1 warning, `max_dev > 0`.
- **Concave dish** -> 1 warning, `max_dev < 0`.
- **Slope change** (two cones meeting) -> 1 warning.
- **Zero-length span** (`start_z == end_z`) -> 0 warnings, no crash.
- **Below tol** (tiny bow < tol) -> 0 warnings.
- Regression: a sweeping/adaptive finishing op and a roughing op -> never flagged
  (branch gating).

---

## 9. Edge cases / guards

- `get_radius_fast` returns `None` at some z -> skip that sample (do not crash).
- `end_z < start_z` (reverse span) -> use `abs`, sample either order; result identical.
- Mode gating: only the `straight_line_mode` branch; `finish_trace_mandrel_profile`
  (adaptive) and sweeping are already surface-following and must **not** be flagged.
- Respect `enabled` (skip disabled ops — the loop already does).

---

## 10. Non-goals / safety envelope

- **No toolpath/G-code change.** Detection is a read-only geometry sample; the emitted
  2-point line is byte-identical to today.
- Not a clearance *fix* — it flags where the mode's assumption breaks so the operator
  switches to sweeping/adaptive or splits the op. Consistent with the "warning-first"
  stance chosen for the clamp zone (#62).
- Zero effect when the surface is conical/cylindrical -> current programs stay silent.

---

## 11. Effort / risk

- **Effort:** small — one geometry loop in the engine, one UI method cloned from clamp,
  3 i18n keys, one test file.
- **Risk:** minimal — advisory, gated by `straight_line_flatness_warn`, mode-scoped,
  no engine-path change.

---

## Appendix — Background (why this is the right guard, not a radial rewrite)

An earlier research report (`RESEARCH_finishing_z_shift.md`) claimed straight-line
finishing starts ~34 mm too high in Z and recommended switching it to a radial offset.
That report was **based on the wrong mandrel orientation** (it skipped the recipe's
`mandrel_rot_x = 90` + `update_geometry`, measuring a raw side-silhouette cone instead
of the real near-cylindrical wall). Running the real pipeline, every finishing pass
lands within ~0.3 mm of its typed Z — no shift. The normal offset the code uses is the
**clearance-correct** construction on a tilted wall; a radial offset would *undershoot*
clearance on cones. Hence the correct action is this precondition warning, not a change
to the offset direction.
