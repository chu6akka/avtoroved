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
    QTabWidget, QFileDialog, QMessageBox, QSplitter,
    QFrame, QToolBar, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QAction, QKeySequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.stanza_backend import StanzaBackend, WORD_RE
from analyzer.errors import ErrorAnalyzer
from analyzer.metrics import calculate_metrics
from analyzer.export import load_text_from_file, export_report_docx, export_comparison_docx
from analyzer.thematic_dicts import ThematicAnalyzer

from ui.tabs.morphology_tab import MorphologyTab
from ui.tabs.statistics_tab import StatisticsTab
from ui.tabs.errors_tab import ErrorsTab
from ui.tabs.internet_tab import InternetTab
from ui.tabs.stratification_tab import StratificationTab
from ui.tabs.comparison_tab import ComparisonTab
from ui.tabs.gigacheck_tab import GigaCheckTab
from ui.tabs.thematic_tab import ThematicTab
from ui.tabs.grammar_query_tab import GrammarQueryTab
from ui.tabs.report_tab import ReportTab

try:
    from lexical_stratification import analyze_stratification
    _STRAT_AVAILABLE = True
except ImportError:
    _STRAT_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class AnalysisThread(QThread):
    """Поток для анализа текста."""
    status = pyqtSignal(str)
    finished = pyqtSignal(str, list, dict, object, object)  # text, tokens, metrics, error_result, strat_result
    error = pyqtSignal(str)

    def __init__(self, stanza: StanzaBackend, error_analyzer: ErrorAnalyzer, text: str):
        super().__init__()
        self.stanza = stanza
        self.error_analyzer = error_analyzer
        self.text = text

    def run(self):
        try:
            self.stanza.ensure_loaded(self.status.emit)
            self.status.emit("Морфологический анализ...")
            tokens = self.stanza.analyze(self.text)
            self.status.emit("Вычисление метрик...")
            metrics = calculate_metrics(tokens, self.text)
            self.status.emit("Анализ ошибок...")
            error_result = self.error_analyzer.analyze(self.text)
            strat_result = None
            if _STRAT_AVAILABLE:
                self.status.emit("Стратификация лексики...")
                lemma_pairs = [(t.text, t.lemma) for t in tokens
                               if WORD_RE.search(t.text) and t.pos != "PUNCT"]
                strat_result = analyze_stratification(self.text, lemma_pairs)
            self.finished.emit(self.text, tokens, metrics, error_result, strat_result)
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
        self.error_analyzer = ErrorAnalyzer()
        self.thematic_analyzer = ThematicAnalyzer()

        self._last_text = ""
        self._last_tokens = []
        self._last_metrics = {}
        self._last_error_result = None
        self._last_strat_result = None
        self._last_thematic_result = None
        self._analysis_thread = None
        self._compare_thread = None

        self._settings = QSettings("AutorovedAnalyzer", "v5")

        self._build_menu()
        self._build_toolbar()
        self._build_ui()
        self._setup_status_bar()
        self._apply_theme()

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
        act_about = QAction("О программе", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_toolbar(self):
        toolbar = QToolBar("Основная панель")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        btn_open = QPushButton("📂 Файл")
        btn_open.setObjectName("secondary")
        btn_open.setFixedHeight(32)
        btn_open.clicked.connect(self._load_file)
        toolbar.addWidget(btn_open)

        self.btn_analyze = QPushButton("▶  Анализ  (Ctrl+Enter)")
        self.btn_analyze.setFixedHeight(32)
        self.btn_analyze.setMinimumWidth(180)
        self.btn_analyze.clicked.connect(self._run_analysis)
        toolbar.addWidget(self.btn_analyze)

        btn_batch = QPushButton("📦 Пакет")
        btn_batch.setObjectName("secondary")
        btn_batch.setFixedHeight(32)
        btn_batch.clicked.connect(self._open_batch)
        toolbar.addWidget(btn_batch)

        toolbar.addSeparator()

        btn_pie = QPushButton("📊 Диаграмма POS")
        btn_pie.setObjectName("secondary")
        btn_pie.setFixedHeight(32)
        btn_pie.clicked.connect(self._show_pie_chart)
        toolbar.addWidget(btn_pie)

        btn_heatmap = QPushButton("🔥 Heatmap")
        btn_heatmap.setObjectName("secondary")
        btn_heatmap.setFixedHeight(32)
        btn_heatmap.clicked.connect(self._show_heatmap)
        toolbar.addWidget(btn_heatmap)

        toolbar.addSeparator()

        btn_clear = QPushButton("🗑 Очистить")
        btn_clear.setObjectName("danger")
        btn_clear.setFixedHeight(32)
        btn_clear.clicked.connect(self._clear_all)
        toolbar.addWidget(btn_clear)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(4)

        # Панель ввода текста
        input_group_layout = QVBoxLayout()
        input_label = QLabel("Введите текст или загрузите файл (.txt / .docx):")
        input_label.setObjectName("subtitle")
        input_group_layout.addWidget(input_label)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(
            "Введите текст для анализа...\n"
            "Минимальный объём: 200 слов (предварительный анализ), 500 слов (судебная экспертиза).")
        self.text_input.setMaximumHeight(160)
        self.text_input.setMinimumHeight(100)
        input_group_layout.addWidget(self.text_input)
        main_layout.addLayout(input_group_layout)

        # Вкладки результатов
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_morph = MorphologyTab()
        self.tab_morph.token_hovered.connect(self._highlight_token)
        self.tabs.addTab(self.tab_morph, "1. Морфология")

        self.tab_stats = StatisticsTab()
        self.tab_stats.show_pie_requested.connect(self._show_pie_chart)
        self.tab_stats.show_heatmap_requested.connect(self._show_heatmap)
        self.tabs.addTab(self.tab_stats, "2. Статистика")

        self.tab_errors = ErrorsTab()
        self.tab_errors.error_selected.connect(self._highlight_error)
        self.tabs.addTab(self.tab_errors, "3. Ошибки и навыки")

        self.tab_internet = InternetTab()
        self.tabs.addTab(self.tab_internet, "4. Интернет-коммуникация")

        self.tab_strat = StratificationTab()
        self.tabs.addTab(self.tab_strat, "5. Стратификация лексики")

        self.tab_compare = ComparisonTab()
        self.tab_compare.compare_requested.connect(self._run_compare)
        self.tab_compare.export_requested.connect(self._export_compare_docx)
        self.tabs.addTab(self.tab_compare, "6. Сравнение текстов")

        self.tab_gigacheck = GigaCheckTab()
        self.tabs.addTab(self.tab_gigacheck, "7. ИИ-детектор")

        self.tab_thematic = ThematicTab()
        self.tabs.addTab(self.tab_thematic, "8. Тематика")

        self.tab_grammar = GrammarQueryTab()
        self.tabs.addTab(self.tab_grammar, "9. Грамм. запросы")

        self.tab_report = ReportTab()
        self.tab_report.export_requested.connect(self._export_docx)
        self.tabs.addTab(self.tab_report, "10. Отчёт")

        main_layout.addWidget(self.tabs)

        # Привязка горячих клавиш
        from PyQt6.QtGui import QShortcut
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._run_analysis)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._load_file)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Готов к работе  |  Stanza: не загружена (загрузится при первом анализе)")
        self.status_bar.addWidget(self.status_label)
        self.word_count_label = QLabel("")
        self.status_bar.addPermanentWidget(self.word_count_label)

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

        self._analysis_thread = AnalysisThread(self.stanza, self.error_analyzer, text)
        self._analysis_thread.status.connect(self.status_label.setText)
        self._analysis_thread.finished.connect(self._on_analysis_done)
        self._analysis_thread.error.connect(self._on_analysis_error)
        self._analysis_thread.start()

    def _on_analysis_done(self, text, tokens, metrics, error_result, strat_result):
        self._last_text = text
        self._last_tokens = tokens
        self._last_metrics = metrics
        self._last_error_result = error_result
        self._last_strat_result = strat_result
        self.btn_analyze.setEnabled(True)

        word_count = metrics["дополнительно"].get("Всего слов", 0)
        self.status_label.setText(f"Анализ завершён  |  Stanza: готова")
        self.word_count_label.setText(f"Слов: {word_count}")

        # Морфология
        self.tab_morph.populate(tokens, text)

        # Статистика
        self.tab_stats.populate(metrics)

        # Ошибки
        self.tab_errors.populate(error_result)

        # Интернет-профиль
        if error_result:
            self.tab_internet.populate(error_result.internet_profile)

        # Стратификация
        if strat_result:
            self.tab_strat.populate(strat_result)

        # GigaCheck: передать текст
        self.tab_gigacheck.set_text(text)

        # Тематический анализ
        lemmas = [t.lemma for t in tokens if WORD_RE.search(t.text) and t.pos != "PUNCT"]
        thematic_result = self.thematic_analyzer.analyze(lemmas)
        self._last_thematic_result = thematic_result
        self.tab_thematic.populate(thematic_result, len(lemmas))

        # Грамматические запросы
        self.tab_grammar.set_tokens(tokens)

        # Отчёт
        self.tab_report.generate_report(text, metrics, error_result, strat_result, thematic_result)

        # Переходим на вкладку статистики
        self.tabs.setCurrentWidget(self.tab_stats)

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
        self._compare_thread = CompareThread(self.stanza, text1, text2)
        self._compare_thread.status.connect(self.status_label.setText)
        self._compare_thread.finished.connect(self._on_compare_done)
        self._compare_thread.error.connect(lambda e: QMessageBox.critical(self, "Ошибка", e))
        self._compare_thread.start()

    def _on_compare_done(self, comp: dict, t1: str, t2: str):
        self.status_label.setText("Сравнение завершено")
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
                    strat_result=self._last_strat_result,
                    thematic_result=self._last_thematic_result)
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
        self.tab_strat.clear()
        self.tab_compare.clear()
        self.tab_gigacheck.clear()
        self.tab_thematic.clear()
        self.tab_grammar.clear()
        self.tab_report.clear()
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
            "• С.М. Вул «Судебно-автороведческая идентификационная экспертиза» (2007)\n"
            "• Litvinova et al. (2015–2016) — POS-биграммы\n"
            "• ЭКЦ МВД России — лексическая стратификация (2021)\n"
            "• GigaCheck (SberDevices) — детекция ИИ-контента\n\n"
            "NLP-движок: Stanford Stanza (русский язык)\n"
            "GUI: PyQt6\n"
            "GitHub: https://github.com/chu6akka/avtoroved"
        )
