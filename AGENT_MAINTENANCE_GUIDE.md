# Agent Maintenance Guide — SpinningCam

Purpose: let a maintenance agent improve **stability, performance, bugs, and structure**
**token-efficiently**. Read this first, then work surgically. Do NOT read the whole codebase.

---

## 0. Token budget rules (follow these)

1. **Read the reference docs before any `.py`** (they're a topic→file:line map, not code):
   - `CODE_NAVIGATION.md` — the master "topic → file:line" index. **Always start here.**
   - `TODO.md` — backlog + known issues (numbered items #NN).
   - `LAST_CHANGES.md` — newest-first change log with *why* and *what's pending*.
   - `backup/HANDOVER_*.md` — deep session notes; read only the one matching your task.
   - `memory/MEMORY.md` (auto-memory index) — project facts, gotchas, decisions.
   - `CAM_INTERFACE_SPEC.md` — SCL/PLC recipe format & constraints (only for export work).
2. **Use `Grep`/`Glob`, not full-file reads.** Read only the function/region you'll change.
3. **Don't re-derive what a doc already states.** Cite `file.py:line` and move on.
4. **One concern per change.** Small diffs, each headless-verified.
5. **Never dump large files into context** (main.py ~1600 lines, path_generator ~2100,
   program_tab ~2700). Grep for the symbol, read ±40 lines.

---

## 1. Environment & running/testing (CRITICAL — get this right first)

- **Conda env `spinning_cam`** has the heavy deps (pythonocc/OCC, pyvista/VTK, cryptography,
  fpdf). **System Python fails imports.** Conda path (this machine):
  `C:\Users\PC\anaconda3\Scripts\conda.exe`.
- **Run headless tests via:** `conda run -n spinning_cam python _test_xxx.py`.
- ⚠️ **Never call the env's `python.exe` directly** (un-activated) → MKL BLAS delay-load crash
  `0xc06d007f` masquerading as a numpy crash. Always `conda run -n spinning_cam ...`.
- **Pure-syntax checks don't need the env:** `python -c "import ast,io; ast.parse(io.open('f.py',encoding='utf-8').read())"`
  (system Python is fine for `ast.parse`; files are UTF-8 with non-ASCII — pass `encoding='utf-8'`).
- **The GUI cannot be tested by the agent** (no display; VTK interactive widgets don't work
  headless). Anything GUI-only must be handed to the user for a smoke test. Flag it clearly.
- **Existing headless tests** (run them as regressions after engine changes):
  `_test_reach.py`, `_test_reach_foldback.py`, `_test_progressive_reach.py`, `_test_real_end_z.py`,
  `_test_flange_reach.py`, `_test_surface_angle.py`, `_test_reach_follow.py`, `_test_deformed_blank.py`,
  `_test_clamp_zone.py`, `_test_split.py`, `_test_continue.py`, `_test_planner*.py`, `test_headless.py`.

---

## 2. Architecture map (one line each — grep the file for detail)

| File | Responsibility |
|------|----------------|
| `main.py` | `SpinningApp`: params dict, pyvista `Plotter`, `update_scene`/`_update_scene_impl` (all 3D rendering), settings load/save, roller/scene actors. Entry `run()`. |
| `path_generator.py` | `PathGenerator.calculate_paths` — the toolpath ENGINE. Per-op/per-pass loop; reach/angle/clearance math; `_create_and_store_pass` (control points `[P1,P2,P3]`). `effective_clamp_length`. |
| `process_planner.py` | Non-UI models: `analyze_profile`, `estimate_flange_reach`, `estimate_surface_angle`, `suggest_operations`. |
| `mandrel_analyzer.py` | `MandrelManager`: STEP load, `update_geometry`, profile scan, `get_radius_fast(z)`, `get_normal_at_z(z)`, `generate_shell_mesh`, `props` (min_z/top_z/br). |
| `ui/main_window.py` | Tk window, startup sequence, menus, `check_sim_loop` (sim polling on main thread), STEP auto-load, changelog. |
| `ui/tabs/program_tab.py` | Operation editor: toolbar, ops tree, property editor (`on_op_select`), `refresh_pass_info`, per-op helper buttons, `_start_async_calc`. Big file. |
| `ui/tabs/process_tab.py`, `machine_tab.py` | Process/machine settings tabs. |
| `simulation_controller.py` | Background-thread sim playback (`current_pos`, `current_pass_idx`); main thread renders via `check_sim_loop`. |
| `kinematics.py` | ID112 tilt-arm (B axis) forward/inverse kinematics. |
| `license_manager.py`, `ui/dialogs/machine_selector.py`, `machine_info.py` | Ed25519 licensing + machine binding. |
| `machine_loader.py` | Machine profiles (`machines/*.json`), `MACHINE_PROFILE_KEYS`. |
| `export_manager.py`, `recipe_to_scl.py`, `gcode_to_recipe.py` | G-code/SCL/recipe export. |
| `i18n.py` | Translations (EN/TR/ES); all UI strings go through `t("key")`. |
| `config_schema.py` | pydantic settings validation + `migrate_clearance`. |
| `version.py`, `changelog.py` | Version single-source + startup changelog. |
| `packaging_manifest.py`, `check_packaging.py`, `build_exe.py` | Exe build drift-protection (single recipe). |

---

## 3. Known gotchas & fragile areas (learned the hard way — respect these)

- **Rendering is batched.** `update_scene` sets `plotter.suppress_rendering=True`, calls
  `_update_scene_impl` (which touches many actors), then renders **once**. Don't add
  `add_mesh`/`remove_actor` calls that force intermediate renders. `update_type` gates which
  blocks run: `"all"`, `"paths"`, `"visual"`, `"shell"`, `"camera"`, etc. — put new actors in
  the block matching when they should refresh.
- **VTK interactive widgets are unreliable here** and a proven time-sink. A drag-edit
  (`add_sphere_widget`) feature was built and **fully reverted** — see TODO #61 "ATTEMPTED &
  REMOVED". Avoid free 3D-drag widgets; prefer numeric fields / point-picking if revisited.
- **`settings.json` is RUNTIME STATE**, continuously rewritten by the running app. Editing it
  on disk while the app runs is futile (app overwrites from memory). It also holds personal
  paths + session state → **do not commit it**. Defaults live in `main.py` `_load_settings`.
- **`app_version` is forced from `version.py`** after settings load AND excluded from the
  customer-settings merge in `_load_machine_profile`. Version = build constant, never from a file.
- **`update_geometry` must be called after `load_step`** or `get_radius_fast` measures a stale/
  default cone (documented gotcha). Mandrel `props`: `min_z`, `top_z`, `br` (base radius).
- **Reach/angle/clearance coupling** (the subtle engine area — read `LAST_CHANGES` 2026-07-05b):
  - `pass_angle` is relative to the approach direction θ_A (linear approach → −90°); `θ_B = θ_A + pass_angle`.
  - When `reach` is set, the exit is anchored clearance-independent (`p3_x -= clearance`) with a
    fold-back/overlap guard. Changing this ripples into End Angle/Reach, fold-back, and overlap.
  - `estimate_flange_reach` is RADIAL v1 (tangent deferred); `blank_radius` is a RADIUS (a
    diameter-in-radius-field bug bit once — there's a guard in `compute_reach_from_blank`).
- **Two different "overrides":** `gui_pass_overrides` (arg to `calculate_paths`, pre-existing,
  keep) vs the removed drag-edit `op["pass_overrides"]` (now ignored — stale data is harmless).
- **i18n:** every user-facing string uses `t("key")`; add keys to `i18n.py` in EN/TR/ES.
- **Help window policy:** update `help_window.py` `_C` dict on any UI/feature change (per memory).
- **Passive ops are skipped everywhere** (`enabled=False`) — cheap; don't "optimize" by special-casing.

---

## 4. Stability / performance / bug hotspots (candidate work — verify current state first)

Grep + `CODE_NAVIGATION.md` before starting any of these; some may already be addressed.

- **`update_scene` cost**: it's the hot path (runs on every edit/pass-step/calc). Look for
  redundant actor rebuilds, per-point Python loops (`_create_sweeping_pass`, projections),
  repeated `get_radius_fast` calls. Prior wins: single-render batching, grid-bounds cache,
  console `UnicodeEncodeError` flood removed (`logger_config`). Profile before changing.
- **Synchronous calc on the Process tab** (noted opt-in-pending in older handovers): the
  Program tab uses `_start_async_calc` (background thread); confirm the Process-tab "Calculate"
  isn't still blocking the UI thread.
- **`path_generator.calculate_paths`** is long and branchy (spline/linear/adaptive/sweeping,
  back-pass interleave, clearance correction loop `~:1183`). High bug surface — change with a
  headless test proving byte-identical output for the unaffected branches.
- **Exception-swallowing**: many `try/except: pass` around rendering. Good for robustness but
  can hide bugs; when chasing a bug, temporarily log the swallowed exception.
- **Thread-safety**: sim runs on a bg thread setting `current_*`; only the main thread (Tk
  `check_sim_loop`) may touch the plotter/actors. Never render from the sim thread.
- **Float/bool serialization**: `on_param_change` historically coerced bools→float (fixed
  once, code-review #43) — watch for regressions when adding params.
- **Licensing** (`license_manager.py`): audited (L1–L6); L5 (clock rollback) deliberately
  deferred. Don't "fix" L5 without asking. Never weaken Ed25519 verification.
- **Packaging**: `check_packaging.py` source-scan warns if a runtime data file isn't in
  `SHIP_NEXT_TO_EXE`. Add new runtime data files there. Never ship `*.pem`/`*.lic`.

---

## 5. Working conventions (match these)

- **Opt-in, risk-free flags.** New behavior that touches toolpaths must default OFF / be a
  labeled estimate; never silently change existing programs. (User's stated preference.)
- **Verify, don't claim.** Run headless tests; if GUI-only, say "GUI smoke pending".
- **Physical-risk features** (reach/`r_tool`, flange reach, tilt angle) can GOUGE — gate them,
  keep guards (`r_tool < radius` refused), and flag "physical validation pending".
- **After a change:** update `LAST_CHANGES.md` (newest on top: what/why/how-verified/pending),
  relevant `TODO.md` item, and `CODE_NAVIGATION.md` if you moved/added a subsystem.
- **Commit discipline:** never stage `settings.json`, `__pycache__`, `dist/`, `build/`, `*.pem`,
  `*.lic` (all gitignored except settings.json which is tracked but should stay unstaged).
  End commit messages with the Co-Authored-By trailer. **Full policy (what ships vs. stays
  local, and the tool-library clean-install invariant): see §8.**

---

## 6. Definition of done (per change)

1. Syntax OK (`ast.parse`) for every edited file.
2. Relevant headless test(s) pass in `spinning_cam` env; add a test for new engine logic.
3. Unaffected toolpath branches proven unchanged (regression) when touching `path_generator`.
4. i18n keys added (EN/TR/ES) for any new UI string; help window updated if UI/feature changed.
5. `LAST_CHANGES.md` + `TODO.md` updated; GUI-only parts flagged "smoke pending".
6. No secrets/artifacts staged.

---

## 7. Do NOT touch without explicit user approval

- Ed25519 licensing verification logic, private key flow, or L5 rollback.
- The single exe build recipe (`build_exe.py`) invariants (see `project_packaging` memory).
- Toolpath math semantics that change existing programs' output, unless behind an opt-in flag.
- `settings.json` on disk while the app is running.
- Re-attempting VTK free-drag widgets (proven unstable) without a different interaction model.

---

## 8. Git & tool-library policy (what ships, what stays local)

Single source of truth for "what to commit / what to leave out." `.gitignore` enforces the
hard cases automatically; this section covers the judgment calls it cannot.

### The clean-install invariant (do not break)
A fresh `git clone` must be able to run. So **every STEP file a shipped `*.default.json` seed
references must be TRACKED in git.** The tool library ships as a *baseline*: the tracked
`tool_geometry/*.STEP` files + the tracked seeds (`tools.default.json`, `machines/*.default.json`)
must always reference each other. `first_run_seed.py` copies a `*.default.json` seed → live file
on first launch, so a seed that points at an untracked/missing STEP crashes first run.

Enforced by `check_seed_step_consistency()` in `check_packaging.py` (also part of
`python check_packaging.py`), and by the standalone `_test_seed_consistency.py`. Run it after any
tool-library or seed change.

### Always commit
- All source code and its `_test_*.py` (tests are tracked — `_test_` is a test, not scratch).
- Docs: `LAST_CHANGES.md`, `changelog.py`, `CODE_NAVIGATION.md`, `TODO.md`, this guide, specs.
- The shipping tool baseline: tracked `tool_geometry/*.STEP` **and** the `*.default.json` seeds
  that reference them — advanced *together*, never one without the other.

### Never commit (default — even though some are git-tracked)
- Secrets/artifacts: `*.pem`, `*.lic`, `__pycache__/`, `build/`, `dist/`, `*.log` (gitignored).
- Per-user runtime state that collides on pull: `settings.json`, live `tools.json`,
  live `machines/*.json` (gitignored; the `*.default.json` seeds ship instead).
- Personal work products: root-level CAD (`/*.STEP`, `/*.stp`, `*.ssp` — gitignored).
- **The user's local tool-library churn.** `tool_geometry/*.STEP` is *tracked*, so git surfaces
  the user's local tool swaps (renames/deletes/adds) as pending. Do **NOT** push these by default
  — the user manages their own tools and shares them via the app's zip Export/Import, not git.
  Leave those deltas unstaged unless the user explicitly says "include my tools" (see below).
- Scratch: `_diag_*.py`, `_research_*.py`, one-off `PROPOSAL_*.md` (unless the user asks to keep it).

### "Include my tools" — advancing the shipping baseline (explicit opt-in only)
When the user says to promote their current library to what ships, do it atomically in ONE commit:
1. `git add tool_geometry/<new ids>.STEP` and stage any tracked-STEP deletions.
2. Regenerate the seed so `tools.default.json` references exactly the STEPs you just staged
   (ids, `step_file` paths, `r_tool`/radius, rotations).
3. Run `_test_seed_consistency.py` — it must pass (proves the seed ⇄ STEP set is closed).
4. Only then commit. Never ship a seed edit without its STEPs, or STEPs without updating the seed.
