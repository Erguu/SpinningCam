# PROPOSAL — Per-Operation Configurable Tool-Change Position

Status: **STUDY / awaiting approval** (2026-07-21). Nothing implemented yet.

## 1. What the user asked

> "Until now we have a fixed position for tool changes. Can we have it also
> configurable — either a **relative** position to the last pass or an **absolute**
> position? But this should not be global, it should be **per operation**."

Two design decisions were confirmed up front:

- **Attribution: the incoming operation owns the setting.** The op that needs the
  new tool carries "where do I change to my tool". The very first op has no prior
  tool, so it always uses the current global home. When an op is reordered / copied,
  its tool-change setting travels with it.
- **Safety guard: warn-only.** If a custom point looks unsafe (inside the mandrel /
  blank swing envelope where the rotating turret could strike), warn the user but let
  them proceed. No hard block.

## 2. How tool changes work today (fixed / global)

The tool change is emitted in **two places that must stay in sync**:

**(a) Geometric sequence — `path_generator.py` `calculate_paths` (~L188-212).**
Drives the 3D-sim rapid moves. On a tool change it does a split retract:
```
safe_mid = [current_pt.x, 0, home_z]     # 1. Z up to home, keep X
home_pt  = [home_x_can,   0, home_z]      # 2. X out to home
current_pt = home_pt
```
`home_x_can` / `home_z` are global (machine Program-Start / home).

**(b) G-code emission — `generate_gcode` (~L1906-1924).**
```
G0 Z{home_z_machine}   (Home Z)
G0 X{safe_x_machine}   (Retract X)   # safe_x_machine = home_x_machine (L1880)
M5 / M1
M6 {op_tool}
```

Both use the **same global home**. The retract is always "Z to home, then X to home",
identical for every tool change in the program.

Relevant data already present at each site (this is why the feature is cheap):
- Sequence: `current_pt` = exact end of the previous pass (canonical coords).
- Emitter: `paths_to_use[global_path_idx-1][-1]` = end of the previous op's last pass;
  `paths_to_use[global_path_idx][0]` = start of the incoming op's first pass.

So both "absolute" and "relative-to-last-pass" targets are computable in both places
with no new plumbing.

## 3. Proposed per-op fields (on the incoming op)

Follows the existing `tilt_mode` / `tilt_offset` per-op mode+value pattern
(`OP_PARAM_UNIVERSE` in `program_tab.py`).

| Field | Type | Meaning |
|-------|------|---------|
| `tool_change_mode` | `"global"` \| `"absolute"` \| `"relative"` | default `"global"` = today's behavior |
| `tool_change_x` | float | absolute mode: X of the change point (machine coords) |
| `tool_change_z` | float | absolute mode: Z of the change point |
| `tool_change_dx` | float | relative mode: X offset from previous pass end |
| `tool_change_dz` | float | relative mode: Z offset from previous pass end |

**Default `"global"` means an existing recipe is byte-for-byte unchanged** — no
migration, no behavior drift for programs that don't opt in.

Resolution (both sites compute the same target point):
- `global`   → `[home_x_can, 0, home_z]` (unchanged path).
- `absolute` → `[tool_change_x, 0, tool_change_z]`.
- `relative` → `prev_pass_end + [dx, 0, dz]`.

The **retract shape stays "Z first, then X"** for consistency and to keep the roller
clear of the part while moving axially — only the destination changes.

## 4. Where the code changes land

Small, localized, and symmetric:

1. **`path_generator.py` `calculate_paths` (~L192-210)** — replace the hard-coded
   `home_pt` with a resolved target from the incoming op's `tool_change_mode`. Keep the
   >1mm split-move guards.
2. **`path_generator.py` `generate_gcode` (~L1909-1916)** — same resolution; emit the
   resolved X/Z into the `G0 Z … / G0 X …` retract lines instead of the global home.
   `M6` and the M5/M1 pause are unchanged.
3. **UI — `program_tab.py` `OP_PARAM_UNIVERSE`** + the per-op editor: a `tool_change_mode`
   dropdown that reveals the X/Z (absolute) or dX/dZ (relative) fields, mirroring the
   tilt fields. Greyed/hidden in `global`.
4. **Warn-only guard** — a helper that checks the resolved point against the mandrel /
   blank swing envelope and surfaces a non-blocking warning (sim overlay marker + a
   collected export-time warning list). Reuses the clamp-zone / clearance geometry
   already in the codebase.
5. **i18n** — new keys for the mode label, X/Z/dX/dZ, and the warning text (EN/TR/ES).
6. **Docs** — `help_window.py` `_C` dict entry (per help-window policy), `changelog.py`
   (next version), `LAST_CHANGES.md`.

**SCL note:** SCL export is unaffected in structure. The tool-change position shows up as
the retract `RecipeLine` X/Z before the `CMD=10` (M6) line — it just carries the resolved
coordinates instead of home. No new header field; the turret/tool table (v1.008) is
independent of this.

## 5. Safety analysis (why warn-only is acceptable here)

`M6` rotates the turret. If the change point sits inside the part/mandrel swing envelope,
a rotating tool could strike. Today's global home is chosen to be clear, so the fixed
behavior is inherently safe. A custom point removes that guarantee.

Warn-only was chosen deliberately: metal-spinning setups vary and an operator who has
measured their fixture may legitimately want a tighter change point. The mitigation:
- Non-blocking **warning** whenever a custom (`absolute`/`relative`) point is inside the
  computed swing envelope, at both edit time (sim marker) and export time (message).
- The default stays `global`, so the risk only exists when the user explicitly opts in.
- The retract still goes **Z-up before X-move**, so even a custom point is approached
  axially-clear-first, not by dragging the roller across the part.

## 6. Test plan (headless first, per project convention)

New `_test_tool_change_position.py`:
- `global` mode → sequence + G-code identical to pre-change (regression byte-check).
- `absolute` → retract lines carry exactly `tool_change_x/z`.
- `relative` → target = previous-pass-end + offset (both sites agree).
- Guard fires (warning present) for a point inside the envelope; silent for a clear point.
- Multi-op program: per-op settings are independent; first op ignores the setting.

Then GUI smoke: dropdown reveal/hide, sim marker, export warning path.

## 7. Effort / risk

- **Effort:** low-moderate. Two engine edits (~10 lines each), one UI block modeled on the
  tilt fields, one guard helper, i18n + docs.
- **Risk:** low for non-opted-in programs (default `global` = no change). The real risk is
  physical (turret swing on a bad custom point) and is mitigated by warn + Z-first retract,
  not eliminated — this is a **physical-verification-required** feature before field use.
- **Sync hazard:** the two engine sites must resolve the point identically. The regression
  test and a shared resolver helper (`_resolve_tool_change_point(op, prev_end, home)`) keep
  them honest — recommend factoring one helper used by both.

## 8. Recommendation

Feasible and cheap. Recommend implementing with a **single shared resolver helper** called
from both `calculate_paths` and `generate_gcode`, default `global`, warn-only guard, and a
headless regression test proving `global` is unchanged before touching the UI.
