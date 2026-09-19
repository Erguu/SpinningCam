# To the PLC team — what does the controller do with a line that asks for no movement?

**Machine:** Mexico Metal Spinning, Siemens S7-1214C / TIA Portal V17
**Subject:** CMD=0 whose X and Z equal the current position; and the cost of a recipe line that moves nothing
**Date:** 2026-09-18
**Follows:** `letter_spinningcam_velocity_path.md` and your reply 3 (2026-09-16), `letter_spinningcam_pass_markers.md`
**Status of our side:** we have stopped emitting these lines (see *What we changed*). The questions stand regardless — we would like to know whether we were chasing the right thing.

---

## Short version

The operator reports that at **some** pass ends the machine stands still for about **3 seconds**
before the next pass starts. His description: it always happens after a reverse pass, just as the
program turns back to a forward pass — the tool comes to the mandrel, waits about 3 seconds, then
starts — *"but it doesn't happen every time"*.

We went looking on our side. In the live program `140926.ssp` we found **two recipe rows that ask
the axes to move to the point they are already standing on**, and one of them sits exactly at the
turn he describes. No other program of his has any.

We cannot tell from here whether the controller spends time on such a row. That is question 1.

---

## What we found, exactly

Recipe built from `140926.ssp` (199 rows, pass markers on). Row numbers are 1-based in the
`Lines` array.

**Row 158 — the reverse → forward turn the operator describes.** Op20 (reverse) ends at
X=179.391 Z=181.000. Row 158 then commands a rapid *to X=179.391 Z=181.000*:

```
  156: CMD=50  X=    0.000 Z=    0.000 F=67     // operation marker
  157: CMD=51  X=    0.000 Z=    0.000 F=1      // pass marker
  158: CMD=0   X=  179.391 Z=  181.000 F=0      // <-- zero distance: already there
  159: CMD=1   X=  179.308 Z=  206.000 F=400
  160: CMD=1   X=  158.887 Z=  261.858 F=400
```

**Row 176 — before the tool change.** Row 174 is the last cut of Op22 and ends at the same point:

```
  174: CMD=1   X=  179.391 Z=  181.000 F=400
  175: CMD=50  X=    0.000 Z=    0.000 F=67
  176: CMD=0   X=  179.391 Z=  181.000 F=0      // <-- zero distance: already there
  177: CMD=0   X=  129.391 Z=  181.000 F=0
  178: CMD=20  X=  129.391 Z=  181.000 F=0
```

Measured across all nine of his programs: **only `140926.ssp` contains such rows, and only these
two.** That matches "it doesn't happen every time" better than anything else we have been able to
measure.

---

## Questions

**1. What does the controller do with `CMD=0` whose X and Z equal the current position?**
Is it issued to the technology object as a MoveAbsolute and waited on until "Done" / in-position?
Is there a minimum execution time, a settling window, or a timeout that applies when the axis has
nothing to travel? An order-of-magnitude answer is enough: microseconds, one scan, or seconds.

**2. Does the `<= 0.01 mm` skip rule apply to `CMD=0` as well, or only to feed commands?**
Your reply 3 told us the PLC skips a line shorter than 0.01 mm, and that a `CMD=2` of zero length
makes the whole recipe rejected (`CMD=2 zero-length: repeats previous point`). We now drop points
closer than 0.012 mm in velocity mode because of that. We have never known what the rule is for a
rapid.

**3. Do `CMD=50` / `CMD=51` markers cost measurable time?**
At row 158 there are two marker rows immediately before the suspect line, and another at row 175.
If each marker costs an HMI handshake rather than a scan, three rows in a row at the same place
would add up — and the markers are ours, so we can move or drop them.

**4. When the path reverses at a pass end, is there a settling wait before the next line starts?**
A pass end that turns by 90° or more becomes an exact stop (`CMD=1`), as your reply 3 specified.
After such a stop, does the controller wait for an in-position window before executing the next
row, and roughly how long is that? This would be a normal and acceptable cost — we would simply
like to know its size, so we can tell the operator what is the machine and what is us.

**5. Is there any other recipe command that can take seconds without moving?**
Specifically: `CMD=20` (spindle setpoint) when the speed is unchanged, and `CMD=10` (tool change)
when the requested tool is already in the spindle. We already suppress a repeated `CMD=20`, but we
would rather know than guess.

**6. Can the time each recipe line took be read back from the HMI or a trace?**
If the operator could point at "line 158 took 3 seconds", questions 1 to 5 would answer
themselves — for this problem and for the next one.

---

## What we changed on our side

From 2026-09-18 the CAM **never writes a rapid to the point the tool already occupies.** A move
with nothing to move is wrong whatever the controller does with it, and it costs one of the 1000
recipe lines.

The rule is deliberately narrow: a `G0` is dropped only when **every axis it names** is already at
that value, tilt (B) included; a feed line is never dropped; a rapid that moves any axis at all,
even 0.001 mm, is never dropped; and nothing is dropped before a position is known, so the
program-start homing rapids always stand.

Measured on the nine shop programs: `140926.ssp` loses exactly the two rows above, **every other
program is byte-identical**, and the full test suite (108 files, including the golden regression
set of real field programs) passes.

**One thing to confirm, please:** if the controller relies on that `CMD=0` for anything other than
motion — re-arming an axis, refreshing a setpoint, a state transition — tell us and we will put it
back. We assumed it is pure positioning.

---

## What we are still chasing

The zero-distance rapid is the best lead we have, but it is a lead, not a conclusion — we have no
PLC-side evidence. Two other things in the same program are being looked at on our side and need
nothing from you:

* at half his pass ends the roller still lifts clear and comes back, because our "no retract at the
  mandrel end" option only covers the reverse → forward turn and not the forward → reverse one;
* the corner feed rule from your reply 3 costs `140926.ssp` a large part of its cutting time at a
  corner tolerance of 0.1 mm (5.4 min of programmed feed becomes 10.8 min). We are looking at
  splitting the long line that arrives at a corner, so that only the short piece next to the corner
  runs at the corner feed instead of the whole 85 mm line. If you see a reason that would not help,
  we would rather hear it before we build it.
