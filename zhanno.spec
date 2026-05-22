# -*- mode: python ; coding: utf-8 -*-
"""
湛诺财务系统 PyInstaller 打包配置
Mac:     pyinstaller zhanno.spec  →  dist/湛诺财务系统.app
Windows: 在 Windows 上执行同一命令  →  dist/湛诺财务系统.exe（目录模式）
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('static', 'static'),          # 前端资源（HTML / JS / CSS）
    ],
    hiddenimports=[
        # uvicorn 动态加载的模块
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # SQLAlchemy sqlite 方言
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.pysqlite',
        # 加密 / 认证
        'passlib.handlers.bcrypt',
        'jose',
        'jose.jwt',
        'jose.exceptions',
        'cryptography',
        'cryptography.fernet',
        # 其他
        'multipart',
        'dotenv',
        'reportlab',
        'pypdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='湛诺财务系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # 不显示终端窗口（用户直接看浏览器）
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
    name='湛诺财务系统',
)

# Mac 专属：生成 .app bundle
import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='湛诺财务系统.app',
        icon=None,
        bundle_identifier='com.zhanno.finance',
        info_plist={
            'CFBundleDisplayName': '湛诺财务系统',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleName': '湛诺财务系统',
            'NSHighResolutionCapable': True,
            'LSUIElement': False,
        },
    )
