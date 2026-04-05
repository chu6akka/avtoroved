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
from analyzer import corpus_manager, learning_backend as lb_module
from analyzer import yandex_speller as yaspell_module
from analyzer import stratification_engine as strat_module
from analyzer import thematic_engine as thematic_module
from analyzer import freq_engine as freq_module
from analyzer import senti_engine as senti_module

from ui.tabs.morphology_tab import MorphologyTab
from ui.tabs.statistics_tab import StatisticsTab
from ui.tabs.errors_tab import ErrorsTab
from ui.tabs.internet_tab import InternetTab
from ui.tabs.comparison_tab import ComparisonTab
from ui.tabs.gigacheck_tab import GigaCheckTab
from ui.tabs.grammar_query_tab import GrammarQueryTab
from ui.tabs.report_tab import ReportTab
from ui.tabs.learning_tab import LearningTab, TrainThread
from ui.tabs.stratification_tab import StratificationTab
from ui.tabs.thematic_tab import ThematicTab
from ui.tabs.nkrya_tab import NkryaTab
from ui.tabs.senti_tab import SentiTab

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


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

            # ── Шаг 2.5: Правила пунктуации ─────────────────────────────────
            punct_errors = punct_module.check(self.text)
            if punct_errors and error_result is not None:
                error_result.errors.extend(punct_errors)
                error_result.errors = self.error_analyzer._dedup_by_span(
                    error_result.errors)
                error_result.errors.sort(key=lambda e: e.position[0])

            # Пересчитать навыки после добавления всех внешних ошибок (LT + Ya + Punct)
            if error_result is not None:
                error_result.skill_levels = self.error_analyzer._assess_skills(
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
    """Поток для сравнения текстов."""
    status = pyqtSignal(str)
    finished = pyqtSignal(dict, str, str)
    error = pyqtSignal(str)

    def __init__(self, stanza: StanzaBackend, text1: str, text2: str):
        super().__init__()
        self.stanza = stanza
        self.text1 = text1
        self.text2 = text2

    def run(self):
        try:
            from analyzer.metrics import compare_texts
            self.stanza.ensure_loaded(self.status.emit)
            self.status.emit("Анализ текста 1...")
            tok1 = self.stanza.analyze(self.text1)
            self.status.emit("Анализ текста 2...")
            tok2 = self.stanza.analyze(self.text2)
            self.status.emit("Вычисление сходства...")
            comp = compare_texts(tok1, tok2, self.text1, self.text2)
            # Сохраняем леммы для FastText-сходства в main_window
            comp["_lemmas1"] = [t.lemma.lower() for t in tok1
                                if WORD_RE.search(t.text) and t.pos != "PUNCT"]
            comp["_lemmas2"] = [t.lemma.lower() for t in tok2
                                if WORD_RE.search(t.text) and t.pos != "PUNCT"]
            self.finished.emit(comp, self.text1, self.text2)
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
        self.yaspell = yaspell_module.get()
        self.strat_engine = strat_module.get()
        self.thematic_engine = thematic_module.get()
        # Активный NLP-бэкенд (может переключаться)
        _saved_backend = app_config.get("nlp_backend", "stanza")
        self._nlp_backend = self.spacy_backend if _saved_backend == "spacy" else self.stanza
        self._lb = lb_module.get()
        self._lb.load_or_init_fasttext()  # загрузить модель если есть
        self._corpus_train_thread = None

        self._last_text = ""
        self._last_tokens = []
        self._last_metrics = {}
        self._last_error_result = None
        self._analysis_thread = None
        self._compare_thread = None

        self._settings = QSettings("AutorovedAnalyzer", "v5")
        self._lt_prewarm_thread = None
        self._yaspell_prewarm_thread = None

        self._build_menu()
        self._build_toolbar()
        self._build_ui()
        self._setup_status_bar()
        self._apply_theme()

        # ── Предзагрузка LanguageTool и Яндекс.Спеллера в фоне ───
        self._start_lt_prewarm()
        self._start_yaspell_prewarm()
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
        act_quit = QAction("Выход", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

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

        def _nav(icon: str, label: str, idx: int) -> QPushButton:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("nav_btn")
            btn.setProperty("active", "false")
            btn.setCheckable(False)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda _=False, i=idx: self._switch_page(i))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
            return btn

        # Группа АНАЛИЗ
        _section("АНАЛИЗ ТЕКСТА")
        _nav("📊", "Статистика",         0)
        _nav("📝", "Ошибки и навыки",    1)
        _nav("🔤", "Морфология",          2)
        _nav("🎨", "Стратификация",       3)
        _nav("🗂", "Тематика",            4)

        _nav("📚", "НКРЯ: частоты",       5)
        _nav("💬", "Тональность",          6)

        _divider()
        _section("ИНСТРУМЕНТЫ")
        _nav("🔍", "Граммзапросы",       7)
        _nav("⚖️", "Сравнение",          8)
        _nav("🌐", "Интернет-профиль",   9)
        _nav("🤖", "ИИ-детектор",        10)

        _divider()
        _section("СЕРВИС")
        _nav("📄", "Отчёт",             11)
        _nav("🎓", "Корпус / Модель",   12)

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

        self._ya_status_label = QLabel("⏳ Спеллер: ...")
        self._ya_status_label.setObjectName("lt_status")
        self._ya_status_label.setContentsMargins(12, 2, 8, 4)
        self._ya_status_label.setWordWrap(True)
        nav_layout.addWidget(self._ya_status_label)

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

    def _switch_page(self, idx: int):
        """Переключить страницу контента и обновить активный nav-элемент."""
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == idx else "false")
            # Qt требует перезаполнить стиль при изменении property
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._current_page = idx

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

        # Текстовое поле (всегда видно)
        input_header = QHBoxLayout()
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

        content_layout.addLayout(input_header)

        self.text_input = QTextEdit()
        self.text_input.setObjectName("text_input")
        self.text_input.setPlaceholderText(
            "Вставьте или введите текст для анализа…\n"
            "Рекомендуемый объём: от 200 слов (предварительно), от 500 слов (экспертиза).")
        self.text_input.setMinimumHeight(60)
        self.text_input.textChanged.connect(self._on_text_changed)
        self._text_expanded = False   # состояние toggle

        # ── Стек страниц ───────────────────────────────────────────
        self.stack = __import__(
            'PyQt6.QtWidgets', fromlist=['QStackedWidget']).QStackedWidget()

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

        # 7 — Граммзапросы
        self.tab_grammar = GrammarQueryTab()
        self.stack.addWidget(self.tab_grammar)

        # 8 — Сравнение
        self.tab_compare = ComparisonTab()
        self.tab_compare.compare_requested.connect(self._run_compare)
        self.tab_compare.export_requested.connect(self._export_compare_docx)
        self.stack.addWidget(self.tab_compare)

        # 9 — Интернет-профиль
        self.tab_internet = InternetTab()
        self.stack.addWidget(self.tab_internet)

        # 10 — ИИ-детектор
        self.tab_gigacheck = GigaCheckTab()
        self.stack.addWidget(self.tab_gigacheck)

        # 11 — Отчёт
        self.tab_report = ReportTab()
        self.tab_report.export_requested.connect(self._export_docx)
        self.stack.addWidget(self.tab_report)

        # 12 — Корпус / Модель
        self.tab_learning = LearningTab()
        self.stack.addWidget(self.tab_learning)

        # ── Вертикальный сплиттер: текст ↕ страницы ──────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setObjectName("text_splitter")
        vsplit.setChildrenCollapsible(False)
        vsplit.addWidget(self.text_input)
        vsplit.addWidget(self.stack)
        # Начальные пропорции: ~200px текст, остальное — страница
        vsplit.setSizes([200, 600])
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
        # Цифровые клавиши для быстрого переключения (Ctrl+1..9, Ctrl+0)
        for i in range(12):
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
            # Свернуть: текст ~200px
            self._vsplit.setSizes([200, total - 200])
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

    def _on_yaspell_status(self, msg: str):
        self.status_label.setText(msg)
        self._ya_status_label.setText(f"⏳ {msg[:30]}")

    def _on_yaspell_ready(self, ready: bool):
        self._yaspell_prewarm_thread = None
        if ready:
            self._ya_status_label.setText("🌐 Спеллер ✓")
            self._ya_status_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")
            self.status_label.setText("Яндекс.Спеллер ✓ готов")
        else:
            self._ya_status_label.setText("✗ Спеллер: офлайн")
            self._ya_status_label.setStyleSheet("color: #6c7086; font-size: 11px;")

    # ──── КОРПУС И САМООБУЧЕНИЕ ────
    def _corpus_add_and_train(self, text: str, tokens: list):
        """Добавить текст в корпус и запустить дообучение если порог достигнут."""
        from analyzer.stanza_backend import WORD_RE
        lemmas = [t.lemma for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
        if not lemmas:
            return

        corpus_manager.add_text(text, lemmas)

        # Запустить обучение если корпус готов и нет активного потока
        if (corpus_manager.stats()["ready_for_training"]
                and self._corpus_train_thread is None):
            sentences = corpus_manager.get_recent_lemma_sentences(50)
            self._corpus_train_thread = TrainThread(self._lb, sentences, parent=self)
            self._corpus_train_thread.finished.connect(self._on_corpus_train_done)
            self._corpus_train_thread.start()

        # Обновить вкладку корпуса
        self.tab_learning.refresh()

    def _on_corpus_train_done(self, success: bool):
        self._corpus_train_thread = None
        self.tab_learning.refresh()

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
        self.btn_analyze.setEnabled(True)

        word_count = metrics["дополнительно"].get("Всего слов", 0)
        cs = cache_manager.stats()
        backend_name = "spaCy ⚡" if isinstance(self._nlp_backend, SpacyBackend) else "Stanza"
        self.status_label.setText(
            f"Анализ завершён  |  NLP: {backend_name}  |  Кэш: {cs['entries']} текстов")
        self.word_count_label.setText(f"Слов: {word_count}")

        # Морфология
        self.tab_morph.populate(tokens, text)

        # Статистика
        self.tab_stats.populate(metrics)

        # Ошибки
        self.tab_errors.populate(error_result)

        # Стратификация
        if strat_result is not None:
            self.tab_strat.populate(strat_result)

        # Тематика
        if thematic_result is not None:
            self.tab_thematic.populate(thematic_result)

        # Интернет-профиль
        if error_result:
            self.tab_internet.populate(error_result.internet_profile)

        # GigaCheck: передать текст
        self.tab_gigacheck.set_text(text)

        # НКРЯ: частотный анализ
        if freq_result is not None:
            self.tab_nkrya.show_result(freq_result)

        # Тональный анализ (RuSentiLex)
        if senti_result is not None:
            self.tab_senti.show_result(senti_result)

        # Грамматические запросы
        self.tab_grammar.set_tokens(tokens, text[:80])

        # Отчёт
        self.tab_report.generate_report(text, metrics, error_result, None, None)

        # Переходим на страницу статистики
        self._switch_page(0)

        # ── Пополнение корпуса и дообучение (фоновый поток) ──────────────
        self._corpus_add_and_train(text, tokens)

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
        self._compare_thread = CompareThread(self._nlp_backend, text1, text2)
        self._compare_thread.status.connect(self.status_label.setText)
        self._compare_thread.finished.connect(self._on_compare_done)
        self._compare_thread.error.connect(lambda e: QMessageBox.critical(self, "Ошибка", e))
        self._compare_thread.start()

    def _on_compare_done(self, comp: dict, t1: str, t2: str):
        self.status_label.setText("Сравнение завершено")
        # Вычислить FastText-сходство если модель готова
        l1 = comp.pop("_lemmas1", [])
        l2 = comp.pop("_lemmas2", [])
        if self._lb.ft_ready and l1 and l2:
            comp["fasttext_sim"] = self._lb.vector_similarity(l1, l2)
        self._last_compare = (comp, t1, t2)
        self.tab_compare.show_result(comp)

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
                export_report_docx(
                    fp, self._last_text, self._last_metrics,
                    self._last_error_result, self._last_tokens,
                    strat_result=None,
                    thematic_result=None)
                QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{fp}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def _export_compare_docx(self):
        if not hasattr(self, '_last_compare') or not self._last_compare:
            QMessageBox.information(self, "Нет данных", "Сначала выполните сравнение текстов.")
            return
        comp, t1, t2 = self._last_compare
        fp, _ = QFileDialog.getSaveFileName(
            self, "Сохранить сравнение", "сравнение_текстов.docx",
            "Word (*.docx)")
        if fp:
            try:
                export_comparison_docx(fp, comp, t1, t2)
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
        self.tab_internet.clear()
        self.tab_compare.clear()
        self.tab_gigacheck.clear()
        self.tab_grammar.clear()
        self.tab_report.clear()
        self._last_text = ""
        self._last_tokens = []
        self._last_metrics = {}
        self._last_error_result = None
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
            "• С.М. Вул «Судебно-автороведческая идентификационная экспертиза» (2007)\n"
            "• Litvinova et al. (2015–2016) — POS-биграммы\n"
            "• ЭКЦ МВД России — лексическая стратификация (2021)\n"
            "• GigaCheck (SberDevices) — детекция ИИ-контента\n\n"
            "NLP-движки: Stanford Stanza / spaCy (русский язык)\n"
            "GUI: PyQt6\n"
            "GitHub: https://github.com/chu6akka/avtoroved"
        )
