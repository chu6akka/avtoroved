# -*- mode: python ; coding: utf-8 -*-
"""
avtoroved.spec — PyInstaller spec для сборки Автороведческого анализатора.

Сборка:
    pip install pyinstaller
    pyinstaller avtoroved.spec
Результат: dist/avtoroved/ (папка-дистрибутив, запускать avtoroved.exe).

НЕ включено в сборку (скачивается при первом использовании, интернет нужен один раз):
  • модели Stanza (~500 МБ) — в кэш пользователя;
  • сервер LanguageTool (~250 МБ) — требует Java 8+ на машине;
  • модель GigaCheck (transformers) — в кэш HuggingFace.
Словари (НКРЯ, RuSentiLex, стратификация, тематика) — ВКЛЮЧЕНЫ (папка data/,
lexicon_stratified.json). База протокола protocol.db создаётся при первом
запуске рядом с программой (в _internal), журнал и материалы — там же.
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPEC))

# ─── Данные ───────────────────────────────────────────────────────────────────
datas = [
    # Словари и данные программы (freq/senti/lexicons/methodology/corpus_auth)
    (os.path.join(ROOT, 'data'), 'data'),
    # Лексикон стратификации лежит в корне программы
    (os.path.join(ROOT, 'lexicon_stratified.json'), '.'),
    # Конфиг фильтра детектора ошибок (единственная точка управления)
    (os.path.join(ROOT, 'protocol', 'detector_filter.json'), 'protocol'),
    # Ресурсы библиотек
    *collect_data_files('PyQt6'),
    *collect_data_files('pymorphy3'),
    *collect_data_files('pymorphy3_dicts_ru'),
    *collect_data_files('stanza', includes=['**/*.json', '**/*.txt']),
    *collect_data_files('transformers'),
    *collect_data_files('navec'),
]

# ─── Скрытые импорты ─────────────────────────────────────────────────────────
# Локальные пакеты собираем целиком: многие вкладки/модули импортируются
# лениво (внутри функций), PyInstaller их статически не видит.
hiddenimports = [
    *collect_submodules('analyzer'),
    *collect_submodules('ui'),
    *collect_submodules('protocol'),
    # Тяжёлые зависимости
    *collect_submodules('stanza'),
    *collect_submodules('pymorphy3'),
    *collect_submodules('torch'),
    *collect_submodules('transformers'),
    'sklearn',
    'sklearn.utils._cython_blas',
    'navec',
    'razdel',
    'language_tool_python',
    'docx',
    'openpyxl',
    'requests',
    'charset_normalizer',
    'certifi',
    'matplotlib',
    'matplotlib.backends.backend_qtagg',
]

# ─── Исключения (уменьшают размер) ───────────────────────────────────────────
excludes = [
    'tkinter', 'test', 'unittest', 'pytest',
    'IPython', 'jupyter', 'notebook',
    'matplotlib.tests', 'numpy.tests',
    'PIL.ImageTk',
    # Не установлены в окружении — импорты в коде защищены try/except
    'spacy', 'gensim', 'diskcache', 'pypdf',
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
    upx=False,               # UPX + torch DLL часто конфликтуют
    console=False,           # Без консольного окна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='avtoroved',
)
