# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Data files (assets, JSON configs)
datas = [
    ('settings.json', '.'),
    ('tools.json', '.'),
]
# Add logo if exists
import os
if os.path.exists('logo.png'):
    datas.append(('logo.png', '.'))
if os.path.exists('logo.ico'):
    datas.append(('logo.ico', '.'))
if os.path.exists('assets/logo.jpg'):
    datas.append(('assets/logo.jpg', 'assets'))

binaries = []
hiddenimports = [
    'vtk', 'tkinter', 'numpy', 'logging', 'json',
    'fpdf', 'pydantic',  # New dependencies
    'export_manager', 'config_schema', 'constants',  # New modules
]

# Collect all from major packages
tmp_ret = collect_all('pyvista')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('OCC')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fpdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main_tk.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PySide2', 'PyQt5'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EMS_SoftSpinner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
