# To the SpinningCam developer — recipe output must be split into chunk arrays

**Machine:** Mexico Metal Spinning, Siemens S7-1214C / TIA Portal V17
**Subject:** a change to the `DB_RecipeProgramN.scl` post-processor output
**Date:** 2026-08-14
**Status of our side:** implemented and running in simulation; hardware test pending

---

## Short version

The PLC can no longer read a recipe as one `Array[0..999]`. Please emit the same data as
**ten arrays of one hundred lines** — `Lines1 .. Lines10`, each `Array[0..99]` — in the same DB,
with everything else unchanged.

```
    VAR
        Header : "RecipeHeader";
        Lines1 : Array[0..99] of "RecipeLine"; // global lines 0..99
        Lines2 : Array[0..99] of "RecipeLine"; // global lines 100..199
        ...
        Lines10: Array[0..99] of "RecipeLine"; // global lines 900..999
    END_VAR
```

Mapping is positional, nothing else changes:

```
global line g   ->   Lines[(g // 100) + 1] [ g % 100 ]

line   0  ->  Lines1[0]
line  99  ->  Lines1[99]
line 100  ->  Lines2[0]
line 207  ->  Lines3[7]
line 998  ->  Lines10[98]
```

`Header` keeps counting in **global** lines: `Header.LineCount := 999` still means 999 lines, and
the mandatory `CMD := 99` END marker still sits at global line `LineCount-1` — which is now written
as `Lines10[98]`, not `Lines[998]`.

We already have a converter (`tools/split_recipe_db.py`) that rewrites your current output into
this form, so **nothing is blocked** waiting for you. We would rather it came from the source, since
every manual step in a recipe pipeline eventually gets skipped once.

---

## Why — this is not cosmetic

Recipes live in the CPU's **load memory** (`UNLINKED`), which costs no work memory but cannot be
addressed by the program at all. The only way in is `READ_DBL`, which copies a block from load
memory into a work-memory buffer.

**`READ_DBL` does not reliably deliver 12 KB on this CPU.** It returns `RET_VAL = 0` and
`BUSY = FALSE` — the contract's definition of success — while the destination comes back with holes
in it. Observed on the machine on 2026-08-13, on two consecutive attempts with the same file:

- once with data present only after roughly line 850
- once with data around line 200 and zeros elsewhere

The failure is silent by construction: nothing in the instruction's result says the copy was short.
The first time it happened with a 38-line program, the missing END marker made the PLC stop. The
second time, with a 999-line program, the END marker happened to be inside the region that *did*
arrive — so the machine started, and ran roughly 900 zero-length moves at X0/Z0 with the operator
watching the line counter advance normally.

Smaller transfers land. So the recipe is now pulled **one chunk at a time**, each chunk verified
line by line before it is accepted, with a retry per chunk and a hard stop (`16#0314`) if a chunk
never arrives intact.

**Why chunks must exist as separate declared arrays.** `READ_DBL`'s source parameter is a `VARIANT`
that the S7-1200 resolves at *compile* time. It accepts a whole declared member and nothing else —
no array slice, no variable index. There is no way to say "copy elements 100 through 199 of `Lines`".
So the only way to transfer a sub-range is for that sub-range to be its own named declaration. That
constraint is the entire reason for this request.

---

## The geometry is configurable — but both sides must agree exactly

100 lines × 10 chunks is not hard-coded in any interesting sense. On our side one setting owns it
and regenerates the loader and the DB declarations together, and we may retune it after the hardware
test: if a chunk still fails to arrive, we halve it (50 × 20), and if transfers prove comfortable we
may enlarge it to save code space.

**What we would like from you is therefore a parameter, not a constant** — chunk size configurable
in the post-processor, defaulting to 100, with the array count following from it. If that is
awkward, a hard-coded 100 is acceptable and we will tell you before we ever change it.

What happens when the two sides disagree, so the risk is on the table:

| Mismatch | Result |
|---|---|
| **Fewer arrays than the PLC expects** (e.g. `Lines1..Lines8`) | **Compile error in TIA** — the loader names `Lines9`/`Lines10` and they do not exist. Loud, safe, caught before download. |
| **More arrays than the PLC expects** | Compiles. The extra arrays are never read, so the tail of the program silently does not exist. Our END-marker check catches it, as a machine stop. |
| **Right count, wrong chunk size** (e.g. ten arrays of 125) | **Compiles.** This is the dangerous one: the transfer moves the wrong number of lines per chunk and the recipe is reassembled scrambled. Some of it is caught downstream, none of it is caught by the compiler. |

Because of that third row we do **not** rely on TIA to catch a mismatch. `split_recipe_db.py --check`
validates every export against the PLC's current geometry — array count, array bounds, element
indices, `LineCount`, and the END marker's position — and refuses the file rather than passing it on.
Please treat a refusal as a real defect report, not as our tool being fussy.

If you can, emit the geometry into the file header as a comment we can parse, e.g.

```
// CHUNKS: 10 x 100
```

Then the check becomes exact rather than inferred, and a future mismatch names itself.

---

## Unchanged requirements, repeated because they still bite

These predate this request and remain mandatory:

1. **`{ S7_Optimized_Access := 'FALSE' }`** — `READ_DBL` refuses an optimized source at runtime
   (`16#0312`). Four of the five recipe files currently in our repository still say `'TRUE'`; they
   cannot be loaded at all.
2. **`UNLINKED` before `NON_RETAIN`**, in that order. Reversed, TIA silently generates nothing.
   Omitted entirely, everything still works and ~12 KB of work memory quietly disappears — the
   failure is invisible until the CPU runs out.
3. **`Header.LineCount`** must equal the number of lines emitted, and the last line
   (`LineCount-1`) must carry **`CMD := 99`**.
4. **The DB name must match the file's slot.** `gcodes/DB_RecipeProgram5.scl` currently declares
   `DATA_BLOCK "DB_RecipeProgram1"` — importing it overwrites program 1 with program 5's data.
5. **A distinct `Header.sName` per program**, please. Every export currently writes
   `'SpinningCam Program'`, so the HMI cannot tell an operator which recipe is loaded.

---

## What we need back

1. Confirmation that chunked output is feasible, and roughly when.
2. Whether chunk size can be a parameter or will be fixed at 100.
3. Whether you can emit the `// CHUNKS: n x m` header line.
4. A single re-exported test file — one program, any length — so we can run it through the
   validator before you do the rest.

Reference implementation of the transformation, including the exact indexing and the validation
rules, is `tools/split_recipe_db.py` in our repository. Happy to send it over; it is about two
hundred lines of Python and the conversion itself is ten of them.
