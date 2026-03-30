# -*- mode: python ; coding: utf-8 -*-
"""
avtoroved.spec — PyInstaller spec для сборки Автороведческого анализатора.

Сборка:
    pip install pyinstaller
    pyinstaller avtoroved.spec

Результат: dist/avtoroved/ (папка) или dist/avtoroved.exe (one-file, медленнее).

ПРИМЕЧАНИЕ: Stanza-модели (русский, ~500MB) скачиваются при первом запуске
программой автоматически. В .exe они НЕ включены — это нормально.
"""
import os, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPEC))

# ─── Данные (папки со словарями, моделями и настройками) ─────────────────────
datas = [
    # Словари и данные программы
    (os.path.join(ROOT, 'data'),     'data'),
    # PyQt6 ресурсы (иконки, шрифты)
    *collect_data_files('PyQt6'),
    # pymorphy3 словари
    *collect_data_files('pymorphy3'),
    *collect_data_files('pymorphy3_dicts_ru'),
    # Stanza ресурсы (кроме моделей — они загружаются отдельно)
    *collect_data_files('stanza', includes=['**/*.json', '**/*.txt']),
]

# ─── Скрытые импорты (модули, которые PyInstaller не видит) ──────────────────
hiddenimports = [
    'analyzer.stanza_backend',
    'analyzer.spacy_backend',
    'analyzer.metrics',
    'analyzer.errors',
    'analyzer.freq_engine',
    'analyzer.senti_engine',
    'analyzer.stratification_engine',
    'analyzer.thematic_engine',
    'analyzer.yandex_speller',
    'analyzer.lt_checker',
    'analyzer.corpus_manager',
    'analyzer.learning_backend',
    'analyzer.export',
    'analyzer.cache_manager',
    'analyzer.config',
    # UI
    'ui.main_window',
    'ui.tabs.morphology_tab',
    'ui.tabs.statistics_tab',
    'ui.tabs.errors_tab',
    'ui.tabs.stratification_tab',
    'ui.tabs.thematic_tab',
    'ui.tabs.nkrya_tab',
    'ui.tabs.senti_tab',
    'ui.tabs.internet_tab',
    'ui.tabs.comparison_tab',
    'ui.tabs.gigacheck_tab',
    'ui.tabs.grammar_query_tab',
    'ui.tabs.report_tab',
    'ui.tabs.learning_tab',
    'ui.dialogs.lexicon_viewer',
    # Тяжёлые зависимости
    *collect_submodules('stanza'),
    *collect_submodules('pymorphy3'),
    *collect_submodules('torch'),
    'sklearn',
    'sklearn.utils._cython_blas',
    'gensim',
    'docx',
    'diskcache',
    'requests',
    'charset_normalizer',
    'certifi',
]

# ─── Exclusions (что НЕ включать — уменьшает размер) ─────────────────────────
excludes = [
    'tkinter', 'test', 'unittest',
    'IPython', 'jupyter', 'notebook',
    'matplotlib.tests', 'numpy.tests',
    'PIL.ImageTk',
]

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name='avtoroved',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # Без консольного окна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # Поставьте путь к .ico если есть
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='avtoroved',
)
