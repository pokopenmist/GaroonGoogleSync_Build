# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['garoon_google_sync_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 実行時に読み込まれないモジュール（サイズ削減）。
    # cryptography は google.auth.crypt が必須importしているため除外不可。
    excludes=['googleapiclient', 'httplib2', 'google.api_core',
              'setuptools', 'pkg_resources', 'distutils', 'packaging',
              'multiprocessing', 'unittest', 'pydoc', 'pydoc_data'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GaroonGoogleSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    upx=False,
    upx_exclude=[],
    name='GaroonGoogleSync',
)
