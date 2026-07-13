# Proposal — ID112 CODESYS kinematics split ("CAM makes the shape, CODESYS moves the machine")

**Status: DRAFT / PLANNING — 2026-07-13. No code changed. Phase 0 (interface
contract) is the first thing to fill in and agree before any code moves.**

Written from the 2026-07-13 planning discussion. Scope is **ID112 only** — the
new tilt-arm machine on a CODESYS IPC. ID111 (S7-1212, SCL export) is out of
scope and untouched; the 112 path is purely additive via `machine_adapter.py`.

Sister references: `kinematics.py` (the math being split), `CODE_NAVIGATION.md`
§19 (tilt kinematics map), memory `project_tilt_kinematics.md`.

---

## 1. The one-sentence architecture

> **The CAM makes the *shape*. CODESYS moves the *machine*.**

The boundary between them is a single per-point record:

```
{ tip_X, tip_Z, orientation θ, feed }   ← Cartesian, tool-side, no calibration baked in
```

Everything machine-specific (pivot, arm length, B travel/home/sign, the θ→axis
transform, path interpolation) lives on the CODESYS side. The CAM never emits an
axis position.

---

## 2. Current stage vs. end state

| | **Now (current code)** | **End state (this proposal)** |
|---|---|---|
| Tip X/Z + orientation θ | CAM computes it (`_compute_tilt_for_path`) | CAM computes it — **unchanged** |
| θ → physical B axis + arm compensation | **CAM** (`kinematics.py inverse`, B-word in `generate_gcode`) | **CODESYS** inverse-kinematics FBs |
| Path interpolation / point density | CAM (decimation, PLC line budget) | **CODESYS** SoftMotion interpolator |
| Export format | SCL (S7-1212) | Cartesian G-code `{X, Z, θ, F}` |
| Calibration (pivot/arm/B sign/home) | placeholder in CAM | **CODESYS = master**; CAM mirrors for offline check |
| CAM's `kinematics.py` role | produces the axis output | **offline reachability check + 3D preview only** |

**Key facts about the current code (verified 2026-07-13):**
- The CAM already produces exactly what CODESYS needs. `_compute_tilt_for_path()`
  (`path_generator.py:768`) computes per-point θ in two modes:
  - **"normal"** — θ = angle of the mandrel surface normal at the point's Z
    (`atan2(nz, nx) + tilt_offset`); cylinder wall → θ=0 = radial (like ID111).
  - **"interp"** — θ ramps linearly from `tilt_start`@start_z to `tilt_end`@end_z.
  This is **pure geometry from the CAD surface** — CODESYS cannot reconstruct it,
  so it **stays in the CAM**.
- `kinematics.py` `forward`/`inverse`/`clamp_tilt`/`check_reachable` is
  headless-verified but **physically UNVERIFIED**, and the machine geometry
  (`TILT_PROFILE_DEFAULTS`) is **placeholder** (pivot=0, B=±60, home=0, sign=+1).

---

## 3. What migrates, what stays (the core decision)

"Migrate" has three distinct fates — this is the crux, not a blanket move:

- **STAYS in CAM (geometry — the CAM's reason to exist):** toolpath generation,
  offsets, clearance/gouge, and the **surface-angle θ decision**
  (`_compute_tilt_for_path`). CODESYS has no CAD model; it cannot do this.
- **MIGRATES to CODESYS (execution):** the inverse kinematics (θ+tip → X_arm,
  Z_car, B) and path interpolation. This becomes the single source of truth for
  machine motion. The CAM stops emitting the B word.
- **STAYS in CAM but DEMOTED:** `check_reachable` becomes an **offline pre-send
  guard** (B within travel, not near ±90° singularity, arm not behind pivot), so
  impossible programs are caught at the desk, not as a runtime fault. It never
  writes the axis value into the program.

### 3a. The θ-vs-B rule (do NOT bake calibration into the G-code)
The CAM emits **orientation θ** (Cartesian geometry), *not* the physical B axis.
They differ by `B = θ·tilt_b_sign + tilt_b_home` — and that sign/home is
**calibration**, which belongs on the controller. Reasons:
1. If the CAM baked in B, **recalibrating the machine would invalidate every
   saved program** (re-post required). With θ, the same program stays valid.
2. It would split the kinematics across two places again (the mess we're leaving).
3. The X/Z are the **tool tip**; when the tool tilts, the tip swings on the arm,
   so the controller must move X_arm/Z_car to keep the tip on the commanded point
   (RTCP — same as a 5-axis mill with TCPM). That compensation *is* the inverse
   kinematics. So tip X, tip Z, and θ are all tool-side; CODESYS turns the triple
   into the three real axes.

The G-code letter *may* still be `B` — what matters is the **contract** that its
value is orientation and CODESYS runs it through the transform.

---

## 4. The phases

```
Phase 0 ─┬─> Phase 1 (CAM)  ─┐
         └─> Phase 2 (PLC)  ─┴─> Phase 3 (calibrate) ─> Phase 4 (commission)
```
Phase 0 blocks everything; Phases 1 and 2 then run in parallel; Phase 3 is the
physical accuracy gate; Phase 4 is end-to-end.

### Phase 0 — Freeze the interface contract *(pure paper, blocks all)*
Define exactly what crosses the boundary. **Fill this in first (see §5).**
- **Deliverable:** signed-off written spec of the `{X, Z, θ, F}` format.
- **Done when:** CAM side and CODESYS side agree on the format on paper.
- **Watch out:** a sign/zero-reference error in the θ convention silently
  poisons every downstream phase. Nail θ=0 reference and +θ direction now.

### Phase 1 — CAM emits the Cartesian program *(no machine needed)*
Add a 112 export via `machine_adapter.py` (additive — 111/SCL untouched). Take
the tip+θ already computed by `_compute_tilt_for_path`, **fit arcs+lines to it
(G1/G2/G3) within tolerance**, and write `{X, Z, B(=θ), F}` to the Phase-0
format. **No inverse-kinematics call, no SCL.** Keep `kinematics.py` inverse only
as the offline reachability guard.
- **Done when:** load a part → export → a 112 file matching the contract,
  cross-checked against the CAM's own 3D preview.
- **New work (from the arc decision):** an arc-fitter (line/arc fit to a
  deviation tolerance — conceptually the arc-based successor to the old RDP
  decimation) and a rule for **θ along each arc** (linear block-interp; segment
  short enough that θ-vs-true stays in tolerance). This is the bulk of Phase 1.
- **Watch out:** the CAM must NOT bake sign/home/arm into the output (§3a); the
  arc-fit tolerance must respect gouge/clearance, not just XZ deviation.

### Phase 2 — CODESYS inverse kinematics + interpolation *(parallel with Phase 1)*
On the IPC: implement the inverse-kinematics FB (port `kinematics.py inverse`:
tip+θ → X_arm, Z_car, B), wire the SoftMotion interpolator, axis config, limit +
±90° singularity handling, and the work-coordinate origin. Prove with
hand-written test paths (radial line, a cone).
- **Done when:** a test program drives the axes so the tip traces the commanded
  Cartesian path (dry, measured).
- **Watch out:** runs on placeholder geometry at first — fine for proving the
  plumbing; real numbers arrive in Phase 3.

### Phase 3 — Real geometry + calibration *(the gate — needs the machine)*
Get machine drawings → real pivot X/Z, arm length, B travel/home/sign. Enter into
CODESYS as **master**. Physically calibrate: command a known tip+θ, measure
actual, tune across the B range. Mirror the same numbers into the CAM's offline
check.
- **Done when:** commanded tip+θ = measured tip+θ within tolerance across the
  working envelope.
- **Watch out:** roller **contact-point migration** (TODO #50) is a CAM-side gap
  that calibration alone will NOT fix — the current model assumes the tool
  rotates about its own tip. It may surface as error at large tilt. Decide here
  whether it needs addressing.

### Phase 4 — End-to-end validation + commissioning
Full chain: CAM part → export → CODESYS → machine. Add a **cross-check harness**:
the CAM's offline inverse vs. CODESYS's inverse must agree on the same path
(guards the two-copies-of-geometry drift). Then air cuts → material trials →
validate surface speed / force.
- **Done when:** a real part spun from a CAM-generated program, motion + surface
  quality acceptable.

---

## 5. Phase 0 interface contract — AGREED 2026-07-13 (2 rows pend PLC side)

The single blocking deliverable. 🔒 = inherited constraint from existing code
(not open); ✅ = decided; ⏳ = pends the CODESYS project / PLC programmer.

| Item | Decision | Status |
|------|----------|--------|
| Record fields | `X, Z, B(=θ), F` + move type (G0/G1/G2/G3) | ✅ |
| **Point emission model** | **Arc segments — G1 + G2/G3.** CAM fits arcs+lines from its point stream; SoftMotion interpolates true arcs. Compact, genuine curves. | ✅ (2026-07-13) |
| Coordinate frame / origin | CAM global frame — X=0 at spindle axis, Z along axis; CODESYS work-coordinate-system maps CAM→machine. **CAM stays calibration-free.** | ✅ — confirm exact origin w/ machine builder |
| Units | mm, degrees, mm/min | 🔒 existing code |
| θ = 0 reference | radial slide (cylinder-wall normal → 0°) | 🔒 must match `_compute_tilt_for_path` |
| +θ direction | tips the tool tip toward +Z | 🔒 `kinematics.py` convention |
| G-code word for θ | `B` — meaning is **orientation**, transform-interpreted (not raw axis) | ✅ letter proposed, ⏳ PLC confirms |
| θ along an arc (G2/G3) | linear from block-start B to block-end B over the arc; keep segments short enough that θ-vs-true error stays in tolerance | ✅ — verify SMC block-interp semantics |
| G-code dialect | DIN 66025 subset via `SMC_NCDecoder`; G0/G1/G2/G3, X/Z/B/F | ⏳ PLC-side |
| Rapid vs. cut moves | G0 = approach/retract, G1/G2/G3 = cut | ✅ |
| θ on rapids | hold last θ (no reorient mid-rapid) | ✅ minor |
| Feed semantics | Cartesian tool-tip speed (true surface speed); controller holds it | 🔒 architecture |
| Calibration ownership | CODESYS = master; CAM mirrors read-only for offline check | ✅ |

---

## 6. Risk / effort summary

- **Software (Phases 1–2) is the lower-risk part.** The math already exists
  (`kinematics.py`), and the CAM already outputs the right data. Phase 1's real
  content is the **arc-fitter + θ-along-arc rule** (the arc emission decision);
  Phase 2 is porting known-good math to ST + SoftMotion plumbing.
- **Phase 3 is where the real work and risk live** — physical geometry,
  calibration, and the unresolved roller contact-migration gap (TODO #50).
- **Do not build the export against placeholder geometry and call it done.** The
  pipeline can be built early, but nothing is *trustworthy* until Phase 3.

---

## 7. Open questions

1. Which SoftMotion package / CODESYS Robotics kinematics interface will host the
   custom tilt-arm transform? (predefined vs. user-defined kinematics)
2. Does the roller contact-migration refinement (TODO #50) need to land before or
   after first parts? (affects accuracy only at large tilt)
3. Feed handling on rapids and at path blends — controller defaults vs. CAM hints.
4. How is the calibrated geometry pushed from the CODESYS master into the CAM's
   offline check (shared file, manual entry, import)?
5. Confirm SoftMotion interpolates the `B` orientation **linearly across a G2/G3
   block** (assumed in §5). If not, the arc-fitter must cap segment length so the
   θ approximation stays within tolerance.

---

## 8. Questions for the PLC / CODESYS programmer

Context in one line: the CAM will output **Cartesian tool-tip path + tool
orientation** (`X, Z, B(=θ), F`, arcs G1/G2/G3), and the **controller** does the
inverse kinematics (θ+tip → real axes X_arm, Z_car, B) and interpolation. These
questions pin the format so both sides can build in parallel.

### A. Blocks the CAM export format — please answer first
1. **Arc format:** for G2/G3, do you want centre offsets **I/K** or a radius
   **R**? Absolute or incremental centre? Which working plane (**G18** = XZ)?
2. **Orientation input:** which G-code letter carries the tool orientation —
   **`B`** or something else? Units **degrees**? Confirm the value is the
   *orientation* and the transform applies `B_axis = θ·sign + home` internally
   (i.e. the CAM must **not** pre-apply sign/home).
3. **Orientation across an arc:** does SoftMotion interpolate that orientation
   **linearly from block-start to block-end over a G2/G3 arc**? If **not**, tell
   us how it behaves — we'll cap arc segment length so the angle stays in
   tolerance. *(This directly sizes our arc-fitter.)*
4. **Program frame:** can the program be in our **CAM global frame** (X=0 at the
   spindle axis, Z along the axis) with the controller applying the work offset /
   kinematic origin — or must the CAM pre-offset into a machine frame?
5. **Program delivery:** how does the IPC receive the program — **file on disk**,
   string, or fed to the interpolator via ST? What file extension / text
   encoding / line ending do you expect?
6. **Feed:** confirm **F = Cartesian tool-tip speed** (true surface speed), in
   **mm/min**. Any **max feed / accel / jerk** we should cap or hint in the CAM?
7. **Rapids:** for G0 approach/retract, should we **hold the last orientation**
   (our assumption) or command a reorientation during the rapid?

### B. Needed for the controller build (Phase 2/3), not blocking the CAM yet
8. **Runtime + package:** which CODESYS runtime and **SoftMotion** package/version
   is on the IPC? Does the licence include **CNC interpolation + kinematic
   transformation** FBs?
9. **Transform type:** will the tilt-arm inverse kinematics be a **predefined**
   SoftMotion kinematic or a **user-defined/custom** transform? (We expect
   custom; our `kinematics.py inverse` is the reference math to port.)
10. **RTCP confirmation:** confirm the controller moves the **linear axes to keep
    the tip on the commanded X/Z while B changes** (tip swings on the arm) — i.e.
    it owns the full transform, not just the B axis.
11. **Calibration ownership:** confirm **pivot X/Z, arm length, B travel/home/sign
    live as controller parameters** (controller = master). How can those values
    be **exported back to us** so the CAM's offline reachability check uses the
    same numbers (params file / manual)?
12. **Limits & singularity:** the B travel limits, and how the controller handles
    **out-of-range or the ±90° singularity** — reject the program up front, or
    fault at runtime? (Sets how strict our offline guard must be.)
13. **Look-ahead / blending:** what path-smoothing / blend tolerance will be
    active, so our arc-fit tolerance and your blending don't fight each other?

---

*Created 2026-07-13 — planning session (CAM/CODESYS kinematics split for ID112).*
