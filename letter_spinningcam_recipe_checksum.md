# To the SpinningCam developer — a checksum in the recipe header

**Machine:** Mexico Metal Spinning, Siemens S7-1214C / TIA Portal V17
**Subject:** one new `Header` field, and the exact algorithm to fill it
**Date:** 2026-08-14
**Follows:** `letter_spinningcam_chunked_recipes.md` (chunked output — implemented on your side, thank you)
**Status of our side:** specified here, not yet implemented; we will build it to match this document

---

## Short version

Please add **two fields** to `RecipeHeader` and fill them from the lines you emit:

```scl
ProvidesChecksum : Bool;    // TRUE = Checksum below is valid
Checksum         : UDInt;   // order-sensitive sum over the emitted lines
```

The algorithm is eight lines of code, uses only integers, and is given in full below with a
reference implementation you can paste. The PLC recomputes the same number after it has reassembled
the recipe and refuses to run if the two disagree.

**Two requests bundled in, both still open from the last letter:**

1. Is chunk size a **parameter** on your side, or fixed at 100?
2. Please confirm the `// CHUNKS: n x m` header line is emitted on every export, not just the test file.

---

## Why — what our current verification cannot see

You already know the background: `READ_DBL` delivers 12 KB out of load memory with silent holes in
it, so we now pull the recipe as ten 100-line chunks and verify each one before accepting it. That
verification is thorough about *one* thing and blind to another.

**What it proves:** every line of every chunk was physically written. Each staging line's `CMD` byte
is poisoned with `16#FF` before the transfer and must come back overwritten. At 100 lines per chunk
that is complete coverage, not sampling.

**What it cannot prove: that the right data arrived.** Nothing in the PLC compares the buffer against
the source. Three failure modes get through it today:

| Failure | Why the current checks miss it |
|---|---|
| A chunk arrives complete but **stale** — an older flash image of the same block | Every line is written, so the poison check passes |
| Chunks reassembled **out of order or at the wrong stride** (a geometry mismatch between your export and our loader) | Every line is written, and the END marker can still land in the right place |
| A line's `CMD` arrives but its `X`/`Z`/`F` bytes do not | We only verify one byte in twelve |

A checksum closes the first two outright, and narrows the third. It is the difference between
*"every line was written"* and *"the recipe in the buffer is the recipe you exported"* — and on this
machine that distinction has already cost one ruined run.

---

## The algorithm

Two 32-bit accumulators, **natural wraparound at 2³²**, no modulo, no floating point.

```
sumA := 0
sumB := 0

for g := 0 to LineCount-1:            # emitted lines ONLY, not padding
    sumA := sumA + CMD[g] + Param[g] + F[g]
    sumB := sumB + sumA

Checksum := sumB XOR (sumA + LineCount)
```

All arithmetic is unsigned 32-bit and **wraps** — that is intended, and both sides must wrap
identically. In SCL that is `UDInt`, which wraps natively. In Python, mask with `& 0xFFFFFFFF`.

Three properties are deliberate:

- **`sumB` makes it order-sensitive.** A plain sum would be identical for a correctly assembled
  recipe and one whose chunks were reassembled in the wrong order — which is precisely the geometry
  mismatch the last letter flagged as the dangerous case. Running `sumB` weights each line by its
  position, so any permutation changes the result.
- **`LineCount` is folded in**, so a truncated recipe cannot coincidentally match.
- **No modulo.** A modulo per line is a division, the most expensive operation on this CPU. Plain
  wraparound costs four adds per line, which is nothing.

### Reference implementation

```python
def recipe_checksum(lines, line_count):
    """lines: sequence of (CMD, Param, F) for global lines 0..line_count-1"""
    M = 0xFFFFFFFF
    a = b = 0
    for cmd, param, f in lines[:line_count]:
        a = (a + cmd + param + f) & M
        b = (b + a) & M
    return (b ^ ((a + line_count) & M)) & M
```

`CMD` and `Param` are the byte values 0–255. `F` is the `Int` feed value exactly as written into the
line. Nothing is scaled, converted, or reordered.

### Worked example, so we can verify we agree before you ship anything

A four-line program (`LineCount = 4`):

| g | CMD | Param | F |
|---|---|---|---|
| 0 | 20 | 120 | 0 |
| 1 | 0 | 0 | 0 |
| 2 | 1 | 0 | 250 |
| 3 | 99 | 0 | 0 |

```
g=0:  a = 140          b = 140
g=1:  a = 140          b = 280
g=2:  a = 391          b = 671
g=3:  a = 490          b = 1161

Checksum = 1161 XOR (490 + 4) = 1161 XOR 494 = 1383
```

Please run your implementation against this before anything else. If it returns `1383` we are
finished agreeing and the rest is mechanical.

---

## Why `X` and `Z` are deliberately excluded

They are the geometry, so leaving them out looks like the wrong choice. It is a considered one.

`X` and `Z` are `Real` (IEEE-754 single). You would compute the checksum in Python `float64`; the PLC
computes in `float32`. Any scheme that sums their *values* — even scaled to integers, e.g.
`ROUND(X * 1000)` — depends on rounding at tie boundaries and on accumulation order, and will
eventually disagree on a perfectly valid recipe. A checksum that occasionally cries wolf is worse
than none, because the alarm gets ignored and then it is ignored on the day it is real.

Checksumming the *bit patterns* rather than the values would be exact, but it needs raw memory reads
on our side and byte-order care on yours. **If you want to add it, we will take it as a separate
field** (`ChecksumXZ : UDInt`, same two-accumulator scheme over
`struct.unpack('<I', struct.pack('<f', x))[0]` for each `X` then `Z`) and implement it as a second
stage. Please do not fold it into `Checksum` — we want to be able to trust one without the other.

The integer checksum on its own already catches every failure mode we have actually observed.

---

## Our side of the handshake

So you know exactly what we are building against this:

- The PLC accumulates during reassembly, inside the loop that already walks every line. Measured cost
  is well under a millisecond per chunk, at cycle start with the machine stationary.
- After the last chunk it compares against `Header.Checksum` and raises a **new error `16#0316`,
  "Recipe checksum mismatch — re-export and re-import the recipe"**, refusing to run.
- **`ProvidesChecksum = FALSE` is accepted and skips the check**, so recipes exported before this
  change still load. We are not making a flag day out of it. `Checksum` is ignored entirely when the
  flag is clear — do not rely on writing `0` to mean "none".

---

## One unavoidable cost, and the good news about timing

Adding fields to `RecipeHeader` changes the block's byte layout, so **every existing recipe export
becomes unloadable and must be re-exported.** There is no migration path; `READ_DBL` copies
`.Header` by length and a short header is a runtime failure.

The good news is that the bill is already due. Our `gcodes/DB_RecipeProgram2..5` are stale for other
reasons (optimized access, and one of them declares the wrong DB name), so they need re-exporting
regardless. If this change lands before you regenerate them, it costs nothing extra.

Please add the fields **at the end of the struct**, after `ToolAngle_List`, and keep everything above
untouched — that keeps the diff reviewable on our side.

---

## What we need back

1. Confirmation that the two header fields and the algorithm are workable.
2. Your implementation's result for the worked example above (expect `1383`).
3. The two carried-over questions: chunk size parameter or fixed 100, and `// CHUNKS: n x m` on
   every export.
4. One re-exported test program carrying a checksum, so we can validate before you regenerate the set.

As before, `tools/split_recipe_db.py --check` will be extended to verify the checksum offline, so a
bad export is caught at the desk rather than at the machine. Happy to send it over.
