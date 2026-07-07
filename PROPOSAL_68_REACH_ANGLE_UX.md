# Proposal #68 — Simplifying the Reach / Pass-Angle parameter family

**Status: APPROVED by user 2026-07-07 → PHASE A IMPLEMENTED same day**
(GUI smoke + commit pending; see LAST_CHANGES 2026-07-07e). Phase B remains
unimplemented and needs its own approval. Q1 = readonly grey; Q2 = keep
toolbar buttons, greyed in follow mode; reversibility guaranteed (§5).

Written 2026-07-07 from a code audit of `path_generator.py` (~lines 300–440) and
`ui/tabs/program_tab.py` (reach editor rows, `_refresh_auto_reach`,
`_blank_reach_values`, `compute_reach_from_blank`, `compute_angle_from_surface`).
Every claim below is code-verified, with locations.

---

## 1. Inventory — what exists today

### Reach family (7 controls)

| # | Control | Where | What it actually does |
|---|---------|-------|----------------------|
| R1 | `reach` field | editor "Path Shape" section | Exit-stroke magnitude \|P2→P3\|. Unset/≤0/invalid → **legacy mode**: magnitude implied by `p3_x`/`p3_z` (`path_generator.py:309-315,333`) |
| R2 | `p3_x` / `p3_z` fields | editor "Path Shape" | POLAR mode (pass_angle set): only used as **legacy magnitude fallback** when reach is unset. RAW mode: the actual exit offsets; reach rescales them keeping the X/Z ratio (`:362-369`) |
| R3 | `reach_follow_blank` checkbox | editor "Path Shape" | **Live**: before every recalc, silently recomputes `reach` (+ fan end) from the flange model (`_refresh_auto_reach`) |
| R4 | `reach_blank_factor` field | editor "Path Shape" | Multiplies the **blank-derived** estimate only (R3 + R5). Does nothing to a manual reach (`_blank_reach_values:3102-3108`) |
| R5 | **Reach⟲** toolbar button | toolbar + context menu | **One-shot**: same flange model as R3, fills `reach`; on a fanned op also **silently enables** `progressive_reach_enabled` + sets the end (`_apply_blank_reach`) |
| R6 | `progressive_reach_enabled` + `progressive_reach_end` | editor "Pass Angle" section | Per-pass length fan: pass 1 = `reach`, last pass = end (lerp). **Only works in POLAR mode** — the code sits inside `if _pa_deg is not None:` (`:338-343`) |
| R7 | *(implicit)* clearance anchoring | engine | **Only when reach is set**, P3 is anchored to the zero-clearance contact → endpoint clearance-independent (`:408-434`). Reach unset → legacy, endpoint moves with clearance |

### Angle family (4 controls)

| # | Control | What it does |
|---|---------|--------------|
| A1 | `pass_angle` field | THE mode switch: set → POLAR (direction = θ_A + angle), empty → RAW X/Z. Also the fan's first-pass angle |
| A2 | `progressive_angle_enabled` + `progressive_angle_end` | Direction fan across passes (needs pass_angle + count>1) |
| A3 | **Angle⟲** button | Fills `progressive_angle_end` from the surface tangent; **silently enables** the fan when count>1 |
| A4 | *(implicit)* θ_A frame | Approach direction the angle is measured from: `p1_x/p1_z` for splines, fixed −90° for linear shapes (`:346-350`) |

### The actual precedence chain (engine truth)

```
pass_angle set?  ──no──►  RAW mode: P3 = (p3_x, p3_z); reach (if set) rescales the vector
       │yes
       ▼
POLAR mode: direction = θ_A + pass_angle  (+ angle fan per pass)
            length    = reach  (else |p3| legacy)  (+ reach fan per pass)
            p3_x/p3_z ← COMPUTED, user values ignored (except legacy length fallback)
       ▼
reach set? → P3 additionally anchored to zero-clearance contact (clearance-independent end)
       ▼
reach_follow_blank? → 'reach' ITSELF is overwritten from the flange model (× factor)
                      before every recalc; Reach⟲ does the same once
```

---

## 2. Confirmed problems

**P1 — silent override + STALE DISPLAY (real bug, found during this audit).**
With `reach_follow_blank` ON, `_refresh_auto_reach` rewrites `op["reach"]`
before each recalc and refreshes the **tree**, but NOT the property editor —
the Reach entry keeps showing the manual value the user typed while the engine
used a different one. Worse: if the user later clicks into that field and tabs
out, its stale displayed value is **written back** over the auto value
(FocusOut saver), then overwritten again at the next calc — a silent ping-pong
between two values, with the UI never showing which one is live.

**P2 — two entry points to one concept.** Reach⟲ (one-shot) and
`reach_follow_blank` (live) run the same flange model with the same factor.
Operator must learn that the button and the checkbox are siblings, and that
the checkbox makes the button pointless.

**P3 — factor looks global.** `reach_blank_factor` sits in the editor
unconditionally but only affects blank-derived reach. Typing a manual reach and
then adjusting the factor does nothing — no feedback why.

**P4 — invisible mode flip.** Whether `pass_angle` is set flips the meaning of
BOTH `p3_x`/`p3_z` (real offsets → ignored) and `reach` (vector rescale → polar
length). Nothing in the editor says which mode the op is in.

**P5 — buttons that flip checkboxes.** Reach⟲ silently turns ON the
progressive-reach fan; Angle⟲ silently turns ON the angle fan. The info popup
mentions values, not the checkbox change.

**P6 — related controls scattered.** Reach/p3/follow/factor live in the "Path
Shape" section; the reach FAN lives in the "Pass Angle" section. One concept,
two homes.

**P7 — subtle engine asymmetry (document, don't change).** Setting
`reach = current |p3|` is NOT a no-op: it turns on clearance anchoring (R7).
Known and deliberate (#61 step 1), but nowhere visible to the operator.

---

## 3. Proposed changes

### Phase A — view layer only (zero engine change, zero .ssp change)

**A1. "Reach source" selector** replacing the follow-blank checkbox row:

```
Reach kaynağı:   (•) Elle      ( ) Sacı takip et (canlı)     [Şimdi doldur ⟲]
Reach:           [ 42.7 ]                        ← editable in Elle
Reach:           [ 42.7 ] (otomatik — sac takibi)  ← READONLY grey in Sacı takip
Sac çarpanı:     [ 1.0 ]                         ← ONLY visible in Sacı takip / after fill
```

- Radio state **derives 1:1 from the existing `reach_follow_blank`** — no new
  param, no migration; old .ssp files map exactly.
- "Şimdi doldur ⟲" = the current Reach⟲ action moved next to the concept it
  belongs to (toolbar/context-menu button: see Q2).
- **Fixes P1 structurally**: in follow mode the Reach entry is readonly → its
  FocusOut saver can never write a stale value back, and the field is refreshed
  when `_refresh_auto_reach` changes the value → the display always shows the
  live number.
- Fixes P2 (one home, one mental model: manual / live / fill-once) and P3
  (factor only visible when it does something).

**A2. Mode indicator + greying in the Path Shape section (fixes P4).**
One small status line at the top of the section, driven by `pass_angle`:
- POLAR: `"Çıkış modu: AÇISAL — yön Pass Angle'dan, uzunluk Reach'ten"` and
  `p3_x`/`p3_z` fields greyed (with hint "açısal modda kullanılmaz").
- RAW: `"Çıkış modu: HAM X/Z — reach girilirse uzunluğu ölçekler"`.

**A3. Honest button messages (fixes P5).** Reach⟲ / Angle⟲ popups append one
line when they enable a fan: "Progressive Reach fan AÇILDI (son pas {re})." No
behavior change — only the message.

**A4. Regroup the editor rows (fixes P6).** Move
`progressive_reach_enabled/_end` rows to sit directly under `reach` (still
gated by pass_angle+count>1 exactly as today). Pure pack-order change; the
Customize/visibility system keys stay identical.

**A5. Pass Diagram window teaching panel (user request).** New entries in the
`_show_pass_diagram` formula panel + diagram annotations:
- the precedence chain diagram from §1 (in operator language, TR+EN),
- what the factor multiplies, when the fans are active,
- the P7 note (reach ⇒ clearance-independent endpoint, with the fold-back
  caveat),
- reach drawn on the P2→P3 arrow with its label, fan shown as a ghost second
  exit.

**A6. Label pass (user request "simplify naming").** Proposed TR labels
(EN analogous) — final wording per user (Q3):

| Key | Today | Proposed |
|-----|-------|----------|
| `reach` | "Reach" | "Reach (çıkış boyu, mm)" |
| `reach_follow_blank` | "Reach sacı takip etsin" | (absorbed into the selector) |
| `reach_blank_factor` | "Reach çarpanı" | "Sac reach çarpanı (×)" |
| `progressive_reach_end` | "Bitiş reach" | "Son pas reach (mm)" |
| `progressive_angle_end` | "Yelpaze bitiş açısı" | "Son pas açısı (°)" |
| `pass_angle` | "Pass Angle" | "Pass Angle (°) — boş = ham X/Z modu" (hint) |

### Phase B — behavior polish (separate approval, later)

- **B1.** Two-way live bind reach ↔ p3_x/p3_z display in RAW mode (the deferred
  #61 step-1 item) — edit either, the other updates.
- **B2.** Remove the toolbar Reach⟲/Açı⟲ buttons once A1 relocates the action
  into the editor (context menu keeps them) — declutters the toolbar.
- **B3.** Optional "effective per-pass table" popup: pass i → angle_i, reach_i,
  after fans and clearance anchoring (ties into the Pass Info panel).

### Explicit non-goals (unchanged forever unless separately approved)

- **No engine changes.** The precedence chain, legacy fallbacks, clearance
  anchoring and fold-back guard stay byte-identical (existing regression tests
  `_test_reach*.py` must keep passing untouched).
- **No parameter renames/removals in storage.** `.ssp` files and old programs
  load identically; `reach_follow_blank`, `reach_blank_factor`, `p3_x/z` keep
  their keys.
- **RAW X/Z mode stays** as the advanced/back-compat path.

---

## 4. Risk & verification

- Phase A touches only `program_tab.py` (editor build + one readonly flag +
  `_refresh_auto_reach` editor refresh), `help_window.py`, `i18n.py`, and the
  Pass Diagram function. No `path_generator.py` edits ⇒ toolpath risk ≈ 0.
- The A1 readonly rule slightly changes WHEN a user edit is possible (not what
  is stored): in follow mode the manual field can't be edited — that's the fix
  for P1, not a regression (today the edit is silently discarded anyway).
- Headless tests: extend the toolbar widget test — selector maps to
  `reach_follow_blank` both ways; readonly state; factor row visibility;
  stale-write-back scenario (P1) asserted fixed. Engine suites re-run unchanged.
- GUI smoke checklist: toggle selector both ways on an op with/without
  pass_angle; type reach in manual mode; watch the auto value refresh in follow
  mode; open Pass Diagram panel.

---

## 5. Reversibility guarantees (user requirement, 2026-07-07)

**Nothing auto-computed may ever be a one-way door.** Concretely:

- **Reach⟲ / Açı⟲ one-shot fills** are already #66 undo-tracked — one Ctrl+Z
  restores the pre-fill values (including the silently-enabled fan checkbox,
  since the snapshot is taken before the write). Stays that way.
- **"Sacı takip" is a mode, not a lock.** The engine never bakes the auto
  value in — `reach` is just a number in the op dict that gets refreshed
  before each calc. Switching the selector back to **Elle** at ANY time
  (including after many calculations) stops the auto-refresh immediately,
  unlocks the field, and leaves the last computed value in place as an
  editable starting point. No hidden state survives the switch.
- The **silent per-calc auto-refresh itself is deliberately NOT an undo step**
  (it would flood the #66 stack on every calculation); the release path is the
  selector, not Ctrl+Z.
- Headless test to prove it: enable follow → calc (value overwritten) →
  switch to Elle → assert field editable, auto-refresh no longer touches the
  op, manual edit survives the next calc.

## 6. Questions — answers so far

- **Q1. ANSWERED (user, 2026-07-07): readonly grey** with the live value (not
  hidden).
- **Q2. ANSWERED (user, 2026-07-07): keep the toolbar Reach⟲/Açı⟲ buttons,
  but GREY them when the selected op is in follow mode** — a one-shot fill
  there would be overwritten at the next calc anyway, so the disabled state
  tells the truth. (Angle⟲ is not affected by follow mode — it stays enabled
  whenever pass_angle is set; only Reach⟲ greys.)
- **Q3.** Label wordings in A6 — approve/adjust the table. *(open)*
- **Q4.** Scope check: implement Phase A as one piece, or split (A1+A2 first,
  A5 diagram panel second)? *(open)*
- **Q5.** Anything in Phase B you want pulled into Phase A? *(open)*
