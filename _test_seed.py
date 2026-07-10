"""Headless tests for first_run_seed (Phase 2 pull-collision fix).

Verifies: seeds create missing live files, existing live files are never overwritten,
seeding is idempotent, and ID112-1 (which does NOT self-create) is restored from its seed.
"""
import json
import os
import shutil
import tempfile

import first_run_seed as S


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_seeds_create_missing_live():
    base = tempfile.mkdtemp()
    try:
        _write(os.path.join(base, "tools.default.json"), [{"id": "T0101"}])
        _write(os.path.join(base, "machines", "ID111-1.default.json"), {"machine_id": "ID111-1"})
        _write(os.path.join(base, "machines", "ID112-1.default.json"), {"machine_id": "ID112-1"})

        n = S.seed_all(base)
        assert n == 3, f"expected 3 seeded, got {n}"
        assert _read(os.path.join(base, "tools.json"))[0]["id"] == "T0101"
        assert _read(os.path.join(base, "machines", "ID111-1.json"))["machine_id"] == "ID111-1"
        # The whole point: ID112-1 comes back from its seed on a fresh clone.
        assert _read(os.path.join(base, "machines", "ID112-1.json"))["machine_id"] == "ID112-1"
        print("PASS: seeds create missing live files (incl. ID112-1)")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_does_not_overwrite_existing_live():
    base = tempfile.mkdtemp()
    try:
        _write(os.path.join(base, "tools.default.json"), [{"id": "SEED"}])
        _write(os.path.join(base, "tools.json"), [{"id": "MY_EDIT"}])          # user's edited live file
        _write(os.path.join(base, "machines", "ID112-1.default.json"), {"machine_id": "SEED"})
        _write(os.path.join(base, "machines", "ID112-1.json"), {"machine_id": "MY_CAL"})  # user calibration

        n = S.seed_all(base)
        assert n == 0, f"expected 0 seeded (all live present), got {n}"
        assert _read(os.path.join(base, "tools.json"))[0]["id"] == "MY_EDIT", "live tools.json was clobbered!"
        assert _read(os.path.join(base, "machines", "ID112-1.json"))["machine_id"] == "MY_CAL", "live machine clobbered!"
        print("PASS: existing live files are never overwritten")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_idempotent():
    base = tempfile.mkdtemp()
    try:
        _write(os.path.join(base, "tools.default.json"), [{"id": "T"}])
        assert S.seed_all(base) == 1
        assert S.seed_all(base) == 0, "second run should seed nothing"
        print("PASS: seeding is idempotent")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_machine_loader_ignores_seeds():
    """Regression: list_machine_profiles must skip <id>.default.json seeds, else every
    machine_id is loaded twice (live + seed) and the machine-selector tree crashes with
    'Item ID111-1 already exists'."""
    import machine_loader
    base = tempfile.mkdtemp()
    try:
        S.seed_all  # ensure module import order is fine
        _write(os.path.join(base, "machines", "ID111-1.default.json"), {"machine_id": "ID111-1"})
        _write(os.path.join(base, "machines", "ID111-1.json"), {"machine_id": "ID111-1"})
        _write(os.path.join(base, "machines", "ID112-1.default.json"), {"machine_id": "ID112-1"})
        _write(os.path.join(base, "machines", "ID112-1.json"), {"machine_id": "ID112-1"})

        profs = machine_loader.list_machine_profiles(base)
        ids = [p["machine_id"] for p in profs]
        assert ids == ["ID111-1", "ID112-1"], f"expected 2 unique live profiles, got {ids}"
        assert not any(p["_path"].endswith(".default.json") for p in profs), "a seed leaked into profiles"
        print("PASS: list_machine_profiles ignores .default.json seeds (no duplicate machine_id)")
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    test_seeds_create_missing_live()
    test_does_not_overwrite_existing_live()
    test_idempotent()
    test_machine_loader_ignores_seeds()
    print("\nAll seed tests passed.")
