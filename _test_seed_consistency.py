"""Clean-install invariant test (AGENT_MAINTENANCE_GUIDE.md §8).

Every STEP file that a shipped ``*.default.json`` seed references must be TRACKED
in git, so a fresh ``git clone`` finds it. Otherwise ``first_run_seed`` copies the
seed to a live ``tools.json`` that points at a missing STEP and the app breaks on
first launch.

This guards the exact drift that "leave my tools to me" allows: the user runs a
local tool set (e.g. T001–T005) that is not tracked, while the shipped seed still
references the tracked baseline (T0101–T0103). It stays green as long as the seed
and the tracked STEPs form a closed set; it fails the moment a seed is pointed at
an untracked/missing STEP.

Run: conda run -n spinning_cam python _test_seed_consistency.py
"""
import sys

from check_packaging import check_seed_step_consistency


def main():
    problems, warnings = check_seed_step_consistency()
    for w in warnings:
        print("WARN:", w)
    if problems:
        print("SEED <-> STEP CONSISTENCY FAILED:")
        for p in problems:
            print("  x", p)
        return 1
    print("seed <-> STEP consistency OK (every shipped seed's STEP is tracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
