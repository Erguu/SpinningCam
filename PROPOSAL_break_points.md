# Break Points — multi-break exit shaping (successor to exit_mid)

Status: **agreed with user 2026-08-27, not yet implemented.**

## What exists today

One break. `exit_mid_t` (0–1 along the exit leg) picks a point M, `exit_mid_rotation`
swings everything after M around M. Op-level params, batch-editable.
`path_generator.py:2236-2251`. Skipped when the curl (`exit_mid_radius`) is set, and
ignored entirely when #100 waypoints exist.

Operators like it and want more of them. That is the whole request.

## Decisions (user, 2026-08-27)

1. **Break points and waypoints are two separate features.** Waypoints stay exactly
   as they are. Break points are parametric and stay live: a percentage remains a
   percentage, so when reach / pass angle / progressive reach changes the leg length,
   the breaks follow. Waypoints keep priority when a pass has both.
2. **Per pass**, stored like waypoints — plus an *Apply to all passes* action, because
   unlike dx/dz a break at 40 % / −12° is usually the same on every pass of the op.
3. **Angles are relative bends.** Each row bends the remaining tail relative to its
   current direction — "then turn another 10°". One break therefore behaves
   identically before and after this change.
4. **The new feature replaces the legacy single break**, via silent fallback rather
   than a file migration (see below).

## Data model

Per pass, alongside `exit_points` / `exit_shape`:

```python
pass_edits[str(i)]["exit_breaks"] = [{"t": 0.40, "angle": -12.0}, ...]
```

`t` = fraction of the ORIGINAL exit leg, `angle` = degrees, signed, same sense as
`exit_mid_rotation`. Sorted by `t`. Absent key = feature off for that pass.

New module `exit_breaks.py` — pure, no Tk / no OCC / no engine state — following the
`exit_waypoints.py` precedent so the dialog and the engine share one implementation
instead of mirroring each other.

## Engine

Replace the single-rotation block at `path_generator.py:2236` with a loop:

* Resolve the list for the pass. **If empty, build a one-item list from the op-level
  `exit_mid_t` / `exit_mid_rotation`** — so every existing program produces
  byte-identical geometry with no file rewriting.
* Indices are computed against the ORIGINAL point array before any rotation. A
  rotation only touches points after its own index, so applying in ascending `t`
  order is stable and earlier breaks never shift later ones. Same clamping as today
  (`t` 0.05–0.95, index in `[1, len-2]`).

Unchanged precedence, all of it already implemented and greyed-out in the UI:

| Condition | Result |
|---|---|
| `exit_points` present (#100) | breaks ignored, added to the existing `_ignored` log line |
| curl (`exit_mid_radius[_end]`) set | breaks disabled — radius wins, field greyed |
| reverse swap-legs mode | skipped, as the single break is today |
| `pass_shape` not linear | n/a |

Clearance: the exit leg's existing correction runs *after* this block and already
covers a rotated tail. Unlike the waypoint dialog there is no live refuse-on-edit —
the dialog does not own the leg geometry, and the engine already protects it.

**Point budget.** K breaks cost at least K+2 lines on the leg. RDP preserves corners
by construction, so every break survives decimation. `exit_max_points` (#101) still
caps it, and the 1000-line PLC ceiling is hard.

## UI

`pass_table.py:450` toolbar:

* rename the existing button to **Waypoints** (`pt_btn_tail`)
* add **Break Points** (`pt_btn_breaks`) beside it

New `ui/dialogs/break_points_dialog.py`. No 3D preview — the shape is 1-D along the
leg. Table: № / % / Angle°, with Add / Delete / Move. *Apply to all passes* writes the
same list to every eligible pass of the op; individual passes can be nudged after.

**Seeded, never blank**, matching the waypoint editor: a pass with no list opens
seeded from the op's legacy single break if one is set, otherwise one row at 50 % / 0°.

The two legacy fields leave the property panel. Nothing is rewritten on load.

## Tests (`_test_exit_breaks.py`, headless)

Legacy equivalence (fallback path reproduces old geometry exactly) · N breaks applied
in order · clamping · ignored when waypoints present · curl precedence · apply-to-all
writes every eligible pass · round-trip through .ssp.

Plus: i18n EN+TR keys, `help_window._C`, `LAST_CHANGES.md`, version bump at session end.
