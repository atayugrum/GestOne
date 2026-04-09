# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('mediapipe')

hiddenimports = [
    'Quartz',
    'AppKit',
    'mediapipe.python.solutions',
    'mediapipe.python.solutions.drawing_styles',
    'mediapipe.python.solutions.drawing_utils',
    'mediapipe.python.solutions.face_mesh',
    'mediapipe.python.solutions.face_mesh_connections',
    'mediapipe.python.solutions.hands',
    'mediapipe.python.solutions.hands_connections',
    'mediapipe.python.solutions.pose',
    'mediapipe.python.solutions.pose_connections',
]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='GestOne',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=['GestOne_Logo.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GestOne',
)
app = BUNDLE(
    coll,
    name='GestOne.app',
    icon='GestOne_Logo.icns',
    bundle_identifier='com.gestone.macapp',
    info_plist={
        'NSCameraUsageDescription': 'GestOne uses the camera for gesture and head tracking.',
        'NSMicrophoneUsageDescription': 'GestOne uses the microphone for voice commands.',
        'NSAppleEventsUsageDescription': 'GestOne el hareketleriyle fareyi kontrol etmek için bu izne ihtiyaç duyar.',
        'LSUIElement': True,
    },
)
