import PyInstaller.__main__
import os
import shutil
import time

# Auto-Kill existing process to prevent PermissionError
print("Ensuring previous instances are closed...")
os.system("taskkill /f /im EMS_SoftSpinner.exe >nul 2>&1")
time.sleep(1) # Wait for release

print("Starting Build Process for EMS SoftSpinner...")

# Define paths
base_path = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(base_path, "assets", "logo.jpg")

# Verify logo
if not os.path.exists(logo_path):
    print("WARNING: Logo not found at assets/logo.jpg. Build will continue but logo may be missing.")
else:
    print(f"Logo found: {logo_path}")

# PyInstaller Arguments
args = [
    'main_tk.py',                  # Entry Point
    '--name=EMS_SoftSpinner',      # Executable Name
    '--onefile',                   # Single EXE
    '--noconsole',                 # No Terminal Window
    '--clean',                     # Clean Cache
    '--add-data=assets/logo.jpg;assets', # Embed Logo
    
    # Critical Dependencies
    '--collect-all=pyvista',       # Collect all PyVista modules/data
    '--collect-all=OCC',           # Collect all PythonOCC modules/DLLs
    '--collect-all=PIL',           # Pillow
    
    # Hidden Imports (Manual safety)
    '--hidden-import=vtk',
    '--hidden-import=tkinter',
    '--hidden-import=numpy',
    '--hidden-import=logging',
    '--hidden-import=json',
    
    # Exclude conflicting Qt bindings (Fix for multiple Qt error)
    '--exclude-module=PySide6',
    '--exclude-module=PySide2',
    '--exclude-module=PyQt5',
]

print("Running PyInstaller... This may take a few minutes.")
try:
    PyInstaller.__main__.run(args)
    print("\n------------------------------------------------")
    print("BUILD SUCCESSFUL!")
    print("Executable is located in the 'dist' folder: dist/EMS_SoftSpinner.exe")
    print("------------------------------------------------\n")
except Exception as e:
    print(f"BUILD FAILED: {e}")
