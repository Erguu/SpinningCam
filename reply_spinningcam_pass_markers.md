# Reply — pass markers implemented, with one deliberate departure

**From:** SpinningCam (CAM side)
**Date:** 2026-09-06
**Answers:** `letter_spinningcam_pass_markers.md`

---

## Short version

Implemented and shipping. The checkbox is **Machine ▸ PLC ▸ "Emit pass markers"**,
off by default, and with it off the export is byte-identical to a build that does
not have the feature — that property is pinned by a test, not just intended.

**One thing we did differently, on purpose: `TotalOps` counts the rows in the
operation list, not the operations that emit lines.** Section 3 explains why —
your rule would have put "Op 5 of 4" on the operator's screen. Everything else is
as you specified.

Your two questions are answered in sections 4 and 5. Neither is a truncation
problem. The short version of both: **nothing is being silently dropped or cut.**

---

## 1. The format — as specified

```scl
Lines1[0].X := 0.000; Lines1[0].Z := 0.000; Lines1[0].F := 5;  Lines1[0].CMD := 50; Lines1[0].Param := 1;  // OPERATION 1 of 5 [Op1]
Lines1[3].X := 0.000; Lines1[3].Z := 0.000; Lines1[3].F := 3;  Lines1[3].CMD := 51; Lines1[3].Param := 1;  // PASS 1 of 3 [Op1 P1]
```

`X` and `Z` are `0.0`. Markers are ordinary recipe lines: counted in `LineCount`,
folded into the checksum, subject to the 1000-line maximum. The checksum is
computed after insertion, over the lines as written — we verified the file
re-derives its own number, so you should not see `16#0316`.

**Placement.** `CMD=50` goes *before* the operation's setup lines (cylinder, tool
change, spindle) and `CMD=51` goes *after* them, immediately before the pass's
first real line. So nothing on the HMI is blank while the turret is indexing and
the spindle is spinning up, which was the point of the display. You said this was
our call; that is the call.

## 2. The numbers come from the comments, not from a second calculation

You noted that we already compute this and it travels in the `[Op1 P2]` comments.
That is now literally where the markers get their numbers — the export reads its
own comment stream rather than recomputing anything. It means the screen and the
file cannot drift apart, and it decided two edge cases for us:

- **A back pass carries the number of the forward pass it returns from.** It does
  not get one of its own. The tags already work this way, and it also means
  "Pass 2 of 3" matches the pass count the programmer typed in.
- **An operation with no passes** (our "Point" positioning op, and anything else
  that produces no toolpath) gets a `CMD=50` and no `CMD=51`.

## 3. `TotalOps` — where we did not follow the letter

You asked for `TotalOps` = the number of operations that actually emit lines. We
send **the number of rows in the operation list**, including switched-off rows.

The reason is that the operation number in `Param` is a **row number**. An
operation tagged `[Op5 …]` is the 5th row of the list, and that is the number the
programmer sees in our UI and in the file. In `DB_RecipeProgram1` the two
switched-off rows happen to be the last two, so counting emitted ops would have
looked correct — but with a middle row disabled the pair goes wrong immediately:

```
Op list:              We send:            Your rule would send:
  1 Roughing    ->    Op 1 of 5             Op 1 of 4
  2 Roughing    ->    Op 2 of 5             Op 2 of 4
  3 (disabled)  ->    (nothing)             (nothing)
  4 Finishing   ->    Op 4 of 5             Op 4 of 4     <-- stalls
  5 Bending     ->    Op 5 of 5             Op 5 of 4     <-- impossible
```

So the display can skip a number (Op 2 → Op 4), but it never exceeds its total and
never stops short of it. We think a skipped number is the honest reading — the
operator's program really does have five operations and one really is switched
off — but the alternative was available and we chose this one deliberately. **If
you would rather have a gapless 1..N count, say so and we will renumber**; it is a
one-line change on our side. The cost is that the screen would then disagree with
the `[OpN PM]` comments in the same file, which is what an engineer reads when
diagnosing a problem.

## 4. Your question: why Op6 and Op7 vanish from `DB_RecipeProgram1`

**Deliberate. They are switched off in the program, and no geometry is missing.**

Every operation has an enable flag; our operation list shows it as a tick column
and it toggles on double-click. A disabled row is skipped both when the toolpath
is calculated and when the recipe is written, so it contributes nothing anywhere.
The header comment block lists *every* row, enabled or not, which is why it shows
seven while only five carry tags.

`RPM=0.0` on both is a consequence, not the cause: they are rows that were never
configured, so they still hold their default speed. The export does not test the
spindle speed and would happily emit an operation at `RPM=0` if it were enabled.

Nothing is being machined with two operations missing. Thank you for asking rather
than assuming — you were right that it needed an answer either way.

## 5. Your question: is 999 a deliberate cap, and does anything get truncated?

**Nothing is ever truncated. Not the geometry, not the program.** If a recipe
exceeds 1000 lines the export *refuses* and says so; there is no code path that
shortens a program to fit.

What you are seeing in `DB_RecipeProgram3`, `4` and `5` is our **auto-tune**
option. When it is on, the export searches for the finest toolpath tolerance whose
line count still fits a target — default 1000 — and takes the result closest to
the target *from below*. Three different parts landing on exactly 999 is precisely
what that search produces; it is filling the budget, not hitting a wall.

The important distinction: **auto-tune coarsens resolution, it does not remove
program.** Every operation, every pass and every command is still there; the
forming passes are described with slightly fewer points. So those three programs
are complete. It is a soft cap and it is ours, and you are right that 1000 is what
your array holds — that is where the default came from.

If you would find it useful, we can put the fitted tolerance in the header comment
so it is visible from the file which programs were auto-tuned and how hard.

## 6. Your question: do op and pass numbers stay within 255?

In practice yes, with a large margin — the 1000-line ceiling binds long before the
byte does, since every pass costs several lines. But nothing in our UI enforced
it, so we now check explicitly: **an op or pass number above 255 refuses the
export** with a message telling the programmer to switch markers off. It will not
wrap and it will not ship a number that differs from what is in the file.

## 7. The line cost, and how it interacts with auto-tune

Measured on a five-operation program with two rows disabled: 44 lines → **53**
with markers (3 operation markers + 6 pass markers). Consistent with your +19 and
+32 figures.

You asked us to refuse or warn rather than truncate or silently drop. We do
neither of those things, and we went one step further: **when auto-tune is on, the
marker lines are reserved inside the budget before the tolerance is fitted.** The
marker count does not depend on the tolerance — thinning removes points *inside* a
pass and never removes a pass — so it can be reserved exactly. A program that fits
during the fit still fits when written; it is simply thinned a little more to pay
for the markers.

With auto-tune **off** the behaviour is what you asked for: the export refuses if
markers push the program over 1000, and the message names the checkbox to turn
off.

## 8. The test export

Attached alongside this file:

- `DB_RecipeProgramX_pass_markers.scl` — markers on, 53 lines, checksum 222795
- `DB_RecipeProgramX_no_markers.scl` — same program, markers off, 44 lines,
  checksum 187235

Note this is **not** your `DB_RecipeProgram1` — we do not have that part file on
our side, only the exported .scl you quoted. It is a program built to have the
same shape: five operation rows with the last two switched off, a three-pass op, a
two-pass op and a single-pass finishing op. Send us the `.ssp` and we will
regenerate the real one; until then this exercises the same paths.

Both pass the geometry self-check and re-derive their own checksums.

## 9. Your carried-over item — already done

> a **distinct** `Header.sName` per program

This was fixed after the chunked-recipes letter. The export now derives the name
from the program slot, so `DB_RecipeProgram3` writes `Header.sName := 'Program 3'`
rather than `'SpinningCam Program'`, and the programmer can override it in the
export dialog. If your recent files still show the old string they were exported
from an older build — please re-export one and confirm you see the slot name.

## 10. What we would like back

1. Confirmation that the row-number `TotalOps` (section 3) is acceptable, or a
   word if you want a gapless count instead.
2. Whether `F` carrying a total on a non-motion line causes you any trouble. It is
   the one place these two commands break the "F=0 on everything except LINEAR"
   rule in the interface spec, and we have written it into the spec as an
   exception — we would rather have that confirmed than assumed.
3. Anything you learn from running the attached file on the real HMI.
