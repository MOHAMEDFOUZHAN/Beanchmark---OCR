# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('DejaVuSans.ttf', '.'),
    ('DejaVuSans-Bold.ttf', '.')
]
datas += collect_data_files('rapidocr_onnxruntime')
datas += collect_data_files('pypdfium2')
datas += collect_data_files('pypdfium2_raw')
datas += collect_data_files('onnxruntime')

binaries = []
binaries += collect_dynamic_libs('pypdfium2_raw')
binaries += collect_dynamic_libs('onnxruntime')

hiddenimports = [
    'backup_manager',
    'smart_report_mailer',
    'ocr_invoice_parser',
    'rapidocr_onnxruntime',
    'rapidocr_onnxruntime.rapid_ocr_api',
    'rapidocr_onnxruntime.utils',
    'rapidocr_onnxruntime.ch_ppocr_v3_det',
    'rapidocr_onnxruntime.ch_ppocr_v3_det.text_detect',
    'rapidocr_onnxruntime.ch_ppocr_v3_det.utils',
    'rapidocr_onnxruntime.ch_ppocr_v3_rec',
    'rapidocr_onnxruntime.ch_ppocr_v3_rec.text_recognize',
    'rapidocr_onnxruntime.ch_ppocr_v3_rec.utils',
    'rapidocr_onnxruntime.ch_ppocr_v2_cls',
    'rapidocr_onnxruntime.ch_ppocr_v2_cls.text_cls',
    'rapidocr_onnxruntime.ch_ppocr_v2_cls.utils',
    'ch_ppocr_v3_det',
    'ch_ppocr_v3_rec',
    'ch_ppocr_v2_cls',
    'pypdfium2',
    'pypdfium2_raw',
    'onnxruntime',
    'cv2',
    'numpy',
    'PIL',
    'PIL.Image',
    'waitress',
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'sqlite3',
    'openpyxl',
    'difflib',
    're',
    'json',
    'io',
    'datetime',
    'threading'
]
hiddenimports += collect_submodules('rapidocr_onnxruntime')

a = Analysis(
    ['MMS.py'],
    pathex=[],
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MMS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static\\images\\logo.ico'],
)
