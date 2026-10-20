# -*- mode: python ; coding: utf-8 -*-
"""Build dell'eseguibile di Forge Custom Card Importer.

Nota importante: le DLL del runtime MSVC (msvcp140*, vcruntime140*)
raccolte da PyInstaller nel bundle sono piu' vecchie di quelle di sistema e
fanno crashare onnxruntime (access violation al caricamento di
onnxruntime_pybind11_state.pyd). Vengono quindi escluse dal bundle, cosi'
il processo usa quelle installate in System32.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for package in ("customtkinter", "rapidocr_onnxruntime", "onnxruntime"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Sotto-moduli importati in modo differito dal launcher.
hiddenimports += [
    "forge_importer.gui",
    "forge_importer.generator",
    "forge_importer.carddb",
    "forge_importer.matcher",
    "forge_importer.ocr",
    "forge_importer.paths",
    "forge_importer.textutil",
]

_MSVC_DLLS = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "concrt140.dll",
}

a = Analysis(
    [str(Path(SPECPATH) / "main.py")],
    pathex=[str(Path(SPECPATH))],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.binaries = [x for x in a.binaries if Path(x[0]).name.lower() not in _MSVC_DLLS]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ForgeCustomImporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
