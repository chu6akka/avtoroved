"""
Главное окно приложения (PyQt6).
Автороведческий анализатор v5.
"""
from __future__ import annotations
import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QStatusBar,
    QStackedWidget, QFileDialog, QMessageBox, QSplitter,
    QScrollArea, QFrame, QToolBar, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QAction, QKeySequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.stanza_backend import StanzaBackend, WORD_RE
from analyzer.spacy_backend import SpacyBackend
from analyzer.errors import ErrorAnalyzer
from analyzer.metrics import calculate_metrics
from analyzer.export import load_text_from_file, export_report_docx, export_comparison_docx
from analyzer import cache_manager, config as app_config
from analyzer import lt_checker as lt_module
from analyzer import punct_checker as punct_module
from analyzer import learning_backend as lb_module
# ИСКЛЮЧЁН из активного контура (docs/module_scope.md): Яндекс.Спеллер —
# сетевой дубль орфографической функции локального LanguageTool; сетевые
# вызовы несовместимы с воспроизводимостью протокола. Модуль сохранён в
# analyzer/yandex_speller.py как перспектива.
# from analyzer import yandex_speller as yaspell_module
from analyzer import stratification_engine as strat_module
from analyzer import thematic_engine as thematic_module
from analyzer import freq_engine as freq_module
from analyzer import senti_engine as senti_module
from analyzer import diagnostic_engine as diag_module

from ui.tabs.morphology_tab import MorphologyTab
from ui.tabs.statistics_tab import StatisticsTab
from ui.tabs.errors_tab import ErrorsTab
from ui.tabs.comparison_tab import ComparisonTab
from ui.tabs.gigacheck_tab import GigaCheckTab
from ui.tabs.report_tab import ReportTab
from ui.tabs.profile_tab import ProfileTab
from ui.tabs.stratification_tab import StratificationTab
from ui.tabs.thematic_tab import ThematicTab
from ui.tabs.nkrya_tab import NkryaTab
from ui.tabs.senti_tab import SentiTab
from ui.tabs.materials_tab import MaterialsTab
from ui.tabs.suitability_tab import SuitabilityTab
from ui.tabs.separate_research_tab import SeparateResearchTab
from ui.tabs.feature_map_tab import FeatureMapTab
from ui.tabs.comparative_research_tab import ComparativeResearchTab
from ui.tabs.conclusion_tab import ConclusionTab
from ui.tabs.token_inspector_tab import TokenInspectorTab
from ui.tabs.ogorelkov_tab import OgorelkovTab

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class _PlainPasteEdit(QTextEdit):
    """QTextEdit с вставкой plain-text — убирает HTML-фон из буфера обмена."""
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)


class LTPrewarmThread(QThread):
    """Фоновый поток предзагрузки LanguageTool при старте приложения."""
    status  = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # (ready, mode)

    def __init__(self, lt):
        super().__init__()
        self.lt = lt

    def run(self):
        self.status.emit("LanguageTool: инициализация...")
        self.lt.ensure_loaded(self.status.emit)
        self.finished.emit(self.lt.is_ready, self.lt.mode)


class YaspellPrewarmThread(QThread):
    """Фоновый поток предзагрузки Яндекс.Спеллера."""
    status   = pyqtSignal(str)
    finished = pyqtSignal(bool)  # ready

    def __init__(self, yaspell):
        super().__init__()
        self.yaspell = yaspell

    def run(self):
        self.yaspell.ensure_loaded(self.status.emit)
        self.finished.emit(self.yaspell.is_ready)


class AnalysisThread(QThread):
    """Поток для анализа текста."""
    status   = pyqtSignal(str)
    # text, tokens, metrics, error_result, strat_result, thematic_result, freq_result, senti_result
    finished = pyqtSignal(str, list, dict, object, object, object, object, object)
    error    = pyqtSignal(str)

    def __init__(self, stanza: StanzaBackend, error_analyzer: ErrorAnalyzer,
                 text: str, lt: object = None, yaspell: object = None,
                 strat_engine: object = None, thematic_engine: object = None,
                 freq_engine: object = None, senti_engine: object = None):
        super().__init__()
        self.stanza          = stanza
        self.error_analyzer  = error_analyzer
        self.text            = text
        self.lt              = lt
        self.yaspell         = yaspell
        self.strat_engine    = strat_engine
        self.thematic_engine = thematic_engine
        self.freq_engine     = freq_engine
        self.senti_engine    = senti_engine

    def run(self):
        try:
            # ── Шаг 0: морфологический анализ ────────────────────────────
            self.stanza.ensure_loaded(self.status.emit)
            self.status.emit("Морфологический анализ...")
            tokens = self.stanza.analyze(self.text)

            self.status.emit("Вычисление метрик...")
            metrics = calculate_metrics(tokens, self.text)

            self.status.emit("Анализ ошибок...")
            error_result = self.error_analyzer.analyze(self.text, tokens)

            # ── Шаг 1: LanguageTool ───────────────────────────────────────
            if self.lt is not None:
                self.lt.ensure_loaded(self.status.emit)
                if self.lt.is_ready:
                    self.status.emit("LanguageTool: орфография и пунктуация...")
                    lt_errors = self.lt.check(self.text)
                    if lt_errors and error_result is not None:
                        error_result.errors.extend(lt_errors)
                        error_result.errors = self.error_analyzer._dedup_by_span(
                            error_result.errors)
                        error_result.errors.sort(key=lambda e: e.position[0])

            # ── Шаг 2: Яндекс.Спеллер ────────────────────────────────────
            if self.yaspell is not None and self.yaspell.is_ready:
                self.status.emit("Яндекс.Спеллер: проверка орфографии...")
                ya_errors = self.yaspell.check(self.text)
                if ya_errors and error_result is not None:
                    error_result.errors.extend(ya_errors)
                    error_result.errors = self.error_analyzer._dedup_by_span(
                        error_result.errors)
                    error_result.errors.sort(key=lambda e: e.position[0])

            # ── Шаг 2.5: Правила пунктуации (regex + depparse) ───────────────
            punct_errors = punct_module.check_with_tokens(self.text, tokens)
            if punct_errors and error_result is not None:
                error_result.errors.extend(punct_errors)
                error_result.errors = self.error_analyzer._dedup_by_span(
                    error_result.errors)
                error_result.errors.sort(key=lambda e: e.position[0])

            # Пересчитать навыки и общий признак после добавления всех внешних ошибок
            if error_result is not None:
                from analyzer.errors import calculate_general_skill
                error_result.skill_levels = self.error_analyzer._assess_skills(
                    error_result.errors, error_result.total_words
                )
                (error_result.general_skill_level,
                 error_result.general_skill_desc,
                 error_result.total_unique_errors) = calculate_general_skill(
                    error_result.errors, error_result.total_words
                )

            # ── Шаг 3: Стратификация ──────────────────────────────────────
            strat_result = None
            if self.strat_engine is not None:
                self.status.emit("Лексическая стратификация...")
                try:
                    strat_result = self.strat_engine.analyze(self.text)
                except Exception:
                    pass

            # ── Шаг 4: Тематика ───────────────────────────────────────────
            thematic_result = None
            if self.thematic_engine is not None:
                self.status.emit("Тематическая атрибуция...")
                try:
                    lemmas = [t.lemma.lower() for t in tokens
                              if WORD_RE.search(t.text) and t.pos not in ("PUNCT", "NUM")]
                    thematic_result = self.thematic_engine.analyze(lemmas)
                except Exception:
                    pass

            # ── Шаг 5: Частотный анализ НКРЯ ─────────────────────────────
            freq_result = None
            if self.freq_engine is not None and self.freq_engine.is_loaded:
                self.status.emit("Частотный анализ по НКРЯ...")
                try:
                    lemma_map = {
                        t.text.lower(): t.lemma.lower()
                        for t in tokens if WORD_RE.search(t.text)
                    }
                    freq_result = self.freq_engine.analyze(self.text, lemma_map)
                except Exception:
                    pass

            # ── Шаг 6: Тональный анализ (RuSentiLex) ─────────────────────
            senti_result = None
            if self.senti_engine is not None and self.senti_engine.is_loaded:
                self.status.emit("Тональный анализ (RuSentiLex)...")
                try:
                    lemma_map_s = {
                        t.text.lower(): t.lemma.lower()
                        for t in tokens if WORD_RE.search(t.text)
                    }
                    senti_result = self.senti_engine.analyze(self.text, lemma_map_s)
                except Exception:
                    pass

            self.finished.emit(
                self.text, tokens, metrics, error_result,
                strat_result, thematic_result, freq_result,
                senti_result,
            )
        except Exception as e:
            self.error.emit(str(e))


class CompareThread(QThread):
    """
    Поток сравнительного исследования (методика Рубцовой 2007, ЭКЦ МВД).

    По каждому тексту собирает признаки (морфология, метрики, навыки из errors.py,
    стратификация), затем comparison_engine строит структуру НН/НС/НСВ.
    Вспомогательные метрики сходства сохраняются отдельно.
    """
    status = pyqtSignal(str)
    # comp (вспомогательные метрики), structured (ComparisonResult), text1, text2
    finished = pyqtSignal(dict, object, str, str)
    error = pyqtSignal(str)

    def __init__(self, stanza: StanzaBackend, text1: str, text2: str,
                 error_analyzer=None, strat_engine=None):
        super().__init__()
        self.stanza = stanza
        self.text1 = text1
        self.text2 = text2
        self.error_analyzer = error_analyzer
        self.strat_engine = strat_engine

    def _build_bundle(self, name: str, text: str, tokens: list):
        """Собрать признаки одного текста для движка сравнения."""
        from analyzer.metrics import calculate_metrics
        from analyzer.errors import calculate_general_skill
        from analyzer import comparison_engine as ce

        metrics = calculate_metrics(tokens, text)
        er = None
        if self.error_analyzer is not None:
            er = self.error_analyzer.analyze(text, tokens)
            # Общий признак письменной речи (ЭКЦ МВД, с. 13) — для уровня НН
            if er is not None and not er.general_skill_level:
                (er.general_skill_level, er.general_skill_desc,
                 er.total_unique_errors) = calculate_general_skill(
                    er.errors, er.total_words)
        sr = None
        if self.strat_engine is not None:
            try:
                sr = self.strat_engine.analyze(text)
            except Exception:
                pass
        return ce.build_bundle(name, text, tokens, metrics, er, sr)

    def run(self):
        try:
            from analyzer.metrics import compare_texts
            from analyzer import comparison_engine as ce

            self.stanza.ensure_loaded(self.status.emit)
            self.status.emit("Анализ текста 1...")
            tok1 = self.stanza.analyze(self.text1)
            self.status.emit("Анализ текста 2...")
            tok2 = self.stanza.analyze(self.text2)

            self.status.emit("Вспомогательные метрики сходства...")
            comp = compare_texts(tok1, tok2, self.text1, self.text2)
            comp["_lemmas1"] = [t.lemma.lower() for t in tok1
                                if WORD_RE.search(t.text) and t.pos != "PUNCT"]
            comp["_lemmas2"] = [t.lemma.lower() for t in tok2
                                if WORD_RE.search(t.text) and t.pos != "PUNCT"]

            self.status.emit("Раздельное исследование признаков...")
            b1 = self._build_bundle("Текст 1", self.text1, tok1)
            b2 = self._build_bundle("Текст 2", self.text2, tok2)

            self.status.emit("Сравнительное исследование (НН/НС/НСВ)...")
            structured = ce.compare(b1, b2, comp)

            self.finished.emit(comp, structured, self.text1, self.text2)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Главное окно Автороведческого анализатора v5."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Автороведческий анализатор v5")
        self.setMinimumSize(1280, 800)
        self.resize(1400, 900)

        self.stanza = StanzaBackend()
        self.spacy_backend = SpacyBackend()
        self.freq_engine = freq_module.get()
        self.senti_engine = senti_module.get()
        self.senti_engine.load()   # быстро, 700KB
        self.error_analyzer = ErrorAnalyzer()
        self.lt = lt_module.get()
        self.yaspell = None   # Яндекс.Спеллер исключён (см. комментарий у импорта)
        self.strat_engine = strat_module.get()
        self.thematic_engine = thematic_module.get()
        # Активный NLP-бэкенд (может переключаться)
        _saved_backend = app_config.get("nlp_backend", "stanza")
        self._nlp_backend = self.spacy_backend if _saved_backend == "spacy" else self.stanza
        self._lb = lb_module.get()
        self._sbert_thread = None
        self._diag_engine = diag_module.get()

        self._last_text = ""
        self._last_tokens = []
        self._last_metrics = {}
        self._last_error_result = None
        self._last_strat_result = None
        self._last_thematic_result = None
        self._analysis_thread = None
        self._compare_thread = None

        self._settings = QSettings("AutorovedAnalyzer", "v5")
        self._lt_prewarm_thread = None
        self._yaspell_prewarm_thread = None

        # Архивные страницы (скрыты из UI, модули работают) — см. комментарий
        # у _DEFAULT_ARCHIVED_PAGES; переопределяется ключом config.json.
        self._archived_pages = set(app_config.get(
            "archived_pages", self._DEFAULT_ARCHIVED_PAGES))

        self._build_menu()
        self._build_toolbar()
        self._build_ui()
        self._setup_status_bar()
        self._apply_theme()

        # ── Предзагрузка LanguageTool в фоне (Спеллер исключён — сеть) ───
        self._start_lt_prewarm()
        # Стратификация загружается лениво при первом анализе
        # (словарь ~9000 слов, не требует сети)

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Файл")
        act_open = QAction("📂 Открыть файл", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._load_file)
        file_menu.addAction(act_open)
        act_export = QAction("📄 Экспорт отчёта в DOCX", self)
        act_export.triggered.connect(self._export_docx)
        file_menu.addAction(act_export)
        file_menu.addSeparator()
        act_batch = QAction("📦 Пакетная обработка...", self)
        act_batch.triggered.connect(self._open_batch)
        file_menu.addAction(act_batch)
        file_menu.addSeparator()
        act_lexupd = QAction("📚 Обновить словарные базы...", self)
        act_lexupd.triggered.connect(self._open_lexicon_update)
        file_menu.addAction(act_lexupd)
        file_menu.addSeparator()
        act_quit = QAction("Выход", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Утилиты вне ленты экспертного процесса (см. docs/module_scope.md)
        service_menu = menubar.addMenu("Сервис")
        act_tokens = QAction("🔍 Инспектор токенов", self)
        act_tokens.setToolTip("Карточки слов: морфология, частотность, регистр")
        act_tokens.triggered.connect(lambda: self._switch_page(17))
        service_menu.addAction(act_tokens)

        view_menu = menubar.addMenu("Вид")
        act_dark = QAction("🌙 Тёмная тема", self)
        act_dark.triggered.connect(lambda: self._set_theme("dark"))
        act_light = QAction("☀ Светлая тема", self)
        act_light.triggered.connect(lambda: self._set_theme("light"))
        view_menu.addAction(act_dark)
        view_menu.addAction(act_light)

        vis_menu = menubar.addMenu("Визуализация")
        act_pie = QAction("📊 Диаграмма частей речи", self)
        act_pie.triggered.connect(self._show_pie_chart)
        act_heatmap = QAction("🔥 Heatmap POS-биграмм", self)
        act_heatmap.triggered.connect(self._show_heatmap)
        vis_menu.addAction(act_pie)
        vis_menu.addAction(act_heatmap)

        help_menu = menubar.addMenu("Справка")
        act_lexicon = QAction("📖 Справочник словарей", self)
        act_lexicon.setShortcut(QKeySequence("F4"))
        act_lexicon.triggered.connect(self._open_lexicon_viewer)
        help_menu.addAction(act_lexicon)
        help_menu.addSeparator()
        act_about = QAction("О программе", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_toolbar(self):
        # Toolbar убран — навигация перенесена в sidebar
        pass

    def _build_sidebar(self) -> "QWidget":
        """Боковая панель навигации (200 px)."""
        from PyQt6.QtWidgets import QScrollArea
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Заголовок ──────────────────────────────────────────────
        title = QLabel("АВТОРОВЕД")
        title.setObjectName("sidebar_title")
        layout.addWidget(title)

        ver = QLabel("v5 · forensic NLP")
        ver.setObjectName("caption")
        ver.setContentsMargins(16, 0, 0, 8)
        layout.addWidget(ver)

        # ── Большая кнопка Анализ ──────────────────────────────────
        self.btn_analyze = QPushButton("▶  Анализировать")
        self.btn_analyze.setObjectName("analyze_btn")
        self.btn_analyze.setToolTip("Ctrl+Enter")
        self.btn_analyze.clicked.connect(self._run_analysis)
        layout.addWidget(self.btn_analyze)

        # ── Прокручиваемая область навигации ──────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("sidebar")

        nav_widget = QWidget()
        nav_widget.setObjectName("sidebar")
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 4, 0, 4)
        nav_layout.setSpacing(0)

        self._nav_buttons = []

        def _section(label: str):
            lbl = QLabel(label)
            lbl.setObjectName("sidebar_subtitle")
            nav_layout.addWidget(lbl)

        def _divider():
            d = QFrame()
            d.setObjectName("sidebar_divider")
            d.setFrameShape(QFrame.Shape.HLine)
            nav_layout.addWidget(d)

        def _nav(icon: str, label: str, idx: int) -> QPushButton | None:
            # Архивные страницы не получают кнопку в сайдбаре: модуль остаётся
            # в программе, но из UI убран (docs/module_scope.md). Утилиты
            # доступны из меню «Сервис» и в ленте процесса не показываются.
            # Вернуть вкладку: правка списка archived_pages в config.json.
            if idx in self._archived_pages or idx in self._UTILITY_PAGES:
                return None
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("nav_btn")
            btn.setProperty("active", "false")
            btn.setCheckable(False)
            btn.setFixedHeight(38)
            btn._page_idx = idx
            btn.clicked.connect(lambda _=False, i=idx: self._switch_page(i))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
            return btn

        # Группа АНАЛИЗ
        _section("АНАЛИЗ ТЕКСТА")
        _nav("📊", "Статистика",      0)
        _nav("📝", "Языковые навыки", 1)
        _nav("🔤", "Морфология",      2)
        _nav("🧷", "Служебная лексика", 18)
        _nav("🎨", "Стратификация",   3)
        _nav("🗂", "Тематика",        4)
        _nav("📚", "НКРЯ: частоты",   5)
        _nav("💬", "Тональность",     6)

        _divider()
        _section("ИНСТРУМЕНТЫ")
        _nav("⚖️", "Сравнение",      7)
        _nav("🤖", "ИИ-детектор",    8)

        _divider()
        _section("СЕРВИС")
        _nav("📄", "Отчёт",           9)
        _nav("🔬", "Профиль автора",  10)

        _divider()
        _section("ЭКСПЕРТНЫЙ ПРОТОКОЛ")
        _nav("📁", "Материалы",       11)
        _nav("✅", "Пригодность",      12)
        _nav("🧩", "Раздельное исслед.", 13)
        _nav("🗺", "Карта признаков",  14)
        _nav("⚖", "Сравнительное исслед.", 15)
        _nav("📜", "Вывод и заключение", 16)
        _nav("🔍", "Инспектор токенов", 17)

        # ── Кнопка справочника словарей ───────────────────────────
        _divider()
        btn_lexicon = QPushButton("📖 Справочник словарей")
        btn_lexicon.setObjectName("sidebar_btn")
        btn_lexicon.setFixedHeight(32)
        btn_lexicon.setToolTip("Просмотр слов тематических доменов и пластов")
        btn_lexicon.clicked.connect(self._open_lexicon_viewer)
        nav_layout.addWidget(btn_lexicon)

        # ── Статусы бэкендов ──────────────────────────────────────
        lt_divider = QFrame()
        lt_divider.setObjectName("sidebar_divider")
        lt_divider.setFrameShape(QFrame.Shape.HLine)
        nav_layout.addWidget(lt_divider)

        self._lt_status_label = QLabel("⏳ LT: инициализация...")
        self._lt_status_label.setObjectName("lt_status")
        self._lt_status_label.setContentsMargins(12, 4, 8, 2)
        self._lt_status_label.setWordWrap(True)
        nav_layout.addWidget(self._lt_status_label)

        self._lt_retry_btn = QPushButton("↻ Подключить LT")
        self._lt_retry_btn.setObjectName("sidebar_btn")
        self._lt_retry_btn.setFixedHeight(28)
        self._lt_retry_btn.setVisible(False)
        self._lt_retry_btn.clicked.connect(self._retry_lt)
        nav_layout.addWidget(self._lt_retry_btn)

        # Блоки Яндекс.Спеллера и SBERT убраны из сайдбара: Спеллер исключён
        # (сетевой дубль LT), SBERT обслуживает только архивное старое
        # сравнение (вкладка 7). См. docs/module_scope.md; методы _load_sbert
        # и _start_yaspell_prewarm сохранены в коде.
        self._ya_status_label = None
        self._sbert_status_label = None
        self._btn_load_sbert = None

        scroll.setWidget(nav_widget)
        layout.addWidget(scroll)

        # ── Нижние кнопки ─────────────────────────────────────────
        _divider()

        # NLP selector
        nlp_row = QHBoxLayout()
        nlp_row.setContentsMargins(8, 6, 8, 2)
        nlp_lbl = QLabel("NLP:")
        nlp_lbl.setObjectName("caption")
        nlp_lbl.setFixedWidth(32)
        nlp_row.addWidget(nlp_lbl)
        from PyQt6.QtWidgets import QComboBox as _CB
        self.backend_combo = _CB()
        self.backend_combo.setObjectName("sidebar_btn")
        self.backend_combo.addItem("Stanza", "stanza")
        self.backend_combo.addItem("spaCy ⚡", "spacy")
        _saved = app_config.get("nlp_backend", "stanza")
        self.backend_combo.setCurrentIndex(1 if _saved == "spacy" else 0)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        nlp_row.addWidget(self.backend_combo)
        layout.addLayout(nlp_row)

        # Util row
        util_row = QHBoxLayout()
        util_row.setContentsMargins(8, 4, 8, 4)
        util_row.setSpacing(4)

        btn_file = QPushButton("📂 Файл")
        btn_file.setObjectName("sidebar_btn")
        btn_file.setFixedHeight(30)
        btn_file.clicked.connect(self._load_file)
        util_row.addWidget(btn_file)

        btn_batch = QPushButton("📦 Пакет")
        btn_batch.setObjectName("sidebar_btn")
        btn_batch.setFixedHeight(30)
        btn_batch.clicked.connect(self._open_batch)
        util_row.addWidget(btn_batch)

        layout.addLayout(util_row)

        util_row2 = QHBoxLayout()
        util_row2.setContentsMargins(8, 0, 8, 10)
        util_row2.setSpacing(4)

        btn_export = QPushButton("💾 Экспорт")
        btn_export.setObjectName("sidebar_btn")
        btn_export.setFixedHeight(30)
        btn_export.clicked.connect(self._export_docx)
        util_row2.addWidget(btn_export)

        btn_clear = QPushButton("🗑 Очистить")
        btn_clear.setObjectName("danger")
        btn_clear.setFixedHeight(30)
        btn_clear.clicked.connect(self._clear_all)
        util_row2.addWidget(btn_clear)

        layout.addLayout(util_row2)

        return sidebar

    # Страницы раздела «Экспертный протокол» — работают с материалами из БД,
    # общее поле «Текст для анализа» на них не используется и скрывается.
    _PROTOCOL_PAGES_FROM = 11

    # Архив: страницы вне идентификационного ядра скрыты из сайдбара
    # (код и модули сохранены — см. docs/module_scope.md). Вернуть страницу:
    # убрать индекс из списка "archived_pages" в config.json рядом с программой.
    # 3 Стратификация, 4 Тематика, 5 НКРЯ, 6 Тональность,
    # 7 Сравнение (старое), 8 ИИ-детектор (диагностика, не идентификация),
    # 9 Отчёт (старый), 10 Профиль автора (диагностика пола/возраста).
    _DEFAULT_ARCHIVED_PAGES = [3, 4, 5, 6, 7, 8, 9, 10]

    # Утилиты: страницы без кнопки в ленте процесса, открываются из меню
    # «Сервис» (не мешают экспертному workflow, но всегда доступны).
    # 17 — Инспектор токенов.
    _UTILITY_PAGES = {17}

    def _switch_page(self, idx: int):
        """Переключить страницу контента и обновить активный nav-элемент."""
        if idx in self._archived_pages and idx not in self._UTILITY_PAGES:
            return   # архивная страница недоступна из UI
        self.stack.setCurrentIndex(idx)
        for btn in self._nav_buttons:
            btn.setProperty("active", "true" if btn._page_idx == idx else "false")
            # Qt требует перезаполнить стиль при изменении property
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._current_page = idx

        # Скрыть/показать поле текста в зависимости от типа страницы
        if hasattr(self, "text_input"):
            analytical = idx < self._PROTOCOL_PAGES_FROM
            self.text_input.setVisible(analytical)
            self._input_header_widget.setVisible(analytical)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Левая: сайдбар ─────────────────────────────────────────
        sidebar = self._build_sidebar()
        root.addWidget(sidebar)

        # ── Правая: контент ────────────────────────────────────────
        content = QWidget()
        content.setObjectName("content_area")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(8)

        # Текстовое поле (видно на аналитических страницах; на страницах
        # экспертного протокола скрывается — там источник текста это БД)
        self._input_header_widget = QWidget()
        input_header = QHBoxLayout(self._input_header_widget)
        input_header.setContentsMargins(0, 0, 0, 0)
        input_lbl = QLabel("Текст для анализа")
        input_lbl.setObjectName("subtitle")
        input_header.addWidget(input_lbl)
        input_header.addStretch()
        self.word_count_label = QLabel("")
        self.word_count_label.setObjectName("caption")
        input_header.addWidget(self.word_count_label)

        # Кнопки управления текстовым полем
        btn_expand = QPushButton("⊞")
        btn_expand.setObjectName("sidebar_btn")
        btn_expand.setFixedSize(26, 26)
        btn_expand.setToolTip("Открыть текст в отдельном окне (F2)")
        btn_expand.clicked.connect(self._open_text_window)
        input_header.addWidget(btn_expand)

        btn_toggle = QPushButton("↕")
        btn_toggle.setObjectName("sidebar_btn")
        btn_toggle.setFixedSize(26, 26)
        btn_toggle.setToolTip("Развернуть/свернуть текстовую область (F3)")
        btn_toggle.clicked.connect(self._toggle_text_area)
        input_header.addWidget(btn_toggle)

        content_layout.addWidget(self._input_header_widget)

        self.text_input = _PlainPasteEdit()
        self.text_input.setObjectName("text_input")
        self.text_input.setPlaceholderText(
            "Вставьте или введите текст для анализа…\n"
            "Рекомендуемый объём: от 200 слов (предварительно), от 500 слов (экспертиза).")
        self.text_input.setMinimumHeight(60)
        self.text_input.textChanged.connect(self._on_text_changed)
        self._text_expanded = False   # состояние toggle

        # ── Стек страниц ───────────────────────────────────────────
        self.stack = QStackedWidget()

        # 0 — Статистика
        self.tab_stats = StatisticsTab()
        self.tab_stats.show_pie_requested.connect(self._show_pie_chart)
        self.tab_stats.show_heatmap_requested.connect(self._show_heatmap)
        self.stack.addWidget(self.tab_stats)

        # 1 — Ошибки
        self.tab_errors = ErrorsTab()
        self.tab_errors.error_selected.connect(self._highlight_error)
        self.tab_errors.highlight_all_requested.connect(self._highlight_all_errors)
        self.stack.addWidget(self.tab_errors)

        # 2 — Морфология
        self.tab_morph = MorphologyTab()
        self.tab_morph.token_hovered.connect(self._highlight_token)
        self.stack.addWidget(self.tab_morph)

        # 3 — Стратификация
        self.tab_strat = StratificationTab()
        self.stack.addWidget(self.tab_strat)

        # 4 — Тематика
        self.tab_thematic = ThematicTab()
        self.stack.addWidget(self.tab_thematic)

        # 5 — НКРЯ: частотный анализ
        self.tab_nkrya = NkryaTab()
        self.stack.addWidget(self.tab_nkrya)

        # 5b — Тональный профиль (RuSentiLex)
        self.tab_senti = SentiTab()
        self.stack.addWidget(self.tab_senti)

        # 7 — Сравнение
        self.tab_compare = ComparisonTab()
        self.tab_compare.compare_requested.connect(self._run_compare)
        self.tab_compare.export_requested.connect(self._export_compare_docx)
        self.stack.addWidget(self.tab_compare)

        # 8 — ИИ-детектор
        self.tab_gigacheck = GigaCheckTab()
        self.stack.addWidget(self.tab_gigacheck)

        # 9 — Отчёт
        self.tab_report = ReportTab()
        self.tab_report.export_requested.connect(self._export_docx)
        self.stack.addWidget(self.tab_report)

        # 10 — Профиль автора (диагностика)
        self.tab_profile = ProfileTab()
        self.stack.addWidget(self.tab_profile)

        # 11 — Материалы (раздел «Экспертный протокол»): переиспользуем Stanza
        self.tab_materials = MaterialsTab(self.stanza)
        self.stack.addWidget(self.tab_materials)

        # 12 — Пригодность (гейт перед анализом): читает материалы из protocol.db
        self.tab_suitability = SuitabilityTab()
        self.stack.addWidget(self.tab_suitability)

        # 13 — Раздельное исследование: профиль каждого текста, без сравнения
        self.tab_separate = SeparateResearchTab(self.stanza)
        self.stack.addWidget(self.tab_separate)

        # 14 — Карта признаков: экспертный отбор кандидатов (решения append-only)
        self.tab_feature_map = FeatureMapTab()
        self.stack.addWidget(self.tab_feature_map)

        # 15 — Сравнительное исследование: принятые признаки пары, без вывода
        self.tab_comparative = ComparativeResearchTab()
        self.stack.addWidget(self.tab_comparative)

        # 16 — Вывод и заключение: правило Рубцовой + экспорт DOCX
        self.tab_conclusion = ConclusionTab()
        self.stack.addWidget(self.tab_conclusion)

        # 17 — Инспектор токенов: карточки слов + внешние словари по клику
        self.tab_token_inspector = TokenInspectorTab()
        self.stack.addWidget(self.tab_token_inspector)

        # 18 — Служебная лексика (Огорелков): ipm-частоты служебных классов
        self.tab_ogorelkov = OgorelkovTab(
            nlp_backend=self.stanza,
            freq_lookup=lambda lem: (self.freq_engine.lookup(lem)
                                     if self.freq_engine.is_loaded else None))
        self.stack.addWidget(self.tab_ogorelkov)

        # ── Вертикальный сплиттер: текст ↕ страницы ──────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setObjectName("text_splitter")
        vsplit.setChildrenCollapsible(False)
        vsplit.addWidget(self.text_input)
        vsplit.addWidget(self.stack)
        # Начальные пропорции: ~200px текст, остальное — страница
        vsplit.setSizes([130, 900])
        vsplit.setHandleWidth(6)
        self._vsplit = vsplit
        content_layout.addWidget(vsplit)

        root.addWidget(content, stretch=1)

        # Начальная страница
        self._current_page = 0
        self._switch_page(0)

        # Горячие клавиши
        from PyQt6.QtGui import QShortcut
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._run_analysis)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._load_file)
        QShortcut(QKeySequence("F2"), self).activated.connect(self._open_text_window)
        QShortcut(QKeySequence("F3"), self).activated.connect(self._toggle_text_area)
        # Цифровые клавиши для быстрого переключения (Ctrl+1..9, Ctrl+0);
        # архивные страницы пропускаются в _switch_page.
        for i in range(11):
            key = str(i + 1) if i < 9 else ("0" if i == 9 else None)
            if key:
                QShortcut(QKeySequence(f"Ctrl+{key}"), self).activated.connect(
                    lambda _=False, n=i: self._switch_page(n))

    def _on_text_changed(self):
        """Обновить счётчик слов при изменении текста."""
        import re
        text = self.text_input.toPlainText()
        words = len(re.findall(r'[А-Яа-яЁёA-Za-z]+', text))
        if words > 0:
            self.word_count_label.setText(f"{words} слов")
        else:
            self.word_count_label.setText("")

    def _open_text_window(self):
        """Открыть текст в отдельном плавающем окне (F2)."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Текст для анализа")
        dlg.resize(800, 600)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        editor = QTextEdit()
        editor.setObjectName("text_input")
        editor.setPlainText(self.text_input.toPlainText())
        editor.setFont(self.text_input.font())
        layout.addWidget(editor)

        btns = QHBoxLayout()
        btn_apply = QPushButton("✓  Применить")
        btn_apply.setObjectName("primary")
        btn_close = QPushButton("Закрыть")
        btn_close.setObjectName("secondary")
        btns.addStretch()
        btns.addWidget(btn_apply)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

        def _apply():
            self.text_input.setPlainText(editor.toPlainText())
            dlg.accept()

        btn_apply.clicked.connect(_apply)
        btn_close.clicked.connect(dlg.reject)

        # Стиль из текущей темы
        dlg.setStyleSheet(self.styleSheet())
        dlg.exec()

    def _toggle_text_area(self):
        """Переключить размер текстовой области (F3): малый → большой → средний."""
        total = sum(self._vsplit.sizes())
        if not self._text_expanded:
            # Развернуть: текст занимает ~60% высоты
            self._vsplit.setSizes([int(total * 0.6), int(total * 0.4)])
            self._text_expanded = True
        else:
            # Свернуть: текст ~130px
            self._vsplit.setSizes([130, total - 130])
            self._text_expanded = False

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        _default_backend = app_config.get("nlp_backend", "stanza")
        self.status_label = QLabel(
            f"Готов к работе  |  NLP: {_default_backend}  |  модель загрузится при первом анализе")
        self.status_bar.addWidget(self.status_label)

    def _apply_theme(self):
        theme = self._settings.value("theme", "dark")
        self._set_theme(theme)

    def _set_theme(self, theme: str):
        from ui.styles import DARK_STYLESHEET, LIGHT_STYLESHEET
        if theme == "dark":
            self.setStyleSheet(DARK_STYLESHEET)
        else:
            self.setStyleSheet(LIGHT_STYLESHEET)
        self._settings.setValue("theme", theme)

    # ──── LANGUAGETOOL ────
    def _start_lt_prewarm(self):
        """Запустить предзагрузку LanguageTool в фоновом потоке."""
        if self._lt_prewarm_thread is not None:
            return
        self._lt_prewarm_thread = LTPrewarmThread(self.lt)
        self._lt_prewarm_thread.status.connect(self._on_lt_status)
        self._lt_prewarm_thread.finished.connect(self._on_lt_ready)
        self._lt_prewarm_thread.start()

    def _on_lt_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_lt_ready(self, ready: bool, mode: str):
        self._lt_prewarm_thread = None
        if ready:
            icon = "🌐" if mode == "public" else "⚙"
            label = "публичный API" if mode == "public" else "локальный"
            text = f"{icon} LT: {label}"
            self._lt_status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            self._lt_retry_btn.setVisible(False)
            self.status_label.setText(f"LanguageTool готов ({label})")
        else:
            text = "✗ LT: недоступен"
            self._lt_status_label.setStyleSheet("color: #f38ba8; font-size: 11px;")
            self._lt_retry_btn.setVisible(True)
            self.status_label.setText(
                "LanguageTool недоступен — установите Java: adoptium.net")
        self._lt_status_label.setText(text)

    def _retry_lt(self):
        """Повторная попытка подключения к LT."""
        self.lt.reset()
        self._lt_status_label.setText("⏳ LT: повторное подключение...")
        self._lt_status_label.setStyleSheet("color: #f9e2af; font-size: 11px;")
        self._lt_retry_btn.setVisible(False)
        self._lt_prewarm_thread = None
        self._start_lt_prewarm()

    # ──── ЯНДЕКС.СПЕЛЛЕР ────

    def _start_yaspell_prewarm(self):
        if self.yaspell is None:   # Спеллер исключён из активного контура
            return
        if self._yaspell_prewarm_thread is not None:
            return
        self._yaspell_prewarm_thread = YaspellPrewarmThread(self.yaspell)
        self._yaspell_prewarm_thread.status.connect(self._on_yaspell_status)
        self._yaspell_prewarm_thread.finished.connect(self._on_yaspell_ready)
        self._yaspell_prewarm_thread.start()

    def _open_lexicon_viewer(self):
        """Открыть справочник словарей (тематики и пласты)."""
        from ui.dialogs.lexicon_viewer import LexiconViewerDialog
        dlg = LexiconViewerDialog(self)
        dlg.exec()

    def _open_lexicon_update(self):
        """Открыть диалог обновления словарных баз (явное действие, с бэкапом)."""
        from ui.dialogs.lexicon_update_dialog import LexiconUpdateDialog
        dlg = LexiconUpdateDialog(self)
        dlg.exec()

    def _on_yaspell_status(self, msg: str):
        self.status_label.setText(msg)
        if self._ya_status_label is not None:
            self._ya_status_label.setText(f"⏳ {msg[:30]}")

    def _on_yaspell_ready(self, ready: bool):
        self._yaspell_prewarm_thread = None
        if self._ya_status_label is None:
            return
        if ready:
            self._ya_status_label.setText("🌐 Спеллер ✓")
            self._ya_status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            self.status_label.setText("Яндекс.Спеллер ✓ готов")
        else:
            self._ya_status_label.setText("✗ Спеллер: офлайн")
            self._ya_status_label.setStyleSheet("color: #6c7086; font-size: 11px;")

    # ──── SBERT ────
    def _load_sbert(self):
        """Загрузить SBERT в фоновом потоке (кнопка убрана из сайдбара —
        метод сохранён для возврата старого сравнения из архива)."""
        if self._btn_load_sbert is None or self._lb.sbert_ready:
            return
        self._btn_load_sbert.setEnabled(False)
        self._sbert_status_label.setText("🧠 SBERT: загрузка…")

        class _SbertThread(QThread):
            status   = pyqtSignal(str)
            finished = pyqtSignal(bool)
            def __init__(self, lb, parent=None):
                super().__init__(parent)
                self.lb = lb
            def run(self):
                ok = self.lb.load_sbert(status_cb=self.status.emit)
                self.finished.emit(ok)

        self._sbert_thread = _SbertThread(self._lb, parent=self)
        self._sbert_thread.status.connect(self.status_label.setText)
        self._sbert_thread.finished.connect(self._on_sbert_loaded)
        self._sbert_thread.start()

    def _on_sbert_loaded(self, success: bool):
        if self._sbert_status_label is None:
            return
        if success:
            self._sbert_status_label.setText("🧠 SBERT: загружен ✓")
            self._sbert_status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            self._btn_load_sbert.setVisible(False)
            self.status_label.setText("SBERT готов — сравнение текстов стало точнее")
        else:
            self._sbert_status_label.setText("🧠 SBERT: ошибка")
            self._sbert_status_label.setStyleSheet("color: #f38ba8; font-size: 11px;")
            self._btn_load_sbert.setEnabled(True)

    # ──── ПЕРЕКЛЮЧЕНИЕ NLP-БЭКЕНДА ────
    def _on_backend_changed(self, index: int):
        key = self.backend_combo.itemData(index)
        self._nlp_backend = self.spacy_backend if key == "spacy" else self.stanza
        app_config.set("nlp_backend", key)
        self.status_label.setText(
            f"NLP-бэкенд: {'spaCy ⚡ (быстрый)' if key == 'spacy' else 'Stanza (точный)'}"
            " — смена вступит в силу при следующем анализе")

    # ──── ЗАГРУЗКА ФАЙЛА ────
    def _load_file(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Открыть файл", "",
            "Тексты (*.txt *.docx);;Все файлы (*)")
        if fp:
            try:
                text = load_text_from_file(fp)
                self.text_input.setPlainText(text)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    # ──── АНАЛИЗ ────
    def _run_analysis(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Нет текста", "Введите текст для анализа.")
            return
        self.btn_analyze.setEnabled(False)
        self.status_label.setText("Анализ...")

        self._analysis_thread = AnalysisThread(
            self._nlp_backend, self.error_analyzer, text,
            lt=self.lt,
            yaspell=self.yaspell,
            strat_engine=self.strat_engine,
            thematic_engine=self.thematic_engine,
            freq_engine=self.freq_engine,
            senti_engine=self.senti_engine,
        )
        self._analysis_thread.status.connect(self.status_label.setText)
        self._analysis_thread.finished.connect(self._on_analysis_done)
        self._analysis_thread.error.connect(self._on_analysis_error)
        self._analysis_thread.start()

    def _on_analysis_done(self, text, tokens, metrics, error_result,
                          strat_result, thematic_result, freq_result,
                          senti_result):
        self._last_text = text
        self._last_tokens = tokens
        self._last_metrics = metrics
        self._last_error_result = error_result
        self._last_strat_result = strat_result
        self._last_thematic_result = thematic_result
        self.btn_analyze.setEnabled(True)

        word_count = metrics["дополнительно"].get("Всего слов", 0)
        cs = cache_manager.stats()
        backend_name = "spaCy ⚡" if isinstance(self._nlp_backend, SpacyBackend) else "Stanza"

        # Трёхуровневая проверка объёма текста (ЭКЦ МВД, с. 31)
        if word_count < 100:
            vol_status = f"⛔ {word_count} сл. — недостаточно для экспертизы (мин. 100)"
        elif word_count < 500:
            vol_status = f"⚠ {word_count} сл. — только диагностическая экспертиза (идент. мин. 500)"
        else:
            vol_status = f"✓ {word_count} сл. — пригоден для идентификационной экспертизы"

        self.status_label.setText(
            f"Анализ завершён  |  NLP: {backend_name}  |  Кэш: {cs['entries']} текстов")
        self.word_count_label.setText(vol_status)

        # Морфология
        morph_indices = metrics.get("morph_indices", {})
        self.tab_morph.populate(tokens, text, morph_indices)

        # Статистика
        self.tab_stats.populate(metrics)

        # Ошибки
        self.tab_errors.populate(error_result)

        # Стратификация
        if strat_result is not None:
            import hashlib as _hl
            _text_hash = _hl.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
            self.tab_strat.populate(strat_result, _text_hash)

        # Тематика
        if thematic_result is not None:
            self.tab_thematic.populate(thematic_result)

        # GigaCheck: передать текст (только если вкладка не в архиве —
        # незачем питать недоступную страницу; docs/module_scope.md)
        if 8 not in self._archived_pages:
            self.tab_gigacheck.set_text(text)

        # НКРЯ: частотный анализ
        if freq_result is not None:
            self.tab_nkrya.show_result(freq_result)

        # Тональный анализ (RuSentiLex)
        if senti_result is not None:
            self.tab_senti.show_result(senti_result)

        # Служебная лексика (Огорелков): ipm служебных классов + SQLite/аудит
        try:
            from analyzer import ogorelkov_engine as og_engine
            if not self.freq_engine.is_loaded:
                self.freq_engine.load()
            og_result = og_engine.analyze(tokens,
                                          freq_lookup=self.freq_engine.lookup)
            self.tab_ogorelkov.populate(og_result)
            import hashlib as _h
            from protocol import db as _pdb_mod
            from protocol import PROGRAM_VERSION as _pv
            _pdb_mod.ProtocolDB().save_ogorelkov_result(
                _h.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
                og_result["dict_sha256"], og_result["total_words"], og_result,
                label="анализ из текстового поля", program_version=_pv)
            self._last_ogorelkov = og_result
        except Exception:
            import traceback
            traceback.print_exc()

        # Отчёт
        self.tab_report.generate_report(text, metrics, error_result, None, None)

        # Диагностический профиль автора — вне идентификационного ядра
        # (диагностика пола/возраста ≠ идентификация; docs/module_scope.md):
        # считается только если вкладка возвращена из архива.
        if 10 not in self._archived_pages:
            try:
                diag_result = self._diag_engine.analyze(
                    tokens, metrics, error_result, thematic_result)
                self.tab_profile.show_result(diag_result)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.tab_profile.clear()
                self.status_label.setText(f"Профиль автора недоступен: {e}")

        # Переходим на страницу статистики
        self._switch_page(0)

    def _on_analysis_error(self, msg: str):
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Ошибка анализа")
        QMessageBox.critical(self, "Ошибка анализа", msg)

    # ──── ПОДСВЕТКА ТОКЕНОВ ────
    def _highlight_token(self, start: int, end: int):
        cursor = self.text_input.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt_reset = QTextCharFormat()
        cursor.setCharFormat(fmt_reset)

        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#f9e2af"))
        fmt.setForeground(QColor("#1e1e2e"))
        cursor.setCharFormat(fmt)

    def _highlight_all_errors(self, positions: list):
        """Подсветить все ошибки в тексте разными цветами по типу."""
        cursor = self.text_input.textCursor()
        # Сначала сбросить форматирование
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(QTextCharFormat())

        _TYPE_COLORS = {
            "Пунктуационная": "#f9e2af",   # жёлтый
            "Орфографическая": "#f38ba8",  # красный
            "Грамматическая": "#cba6f7",   # фиолетовый
            "Лексическая": "#89dceb",      # голубой
            "Стилистическая": "#a6e3a1",   # зелёный
            "LanguageTool": "#fab387",     # оранжевый (LT без категории)
        }
        _TEXT_COLOR = "#1e1e2e"

        for start, end, error_type in positions:
            if start >= end:
                continue
            bg = _TYPE_COLORS.get(error_type, "#fab387")
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(bg))
            fmt.setForeground(QColor(_TEXT_COLOR))
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    def _highlight_error(self, start: int, end: int):
        cursor = self.text_input.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#f38ba8"))
        fmt.setForeground(QColor("#1e1e2e"))
        cursor.setCharFormat(fmt)
        self.text_input.setTextCursor(cursor)
        self.text_input.ensureCursorVisible()

    # ──── СРАВНЕНИЕ ТЕКСТОВ ────
    def _run_compare(self, text1: str, text2: str):
        self.status_label.setText("Сравнение текстов...")
        self._compare_thread = CompareThread(
            self._nlp_backend, text1, text2,
            error_analyzer=self.error_analyzer,
            strat_engine=self.strat_engine)
        self._compare_thread.status.connect(self.status_label.setText)
        self._compare_thread.finished.connect(self._on_compare_done)
        self._compare_thread.error.connect(lambda e: QMessageBox.critical(self, "Ошибка", e))
        self._compare_thread.start()

    def _on_compare_done(self, comp: dict, structured, t1: str, t2: str):
        self.status_label.setText("Сравнение завершено")
        # SBERT-сходство — вспомогательный объективизирующий показатель
        l1 = comp.pop("_lemmas1", [])
        l2 = comp.pop("_lemmas2", [])
        if self._lb.sbert_ready and l1 and l2:
            sbert_sim = self._lb.vector_similarity(l1, l2)
            comp["sbert_sim"] = sbert_sim
            comp["overall"] = round(
                comp.get("jaccard", 0)                * 0.22
                + comp.get("pos_similarity", 0)       * 0.15
                + comp.get("syntactic_similarity", 0) * 0.13
                + comp.get("ttr_similarity", 0)       * 0.13
                + comp.get("bigram_similarity", 0)    * 0.17
                + sbert_sim                            * 0.20,
                3,
            )
        if structured is not None:
            structured.auxiliary = comp   # обновить вспомогательные метрики (с SBERT)
        self._last_compare = (comp, structured, t1, t2)
        self.tab_compare.show_result(structured, comp)

    # ──── ЭКСПОРТ ────
    def _export_docx(self):
        if not self._last_metrics:
            QMessageBox.information(self, "Нет данных", "Сначала выполните анализ.")
            return
        fp, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчёт", "отчёт_автороведческий.docx",
            "Word (*.docx)")
        if fp:
            try:
                og_result, og_detailed = self.tab_ogorelkov.export_settings()
                export_report_docx(
                    fp, self._last_text, self._last_metrics,
                    self._last_error_result, self._last_tokens,
                    strat_result=self._last_strat_result,
                    thematic_result=self._last_thematic_result,
                    ogorelkov_result=og_result,
                    ogorelkov_detailed=og_detailed)
                QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def _export_compare_docx(self):
        if not hasattr(self, '_last_compare') or not self._last_compare:
            QMessageBox.information(self, "Нет данных", "Сначала выполните сравнение текстов.")
            return
        comp, structured, t1, t2 = self._last_compare
        fp, _ = QFileDialog.getSaveFileName(
            self, "Сохранить сравнение", "сравнение_текстов.docx",
            "Word (*.docx)")
        if fp:
            try:
                export_comparison_docx(fp, structured, comp, t1, t2,
                                       expert_verdict=self.tab_compare.get_expert_verdict())
                QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    # ──── ПАКЕТНАЯ ОБРАБОТКА ────
    def _open_batch(self):
        from ui.dialogs.batch_dialog import BatchDialog
        dlg = BatchDialog(self.stanza, self)
        dlg.exec()

    # ──── ВИЗУАЛИЗАЦИЯ ────
    def _show_pie_chart(self):
        if not self._last_metrics or not self._last_metrics.get("частоты"):
            QMessageBox.information(self, "Нет данных", "Сначала выполните анализ.")
            return
        if not _MPL_AVAILABLE:
            QMessageBox.warning(self, "matplotlib не установлен",
                                "Установите: pip install matplotlib")
            return
        self._open_pie_window()

    def _open_pie_window(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        import matplotlib.pyplot as plt

        dlg = QDialog(self)
        dlg.setWindowTitle("Распределение частей речи")
        dlg.resize(700, 500)
        layout = QVBoxLayout(dlg)

        freq = self._last_metrics["частоты"]
        entries = [(k, float(v["коэффициент"])) for k, v in freq.items()
                   if float(v["коэффициент"]) > 0]
        labels = [e[0] for e in entries]
        values = [e[1] for e in entries]

        fig, ax = plt.subplots(figsize=(7, 5))
        fig.patch.set_facecolor("#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        wedges, texts, autotexts = ax.pie(
            values, labels=None, autopct="%1.1f%%",
            startangle=140, pctdistance=0.85)
        for t in autotexts:
            t.set_color("#cdd6f4")
        ax.legend(wedges, labels, loc="center left",
                  bbox_to_anchor=(1, 0, 0.5, 1),
                  facecolor="#313244", labelcolor="#cdd6f4")
        ax.set_title("Распределение частей речи", color="#cdd6f4")
        fig.tight_layout()

        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        dlg.exec()
        plt.close(fig)

    def _show_heatmap(self):
        if not self._last_metrics:
            QMessageBox.information(self, "Нет данных", "Сначала выполните анализ.")
            return
        if not _MPL_AVAILABLE:
            QMessageBox.warning(self, "matplotlib не установлен",
                                "Установите: pip install matplotlib")
            return
        self._open_heatmap_window()

    def _open_heatmap_window(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        import matplotlib.pyplot as plt
        import numpy as np

        pos_bg = self._last_metrics.get("pos_bigrams", {})
        matrix = pos_bg.get("matrix", {})
        labels = pos_bg.get("pos_labels", [])
        if not labels:
            QMessageBox.information(self, "Нет данных", "Недостаточно данных для heatmap.")
            return

        from analyzer.stanza_backend import UPOS_SHORT
        short = [UPOS_SHORT.get(l, l[:4]) for l in labels]
        n = len(labels)
        data = np.array([[matrix.get(r, {}).get(c, 0) for c in labels] for r in labels])

        dlg = QDialog(self)
        dlg.setWindowTitle("Тепловая карта POS-биграмм")
        dlg.resize(750, 650)
        layout = QVBoxLayout(dlg)

        fig, ax = plt.subplots(figsize=(8, 7))
        fig.patch.set_facecolor("#1e1e2e")
        ax.set_facecolor("#1e1e2e")
        im = ax.imshow(data, cmap="Blues", aspect="auto")
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels(short, rotation=45, ha="right", color="#cdd6f4", fontsize=8)
        ax.set_yticklabels(short, color="#cdd6f4", fontsize=8)
        for i in range(n):
            for j in range(n):
                val = data[i, j]
                if val > 0:
                    ax.text(j, i, f"{val:.3f}", ha="center", va="center",
                            fontsize=6, color="white" if val > data.max() * 0.5 else "#333")
        plt.colorbar(im, ax=ax)
        ax.set_title("Сочетаемость частеречных пар (POS-биграммы)", color="#cdd6f4")
        fig.tight_layout()

        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        dlg.exec()
        plt.close(fig)

    # ──── ОЧИСТКА ────
    def _clear_all(self):
        self.text_input.clear()
        self.tab_morph.clear()
        self.tab_stats.clear()
        self.tab_errors.clear()
        self.tab_compare.clear()
        self.tab_gigacheck.clear()
        self.tab_report.clear()
        self.tab_profile.clear()
        self.tab_ogorelkov.clear()
        self._last_text = ""
        self._last_tokens = []
        self._last_metrics = {}
        self._last_error_result = None
        self._last_strat_result = None
        self._last_thematic_result = None
        self.status_label.setText("Готов к работе")
        self.word_count_label.setText("")

    # ──── О ПРОГРАММЕ ────
    def _show_about(self):
        QMessageBox.about(
            self,
            "О программе",
            "Автороведческий анализатор v5\n\n"
            "Инструмент судебно-автороведческой экспертизы текста\n\n"
            "Методики:\n"
            "• Рубцова И.И., Ермолова Е.И., Безрукова А.И. «Комплексная методика производства\n"
            "  автороведческих экспертиз» — М.: ЭКЦ МВД России, 2007. — 192 с.\n"
            "• С.М. Вул «Судебно-автороведческая идентификационная экспертиза» (2007)\n"
            "• Litvinova et al. (2015–2016) — POS-биграммы\n"
            "• ЭКЦ МВД России — лексическая стратификация (2021)\n"
            "• GigaCheck (SberDevices) — детекция ИИ-контента\n\n"
            "NLP-движки: Stanford Stanza / spaCy (русский язык)\n"
            "GUI: PyQt6\n"
            "GitHub: https://github.com/chu6akka/avtoroved"
        )
