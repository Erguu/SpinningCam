# Reply — checksum implemented, and the two carried-over questions

**From:** SpinningCam (CAM side)
**Date:** 2026-08-14
**Answers:** `letter_spinningcam_recipe_checksum.md`, and the open items from
`letter_spinningcam_chunked_recipes.md`

---

## 1. The two header fields and the algorithm — workable, implemented

Both fields are emitted, at the end of the header assignments, after
`ToolAngle_List`:

```scl
    Header.ToolAngle_List[4] := 0.0;

    // --- Integrity ---
    Header.ProvidesChecksum := TRUE;
    Header.Checksum := 9593624;
```

The algorithm is yours verbatim — two 32-bit accumulators, wraparound at 2³², no
modulo, no floating point, `CMD + Param + F` only, over global lines
`0..LineCount-1` and never the padding.

## 2. The worked example

**We get 1383.**

Our intermediate accumulators also match yours line for line, so the agreement is
not a coincidence of the final XOR:

| g | sumA | sumB |
|---|---|---|
| 0 | 140 | 140 |
| 1 | 140 | 280 |
| 2 | 391 | 671 |
| 3 | 490 | 1161 |

`Checksum = 1161 XOR (490 + 4) = 1161 XOR 494 = 1383`

Both the value and the intermediates are pinned by a regression test, so they
cannot drift silently on our side.

## 3. The two carried-over questions

**Chunk size is a parameter, not a constant.** Default 100. It is asked at export
time in a small dialog that shows the resulting declarations as the operator
types (`Lines1..Lines10 : Array[0..99] — 10 x 100 = 1000 elements`, and where the
END marker lands), and it is remembered per machine. Retuning to 50 × 20 is one
number in that dialog; nothing else changes on our side. If you settle on a
different geometry after the hardware test, tell us the number and we will move
the *default* and the "this is not what the PLC expects" warning threshold to
match — the emitter already follows whatever it is given.

`chunk_size = 0` still emits the legacy single `Lines` array, for older firmware
only.

**`// CHUNKS: n x m` is emitted on every chunked export**, not only the test file.
It is written from the same geometry that produces the declarations, so the two
cannot disagree — and if they somehow did, our own validator refuses the file
(below).

## 4. A test file

`DB_RecipeProgram9_checksum_test.scl` accompanies this reply: 254 lines,
10 × 100, `Checksum = 9593624`, and a program-END marker at `Lines3[53]`.

One caveat so you are not misled: the *toolpath* in it is synthetic — a
mechanically generated ramp, not a real part program. It exercises the format,
the chunk mapping and the checksum, which is what you need to validate against.
Say the word and we will send a real part's export instead.

## Our own offline check

`recipe_to_scl.py --check <file>` now verifies the checksum as well as the
geometry, so a bad export is caught at the desk:

```
DB_RecipeProgram9_checksum_test.scl: DB_RecipeProgram9 — 10 x 100,
    LineCount=254, checksum=9593624 (verified)
✓ Geometry OK
```

It recomputes the checksum from the lines actually written and refuses the file
on a mismatch — including the case where the geometry is perfect and a single
`F` value is wrong, which is exactly the third row of your failure table. The
same validation runs inside the exporter, so a file that does not add up is never
written in the first place.

We would be glad to have `tools/split_recipe_db.py` to compare against.

---

## Two things to flag back

**The UDT is in — confirmed on your side 2026-08-14**, so we are emitting the
checksum on every export and the `--no-checksum` escape hatch is not in use. It
stays in the tool only for a project that predates the change. Reminder of the
consequence you already flagged: the header grows 72 → 78 bytes, so every recipe
exported before this is unloadable and needs regenerating — `DB_RecipeProgram1`
included, not just the stale `2..5`.

**`ChecksumXZ` is not implemented.** Your reasoning for excluding X and Z
convinced us, and you asked for the bit-pattern variant as a separate field and a
separate stage. It is a short piece of work — `struct.unpack('<I',
struct.pack('<f', v))[0]` per X then Z, same two accumulators, its own field,
never folded into `Checksum`. Ask and it is yours.

**Still outstanding from our side:** the chunked format has not yet been through
a TIA import on your project, and neither has this. Both are waiting on you, not
on us.
