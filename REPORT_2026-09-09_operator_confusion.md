# Report — Why the operator keeps saying "the CAM program is acting weird again"

**Date:** 2026-09-09
**Author:** research session (read-only; **no project file was modified**)
**Branch at time of research:** `feature/point-control` (HEAD `7be8454`, v1.031)
**Status:** Findings reproduced and measured. **Nothing implemented.** Fix proposals only.
**Scope:** `path_generator.py` (clearance correction + follow-blank reach),
`ui/tabs/program_tab.py` (conformal checkbox), warning plumbing in `ui/main_window.py`.
**Risk of the findings themselves:** two of them silently change what the machine runs.

---

## 0. The complaint we started from

The shop operator periodically calls and says *"hey, the CAM program is acting weird
again"*, then sends a screenshot. The screenshot is almost always one of two things:

**Complaint A —** a pass shows **a very big reach value**, far bigger than anything
that was typed.

**Complaint B —** *"I changed the clearance on some of the passes and the change does
not appear"* — not in the SCL Inspector, not in the 3D view.

The working assumption up to now has been that this is a **training / UI problem**: no
matter how many info boxes, tooltips and explanatory dialogs get added, the operator
cannot locate the cause quickly. The stated goal of this session was to research the
problem and improve that.

**The research says the assumption was wrong.** Both complaints are backed by real
defects in the engine. The operator cannot find the cause because in these two cases
**there is nothing on screen to find** — the number he typed is displayed correctly
everywhere, and the engine overrides it afterwards without telling anybody.

---

## 1. Method

All measurements were produced by driving the real `PathGenerator.calculate_paths`
headlessly against a synthetic mandrel, and by calling `process_planner` directly. No
GUI, no `.ssp` file, no mandrel STEP needed. Reproduction scripts are in Appendix A.

> **Environment note.** These scripts must run in the `spinning_cam` conda env —
> the system Python has no `OCC` and the import fails immediately.
>
> **ACTIVATE the env; do not call `envs\spinning_cam\python.exe` by absolute path.**
> The env's `Library\bin` is only put on `PATH` by activation, and `mkl_rt.3.dll`
> resolves its kernel DLLs lazily. Without activation every LAPACK-backed call
> (`np.linalg.inv/solve/svd/lstsq`, and `np.polyfit`, which the engine reaches via
> `mandrel_analyzer._flat_start_params` whenever `straighten_start_fillet` is on)
> kills the process with a delay-load fault — **exit 127, no traceback**. Healthy
> code then looks broken. Use:
>
> ```
> call C:\Users\PC\anaconda3\Scripts\activate.bat spinning_cam
> python <script>
> ```
>
> This is a known, recurring trap; see `backup/HANDOVER_2026-07-01b.md`.

Verification approach for each finding: change **one** operator-facing input, run the
engine twice, and compare the resulting toolpath arrays. If the arrays are identical,
the input is dead.

---

## 2. Findings

### F1 — The operation's **Clearance** field can have literally zero effect  ⛔ SEVERITY: HIGH

**This is the direct explanation for Complaint B.**

#### What happens

After a pass is built, `_create_and_store_pass` runs a safety check
(`path_generator.py:3050-3080`). It finds the closest point of the **whole** pass to the
part, and if that point is nearer than the safety floor (`min_safety_gap`), it shifts
**every control point of the pass outward in X** by the shortfall.

The measurement it uses is:

```python
clearance = dist_to_axis - (m_rad + blank_thick + shell_offset + r_tool)
```

**The operation's `clearance` is not in that formula.** It is already baked into where
the pass sits. So:

- raise the typed clearance by δ → the whole pass starts δ further out
- → `min_clearance` is δ larger
- → `diff = floor − min_clearance` is δ smaller
- → the pass is pushed out δ less

**The two terms cancel exactly.** Whenever this correction fires, the final position of
the pass is decided entirely by the floor and the *geometry of the worst point*, and the
Clearance field contributes nothing at all.

#### Measured evidence

Tapered mandrel (radius 50 mm at the base falling to 8 mm at the top), one
`linear_approach` roughing pass anchored at Z=60, **`min_safety_gap = 0.0` — the
shipped default**, nothing unusual switched on:

| Clearance typed by operator | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 | 8.0 |
|---|---|---|---|---|---|---|
| Gap actually held at the contact point | **21.000** | **21.000** | **21.000** | **21.000** | **21.000** | **21.000** |

The generated toolpath arrays are **bit-identical** across all six runs. The roller sits
21 mm off the work. The pass runs its full cycle time and **does no forming at all**.

What is binding is *not* the contact point. It is the **approach arm**, which reaches
down the cone to a region of larger radius. One distant point drags the entire pass —
including the contact point — away from the part.

#### Why it looks like "only *some* passes"

On a **cylinder** the same code merely clamps, which is defensible behaviour for a
floor:

| Clearance typed | 0.5 | 1.0 | 2.0 | 3.0 | 5.0 |
|---|---|---|---|---|---|
| Gap held (cylinder, floor 2.0) | 2.01 | 2.01 | 2.01 | 2.88 | 4.88 |

Below the floor it clamps; above the floor it works normally. So the failure appears on
**cones, shoulders and tapers and not on straight walls** — i.e. on some passes of a
program and not others. That is exactly the pattern the operator reports.

#### Why no screen shows it

- The pass table's Clearance column shows the **commanded** value (`compute_pass_rows`
  reads `op["clearance"]`). It shows 2.0 while the machine runs 21.0.
- "Why is my pass weird?" (`recipe_explain.audit_operations`) checks *where a value came
  from*. This value came from the operation field, correctly. The audit has nothing to
  complain about.
- The achieved gap is only visible through the analysis-line overlay
  (`show_analysis_lines`, `main.py:1395`), which is **off by default** and has no entry
  in `load_settings` defaults at all.
- The engine **computes the exact explaining number** — `_total_shift` at
  `path_generator.py:3117` — formats it into a log sentence
  (`"P2 X: 40.04 → 61.04 (clearance shift +21.00mm)"`), and **discards it**. It is never
  assigned to a field, never returned, never surfaced. It exists only in
  `spinning_cam.log`, which the operator never opens.

So the program knows the answer, writes it down, and throws it away.

---

### F2 — The follow-blank reach has **no upper bound**  ⛔ SEVERITY: HIGH

**This is the direct explanation for Complaint A.**

#### What happens

With *Follow blank edge* enabled, the pass length is taken from
`process_planner.estimate_flange_reach` and then converted from a flat overhang to a
slant length by `flange_slant_length` (`path_generator.py:1300-1360`).

The area maths is correct, but the solution behaves like

```
L → fr + fr² / (2·r_contact)      as the exit direction approaches axial
```

so it **diverges as the contact radius shrinks**. There is a *lower* guard
(`reach_follow_min`, default 10 mm, plus a fallback for `target_z <= min_z`). There is
**no upper guard and no warning of any kind.**

#### Measured evidence

Operation Reach field set to **60 mm**, contact at a radius of 13 mm, blank radius
190 mm, follow-blank on:

| Pass angle | 0° | 30° | 60° | 85° | 95° |
|---|---|---|---|---|---|
| Reach the engine actually commands | **1057.6 mm** | 210.2 | 164.0 | 153.8 | 153.8 |

At a 0° pass angle the commanded exit point lands at **Z = −1057 mm**. The operator
typed 60.

Standalone view of the same divergence (flat overhang 80 mm; `dx` = 1.0 is a flat
radial exit, 0.0 is fully axial):

| contact radius \ exit | dx=1.0 | dx=0.4 | dx=0.2 | dx=0.0 |
|---|---|---|---|---|
| 150 mm | 80.0 | 90.4 | 95.3 | 101.3 |
| 60 mm | 80.0 | 100.0 | 112.3 | 133.3 |
| 25 mm | 80.0 | 110.4 | 135.0 | 208.0 |
| 8 mm | 80.0 | 120.0 | 160.0 | **480.0** |

#### One thing that is *not* broken

The pass-table mirror (`ui/dialogs/pass_table.py:227-244`) **is** in parity with the
engine here — it applies the same slant conversion and the same lower guard. So the pass
table does display the huge number honestly. This is not a mirror-drift bug like the one
fixed on 2026-07-28. The model itself is unbounded, and the operator is simply never
told that the number he typed was replaced.

---

### F3 — The **Conformal Clearance** checkbox displays the wrong state  ⚠ SEVERITY: MEDIUM

#### What happens

Everything that *computes* resolves the per-op flag with a fallback to the global
setting:

```python
op.get("conformal_clearance_operation_specific",
       params.get("conformal_clearance_all_operations", False))
```

- `path_generator.py:1467` (the engine)
- `main.py:516` (the angled-clearance advisory)
- `ui/dialogs/pass_table.py:101` (the pass-table mirror)

Everything that *displays* uses a hard `False`:

- `ui/tabs/program_tab.py:2958` — the checkbox itself
- `ui/tabs/program_tab.py:3499` and `:3694` — both pass-diagram previews

#### Consequences

1. With the global *Conformal Path – Rough* switched on, an untouched operation runs
   conformal in the engine while its checkbox shows **empty**, and the pass diagram
   draws the **non**-conformal shape. The picture disagrees with the machine.
2. Worse: ticking that checkbox on and off writes an explicit `False` into the
   operation. That explicit `False` now defeats the global fallback, so the pass
   **switches from normal-projected to pure radial placement** — a real change in
   standoff on any sloped surface. The checkbox looks identical before and after, and
   nothing is reported.

This is a second, independent way for "I touched something and the clearance behaviour
changed / didn't change and I can't see why" to happen.

---

### F4 — Two warning channels are written and never read  ⚠ SEVERITY: MEDIUM

`last_back_pass_ignored` and `last_kinematic_warnings` are populated by the engine and
have **zero consumers anywhere outside `path_generator.py`** (verified repo-wide, tests
and `backup/` excluded).

The comment above `last_back_pass_ignored` (`path_generator.py:1684`) literally reads
*"Reported rather than dropped in silence"* — and the report goes nowhere but the log.
So a back pass the operator explicitly enabled is silently not built.

`last_kinematic_warnings` carries tilt-arm (ID112) reachability problems, i.e. angles
that were clamped because the machine cannot reach them.

*Partial mitigation, for accuracy:* the back-pass-on-a-reverse-pass case **is**
separately covered by the static audit as `rx_f_bp_reverse`, so an operator who opens
"Why is my pass weird?" would see that one. The kinematic warnings are not covered
anywhere.

This repeats a lesson already recorded from the `#100` research: **adding a `last_*`
list is not the job — wiring its reader is.** The ten other channels do have readers in
`ui/main_window.py`; these two were missed.

---

### F5 — Cross-cutting: the existing diagnostic tools cannot see this class of bug

This is the most important structural point in the report, and I would ask the reader to
weigh it before choosing fixes.

The program already has a strong diagnostic suite — the pass table with per-field
provenance, "Why is my pass weird?", "Compare two passes", `explain.py`. All of them
answer the same question:

> **"Where did this number come from?"** — operation field, progressive ramp, pass pin,
> follow-blank, staged edit.

That machinery is well built and it works. But **F1 and F2 are not that question.** In
both, the provenance is perfectly ordinary and correct: the operator typed a value in
the operation field, and every tool faithfully reports "this came from the operation
setting." The value is then **overridden downstream by the engine** — by the safety
shift in F1, by the unbounded flange model in F2.

There is currently **no tool that answers the second question**:

> **"Is the number that was resolved actually the number the machine will run?"**

That gap is structural, not cosmetic. Adding more tooltips and info boxes to the
existing screens cannot close it, which is consistent with the observation that none of
the previous UI additions helped this particular complaint.

---

## 3. Proposals

Ordered by value per unit of risk. Every proposal follows the project's standing rules:
**advisory first, behaviour changes opt-in behind a flag, defaults bit-identical to
today.**

### P1 — Report the commanded-vs-achieved clearance gap  ✅ zero toolpath risk — DO THIS FIRST

Directly closes F1 and F5 for the most damaging case.

1. In `_create_and_store_pass`, keep the number that is currently thrown away.
   `_total_shift` already exists at `path_generator.py:3117`. Also compute the gap
   actually achieved **at the contact point** (not the minimum over the pass — the
   minimum is the constraint, the contact point is what the operator cares about).
2. Record a new engine channel, e.g. `last_clearance_shift_warnings`, with
   `{op_name, pass_name, commanded, achieved, shift, binding_z}`, gated by a report
   threshold in the style of the existing `TAIL_SHIFT_REPORT_MM = 1.0`.
3. **Wire the reader in the same change** (this is the F4 lesson). Follow the existing
   calm-note pattern — `refresh_retract_motion_status` in `ui/main_window.py` is the
   model to copy. **No modal popup.**
4. Word it as one number an operator can act on, per the shop-UX rule. Suggested
   phrasing, to be translated EN/TR/ES:
   > *"Roughing 3: you asked for 2.0 mm clearance, the pass is running at 21.0 mm. The
   > approach arm at Z = 12 is what is holding it out."*

   Naming the **binding Z** is the part that turns a mystery into a five-second fix, and
   it is the piece no current screen provides.
5. Add the same check to `recipe_explain.audit_operations` as a new severity-`warn`
   finding so it appears in "Why is my pass weird?" and in the headless `explain.py`
   output. That also makes it visible for customer `.ssp` files sent in by e-mail.

Also worth surfacing in the pass table: show the achieved gap next to the commanded one
when they differ. That single column would have made this complaint self-diagnosing.

### P2 — Bound the follow-blank reach  ✅ warning risk-free; cap opt-in

Closes F2.

1. **Always-on advisory (no behaviour change):** when the follow-blank result exceeds
   the operation's own Reach by a large factor, or exceeds the machine's workspace X
   travel, record it and show it through the same calm-note channel as P1.
2. **Opt-in cap:** a new per-op field `reach_follow_max`, unset by default so existing
   programs are bit-identical. When set, the follow-blank reach is clamped to it and the
   clamp is reported.
3. **Also evaluate** clamping the direction term `dx` to a sensible minimum inside
   `flange_slant_length`, since the divergence is entirely the `dx → 0` cylinder limit.
   This is a **model change** and must be behind its own flag with a field test — the
   present maths is not *wrong*, it is unbounded, and I have not verified which
   behaviour the real sheet follows. Do not ship this one on theory alone.
4. Mirror any change into `ui/dialogs/pass_table.py:227-244`, which is the hand-kept
   mirror of this exact block. **Do not skip this** — the 2026-07-28 incident (table
   showing 9.8 mm while the machine ran 39 mm) came from missing precisely this step.

### P3 — Fix the conformal checkbox  ✅ display-only, no toolpath change

Closes F3. Small and unambiguous.

1. Change the three UI read sites (`program_tab.py:2958`, `:3499`, `:3694`) to use the
   **same fallback expression the engine uses**. Best done as one shared helper so a
   fourth site cannot drift again — the project already uses this "one source of truth"
   pattern for `resolve_retract_motion`, `resolve_speed_mode` and friends.
2. When an operation has no explicit value, show that the state is inherited — e.g. a
   *"(from global setting)"* note beside the checkbox — so the operator can see the
   difference between "off" and "not set".
3. Decide deliberately what the first click writes. Today it silently writes `False` and
   changes the toolpath. It should write the value the user actually sees themselves
   toggling away from.

### P4 — Wire the two orphan warning channels  ✅ zero risk

Closes F4. `last_back_pass_ignored` and `last_kinematic_warnings` get readers in
`ui/main_window.py` alongside the ten existing ones.

Worth adding a cheap guard so this cannot recur: a test that walks
`PathGenerator`'s `last_*_warnings` / `last_*_ignored` attributes and asserts each one is
referenced somewhere under `ui/`. That converts a recurring class of mistake into a
failing test.

### P5 — The structural one: an "is this what will actually run?" check

Follows from F5, and is the answer to the original goal of the session.

The existing tools explain **provenance**. What is missing is a check of
**commanded vs. delivered**, run automatically after every calculation, comparing what
each pass was told to do against what the built toolpath actually does — clearance,
reach, contact Z — and reporting only the passes where the two disagree beyond a
threshold.

P1 and P2 are the first two entries of exactly that check. I would suggest building them
in that shape from the start, rather than as two one-off warnings, so the pattern is
established and cheap to extend.

**Note on the shop-floor UX rule:** the operator is not a technical user. The output of
this check should be *one sentence naming one pass and one number*, on the status line —
never a list, never a modal.

---

## 4. Suggested order

| # | Item | Risk | Why here |
|---|---|---|---|
| 1 | **P1** — clearance commanded vs achieved | none (advisory) | Explains the most damaging complaint; a pass that cuts nothing is scrap plus wasted cycle time |
| 2 | **P3** — conformal checkbox | none (display) | Small, self-contained, removes a live source of silent toolpath change |
| 3 | **P4** — wire orphan warnings + the guard test | none | Cheap, prevents recurrence |
| 4 | **P2.1** — follow-blank advisory | none (advisory) | Explains the big-reach screenshots |
| 5 | **P2.2** — opt-in reach cap | low (opt-in) | Needs a shop decision on what the cap should be |
| 6 | **P2.3** — bound the flange model | **medium** | Needs a real field test first. Do not ship on theory |
| 7 | **P5** — generalise into one check | low | Once 1 and 4 exist, this is mostly refactoring |

**Standing project rules that apply to all of the above:** update the `_C` dictionary in
`help_window.py` for any UI change; add EN/TR/ES strings for every new message in
`i18n.py`; keep `ui/dialogs/pass_table.py:compute_pass_rows` in sync with any engine
resolution change; and ask about the version bump (`version.py`, `changelog.py`,
`LAST_CHANGES.md`) at the end of the session.

---

## 5. What this report does **not** establish

Stated plainly so nobody builds on top of an assumption I did not test.

- **Whether F1 fires on the shop's real programs.** It was reproduced on a synthetic
  cone with a deliberately long approach arm. The mechanism (exact cancellation) is
  algebraic and holds generally, but *how often* it bites on the actual `.ssp` files in
  use is unmeasured. **This is the first thing to check**, and it is cheap: run the
  operator's real programs and log every pass where the safety shift is non-zero. If the
  shift is large on real work, F1 is the whole story and P1 is urgent.
- **Whether the unbounded flange length in F2 is physically wrong.** The area
  equivalence is internally consistent. Whether a real sheet behaves that way at a small
  contact radius is a shop question, not a code question. The *reporting* fix is safe
  either way; the *model* fix is not.
- **The correct fix for F1's root cause.** I am proposing to *report* it, not to change
  it. Two candidate behaviour fixes exist and neither was tested: (a) exclude the
  approach arm from the floor check, since it is a positioning move, not a forming move;
  (b) use the already-implemented per-point normal correction
  (`params["clearance_correction_per_point"]`, `path_generator.py:3042`), which pushes
  only the violating points instead of shifting the whole pass and would preserve the
  contact-point clearance. Option (b) is attractive because the code already exists —
  but it changes toolpaths and needs its own evaluation and flag.
- **Anything about ID112 / tilt-arm behaviour** beyond noting that its reachability
  warnings have no reader. The pivot geometry is still a placeholder pending machine
  drawings.

---

## Appendix A — Reproduction

Both scripts are self-contained, headless, and need no `.ssp` or STEP file. Run them in
the **activated** env (see the environment note in §1 — calling the env's `python.exe`
by absolute path crashes on any LAPACK call with exit 127 and no traceback):

```
call C:\Users\PC\anaconda3\Scripts\activate.bat spinning_cam
python <script>
```

**A1 — F1, clearance cancelled on a taper.** Builds one `linear_approach` roughing pass
against a cone (r = 50 mm at Z=0 falling to 8 mm), `min_safety_gap = 0.0`, and sweeps the
operation's clearance from 0.5 to 8.0 mm, printing the gap actually held at the contact
point. Expected output: the same `21.000` on every row.

**A2 — F1, the cylinder contrast.** Same harness on a cylinder, floor 0.0 and 2.0,
showing the clamp-then-work pattern that makes the fault look intermittent.

**A3 — F2, unbounded reach.** One pass with `reach_follow_blank` on, operation Reach
60 mm, contact radius 13 mm, blank radius 190 mm; sweeps the pass angle and reads the
commanded reach out of the `[PARAM_DEBUG2]` log line. Expected: `reach=1057.632` at 0°.

**A4 — F2, the pure maths.** Calls `process_planner.flange_slant_length` directly across
a grid of contact radius × exit direction. No engine involved; four lines of code.

The scripts live in the session scratchpad
(`...\scratchpad\_proof_silent.py`, `_proof2.py`, `_proof3.py`). They are throwaway
diagnostics and were deliberately **not** added to the repository, in line with the
project's commit-hygiene rule.

---

## Appendix B — Code locations referenced

| Finding | File | Location |
|---|---|---|
| F1 safety-floor shift | `path_generator.py` | `3050-3080` (uniform shift), `3042` (per-point alternative) |
| F1 discarded number | `path_generator.py` | `3117` (`_total_shift`) |
| F1 commanded value shown in table | `ui/dialogs/pass_table.py` | `compute_pass_rows` clearance column |
| F1 achieved gap overlay (off by default) | `main.py` | `1395` (`show_analysis_lines`) |
| F2 follow-blank block | `path_generator.py` | `1300-1360` |
| F2 flange maths | `process_planner.py` | `estimate_flange_reach` `235`, `flange_slant_length` `273` |
| F2 mirror (keep in sync) | `ui/dialogs/pass_table.py` | `227-244` |
| F3 engine + mirrors (correct) | `path_generator.py` `1467`, `main.py` `516`, `pass_table.py` `101` | — |
| F3 UI (wrong) | `ui/tabs/program_tab.py` | `2958`, `3499`, `3694` |
| F4 orphan channels | `path_generator.py` | `1687` (`last_back_pass_ignored`), `3868`/`4007` (`last_kinematic_warnings`) |
| F4 reader pattern to copy | `ui/main_window.py` | `refresh_retract_motion_status` |
| Audit to extend | `recipe_explain.py` | `audit_operations` |
