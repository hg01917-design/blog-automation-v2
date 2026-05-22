# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

pyqt5_datas, pyqt5_binaries, pyqt5_hiddenimports = collect_all('PyQt5')

_ROOT = Path(globals().get("SPECPATH", ".")).resolve()
_VER_FILE = _ROOT / "build_version.txt"
_DEFAULT_MAJOR = 3

try:
    _current = int(_VER_FILE.read_text(encoding="utf-8").strip()) if _VER_FILE.exists() else _DEFAULT_MAJOR
except Exception:
    _current = _DEFAULT_MAJOR

APP_MAJOR = _current + 1
_VER_FILE.write_text(str(APP_MAJOR), encoding="utf-8")

APP_NAME = 'Blog Automation'
APP_SHORT_VERSION = f'{APP_MAJOR}.0.0'
APP_BUILD_VERSION = str(APP_MAJOR * 100)
BUNDLE_ID = 'com.hana.blogautomation'

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=pyqt5_binaries,
    datas=pyqt5_datas + [
        ('assets', 'assets'),
        ('agents', 'agents'),
        ('keyword_engine', 'keyword_engine'),
        ('config.py', '.'),
        ('notion_prompt.py', '.'),
        ('poster.py', '.'),
        ('browser.py', '.'),
        ('keyword_crawler.py', '.'),
        ('overnight_run.py', '.'),
        ('claude_playwright.py', '.'),
        ('content_builder.py', '.'),
        ('coupang_api.py', '.'),
        ('agoda_api.py', '.'),
        ('blog_stats.py', '.'),
        ('image_parser.py', '.'),
        ('gemini_image.py', '.'),
        ('login_playwright.py', '.'),
        ('blog_visitor.py', '.'),
        ('claude_direct.py', '.'),
        ('image_router.py', '.'),
        ('keyword_analyzer.py', '.'),
        ('tg_send.py', '.'),
        ('issue_card.py', '.'),
        ('cdp_utils.py', '.'),
        ('public_api.py', '.'),
    ],
    hiddenimports=pyqt5_hiddenimports + ['playwright', 'requests', 'anthropic', 'mrt_affiliate'],
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
app = BUNDLE(
    coll,
    name=f'{APP_NAME}.app',
    icon=None,
    bundle_identifier=BUNDLE_ID,
    info_plist={
        'CFBundleShortVersionString': APP_SHORT_VERSION,
        'CFBundleVersion': APP_BUILD_VERSION,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleName': APP_NAME,
        'CFBundleIdentifier': BUNDLE_ID,
    },
)
