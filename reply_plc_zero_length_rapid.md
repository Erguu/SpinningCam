# Reply — what the controller does with a line that moves nothing

**From:** PLC side (Mexico Metal Spinning, Siemens S7-1214C / TIA V17)
**Date:** 2026-09-19
**Answers:** `letter_spinningcam_zero_length_rapid.md` (2026-09-18)

---

## Short version

**The zero-distance rapid was not costing three seconds. It costs about 0.1 s.**
No `MC_MoveAbsolute` is issued for it, there is no in-position wait and no timeout — the
handler recognises it as a null move and advances. Your change is still right (a line that
moves nothing is wrong, and it costs one of the 1000 slots), and **nothing in the PLC depends
on that line** — drop them.

But you should keep looking, and we think the answer may already be in the rows you quoted:

> **Row 159 takes 3.75 seconds by itself.** `X 179.391 -> 179.308, Z 181.000 -> 206.000` is a
> 25.0 mm line at `F=400` mm/min = 6.67 mm/s. That is 3.75 s of programmed feed, at exactly
> the turn the operator describes, on the row immediately after the one you suspected. At 50 %
> feed override it is 7.5 s. Row 160 is 59.5 mm at the same feed = 8.9 s.

Before any more PLC work: have the operator confirm whether what he is timing is the machine
standing still, or row 159 executing normally with the roller creeping near the mandrel.
Those look very similar from two metres away.

---

## A caveat on the numbers below

Scan counts depend on which build is in the CPU. The line-to-line dead time was halved on
2026-09-02 (4 scans -> 2), but **that change is on an experimental branch and has not been
downloaded to the machine.** Unless a download happened that we have not recorded, the machine
runs the 4-scan structure. Both figures are given. OB1 cycle is **measured at 40-45 ms**
(2026-09-15); we use 45 ms.

---

## 1. What `CMD=0` with zero distance costs

`STATE_READ` copies X and Z into the target registers and selects `STATE_EXEC`. `STATE_EXEC`
computes the per-axis deltas, finds both at or below 0.01 mm, sets neither axis to move, and
falls through to `STATE_NEXT`:

```scl
#bMoveX := #deltaX > 0.01;
#bMoveZ := #deltaZ > 0.01;
...
ELSIF NOT #bMoveX AND NOT #bMoveZ THEN
    #state := STATE_NEXT;
```

- **No `MC_MoveAbsolute` is issued** — the motion FBs are called with `Execute := FALSE`.
- **No in-position window, no settling, no minimum execution time.** The handler has none, and
  the TO is never given a command to be in position about.
- **No timeout applies.** The 300 s motion timeout only counts in `STATE_WAIT`, which this line
  never enters.

| | Deployed build (4-scan) | After the 2026-09-02 fix (2-scan) |
|---|---|---|
| Scans | 3 (`READ`, `EXEC`, `NEXT`) | 2 (`READ`+`EXEC`, `NEXT`) |
| Time at 45 ms | **~135 ms** | **~90 ms** |

Order of magnitude answer to your question: **one tenth of a second.** Not seconds.

---

## 2. Does the 0.01 mm rule apply to `CMD=0`?

Yes — and to `CMD=1` as well. It is not a feed-only rule; it is the same code for every
`MC_MoveAbsolute` line. But the **shape** differs from the velocity-mode rule, and the
difference matters to you:

| | Rapid / feed (`CMD=0`, `CMD=1`) | Continuous (`CMD=2`) |
|---|---|---|
| Test | **per axis**: `ABS(dX) > 0.01` and `ABS(dZ) > 0.01`, independently | **vector**: `SQRT(dx^2+dz^2) <= 0.01` |
| Zero-length line | silently skipped | whole recipe **refused** by pre-scan |
| Partial case | `dX = 0.5, dZ = 0.005` commands **X only**; Z is not commanded at all, and that costs nothing | n/a |

Consequences worth knowing:

- A line with `dX = 0.008` **and** `dZ = 0.008` is dropped even though its vector length is
  0.0113 mm. The per-axis test is slightly more permissive than a vector test.
- Your 0.012 mm drop threshold is safe against both rules.
- **No drift accumulates.** A skipped line does **not** advance the handler's `currX/currZ` —
  those only move when a move actually completes. The next line's delta is therefore measured
  from the last point genuinely reached, so a run of sub-threshold points eventually exceeds
  0.01 mm and moves. You do not need to compensate for skipped lines.

---

## 3. Do `CMD=50` / `CMD=51` cost measurable time?

Yes, but scans — **not an HMI handshake.** The markers write four integers into a data block
and the panel polls that block asynchronously. **Nothing in the PLC ever waits for the HMI.**

Each marker: `STATE_READ` (write the values, go to `NEXT`) then `STATE_NEXT` = **2 scans,
~90 ms**. That figure is the same on a build *without* the marker handler, where the code falls
into `ELSE // unknown command - skip` and takes the identical two scans.

So your rows 156 + 157 + 158 together cost about **0.3 s** on the deployed build. Real, and
worth knowing, but not three seconds. Across a whole program the 28 markers in the export we
have here cost roughly **2.5 s**. If you ever want that back it is yours to spend; we would not
move them on this evidence.

---

## 4. Is there a settling wait when the path reverses?

**No in-position window and no dwell exist in the PLC.** The handler waits only for the TO's
`Done`, then spends the dead scans.

The thing that actually costs time at a turn is larger than any wait, and it is not specific to
turns: **the S7-1200 cannot blend.** `MC_MoveAbsolute` on a PTO axis has no look-ahead and no
command buffer, so **every line ends at v = 0** — corner or not. The per-junction cost is:

| Component | At `F=400` (6.67 mm/s) |
|---|---|
| Decel ramp (jerk-limited, `T = 2*sqrt(v/j)`, `j = 2564` mm/s^3) | ~102 ms |
| Dead scans between lines | ~180 ms deployed / ~90 ms after the fix |
| Accel ramp | ~102 ms |
| **Total per junction** | **~0.4 s deployed, ~0.3 s after the fix** |

Over a 199-line program that is **35-70 s of pure stop-start**, spent at every line and not
only at pass ends. That is the real prize, and removing it is exactly what `CMD=2` velocity
mode exists for.

---

## 5. Other commands that can take seconds without moving

| Command | Cost | Mechanism |
|---|---|---|
| `CMD=20`, speed unchanged | 1-3 scans | `AtSpeed` is computed from the spindle TO's own velocity, which already equals the target, so the wait passes on entry. Suppressing repeats is still correct — it just was not costing you anything. |
| `CMD=20`, speed changed | the TO's ramp to the new pulse frequency; timeout 10 s -> `16#030A` | **There is no spindle encoder.** `AtSpeed` means "the PTO frequency has ramped", not "the mandrel is turning". The VFD's own ramp is not measured at all. |
| `CMD=21` | ~2 scans to report stopped, **plus a 2 s lock-out before any restart** (`SpindleDecelTime`) | A `CMD=20` arriving within 2 s of a `CMD=21` is **deferred** to the end of that window. This is a genuine ~2 s stall — but it needs an off/on pair, which your exports only have at the start and the end. |
| `CMD=10`, tool already in the spindle | ~3 scans | The process compares the requested slot with `CurrentTool` and clears the request. **Caveat:** `CurrentTool` is maintained only by homing and by a real tool change. If anyone has stepped the turret by hand from the panel, this compare is wrong (our open item ITEM-57). |
| `CMD=10`, different tool | seconds: 2 s lock release + turret rotation + up to 6 s lock engage | — |
| **`CMD=40`** | **exactly 3.0 s, every time** | The BackSupport has **no position feedback** (`PositioningMode = 0`), so "reached" is defined as `Timeout_Extend` elapsing, and that is `T#3S`. The handler blocks for the whole 3 s. |
| `CMD=41` P1 / P2 / P3 | 2 scans | fire-and-go, no wait. |

**`CMD=40` is the only command in the set that takes exactly three seconds of standing still.**
In the export we hold it appears once, at the top of the program, so it is not a pass-end
candidate — but if the recipe built from `140926.ssp` has a `CMD=40` anywhere near that turn,
that is your answer with no further measurement needed. Worth one grep before anything else.

---

## 6. Reading back the time each line took

Yes, three ways, in increasing cost:

1. **Watch table, nothing to download.** `DB_HMI.CurrentLine` is written **every scan** while
   the recipe runs. It is the handler's **0-based** `lineIndex` — **your 1-based row N is
   `CurrentLine` N-1**, so your row 158 is `CurrentLine` 157. Three seconds is long enough to
   read by eye; it will not time the stall but it names the line, which is most of the answer.
   `DB_Diagnostic.Recipe_CurrentLine` carries the same number.
2. **TIA Trace**, also nothing to download. Record `DB_HMI.CurrentLine` sampled on the OB1
   cycle: a stall appears as a flat step, and the step's value is the line. Recording depth on
   the 1200 is small, so arm it on a trigger near the turn rather than trying to capture a
   whole program.
3. **Permanent instrumentation.** About ten lines in the handler would time every line and latch
   the longest one plus its index into `DB_Diagnostic`. Say the word — it is cheap, and it would
   settle this class of question for good rather than one program at a time.

---

## Your confirmation question: nothing depends on the zero-distance `CMD=0`

The `CMD=0` branch does exactly two things: copy X and Z into the target registers, and select
the motion state. There is no re-arming, no setpoint refresh, no state transition, no actuator,
nothing latched. A skipped line does not even advance `currX/currZ`.

**Drop them. Keep the rule exactly as narrow as you have written it** — in particular "never
drop a feed line" and "never drop before a position is known" are both right, and the second
matters more than it looks: the program-start rapids are what establish `currX/currZ`.

One caution that is not about zero-length lines. **Re-exporting renumbers.** If a program stops
mid-run and is then re-exported with a different line count, a warm restart from the saved line
refers to the old numbering and nothing detects it. After any re-export the operator must start
from the beginning. This applies to the marker option too, not only to this change.

---

## Where we think the three seconds is

Honestly: we do not know, and your letter is right that there is no PLC-side evidence yet.
What the arithmetic settles, and what it leaves:

**Ruled out** — each is 0.1 s or less: the zero-distance rapid, the pass markers, any
in-position settling (there is none).

**Still open, in the order we would check them:**

1. **Row 159 itself.** 25.0 mm at `F=400` is 3.75 s of programmed feed, at exactly the turn he
   describes. This is our first suspect precisely because it requires nothing to be wrong.
   Ask him to watch the Z axis during the three seconds: if Z is travelling, the machine is
   doing what the program told it to.
2. **A `CMD=40`, or a spindle off/on pair, near that turn** in that specific program. Five
   minutes with grep; 3.0 s and ~2 s respectively if present.
3. **The corner feed**, *if* the program he runs carries it. Our understanding is that corner
   planning is velocity-mode only, and the machine is not running a velocity-mode build —
   please confirm which export he actually loaded. If it does carry it, a line arriving at
   `F_min = 180` mm/min covers 9 mm in 3 s, and a roller creeping at 3 mm/s next to the mandrel
   is indistinguishable from a machine standing still.
4. The pass-end retract-and-return you already identified.

**On your plan to split the line arriving at a corner:** we see no reason it would not help, and
it is what we would have proposed. Two conditions. The split point must lie on the original
straight line, so the geometry is unchanged. And the split **adds a line**, which costs another
full stop — ~0.3-0.4 s at the figures in section 4 — so put the boundary far enough back that
the slow piece is short, and do not split lines that are not actually arriving at a tight
corner. Trading one 0.4 s stop for several seconds of crawling is a clear win; doing it on
every line is not.
