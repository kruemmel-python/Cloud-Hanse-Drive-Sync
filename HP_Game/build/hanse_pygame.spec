# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parent

datas = [
    (str(project_root / "images"), "images"),
    (str(project_root / "Hanse_Atheria.ogg"), "."),
    (str(project_root / "Hanse_Atheria.opus"), "."),
    (str(project_root / "SPIELHANDBUCH.html"), "."),
    (str(project_root / "SPIELANLEITUNG.html"), "."),
]


a = Analysis(
    [str(project_root / "main_pygame.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["pygame"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Hanse_Atheria",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Hanse_Atheria",
)
