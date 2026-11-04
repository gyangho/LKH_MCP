# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/native_uiux.py'],
    pathex=['src', 'vendor/ui-ux-pro-max-skill/src/ui-ux-pro-max/scripts'],
    binaries=[],
    datas=[('vendor/ui-ux-pro-max-skill', 'vendor/ui-ux-pro-max-skill')],
    hiddenimports=['win32timezone', 'core', 'design_system', 'reasoning_contract'],
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
    name='LKH-MCP-UIUX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LKH-MCP-UIUX',
)
