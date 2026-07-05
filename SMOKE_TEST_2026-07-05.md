# GUI Smoke Test — 2026-07-05 authoring batch

Covers the uncommitted/headless-only work: #61 (reach, Continue, Reach⟲), #62 (clamp
zone), #64 (Split), plus older unchecked items #56, #57, #58.

> **Launch note (from HANDOVER 2026-07-01b):** start via the `.bat` / activated
> `spinning_cam` conda env — calling `python.exe` directly triggers the MKL BLAS
> delay-load crash `0xc06d007f` (fake numpy crash). Load a STEP first, then check
> `update_geometry` ran (clearance model gotcha) before judging geometry.

Tick each box in a real window. "Headless PASS" is already true for all of these —
this only proves the GUI wiring, not the math.

---

## Pre-flight
- [ ] App launches from the batch/activated env without error.
- [ ] Load a STEP model; 3D view shows mandrel + flat blank disc.
- [ ] Program tab opens; ops tree shows columns incl. **RealEndZ**, **End Reach**, **End Angle**.

## #61 step 1 — Single `reach` parameter + End columns
- [ ] Select an op → property editor shows **"Reach |P2→P3| (mm)"** field.
- [ ] Leave `reach` empty → Calculate → toolpath identical to before (back-compat).
- [ ] Set `reach` to a value → Calculate → exit (P3) stroke length changes as expected.
- [ ] **End Reach** / **End Angle** columns populate after Calculate (not blank/0).
- [ ] Change **clearance** only, same `reach` → Calculate → absolute END point stays put
      (clearance-independent reach). Low clearance may safety-correct — that's expected.

## #61 — Angle⟲ (surface-derived fan-end angle)  [NEW 2026-07-05b]
- [ ] Toolbar shows **Angle⟲** (after Reach⟲).
- [ ] Select an op with a **Pass Angle** set → click Angle⟲ → `progressive_angle_end` fills;
      popup shows slope / approach / result. Cylinder wall → ~180°, cone → the wall slope.
- [ ] No Pass Angle → info popup ("set a Pass Angle first"), nothing filled.
- [ ] ⚠️ Confirm forming direction (up/down the wall) on a real part before trusting it.

## #61 — "Reach follows blank" toggle (option B)  [NEW 2026-07-05b]
- [ ] Op editor shows **"Reach follows blank"** checkbox under the Reach field.
- [ ] Tick it → reach fills immediately from the flange; the Reach field + End Reach column update.
- [ ] Change the op's **end_z** (form higher) → after recalc, reach **shrinks** (kisses the smaller flange); lower end_z → reach grows back.
- [ ] Untick → reach stays at the last value and becomes manually editable again.
- [ ] No blank / cutting-bending op → toggle does nothing harmful.

## #61 — Reach fold-back clamp (verify the >180° fold is gone)  [NEW 2026-07-05b]
- [ ] Reload/recalc the tall roughing fan (angle sweeping toward ~180°).
- [ ] Top passes now stop at vertical — **no curling past 180°** in the 3D view.
- [ ] Lower the op's clearance → behaves the same (no fold); raising it doesn't re-introduce it.

## End Angle column frame fix (verify)  [NEW 2026-07-05b]
- [ ] A pass authored at e.g. 113° Pass Angle now reads **~113° in End Angle** (not 23°).

## Reach⟲ diameter guard (verify)  [NEW 2026-07-05b]
- [ ] Set Sheet Radius to a diameter-like value (> mandrel base × 2.5) → Reach⟲ pops the
      "did you enter the diameter?" question; correct radius → no warning.

## #61 step 2 — "Continue ⤵" button  ✅ GUI VERIFIED (user 2026-07-05)
- [x] Toolbar shows **"Continue ⤵"**.
- [x] Build op A (multi-pass, with Pass Angle + reach) → Calculate.
- [x] Add op B, select it, click **Continue ⤵**.
- [x] B's **Start Z / angle / reach / clearance** fill from A's last-pass end-state.
- [x] **Tool is NOT copied** (B keeps its own tool).
- [x] Edit B afterwards → A is unaffected (one-shot, no live link).
- [x] Click Continue on the FIRST op (no previous) → graceful message, no crash.

## #61 step 4 — "Reach⟲" (flange reach estimate) ⚠️ also needs PHYSICAL check
- [ ] Toolbar shows **"Reach⟲"**.
- [ ] Select an op, click **Reach⟲** → `reach` field fills; labeled/announced as ESTIMATE
      (never silent).
- [ ] Multi-pass op with **Pass Angle set** → it also fans **progressive_reach_end**
      (bigger reach at base, smaller near top).
- [ ] Click with no op selected → info popup ("select an op"), no crash.
- [ ] Sanity: computed reach shrinks for passes higher up the mandrel (toward flange).
- [ ] ⚠️ DO NOT run on the machine until a physical touch check confirms no gouge.

## #62 — Clamp-zone exclusion (Phase 1, warn-only)  ✅ WARNING VERIFIED (user 2026-07-05)
- [x] Machine tab shows **clamp_zone_baseline**; Process/part shows **clamp_zone_length**.
- [x] Set a clamp length → 3D view draws the **red excluded band** at the mandrel base.
- [x] Give an op a `start_z` inside the clamp zone → Calculate → **warning** appears
      (`last_clamp_warnings`), but paths still generate (Phase 1 = warn, not clip).
- [ ] Per-part override persists after save/reload of the .ssp.
- [ ] ⚠️ KNOWN COSMETIC (deferred, user 2026-07-05): the red band is a fat solid cylinder,
      so a pass just above the zone can *look* inside it though it's outside (no warning =
      correct). Z-math matches the warning exactly. Fix = slim the band to hug the surface.

## #64 — "Split…" operation  ✅ GUI VERIFIED (user 2026-07-05)
- [x] Toolbar shows **"Split…"**.
- [x] Select a multi-pass op → **Split…** opens the divider dialog.
- [x] Choose chunks → confirm → op replaced by N chunk-ops.
- [x] Calculate → union of chunk toolpaths == original (visually same forming path).
- [x] Each chunk is a normal, independently-selectable op; Move Up/Down works to reorder.
- [x] Cancel in the dialog → nothing changes.

## #57 — Progressive Reach checkbox (gating)  ✅ GUI VERIFIED (user 2026-07-05)
- [x] Op WITHOUT Pass Angle → no Progressive Reach checkbox shown.
- [x] Set **Pass Angle** → **Progressive Reach** checkbox appears.
- [x] Tick it → **reach end** field appears; untick → field hides.

## #56 — Delete/reorder no longer reverts next op (regression)  ✅ GUI VERIFIED (user 2026-07-05)
- [x] Create two rough/finish sets; second created from default, then EDIT its values.
- [x] Delete the FIRST set → the second set **keeps its edited values** (not reverted).
- [x] Move Up/Down between two edited ops → neither op's values get clobbered.

## #58 — Calibration "Challenger Rr (axis)" (also needs physical A/B)
- [ ] Open Touch Calibration; with a STEP tool loaded, **"Challenger Rr (axis):"** shows a
      value + **Δ vs current**.
- [ ] **"Use ▸"** types the challenger value into the **Rr** box (only that field changes).
- [ ] Confirm no tool value / tools.json is written (read-only) — Δ read-out updates.
- [ ] ⚠️ Physical A/B (T0101 then T0103, compare Delta X) is separate, on-machine.

---

## After the smoke test
- [ ] Note any failures inline above.
- [ ] Before committing: ensure `__pycache__` / `dist` / `build` are untracked.
- [ ] Commit the passing batch (leave #61 step 4 & #58 flagged until physical validation).
- [ ] Update TODO.md status lines + LAST_CHANGES.md.
