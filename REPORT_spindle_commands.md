# Spindle ON / OFF in the exported SCL

2026-08-31 · read-only investigation, nothing changed.

## What decides it

`recipe_to_scl.py` decides nothing — it just translates `M3` → `CMD=20` and
`M5` → `CMD=21` in file order. The real rule is in `path_generator.generate_gcode`,
and it is **operation boundaries**:

| When | Result | Where |
|---|---|---|
| Each enabled operation starts | SPINDLE_ON | `path_generator.py:3120`, `:3126` |
| ~~Tool changes between ops~~ | ~~SPINDLE_OFF, then ON after `M6`~~ — **removed 2026-08-31**, the turret is automatic so the spindle now runs straight through the change (and the `M1` that decoded to `CMD=1` went with it) | `:3153` |
| End of program (footer `M5`) | SPINDLE_OFF | `:3333` |
| End of parse (always) | one more SPINDLE_OFF | `recipe_to_scl.py:632` |
| No `M3` in the file at all | SPINDLE_ON @1000 RPM at line 0 | `recipe_to_scl.py:624` |

So: **one ON per operation, one OFF per tool change, two OFF at the end.**
Passes, zones, break points, retracts and back passes emit nothing — a 12-pass
operation gets one `M3`.

`Param = rpm // 10` (max 255 = 2550 RPM). X/Z/F on these lines are ignored by the PLC.

Real example — `spinning_output.nc`, 2 ops, 1581 lines:
`idx 3 CMD=20 Param=20` · `idx 1314 CMD=20 Param=20` · `idx 1578 + 1579 CMD=21` · `idx 1580 CMD=99`.

## Problems found

**1. CSS speed is sent as RPM. — FIXED 2026-08-31: CSS disabled.**
`speed_mode` defaulted to CSS, so the emitter wrote `G96 S200 M3`. The converter reads
only `M3`+`S200` — never the `G96` — and sent `Param=20` = **200 RPM**, when the operator
asked for 200 m/min. Your sample file does this.

The PLC has no CSS mode, so CSS could not be honoured at all. Per user decision
("we don't use it"), CSS is now switched off: `path_generator.CSS_SPEED_MODE_ENABLED = False`,
and every consumer reads the mode through `resolve_speed_mode()`. Old ops still carrying
`speed_mode="CSS"` keep their number and are read as RPM — which is what the machine has
been running all along, so **no recipe changes value**; the UI, the `.nc` and the time
estimate simply stop disagreeing with it. Flip the constant to re-enable.

**2. `M1` becomes a LINEAR move. — FIXED 2026-08-31 by deleting `M1`.**
Tool change emitted `["M5", "M1"]`. `M1` is unknown to the converter, so the generic
fallback set `CMD = 1` — the LINEAR opcode. Result: `CMD=1 F=0`, a zero-length feed move
eating a PLC line, and the operator pause it was meant to be never existed on the PLC.
Two of them shipped in `DB_RecipeProgram1.scl` (`Lines2[5]`, `Lines2[15]`).

Both `M5` and `M1` are now gone from the tool-change block (see the table above).
**The underlying converter trap is still open:** any custom M-code whose number collides
with `0,1,10,20,21,30,99` still becomes that opcode. Worth guarding the way `PARAM_RANGE`
already refuses out-of-range params — loudly.

**3. Speeds are clamped silently.** `recipe_to_scl.py:428` does `min(rpm,2550)//10`
with no warning: 4000 → 2550 RPM; 1595 → 1590; entering 5 gives `Param=0`,
i.e. SPINDLE_ON at zero RPM, no error.

**4. Duplicate SPINDLE_OFF at the end.** Footer `M5` plus the converter's automatic
one. Harmless, wastes one of the 1000 lines on every export. Keep one.

## For the operator

- Speed = Program tab, per operation, in **RPM** (CSS is no longer offered).
- Extra mid-program stop = custom M-code `M5` on a pass or Z trigger.
- Fewer spindle lines = merge ops that share tool and speed.
