# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['AICcode.py'],
    pathex=[],
    binaries=[],
    datas=[d for d in [
        ('Vector logo.png', '.') if os.path.exists('Vector logo.png') else None,
        ('app_icon.ico', '.') if os.path.exists('app_icon.ico') else None,
    ] if d is not None],
    hiddenimports=[
        'tinvest.data_loader',
        'tinvest.analyzer',
        'tinvest.storage_manager',
        'tinvest.vietstock_client',
        'tinvest.config_manager',
        'tinvest.ichimoku_engine',
        'tinvest.vsa_engine',
        'tinvest.advanced_entry',
        'tinvest.accumulation_engine',
        'tinvest.ma_engine',
        'tinvest.valuation_engine',
        'tinvest.mcdx_engine',
        'tinvest.heatmap_engine',
        'tinvest.heikin_engine',
        'tinvest.greenpink_engine',
        'tinvest.octopus_engine',
        'tinvest.state_engine',
        'tinvest.portfolio_engine',
        'tinvest.token_refresher',
        'tinvest.market_engine',
        'matplotlib.offsetbox',
        'matplotlib.image',
        'matplotlib.lines',
        'matplotlib.ticker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIC PRO 2.0',
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
    icon='app_icon.ico' if os.path.exists('app_icon.ico') else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AIC PRO 2.0',
)
