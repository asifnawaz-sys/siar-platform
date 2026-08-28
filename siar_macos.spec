# PyInstaller spec file for SIAR Digital Platform - macOS
# Build command (on macOS): pyinstaller siar_macos.spec

block_cipher = None

a = Analysis(
    ['launcher_pywebview.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Source Code/backend', 'backend'),
        ('Source Code/frontend', 'frontend'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'flask', 'flask_cors', 'sqlalchemy', 'pillow', 'cv2',
        'requests', 'jwt', 'webview', 'pywebview',
        'werkzeug', 'jinja2', 'markupsafe',
        'sqlalchemy.dialects.sqlite',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SIAR Digital Platform',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='SIAR Digital Platform.app',
    icon=None,
    bundle_identifier='com.siardigital.platform',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'NSSupportsAutomaticGraphicsSwitching': True,
    },
)
