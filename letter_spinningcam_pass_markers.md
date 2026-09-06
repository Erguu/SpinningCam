# To the SpinningCam developer — showing the operator which pass is running

**Machine:** Mexico Metal Spinning, Siemens S7-1214C / TIA Portal V17
**Subject:** two new CMD codes, behind an option in the PLC-mode section
**Date:** 2026-09-06
**Follows:** `letter_spinningcam_chunked_recipes.md`, `letter_spinningcam_recipe_checksum.md`
**Scope: PLC mode / SCL export only.** The `.nc` G-code path is not involved and must not change.
**Status of our side: IMPLEMENTED (2026-09-06), built to match this document.** A recipe without
markers loads and runs exactly as it does today, so there is no rush and no ordering constraint.

---

## Short version

Please add an option to the PLC-mode section — *"Emit pass markers"* or similar — which, when on,
inserts two kinds of zero-motion line into the SCL export:

```scl
CMD := 50   Param := <operation number>   F := <total operations>    // at the start of each operation
CMD := 51   Param := <pass number>        F := <passes in this op>   // at the start of each pass
```

`X` and `Z` are `0.0`. They are ordinary recipe lines: counted in `LineCount`, folded into the
checksum, subject to the 1000-line maximum. With the option **off, the export is byte-identical to
today's** — that is the whole point of it being an option, and we would like it to stay that way
rather than becoming a format everyone must adopt.

**Three questions are at the end.** One of them (the 999-line ceiling) matters more than this
feature does.

---

## Why

The HMI can only tell the operator which **line** is running. "Line 47 of 99" means nothing to
someone standing at the machine. The job is described in passes — your own header says so:

```
// Op1: ROUGHING, 10 paso, T004, R=44.56mm, RPM=600.0, mm_min=300.0
```

An operator watching a ten-pass roughing operation currently has no way to tell pass 2 from pass 9.
That matters most when proving out a new product, which is exactly when someone is standing there
watching.

**You already compute this.** It is in every line you emit, in the comment:

```scl
Lines1[10].X := 259.778; Lines1[10].Z := 213.444; Lines1[10].F := 300; Lines1[10].CMD := 1; ...  // G1 Linear [Op1 P2]
```

SCL comments are discarded when TIA compiles the block, so the PLC never sees `[Op1 P2]`. All we
are asking is that the same two numbers also travel as data. Nothing needs to be calculated that
you are not calculating already.

---

## The format

| CMD | Meaning | `Param` | `F` |
|-----|---------|---------|-----|
| 50 | Operation start | operation number, 1-based | total operations in the program |
| 51 | Pass start | pass number within the operation, 1-based | passes in this operation |

- `X := 0.0`, `Z := 0.0`.
- Emit **CMD=50 once** at the start of each operation, **CMD=51 once** at the start of each pass,
  immediately before that pass's first real line.
- Both values are bytes: **maximum 255**. Please confirm no realistic program exceeds that; if one
  can, tell us and we will widen the field rather than have it wrap silently.
- `F` is a signed 16-bit integer, so the totals are unbounded in practice.

### Worked example — the real `DB_RecipeProgram1`

Its first two passes look like this today (line numbers are the current ones):

```scl
Lines1[3] ... CMD := 41; Param := 1;   // M41 P1        [Op1 P1]
Lines1[4] ... CMD := 0;  Param := 0;   // G0 Rapid      [Op1 P1]
...
Lines1[8] ... CMD := 41; Param := 2;   // M41 P2        [Op1 P2]
Lines1[9] ... CMD := 0;  Param := 0;   // G0 Rapid      [Op1 P2]
```

With the option on, they become — note `LineCount` grows and every index after an insertion shifts:

```scl
Lines1[0] ... F := 5;  CMD := 50; Param := 1;   // OPERATION 1 of 5
Lines1[1] ... F := 10; CMD := 51; Param := 1;   // PASS 1 of 10
Lines1[2] ... CMD := 40; Param := 1;            // Cylinder GOTO P1
Lines1[3] ... CMD := 10; Param := 4;            // Tool Change T4
Lines1[4] ... CMD := 20; Param := 60;           // Spindle ON 600 RPM
Lines1[5] ... CMD := 41; Param := 1;            // M41 P1        [Op1 P1]
Lines1[6] ... CMD := 0;  Param := 0;            // G0 Rapid      [Op1 P1]
...
Lines1[11] ... F := 10; CMD := 51; Param := 2;  // PASS 2 of 10
Lines1[12] ... CMD := 41; Param := 2;           // M41 P2        [Op1 P2]
Lines1[13] ... CMD := 0;  Param := 0;           // G0 Rapid      [Op1 P2]
```

Whether the op/pass marker goes before or after the `CMD=40`/`CMD=10`/`CMD=20` setup lines is your
call — the display is what it is for, so put it wherever the operator would consider the pass to
have begun. Ours does nothing but store the numbers and move on.

### What the operator ends up seeing

```
Line:  47 / 99
Op 1 (of 5)
Pass:   3 / 10
```

---

## What `TotalOps` must count — and a discrepancy we found

**`TotalOps` must be the number of operations that actually emit lines, not the number in the
operation list.** They are not the same today. In `DB_RecipeProgram1`:

- the header comment block lists **seven** operations, `Op1` through `Op7`;
- the emitted lines carry tags for **five**, `[Op1 …]` through `[Op5 …]`;
- the program ends after Op5 (`Lines1[77]` spindle off, `Lines1[79]` `CMD=99`).

Op6 and Op7 are `ROUGHING` and `BENDING`, both at `RPM=0.0`. So either they are deliberately
skipped, or two operations are being silently dropped from the export.

If we sent `TotalOps = 7`, the display would reach "Op 5 of 7" and stop there, and the operator
would reasonably conclude the machine had hung with two operations to go. So please count what you
emit.

**But the more important question is why those two vanish.** If that is deliberate — `RPM=0` means
nothing to cut, so nothing to emit — then all is well and we would just like it stated. If it is
not deliberate, then parts are being machined with two operations missing and this pass display is
the least of it. We would rather ask now than find out later.

---

## The checksum

No change to the algorithm. Markers are ordinary lines, so they fold in through the existing
`sumA += CMD + Param + F` exactly like any other. The only requirement is ordering: **compute the
checksum after the markers are inserted**, over the lines as they are actually written to the file.
`LineCount` likewise counts them.

Our loader re-derives the same number after reassembling the recipe, so if the two are computed
over different line sets we will get `16#0316` and refuse to run.

---

## The 1000-line ceiling — and why this is an option

Our recipe buffer is a fixed `Array[0..999]`. That is not changing: it is 12 KB of the CPU's 100 KB
of work memory, and it is allocated whether a program uses 80 lines or 999.

So markers are free in memory but not free in **slots**. Measured on the real exports:

| Program | Lines today | Ops / passes | Markers | With markers |
|---------|-------------|--------------|---------|--------------|
| `DB_RecipeProgram1` | 80 | 5 / 14 | +19 | 99 — plenty of room |
| `DB_RecipeProgram3`, `4`, `5` | 999 each | 16 / 16 | +32 | **1031 — over the limit** |

That is the real reason for the option. On a short program the markers cost nothing anyone will
notice. On a long one they would have to come out of the geometry, and coarser toolpath resolution
is a bad trade for a nicer display. Putting a checkbox in the PLC-mode section lets whoever exports
the program decide, per program, which they want — pass information while proving out a new part,
full resolution once it is in production.

**If the option is on and the markers would push a program past 1000 lines, please refuse or warn.
Do not truncate the geometry, and do not silently drop the markers** — a warning tells the
programmer to switch the option off, which is a decision they can make. A silent drop just looks
like the feature is broken.

---

## Our side of the handshake

Already implemented and waiting:

- `FB_RecipeHandler` reads CMD 50 and 51 and stores four values. Neither command touches an
  actuator, waits for anything, or moves an axis — each costs about two PLC scans, the same as any
  other non-motion line. Nineteen markers cost under half a second across a whole program.
- The numbers are mirrored to `DB_HMI.CurrentOp / TotalOps / CurrentPass / TotalPasses` every scan.
- **`0` means "no pass information"** and the HMI blanks the display on it. A recipe without markers
  therefore shows nothing rather than "Pass 0 / 0" — which is why the option being off is a
  supported, permanent state and not a legacy case we are waiting to retire.
- Unknown CMD values were already skipped by our command dispatcher, and the pre-scan validator only
  bounds-checks `CMD <= 1`, so marker lines pass through a **PLC that has not been updated yet**
  without faulting. You can ship this whenever suits you, in either order.

---

## What we need back

1. Confirmation that the option and the two CMD codes are workable.
2. **Whether the missing Op6/Op7 in `DB_RecipeProgram1` is deliberate.** See above — this one
   matters regardless of what happens with the pass display.
3. **Is 999 a deliberate line cap?** `DB_RecipeProgram3`, `4` and `5` are three different parts and
   all three export to exactly 999 lines, which is too neat to be a coincidence. If a part needing
   more gets **truncated**, we need to know now — a silently shortened program is a far worse
   problem than a missing pass counter. If it is a soft cap, 1000 is what our array holds.
4. Confirmation that operation and pass numbers stay within 255.
5. One test export of `DB_RecipeProgram1` with the option on, so we can verify against our
   implementation before you regenerate anything else.

Still open from the previous letters, in case it is easy to fold in: a **distinct** `Header.sName`
per program. Every export still says `'SpinningCam Program'`, so the operator's program-name display
cannot distinguish them.
