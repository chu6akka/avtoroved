"""
ui/tabs/ogorelkov_tab.py — вкладка «Служебная лексика (Огорелков)».

Частотный анализ закрытого перечня служебных лексико-грамматических классов
слов: сводная таблица по 11 категориям + разворачиваемые детальные таблицы
по леммам (ipm текста, ipm НКРЯ, коэффициент отклонения). Только числа —
никакой цветовой маркировки «мужское/женское» и никаких интерпретаций.

Заполняется из аналитического пайплайна (populate) после «Анализировать»;
режим сравнения: кнопка загружает второй текст, добавляются колонки
ipm_текст2 и коэффициент отклонения второго текста.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QFileDialog, QMessageBox,
)

from analyzer import ogorelkov_engine as og_engine


def _fmt(v, na="н/д"):
    return na if v is None else (f"{v:g}" if isinstance(v, float) else str(v))


class _SecondTextThread(QThread):
    """Разметка второго текста для режима сравнения (тем же бэкендом)."""
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, backend, text, freq_lookup, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.text = text
        self.freq_lookup = freq_lookup

    def run(self):
        try:
            tokens = self.backend.analyze(self.text)
            self.done.emit(og_engine.analyze(tokens, freq_lookup=self.freq_lookup))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class OgorelkovTab(QWidget):
    """Вкладка частотного анализа служебной лексики."""

    def __init__(self, nlp_backend=None, freq_lookup=None, parent=None):
        super().__init__(parent)
        self._backend = nlp_backend
        self._freq_lookup = freq_lookup
        self._result: dict | None = None      # текст 1 (основной анализ)
        self._result2: dict | None = None     # текст 2 (режим сравнения)
        self._thread: _SecondTextThread | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel(
            "Служебная лексика (Огорелков): относительные частоты ipm, "
            "нормирование по частотному словарю Ляшевской–Шарова")
        title.setObjectName("subtitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        top = QHBoxLayout()
        self.btn_compare = QPushButton("⚖ Загрузить текст для сравнения…")
        self.btn_compare.clicked.connect(self._load_second_text)
        top.addWidget(self.btn_compare)
        self.btn_clear2 = QPushButton("✕ Убрать сравнение")
        self.btn_clear2.clicked.connect(self._clear_second)
        self.btn_clear2.setEnabled(False)
        top.addWidget(self.btn_clear2)
        self.chk_export_detail = QCheckBox("Детальные таблицы в DOCX-отчёт")
        top.addWidget(self.chk_export_detail)
        top.addStretch()
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("QTreeWidget::item { padding: 4px 6px; }")
        layout.addWidget(self.tree, stretch=1)

        self.status_label = QLabel("Выполните анализ текста («Анализировать»).")
        self.status_label.setObjectName("caption")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    # ── данные ───────────────────────────────────────────────────────────────
    def populate(self, result: dict):
        """Показ результата основного анализа (вызывается из main_window)."""
        self._result = result
        self._rebuild()

    def clear(self):
        self._result = None
        self._result2 = None
        self.btn_clear2.setEnabled(False)
        self.tree.clear()

    def export_settings(self) -> tuple[dict | None, bool]:
        """(результат текста 1, включать ли детальные таблицы) — для DOCX."""
        return self._result, self.chk_export_detail.isChecked()

    # ── режим сравнения ──────────────────────────────────────────────────────
    def _load_second_text(self):
        if self._backend is None:
            QMessageBox.information(self, "Нет NLP", "Бэкенд не подключён.")
            return
        fp, _ = QFileDialog.getOpenFileName(
            self, "Текст для сравнения", "", "Тексты (*.txt *.docx);;Все файлы (*)")
        if not fp:
            return
        try:
            from analyzer.export import load_text_from_file
            text = load_text_from_file(fp)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка чтения", str(e))
            return
        self.status_label.setText("Разметка второго текста…")
        self.btn_compare.setEnabled(False)
        self._thread = _SecondTextThread(self._backend, text,
                                         self._freq_lookup, parent=self)
        self._thread.done.connect(self._on_second_done)
        self._thread.failed.connect(self._on_second_failed)
        self._thread.start()

    def _on_second_done(self, result: dict):
        self.btn_compare.setEnabled(True)
        self.btn_clear2.setEnabled(True)
        self._result2 = result
        self._rebuild()

    def _on_second_failed(self, msg: str):
        self.btn_compare.setEnabled(True)
        self.status_label.setText(f"Ошибка второго текста: {msg}")

    def _clear_second(self):
        self._result2 = None
        self.btn_clear2.setEnabled(False)
        self._rebuild()

    # ── отрисовка ────────────────────────────────────────────────────────────
    def _rebuild(self):
        self.tree.clear()
        if not self._result:
            self.status_label.setText("Выполните анализ текста («Анализировать»).")
            return
        compare = self._result2 is not None
        if compare:
            headers = ["Категория / лемма", "Вхождения (т1)", "ipm текст 1",
                       "ipm текст 2", "ipm НКРЯ", "коэф. т1", "коэф. т2"]
        else:
            headers = ["Категория / лемма", "Использовано лемм", "Вхождения",
                       "ipm", "доля %", "ipm НКРЯ", "коэф. отклонения"]
        self.tree.setColumnCount(len(headers))
        self.tree.setHeaderLabels(headers)
        hh = self.tree.header()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(0, 280)
        for c in range(1, len(headers)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        cats = self._result["categories"]
        cats2 = self._result2["categories"] if compare else {}
        for cat, data in cats.items():
            if compare:
                d2 = cats2.get(cat, {})
                top = QTreeWidgetItem([
                    cat.replace("_", " "),
                    str(data["total_count"]), _fmt(data["total_ipm"]),
                    _fmt(d2.get("total_ipm")), "", "", ""])
            else:
                top = QTreeWidgetItem([
                    cat.replace("_", " "),
                    f"{data['used']} из {data['total_lemmas']}",
                    str(data["total_count"]), _fmt(data["total_ipm"]),
                    _fmt(data["share_pct"]), "", ""])
            self.tree.addTopLevelItem(top)
            # Детальная таблица: сортировка по ipm текста по убыванию —
            # порядок уже обеспечен движком.
            lemmas2 = d2.get("lemmas", {}) if compare else {}
            for lem, ld in data["lemmas"].items():
                if compare:
                    l2 = lemmas2.get(lem, {})
                    row = QTreeWidgetItem([
                        lem, str(ld["count"]), _fmt(ld["ipm_text"]),
                        _fmt(l2.get("ipm_text", 0.0)), _fmt(ld["ipm_rnc"]),
                        _fmt(ld["ratio"]), _fmt(l2.get("ratio"))])
                else:
                    row = QTreeWidgetItem([
                        lem, "", str(ld["count"]), _fmt(ld["ipm_text"]),
                        "", _fmt(ld["ipm_rnc"]), _fmt(ld["ratio"])])
                top.addChild(row)

        n = self._result["total_words"]
        note2 = (f" Текст 2: {self._result2['total_words']} словоупотреблений."
                 if compare else "")
        self.status_label.setText(
            f"Словоупотреблений: {n}. Словарь маркеров: "
            f"sha256 {self._result['dict_sha256'][:12]}…{note2} "
            "Только наблюдаемые частоты — выводов модуль не формулирует.")
