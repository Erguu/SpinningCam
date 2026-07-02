import PyInstaller.__main__
import os
import time

print("Killing existing MachineInfo instances...")
os.system("taskkill /f /im EMS_MachineInfo.exe >nul 2>&1")
time.sleep(1)

print("Building EMS_MachineInfo.exe...")

args = [
    "machine_info.py",
    "--name=EMS_MachineInfo",
    "--onefile",        # Single .exe — stdlib only, no folder needed
    "--noconsole",
    "--clean",

    "--hidden-import=tkinter",
    "--hidden-import=tkinter.ttk",
    "--hidden-import=uuid",
    "--hidden-import=winreg",
    "--hidden-import=hashlib",

    "--exclude-module=PySide6",
    "--exclude-module=PySide2",
    "--exclude-module=PyQt5",
    "--exclude-module=PyQt6",
    "--exclude-module=numpy",
    "--exclude-module=pyvista",
    "--exclude-module=OCC",
]

try:
    PyInstaller.__main__.run(args)
    print("\n" + "=" * 55)
    print("BUILD SUCCESSFUL!")
    print("File: dist/EMS_MachineInfo.exe")
    print("Send to customer to get their MAC / GUID / fingerprint.")
    print("=" * 55)
except Exception as e:
    print(f"\nBUILD FAILED: {e}")
