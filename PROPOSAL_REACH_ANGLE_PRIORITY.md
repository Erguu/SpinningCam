# Proposal — Reach / Pass-Angle priority model + per-pass table ("ride with me, don't fight me")

**Status: APPROVED + IMPLEMENTED 2026-07-08 (P1–P4 in one session; headless-verified,
GUI smoke + commit + #82 physical validation PENDING — see
`backup/HANDOVER_2026-07-08.md` and `LAST_CHANGES.md` 2026-07-08).**

**User decisions (2026-07-08):** table = popup ✓; table edits = STAGED
(double-click → ✎ pending, [Apply] = one undo step, [Cancel] reverts) ✓;
follow-mode modifiers = factor (×) + NEW `reach_blank_offset` (mm), both
user-owned ✓; reverse-pass geometry fix = **NEW DEFAULT** (escape hatch:
`reverse_legacy_flip` per op) ✓; legacy hidden overrides: NOT auto-migrated —
surfaced in the table (⭑) with an undoable "Unpin" that clears them ✓.

**Implementation deltas vs. §3 below:** Q2 was resolved the strong way —
follow-blank moved INTO the engine per pass (supersedes B-v1 "display-only"),
which killed #74/#75 at the root; per-pass pins (`op["pass_edits"]`) became the
highest-priority engine source (pin > follow > fan > reach > |p3|); the fan
"effect-based distribution" (C) remains future opt-in work.

Written from the user's requirements walkthrough (2026-07-07 evening) plus the
same-day code audit. Covers TODO **#72–#83**. Sister doc:
`PROPOSAL_68_REACH_ANGLE_UX.md` (Phase A shipped; its Phase B item B3 is pulled
forward here as the per-pass table).

The user's summary, in his own words: *"if we have some priority, I can feel I
have the control. now I don't feel it. the program doesn't ride with me, it
fights with me."*

---

## 1. The priority model (the constitution)

Four rules. Every fix in this proposal exists to enforce one of them.

**R1 — Three dials, no overlap.**
- **Direction** = `pass_angle` (+ progressive angle fan: start angle → end
  angle, equal steps — kept exactly as today; user approves this feature).
- **Length** = `reach` (+ progressive reach fan, or follow-blank mode).
- **Shape** (the P2→P3 curve) = per-op curve controls: `exit_arc_angle`
  (→ #81 makes it per-op), `p2_radius`, `exit_mid_rotation`/`exit_mid_t`.
No parameter may secretly influence another dial. (`end_z` is untouched by all
reach code — verified; the table in §2 makes that visible.)

**R2 — Manual beats automatic, always.**
Anything the user typed or unticked stays until HE changes it. Follow mode may
only refresh the values it owns (`reach`, and the fan end IF the fan is his);
it must never re-enable a fan the user turned off (#75), never freeze a field
without telling why (#73), never write values the display doesn't show (#74).

**R3 — One calculation path.**
Identical inputs → identical toolpath, no matter which button/checkbox/slider
triggered the calc. Today there are two families (async with follow-refresh vs
sync without: #76, #83). All op-param triggers route through the async worker
with `_refresh_auto_reach` at its single entry.

**R4 — Everything automatic is visible and undoable.**
Auto-computed values show their source (§2 "Kaynak" column); per-pass overrides
get badges + a clear button + undo coverage (#79); mode switches push undo
snapshots (#77).

## 2. The per-pass table (centerpiece — implement FIRST)

A read-only popup per operation (button next to Pass Diagram, also in the
right-click menu): one row per pass, computed with the exact engine formulas
(reuse the `_split_op`/`_pass_previews` lerp logic + fold-back guard check).

```
Op: Ro-Start (roughing, 30 pas)                    [Yenile] [Kapat]
┌────┬─────────┬────────┬───────────┬───────────────┬──────────┬─────────────────────────────┐
│Pas │ Z temas │ Açı °  │ Reach mm  │ Uç noktası    │ Kaynak   │ Uyarı                       │
│    │ (start→ │ (yelpa-│ (yelpaze/ │ X / Z (mutlak)│          │                             │
│    │  end_z) │  ze)   │  takip)   │               │          │                             │
├────┼─────────┼────────┼───────────┼───────────────┼──────────┼─────────────────────────────┤
│ 1  │  10.0   │  93.0  │   40.0    │ 137.1 /  3.2  │ elle     │ ⭑ override: açı 264.3!      │
│ 2  │  10.2   │  95.9  │   39.7    │ 135.8 /  8.1  │ elle     │                             │
│ …  │   …     │   …    │    …      │       …       │          │                             │
│ 15 │  12.4   │ 133.4  │   35.2    │ 118.3 / 30.9  │ takip    │                             │
│ …  │   …     │   …    │    …      │       …       │          │                             │
│ 27 │  14.6   │ 168.2  │   31.0    │  95.1 / 44.6  │ takip    │                             │
│ 28 │  14.7   │ 171.2  │   30.7    │  99.3 / 44.9  │ takip    │ ⚠ clearance guard devrede:  │
│    │         │        │           │               │          │   uç +4.5mm dışarı sıçrar   │
│ 29 │  14.9   │ 174.1  │   30.3    │  98.9 / 45.0  │ takip    │ ⚠ önceki pasla ~aynı (Δ<1mm)│
│ 30 │  15.0   │ 178.0  │   30.0    │  98.6 / 45.1  │ takip    │ ⚠ önceki pasla ~aynı        │
└────┴─────────┴────────┴───────────┴───────────────┴──────────┴─────────────────────────────┘
Sac kenarı (takip modeli): pas 1 → 46.2mm, pas 30 → 30.1mm   [pas başına gerçek kenar: göster]
```

- **Kaynak** column: `elle` / `yelpaze` / `takip` / `⭑override` — R4 made
  concrete. Overrides stop being invisible the day this ships (#79 visibility
  half).
- **Uyarı** column carries the three #80 detections: fold-back-guard flip
  (endpoint jumps ~clearance), near-duplicate pass (endpoint within ~1 mm of
  previous), reach-fan→0 (falls back to raw default exit).
- Row click → highlight that pass in the 3D view (reuses the pass-stepping
  recolor machinery).
- For follow mode, a footer line shows the flange-edge estimate per endpoint
  (and optionally per pass), so the user can VERIFY the edge — his #1 trust
  requirement.

**What changes for the operator:** before running a 30-pass program he opens
one window and sees what every pass will actually do and WHY — no more
discovering senseless end passes on the machine or hunting hidden overrides.

## 3. Work packages & order

| Phase | Content | TODO refs | Risk |
|-------|---------|-----------|------|
| **P1 — Visibility** | Per-pass table + warnings + override badges (read-only; zero engine change) | #80, #79(view) | ~0 |
| **P2 — Trust** | Single calc entry (route sync `update_scene("paths")` callers + Process-tab Calculate through async worker with `_refresh_auto_reach`); manual-beats-auto (follow stops flipping the fan flag); undo covers radio switch + `gui_pass_overrides`; blank slider debounce | #75, #76, #77, #79(undo), #83 | medium (calc plumbing) — behind it, calc profiling |
| **P3 — Control** | Per-op `exit_arc_angle` (global = fallback); #72/#73/#74 field-locking fixes; follow-mode per-pass edge (engine: compute flange at each pass Z instead of linear lerp — opt-in first) | #81, #72–#74 | low/medium |
| **P4 — Geometry** | Reverse-pass segment-role swap (straight arm INTO mandrel-near P2, curve on the way out) — opt-in flag first, own regression test, physical validation before default | #82 | high (toolpath change) |

Each phase is separately approvable; P1 ships value alone.

## 4. Non-goals / guarantees

- Engine precedence chain (POLAR/RAW, legacy fallbacks, clearance anchoring,
  fold-back guard) unchanged through P1–P2. P3's per-pass edge and P4 are the
  only engine changes, both opt-in first.
- No .ssp key renames; old programs load identically.
- Progressive angle fan stays exactly as-is (user: "nice, simple, keep it").
- All existing reach suites must pass untouched at every phase.

## 5. Open questions (user)

- **Q1.** Per-pass table: popup window (proposed) or embedded panel under the
  op list?
- **Q2.** Follow-mode per-pass edge (P3): engine applies per-pass flange reach
  directly, or keep the linear fan and only SHOW the per-pass edge in the table
  (display-only)? Display-only is safer; engine version is more correct.
- **Q3.** Reverse-pass swap (#82): opt-in per-op flag (safe) or new default
  with a legacy flag (cleaner)? Recommend opt-in until physically validated.
- **Q4.** Overrides (#79): keep-and-manage (badges + clear buttons) or a
  stronger "clear all overrides on structural change with warning"?
