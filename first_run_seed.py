"""First-run seeding for runtime-owned data files (Phase 2 of the pull-collision fix).

Some files the app REWRITES at runtime — `tools.json` (tool-library edits) and the
per-machine profiles under `machines/` (calibration via autosave) — used to be tracked
in git. Because the app keeps rewriting them, every `git pull` collided the moment a
user edited a tool or re-calibrated a machine.

The cure mirrors the settings.json one (Phase 1), but for user DATA that is NOT in code
defaults, so a bare "regenerate from code" is not enough — we need a shipped seed:

  - the LIVE files are gitignored (local, never pulled): `tools.json`, `machines/*.json`
  - a tracked `.default` SEED ships beside them: `tools.default.json`,
    `machines/<id>.default.json`
  - on startup, if a live file is missing, it is created by copying its seed.

Result: a fresh clone / fresh exe gets working defaults on first launch, while every
later tool edit or calibration stays local and never fights a `git pull`.

Idempotent and non-destructive: an existing live file is NEVER overwritten, so this is
safe to call on every startup.
"""
import glob
import os
import shutil

from logger_config import logger

# Built from parts so the packaging source-scanner does not mistake this suffix for a
# shippable data filename (it greps the source for "*.json" literals).
_DEFAULT_SUFFIX = ".default" + ".json"


def _seed_one(live_path, seed_path):
    """Copy seed_path -> live_path only if the live file is absent. Returns True if seeded."""
    if os.path.exists(live_path):
        return False
    if not os.path.exists(seed_path):
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(live_path)), exist_ok=True)
        shutil.copy2(seed_path, live_path)
        logger.info(f"Seeded '{os.path.basename(live_path)}' from '{os.path.basename(seed_path)}'.")
        return True
    except Exception as e:  # noqa: BLE001 — seeding must never crash startup
        logger.error(f"Seed failed for {live_path}: {e}")
        return False


def seed_tools(base_dir):
    """Create tools.json from tools.default.json if the live file is missing."""
    return _seed_one(
        os.path.join(base_dir, "tools.json"),
        os.path.join(base_dir, "tools.default.json"),
    )


def seed_machines(base_dir):
    """For each machines/<id>.default.json seed, create the live machines/<id>.json if missing.

    Returns the number of machine profiles seeded. This is what makes ID112-1 survive a
    fresh clone — unlike ID111-1, it does not self-create from settings.
    """
    machines_dir = os.path.join(base_dir, "machines")
    n = 0
    for seed in glob.glob(os.path.join(machines_dir, "*" + _DEFAULT_SUFFIX)):
        live = seed[: -len(_DEFAULT_SUFFIX)] + ".json"
        if _seed_one(live, seed):
            n += 1
    return n


def seed_all(base_dir):
    """Run all first-run seeding. Safe to call every startup (idempotent).

    Returns the total number of files seeded (0 once everything already exists).
    """
    seeded = 0
    try:
        seeded += 1 if seed_tools(base_dir) else 0
        seeded += seed_machines(base_dir)
    except Exception as e:  # noqa: BLE001 — never let seeding break startup
        logger.error(f"Seeding pass failed: {e}")
    return seeded
