"""Single source of truth for what a shipped SpinningCam.exe must contain.

Read by three places so "a correct build" has ONE definition:
  - build_exe.py            → bundles data and places it NEXT TO the exe
  - check_packaging.py      → verifies a build (statically + post-build)
  - main_tk.py --selfcheck  → proves the frozen exe is complete at runtime

WHY next-to-the-exe: the app resolves data files with
``get_base_path() == os.path.dirname(sys.executable)`` when frozen. PyInstaller's
``--add-data`` drops files into the ``_internal`` subfolder, which the app never
reads. So shipped data must be copied beside the exe, not just bundled.

MAINTENANCE RULE: when you add a feature that reads a NEW data file beside the
exe, add it to SHIP_NEXT_TO_EXE. If you add a module that is only imported
lazily (inside a function) and is critical, add it to CRITICAL_MODULES.
check_packaging.py will WARN when it finds a runtime file read in the source
that is not covered here, so a forgotten file cannot stay silent.
"""

# ── Files/dirs that MUST sit next to the exe ────────────────────────────────────
# Relative to the project root (dev) / exe folder (frozen). Dirs are copied whole.
# `optional=True` → shipped if present, but its absence is not a build failure.
SHIP_NEXT_TO_EXE = [
    ("settings.json",  False),  # seed defaults; customer-editable afterwards
    ("tools.json",     False),  # seed tool library; customer-editable afterwards
    ("tool_geometry",  True),   # tool STEP files, ID-named (T0103.STEP); portable geometry
    ("materials.json", False),  # process-planner heuristics (self-creates, ship a copy)
    ("machines",       False),  # machine profiles: ID111-1 self-creates, ID112-1 does NOT
    ("logo.png",       True),   # window/splash logo (optional)
    ("logo.ico",       True),   # window icon (optional)
]

# ── Files that must NEVER ship ──────────────────────────────────────────────────
# Listed so the post-build check can FAIL LOUDLY if any leaked into dist/.
MUST_NOT_SHIP = [
    "license_private_key.pem",  # EMS Ed25519 signing key — leaking it breaks all licensing
    "admin.lic",                # dev/admin bootstrap license
]

# ── Files intentionally NOT shipped (per-customer / generated at runtime) ────────
# Listed so the source scanner does not flag them as "forgotten to ship".
NOT_SHIPPED = [
    "license.lic",       # per-customer, browsed at startup
    "layout.json",       # window layout, regenerated at runtime, optional
    "spinning_cam.log",  # runtime log
    "spinning_output.nc",# generated g-code output
    "ops_library.json",  # user's operation library (#71), created at runtime
]

# ── Modules that MUST be importable in the frozen exe ───────────────────────────
# Feature code is normally auto-discovered by PyInstaller (all imports are static),
# but listing the critical/recent ones makes --selfcheck fail loudly if the bundle
# is ever incomplete — especially cryptography, which has compiled backends.
CRITICAL_MODULES = [
    "cryptography.hazmat.primitives.asymmetric.ed25519",  # license verification backend
    "license_manager",
    "machine_adapter",
    "machine_loader",
    "kinematics",
    "process_planner",
    "tool_step_loader",
    "path_generator",
    "recipe_to_scl",
    "export_manager",
    "gui_manager",
    "ui.main_window",
    "ui.dialogs.machine_selector",
    "ui.dialogs.op_suggester",
    "ui.dialogs.view_customizer",
    "ui.dialogs.touch_calibration",
    "ui.dialogs.help_window",
    "ops_library",                    # op library core (#71), lazily imported
    "ui.dialogs.op_library_dialog",   # op library UI (#71), lazily imported
    "ui.dialogs.batch_edit_dialog",   # batch edit UI (#67), lazily imported
    "ui.dialogs.pass_table",          # per-pass table (#80/#79), lazily imported
]


def ship_base_path():
    """Folder the frozen app treats as its base — mirrors SpinningApp.get_base_path()."""
    import os
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def run_selfcheck():
    """Runtime completeness probe. Returns 0 if the exe is whole, 1 otherwise.

    Invoked as ``SpinningCam.exe --selfcheck`` (see main_tk.py). Proves, without
    opening the GUI, that: (1) every critical module imports, (2) the license
    crypto backend actually loads and can build the public key, and (3) every
    required data file is present beside the exe.
    """
    import importlib
    import os

    problems = []

    # 1. Critical modules import (proves the bundle is complete).
    for mod in CRITICAL_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001 — report, don't crash
            problems.append(f"MODULE  {mod}: {type(e).__name__}: {e}")

    # 2. License crypto backend genuinely works (not just importable).
    try:
        import license_manager
        license_manager._public_key()  # builds Ed25519 key → forces cryptography backend
    except Exception as e:  # noqa: BLE001
        problems.append(f"LICENSE public-key build failed: {type(e).__name__}: {e}")

    # 3. Required data files present beside the exe.
    base = ship_base_path()
    for name, optional in SHIP_NEXT_TO_EXE:
        path = os.path.join(base, name)
        if not os.path.exists(path):
            if optional:
                print(f"[selfcheck] note: optional '{name}' not present")
            else:
                problems.append(f"DATA    missing next to exe: {name}")

    if problems:
        print("SELFCHECK FAILED — the exe is incomplete:")
        for p in problems:
            print("  - " + p)
        return 1

    print("SELFCHECK OK — all critical modules, license crypto, and data files present.")
    return 0
