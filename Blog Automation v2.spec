# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

pyqt5_datas, pyqt5_binaries, pyqt5_hiddenimports = collect_all('PyQt5')

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
    ],
    hiddenimports=pyqt5_hiddenimports + ['playwright', 'requests', 'anthropic'],
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
    name='Blog Automation v2',
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
    name='Blog Automation v2',
)
app = BUNDLE(
    coll,
    name='Blog Automation v2.app',
    icon=None,
    bundle_identifier=None,
)
