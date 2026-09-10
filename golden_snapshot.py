# -*- coding: utf-8 -*-
"""Regenerate a saved program headlessly and describe what came out.

WHY GOLDEN SNAPSHOTS

Every other test in this repo asks "does this feature behave as specified".
None of them asks "did anything change that I did not mean to change". On an
engine where one op's geometry feeds the next pass's index, that second question
is the one that catches the expensive mistakes — and the only honest way to ask
it is to run REAL programs and compare against what they produced last time.

WHAT IS COMPARED

Not the raw G-code. A digest:

    a sha256 of the whole normalised .nc and of the recipe   (catches ANY change)
    per-path: point count, first point, last point, bounding box
    counts: toolpaths, .nc lines, recipe motion lines

The hashes make the test sensitive to everything; the per-path rows make a
failure READABLE — when path 14 moves you can see it moved, and which operation
it belongs to, without storing a megabyte of customer toolpath in git. To see
the exact coordinate change, regenerate locally with --write-full.

WHY IT DOES NOT USE SpinningApp.load_project

`load_project` needs the pyvista plotter (it ends in `update_scene`) and it
deliberately does NOT apply the file's machine settings — the machine in front
of the operator wins, which is correct for the UI and fatal for a snapshot: the
baseline would depend on whatever the Machine tab happens to hold today.

So this reads the file directly and uses the file's OWN params for everything.
A snapshot then depends on exactly two things: the frozen fixture and the
engine. The UI's machine-conflict policy is a separate question with its own
test (`_test_project_machine_params.py`).

FIXTURES ARE FROZEN COPIES, NOT THE LIVE FILES

The programs in the shop folder are working files — one of them was edited an
hour before this module was written. Pointing a snapshot at a file somebody is
still editing produces failures that mean nothing, which is how a suite stops
being read. `import_fixtures` takes copies; the snapshot records the copy's
sha256 so a fixture that changes cannot silently move the baseline.
"""
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DIR = os.path.join(HERE, "golden")
FIXTURE_DIR = os.path.join(GOLDEN_DIR, "fixtures")
SNAPSHOT_DIR = os.path.join(GOLDEN_DIR, "snapshots")

# Coordinates are rounded before hashing. The engine is deterministic on one
# machine, but a snapshot that changes on the last float bit would be a tripwire
# rather than a test. 4 decimals is a tenth of a micron — far below anything a
# spinning lathe can act on, and far above float noise.
ROUND = 4


def sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:32]


def normalise(txt):
    """Drop the generation timestamp. Two runs a second apart are not a change."""
    return "\n".join(l for l in txt.splitlines()
                     if not l.strip().startswith("(Generated:"))


def file_sha(path):
    with open(path, "rb") as f:
        return sha(f.read())


# ── loading ───────────────────────────────────────────────────────────────

def load_program(path):
    """(params, overrides, step_path) from a .ssp, migrations applied.

    The migrations are the ones `load_project` runs (main.py ~2295). Without
    them an older fixture is measured through a code path the app never uses.
    """
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    params = d.get("params", {}) or {}
    overrides = {int(k): v for k, v in (d.get("overrides", {}) or {}).items()}
    step = d.get("step", "") or ""

    from config_schema import (migrate_bend_points, migrate_clearance,
                               migrate_cylinder_mcode, migrate_pass_retract)
    for fn in (migrate_clearance, migrate_pass_retract,
               migrate_cylinder_mcode, migrate_bend_points):
        try:
            fn(params)
        except Exception:
            pass
    return params, overrides, step


def resolve_step(step, extra_dirs=()):
    """Find the mandrel model.

    The path inside a .ssp is absolute and belongs to whichever machine saved
    it, so it is matched by BASENAME against the fixture folder first. A
    snapshot must not depend on a path outside the repo.
    """
    base = os.path.basename(step or "")
    if not base:
        return None
    for d in (FIXTURE_DIR,) + tuple(extra_dirs) + (HERE,):
        cand = os.path.join(d, base)
        if os.path.isfile(cand):
            return cand
    if step and os.path.isfile(step):
        return step
    return None


def build_mandrel(params, step_path):
    from mandrel_analyzer import MandrelManager
    mgr = MandrelManager()
    loaded = bool(step_path) and bool(mgr.load_step(step_path))
    if not loaded:
        mgr.create_default_cone()
    mgr.update_geometry(
        float(params.get("mandrel_rot_x", 0.0) or 0.0),
        float(params.get("mandrel_rot_y", 0.0) or 0.0),
        float(params.get("mandrel_rot_z", 0.0) or 0.0),
        float(params.get("mandrel_pos_x_offset", 0.0) or 0.0),
        float(params.get("mandrel_pos_z_offset", 0.0) or 0.0))
    return mgr, loaded


# ── the digest ────────────────────────────────────────────────────────────

def _path_rows(paths):
    """One readable row per toolpath. This is what makes a failure locatable."""
    rows = []
    for i, p in enumerate(paths or []):
        try:
            import numpy as np
            a = np.asarray(p, dtype=float)
            if a.ndim != 2 or a.shape[0] == 0:
                rows.append({"i": i, "n": 0})
                continue
            rows.append({
                "i": i,
                "n": int(a.shape[0]),
                "first": [round(float(v), ROUND) for v in a[0]],
                "last": [round(float(v), ROUND) for v in a[-1]],
                "min": [round(float(v), ROUND) for v in a.min(axis=0)],
                "max": [round(float(v), ROUND) for v in a.max(axis=0)],
            })
        except Exception as e:                               # pragma: no cover
            rows.append({"i": i, "error": repr(e)[:80]})
    return rows


def snapshot(ssp_path, extra_step_dirs=(), full=None):
    """Regenerate `ssp_path` and return its digest dict.

    `full`, if given, is a directory to drop the complete .nc and recipe into —
    for looking at a failure locally. Never part of the snapshot.
    """
    from path_generator import PathGenerator

    params, overrides, step = load_program(ssp_path)
    step_path = resolve_step(step, extra_step_dirs)
    mgr, step_loaded = build_mandrel(params, step_path)

    pg = PathGenerator()
    pg.calculate_paths(params, overrides, mgr)

    nc_params = dict(params)
    nc_params["plc_mode"] = False      # the .nc is always full resolution
    nc = normalise(pg.generate_gcode(params=nc_params))
    rec = normalise(pg.generate_gcode(params=params, for_recipe=True))

    if full:
        os.makedirs(full, exist_ok=True)
        stem = os.path.splitext(os.path.basename(ssp_path))[0]
        for name, txt in ((stem + ".nc", nc), (stem + ".recipe.nc", rec)):
            with open(os.path.join(full, name), "w", encoding="utf-8") as f:
                f.write(txt)

    rec_motion = [l for l in rec.splitlines()
                  if l.strip() and not l.strip().startswith("(")]
    ops = params.get("operations", []) or []
    return {
        "fixture": os.path.basename(ssp_path),
        "fixture_sha": file_sha(ssp_path),
        "step": os.path.basename(step or "") or None,
        "step_loaded": step_loaded,
        "machine_id": params.get("machine_id"),
        "ops_total": len(ops),
        "ops_enabled": sum(1 for o in ops if o.get("enabled", True)),
        "paths": len(pg.last_calculated_paths or []),
        "nc_lines": len(nc.splitlines()),
        "nc_sha": sha(nc),
        "recipe_motion_lines": len(rec_motion),
        "recipe_sha": sha(rec),
        "path_rows": _path_rows(pg.last_calculated_paths),
    }


# ── fixture and snapshot management ───────────────────────────────────────

def fixture_key(name):
    """A filesystem-safe snapshot name. Fixtures have Turkish names and spaces;
    the snapshot file must not depend on the filesystem's encoding."""
    stem = os.path.splitext(name)[0]
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem)
    return safe.strip("_").lower() or "program"


def fixtures():
    if not os.path.isdir(FIXTURE_DIR):
        return []
    return sorted(os.path.join(FIXTURE_DIR, f)
                  for f in os.listdir(FIXTURE_DIR)
                  if f.lower().endswith(".ssp"))


def snapshot_path(ssp_path):
    return os.path.join(SNAPSHOT_DIR, fixture_key(os.path.basename(ssp_path)) + ".json")


def read_snapshot(ssp_path):
    p = snapshot_path(ssp_path)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_snapshot(ssp_path, data):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    p = snapshot_path(ssp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
    return p


def import_fixtures(src_dir, also_step=True):
    """Copy .ssp files (and the mandrels they name) into golden/fixtures.

    Copies rather than references: the shop folder holds working files, and a
    baseline that moves when somebody edits their program is not a baseline.
    """
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    copied, steps = [], set()
    for fn in sorted(os.listdir(src_dir)):
        if not fn.lower().endswith(".ssp"):
            continue
        src = os.path.join(src_dir, fn)
        shutil.copy2(src, os.path.join(FIXTURE_DIR, fn))
        copied.append(fn)
        if also_step:
            try:
                _, _, step = load_program(src)
            except Exception:
                continue
            base = os.path.basename(step or "")
            if not base or base in steps:
                continue
            found = resolve_step(step, (src_dir,))
            if found and os.path.dirname(found) != FIXTURE_DIR:
                shutil.copy2(found, os.path.join(FIXTURE_DIR, base))
                steps.add(base)
    return copied, sorted(steps)


def compare(old, new):
    """Human-readable differences. [] means identical."""
    if old is None:
        return ["no snapshot on record"]
    out = []
    for key in ("fixture_sha", "step", "step_loaded", "machine_id",
                "ops_total", "ops_enabled", "paths",
                "nc_lines", "nc_sha", "recipe_motion_lines", "recipe_sha"):
        a, b = old.get(key), new.get(key)
        if a != b:
            out.append("%-20s %r -> %r" % (key, a, b))

    o_rows = {r["i"]: r for r in old.get("path_rows", [])}
    n_rows = {r["i"]: r for r in new.get("path_rows", [])}
    for i in sorted(set(o_rows) | set(n_rows)):
        a, b = o_rows.get(i), n_rows.get(i)
        if a == b:
            continue
        if a is None:
            out.append("path %-3d ADDED   %s" % (i, b))
        elif b is None:
            out.append("path %-3d REMOVED %s" % (i, a))
        else:
            bits = ["%s %s->%s" % (k, a.get(k), b.get(k))
                    for k in ("n", "first", "last", "min", "max")
                    if a.get(k) != b.get(k)]
            out.append("path %-3d %s" % (i, "; ".join(bits)))
    return out


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--import-from", metavar="DIR",
                    help="copy .ssp fixtures (and their mandrels) from DIR")
    ap.add_argument("--accept", action="store_true",
                    help="regenerate and OVERWRITE the snapshots (review the diff first)")
    ap.add_argument("--write-full", metavar="DIR",
                    help="also write the complete .nc and recipe there, for eyeballing")
    ap.add_argument("--step-dir", action="append", default=[],
                    help="extra folder to look for mandrel STEP files in")
    args = ap.parse_args(argv)

    if args.import_from:
        copied, steps = import_fixtures(args.import_from)
        print("imported %d program(s) into %s" % (len(copied), FIXTURE_DIR))
        for c in copied:
            print("   " + c)
        for s in steps:
            print("   [mandrel] " + s)
        if not args.accept:
            return 0

    fx = fixtures()
    if not fx:
        print("No fixtures in %s — run with --import-from DIR" % FIXTURE_DIR)
        return 1

    rc = 0
    for path in fx:
        name = os.path.basename(path)
        try:
            new = snapshot(path, tuple(args.step_dir), full=args.write_full)
        except Exception as e:
            print("%-36s RAISED %r" % (name, e))
            rc = 1
            continue
        old = read_snapshot(path)
        diffs = compare(old, new)
        if args.accept:
            write_snapshot(path, new)
            print("%-36s snapshot written (%d path(s), %d nc lines)"
                  % (name, new["paths"], new["nc_lines"]))
            for d in diffs[:10]:
                print("      was: " + d)
        elif diffs:
            print("%-36s CHANGED" % name)
            for d in diffs[:20]:
                print("      " + d)
            rc = 1
        else:
            print("%-36s ok (%d paths, %d nc lines)"
                  % (name, new["paths"], new["nc_lines"]))
    return rc


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
