# CAM Handover — Recipe-Carried Tool Table

**Audience:** the agent/developer updating the **SpinningCam post-processor**.
**Goal:** make the CAM emit a **tool table inside every recipe's `Header`** so the PLC
takes its turret setup (tool-code→slot mapping, slot count, slot angles) directly from
the downloaded recipe. This replaces the old HMI-entered mapping.

The PLC side of this change is **already implemented** (see "PLC changes already done"
below). The only remaining work is on the CAM post-processor: it must populate the new
header fields in the generated `DB_RecipeProgram[N].scl` files.

---

## 1. Why this change

- Operators re-download recipes to the PLC frequently. The old mapping lived in
  `DB_ToolConfig` (a `NON_RETAIN` DB set from the HMI) and did **not** travel with the
  program, so it could be lost on a full download and had to be re-entered by hand.
- New model: **the recipe is the single source of truth for the tool setup.** The CAM
  already knows which tools each operation uses; it now also emits the slot mapping,
  slot count, and (optionally) slot angles into the recipe header.
- Policy chosen by the machine owner: **"recipe always wins."** The HMI can no longer
  edit the mapping (its field is now a read-only mirror), and a recipe that does **not**
  carry a tool table is **rejected at Start** with error `16#0311`.

---

## 2. New `RecipeHeader` layout

The PLC data type `RecipeHeader` (in `Program/01_DataTypes.scl`) now has these fields
appended after the bounding box. The CAM must write the tool-table fields.

```scl
TYPE "RecipeHeader"
VERSION : 0.2
    STRUCT
        sName : String[20];                    // Program name (max 20 chars)
        LineCount : Int;                        // Total lines in program
        Valid : Bool;
        PreScanned : Bool;
        MinX : Real;                            // Bounding box (existing)
        MaxX : Real;
        MinZ : Real;
        MaxZ : Real;
        // ---- NEW: tool table ----
        ProvidesToolConfig : Bool;              // MUST be TRUE, else recipe rejected (16#0311)
        ToolCount : Int;                        // Physical slots in use (valid 1..4; PLC clamps)
        AutoCalcAngles : Bool;                  // TRUE = angles auto-spaced; FALSE = use ToolAngle_List
        ToolCode_List : Array[1..4] of Int;     // External tool code in each slot (0 = slot unused)
        ToolAngle_List : Array[1..4] of Real;   // Turret angle per slot (deg); used only if AutoCalcAngles=FALSE
    END_STRUCT;
END_TYPE
```

### Field semantics

| Field | Type | Rule |
|-------|------|------|
| `ProvidesToolConfig` | Bool | **Always emit `TRUE`.** If FALSE/absent → recipe rejected with `16#0311`. |
| `ToolCount` | Int | Number of physical slots used, **1–4**. Values >4 are clamped to 4 by the PLC (arrays are `[1..4]`). |
| `AutoCalcAngles` | Bool | `TRUE` → PLC auto-spaces angles evenly from `ToolCount` (1→0°, 2→0/180, 3→0/120/240, 4→0/90/180/270). `FALSE` → PLC uses `ToolAngle_List`. |
| `ToolCode_List[1..4]` | Int | The **external tool code** installed in each physical slot. **1-based** (`[1]`=slot 1). Every `CMD=10 Param` in the program's `Lines[]` MUST appear here, or pre-scan fails (`16#0308`/pre-scan variant). Unused slots = `0`. Each code must fit in a **Byte (0–255)** because `Param` is a byte. |
| `ToolAngle_List[1..4]` | Real | Turret angle in degrees for each slot. Only consumed when `AutoCalcAngles=FALSE`. Still emit sensible values (e.g. the auto-spaced ones) for completeness. |

> **Array base is 1** (`Array[1..4]`), matching slot numbering 1–4. Do **not** use a
> 0-based index for the tool arrays. (The `Lines[]` motion array remains 0-based — that
> is unrelated.)

---

## 3. What the CAM must generate

For each program, in the `Header` init section of `DB_RecipeProgram[N].scl`, add the
five tool-table assignments **after** the existing `Header.MaxZ` line.

The CAM already knows, per program:
- the set of tool codes referenced by the operations (`CMD=10 Param`), and
- which slot each code is assigned to (from the machine/tooling setup in CAM).

It must serialize that assignment into `ToolCode_List`, set `ToolCount` to the number of
slots used, and set `ProvidesToolConfig := TRUE`.

### Worked example (the current `DB_RecipeProgram1`, hand-filled and verified)

`Op1: ROUGHING ... T0103` → the program issues `CMD=10 Param=103`. Slot mapping used:
slot1=101, slot2=102, slot3=103. Emitted header:

```scl
    // Header
    Header.sName := 'SpinningCam Program';
    Header.LineCount := 350;
    Header.Valid := TRUE;
    Header.PreScanned := FALSE;
    Header.MinX := 0.000;
    Header.MaxX := 267.556;
    Header.MinZ := 0.000;
    Header.MaxZ := 279.429;

    // --- Tool table (CAM-authored) ---
    Header.ProvidesToolConfig := TRUE;
    Header.ToolCount := 3;              // 3 physical slots in use
    Header.AutoCalcAngles := TRUE;      // angles auto-spaced (3 slots -> 0/120/240)
    Header.ToolCode_List[1] := 101;     // slot 1 -> code T101
    Header.ToolCode_List[2] := 102;     // slot 2 -> code T102
    Header.ToolCode_List[3] := 103;     // slot 3 -> code T103  (used by this program)
    Header.ToolCode_List[4] := 0;       // slot 4 unused (ToolCount=3)
    Header.ToolAngle_List[1] := 0.0;
    Header.ToolAngle_List[2] := 120.0;
    Header.ToolAngle_List[3] := 240.0;
    Header.ToolAngle_List[4] := 0.0;

    // Recipe Lines (350 total)
    Lines[0].X := 0.000; Lines[0].Z := 0.000; Lines[0].F := 0; Lines[0].CMD := 0; Lines[0].Param := 0;
    // ... T103 tool change appears at Lines[2]: CMD=10, Param=103 ...
```

### Template for the post-processor

```
Header.ProvidesToolConfig := TRUE;
Header.ToolCount := <number of slots used, 1..4>;
Header.AutoCalcAngles := <TRUE|FALSE>;
Header.ToolCode_List[1] := <code in slot 1 or 0>;
Header.ToolCode_List[2] := <code in slot 2 or 0>;
Header.ToolCode_List[3] := <code in slot 3 or 0>;
Header.ToolCode_List[4] := <code in slot 4 or 0>;
Header.ToolAngle_List[1] := <deg>;   // only used if AutoCalcAngles=FALSE
Header.ToolAngle_List[2] := <deg>;
Header.ToolAngle_List[3] := <deg>;
Header.ToolAngle_List[4] := <deg>;
```

---

## 4. Validation rules the CAM must satisfy (else the PLC rejects/faults)

1. **`ProvidesToolConfig := TRUE`** on every program. Missing → `16#0311` at Start.
2. **Every `CMD=10 Param` value must be present in `ToolCode_List[1..ToolCount]`.**
   A tool code not found → pre-scan fails / `16#0308` at runtime.
3. **`ToolCount` in 1..4.** (PLC clamps >4 to 4, but emit a correct value.)
4. **Tool codes are bytes (0–255).** `Param` is a single byte; codes outside 0–255
   cannot be represented.
5. **Slot indices are 1-based** (`ToolCode_List[1]`…`[4]`).
6. Unused slots set to `0`.
7. If `AutoCalcAngles := FALSE`, populate `ToolAngle_List` with real turret angles.

---

## 5. Backward compatibility

- Old recipes generated **before** this change (no tool table) will have
  `ProvidesToolConfig = FALSE` (uninitialised Bool default) and will be **rejected with
  `16#0311`**. They must all be regenerated by the updated CAM post.
- Adding the fields to the UDT is backward-compatible at compile time — programs that
  don't set the fields still compile; they just fail at Start.

---

## 6. PLC changes already done (for reference — no CAM action needed)

| File | Change |
|------|--------|
| `Program/01_DataTypes.scl`, `Program/UDT_RecipeHeader.scl` | `RecipeHeader` extended with the 5 tool-table fields (VERSION 0.2). |
| `Program/06_MainProcess.scl` (STATE_PRE_SCAN) | Reads the header tool table per active program; rejects with `16#0311` if `ProvidesToolConfig=FALSE`; otherwise clamps `ToolCount` to 1..4 and copies the table into `DB_MachineConfig.ToolCount` / `DB_ToolConfig` **before** pre-scan validates tool codes. |
| `Program/06_MainProcess.scl` (top of scan) | HMI Apply path disabled; `DB_HMI.ToolSlotCode` is now a read-only mirror of `DB_ToolConfig.ToolCode_List`. |
| `Program/06_MainProcess.scl` (FB_AlarmManager) | New error `16#0311` (EN/ES text, severity tier 2 "Recipe"). |
| `gcodes/DB_RecipeProgram1.scl` | Hand-filled with the example tool table above (bench-testable now). |

**Error code added:** `16#0311` — "Recipe has no tool table - regenerate in CAM" /
"Receta sin tabla de herramientas - regenerar en CAM". Severity tier 2 (Recipe).

---

## 7. Quick test checklist (after CAM update)

1. Generate a recipe with the new header; download `DB_RecipeProgram1` to the PLC.
2. Press Start. Confirm it does **not** raise `16#0311`.
3. On the HMI Tool Setup screen, confirm `ToolSlotCode[1..4]` now shows the recipe's
   codes (mirror), and that editing them has no effect (recipe always wins).
4. Confirm the `CMD=10` tool change rotates the turret to the mapped slot.
5. Negative test: set `ProvidesToolConfig := FALSE` in a test recipe → Start must fault
   with `16#0311` and a clear HMI message.
