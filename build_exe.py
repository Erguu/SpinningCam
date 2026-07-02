import PyInstaller.__main__
import os
import time

# Kill any running instances to prevent PermissionError
print("Killing existing SpinningCam instances...")
os.system("taskkill /f /im SpinningCam.exe >nul 2>&1")
time.sleep(1)

print("Starting Build Process for SpinningCam...")

base_path = os.path.dirname(os.path.abspath(__file__))
sep = os.pathsep  # ';' on Windows

# Data files/folders to bundle into the exe folder
data_files = [
    f"settings.json{sep}.",
    f"tools.json{sep}.",
    f"images{sep}images",
]

args = [
    "main_tk.py",              # Entry point (what SpinningCam.bat runs)
    "--name=SpinningCam",      # Executable name
    "--onedir",                # Folder mode — reliable with heavy libs like OCC and PyVista
    "--noconsole",             # No terminal window
    "--clean",                 # Clean PyInstaller cache before build

    # Bundle data files
    *[f"--add-data={d}" for d in data_files],

    # Collect ALL modules, DLLs, and data for heavy packages
    "--collect-all=pyvista",
    "--collect-all=vtkmodules",
    "--collect-all=OCC",
    "--collect-all=PIL",
    "--collect-all=fpdf",
    "--collect-all=pydantic",
    "--collect-all=pydantic_core",

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

    # ui/ package and all submodules (PyInstaller won't auto-discover these)
    "--hidden-import=ui",
    "--hidden-import=ui.main_window",
    "--hidden-import=ui.helpers_ui",
    "--hidden-import=ui.tabs",
    "--hidden-import=ui.tabs.machine_tab",
    "--hidden-import=ui.tabs.process_tab",
    "--hidden-import=ui.tabs.program_tab",
    "--hidden-import=ui.tabs.scrollable_tab_base",
    "--hidden-import=ui.dialogs",
    "--hidden-import=ui.dialogs.tool_manager",
    "--hidden-import=ui.dialogs.zone_manager",
    "--hidden-import=ui.dialogs.machine_selector",
    "--hidden-import=ui.dialogs.license_generator",
    "--hidden-import=license_manager",
    "--hidden-import=machine_info",
    "--hidden-import=hmac",
    "--hidden-import=hashlib",
    "--hidden-import=uuid",
    "--hidden-import=winreg",

    # Exclude Qt bindings — not used in the Tkinter UI stack
    "--exclude-module=PySide6",
    "--exclude-module=PySide2",
    "--exclude-module=PyQt5",
    "--exclude-module=PyQt6",
    "--exclude-module=qtpy",
    "--exclude-module=pyvistaqt",
]

print("Running PyInstaller... This will take several minutes.")
print("Output will be in: dist/SpinningCam/\n")

try:
    PyInstaller.__main__.run(args)
    print("\n" + "=" * 55)
    print("BUILD SUCCESSFUL!")
    print("Folder: dist/SpinningCam/")
    print("Run:    dist/SpinningCam/SpinningCam.exe")
    print("=" * 55)
except Exception as e:
    print(f"\nBUILD FAILED: {e}")
