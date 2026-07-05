import PyInstaller.__main__
import os
import shutil
import subprocess
import sys
import time

import packaging_manifest as M

# Kill any running instances to prevent PermissionError
print("Killing existing SpinningCam instances...")
os.system("taskkill /f /im SpinningCam.exe >nul 2>&1")
time.sleep(1)

print("Starting Build Process for SpinningCam...")

base_path = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(base_path, "dist", "SpinningCam")

# NOTE: app data (settings.json, tools.json, machines/, materials.json, logo.*)
# is NOT passed to --add-data. The app reads it from get_base_path() == the exe
# folder, but --add-data lands files in _internal/ which the app never reads.
# Instead we COPY the packaging manifest next to the exe after the build (below).
# Single source of truth for that list: packaging_manifest.SHIP_NEXT_TO_EXE.

args = [
    "main_tk.py",              # Entry point (what SpinningCam.bat runs)
    "--name=SpinningCam",      # Executable name
    "--onedir",                # Folder mode — reliable with heavy libs like OCC and PyVista
    "--noconsole",             # No terminal window
    "--clean",                 # Clean PyInstaller cache before build

    # Collect ALL modules, DLLs, and data for heavy packages
    "--collect-all=pyvista",
    "--collect-all=vtkmodules",
    "--collect-all=OCC",
    "--collect-all=PIL",
    "--collect-all=fpdf",
    "--collect-all=pydantic",
    "--collect-all=pydantic_core",
    "--collect-all=cryptography",   # Ed25519 license verification — compiled backend

    # Hidden imports PyInstaller may miss
    "--hidden-import=tkinter",
    "--hidden-import=tkinter.ttk",
    "--hidden-import=tkinter.messagebox",
    "--hidden-import=tkinter.filedialog",
    "--hidden-import=tkinter.simpledialog",
    "--hidden-import=numpy",
    "--hidden-import=logging",
    "--hidden-import=json",
    "--hidden-import=fpdf",
    "--hidden-import=pydantic",

    # Exclude Qt bindings — not used in the Tkinter UI stack
    "--exclude-module=PySide6",
    "--exclude-module=PySide2",
    "--exclude-module=PyQt5",
    "--exclude-module=PyQt6",
    "--exclude-module=qtpy",
    "--exclude-module=pyvistaqt",
]

# Critical modules from the manifest, added as hidden-imports (belt-and-suspenders;
# most are auto-discovered, but this keeps the builder honest as features are added).
for mod in M.CRITICAL_MODULES:
    if not mod.startswith("cryptography"):  # already collected in full above
        args.append(f"--hidden-import={mod}")

print("Running PyInstaller... This will take several minutes.")
print("Output will be in: dist/SpinningCam/\n")

try:
    PyInstaller.__main__.run(args)
except Exception as e:
    print(f"\nBUILD FAILED: {e}")
    sys.exit(1)

# ── Copy the packaging manifest NEXT TO the exe (where the app actually looks) ──
print("\nCopying shipped data files next to the exe...")
for name, optional in M.SHIP_NEXT_TO_EXE:
    src = os.path.join(base_path, name)
    dst = os.path.join(dist_dir, name)
    if not os.path.exists(src):
        print(f"  - skip (optional, not present): {name}" if optional
              else f"  ! WARNING: required '{name}' not found in project — build will be incomplete")
        continue
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    print(f"  + {name}")

# ── Verify the build matches the app (static + post-build + exe --selfcheck) ──
print("\nRunning packaging check...")
check = subprocess.run(
    [sys.executable, os.path.join(base_path, "check_packaging.py"), "--post-build", dist_dir]
)

print("\n" + "=" * 55)
if check.returncode == 0:
    print("BUILD SUCCESSFUL and VERIFIED!")
    print("Folder: dist/SpinningCam/")
    print("Run:    dist/SpinningCam/SpinningCam.exe")
else:
    print("BUILD COMPLETED but PACKAGING CHECK FAILED (see above).")
    print("The exe may be incomplete — fix before shipping.")
print("=" * 55)
sys.exit(check.returncode)
