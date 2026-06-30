"""
Вкладка 6: Сравнительное исследование текстов.

Структура — по методике Рубцовой 2007 (ЭКЦ МВД):
  два комплекса признаков (совпадающие / различающиеся), разнесённые
  по трём уровням НН/НС/НСВ; счётчик высокоинформативных совпадений
  против порога 20; вспомогательные объективизирующие метрики отдельно;
  подсказка по шкале (с. 85) и ПОЛЕ ДЛЯ ВЫВОДА ЭКСПЕРТА.

Модуль не выносит решение — окончательный вывод формулирует эксперт.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QTextEdit, QPushButton, QLabel,
    QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from analyzer import comparison_engine as ce

_MATCH_BG = QColor("#1e2e1e")
_DIFF_BG = QColor("#2e1e1e")


class ComparisonTab(QWidget):
    """Идентификационная задача: сравнительное исследование двух текстов."""

    compare_requested = pyqtSignal(str, str)
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._structured = None      # ComparisonResult
        self._aux = None             # вспомогательные метрики
        self._features = []          # CompFeature в порядке строк таблицы
        self._populating = False
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель: ввод текстов
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        g1 = QGroupBox("Текст 1")
        g1_layout = QVBoxLayout(g1)
        btn1 = QPushButton("📂 Загрузить")
        btn1.setObjectName("secondary")
        btn1.clicked.connect(lambda: self._load_file(1))
        g1_layout.addWidget(btn1)
        self.text1 = QTextEdit()
        self.text1.setPlaceholderText("Введите или загрузите первый текст...")
        g1_layout.addWidget(self.text1)
        left_layout.addWidget(g1)

        g2 = QGroupBox("Текст 2")
        g2_layout = QVBoxLayout(g2)
        btn2 = QPushButton("📂 Загрузить")
        btn2.setObjectName("secondary")
        btn2.clicked.connect(lambda: self._load_file(2))
        g2_layout.addWidget(btn2)
        self.text2 = QTextEdit()
        self.text2.setPlaceholderText("Введите или загрузите второй текст...")
        g2_layout.addWidget(self.text2)
        left_layout.addWidget(g2)

        self.btn_compare = QPushButton("▶ Сравнить тексты")
        self.btn_compare.clicked.connect(self._request_compare)
        left_layout.addWidget(self.btn_compare)
        splitter.addWidget(left)

        # Правая панель: результат
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # Счётчики + подсказка
        self.summary_lbl = QLabel("Выполните сравнение текстов.")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.setStyleSheet("font-size:11px; padding:4px;")
        right_layout.addWidget(self.summary_lbl)

        # Таблица признаков (два комплекса по уровням)
        feat_group = QGroupBox("Сопоставление признаков (НН / НС / НСВ)")
        fg_layout = QVBoxLayout(feat_group)
        hint_hdr = QLabel("Отметьте «высокоинф.» для высокоинформативных признаков "
                          "(методика, с. 35/85) — подсказка пересчитается.")
        hint_hdr.setStyleSheet("font-size:10px; color:#8a8278;")
        hint_hdr.setWordWrap(True)
        fg_layout.addWidget(hint_hdr)

        self.feat_table = QTableWidget()
        self.feat_table.setColumnCount(6)
        self.feat_table.setHorizontalHeaderLabels(
            ["Комплекс", "Ур.", "Признак", "Текст 1", "Текст 2", "Высокоинф."])
        hh = self.feat_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.feat_table.verticalHeader().setVisible(False)
        self.feat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.feat_table.itemChanged.connect(self._on_item_changed)
        fg_layout.addWidget(self.feat_table)
        right_layout.addWidget(feat_group, stretch=3)

        # Вспомогательные метрики
        aux_group = QGroupBox("Вспомогательные объективизирующие показатели (не являются выводом)")
        aux_layout = QVBoxLayout(aux_group)
        self.aux_table = QTableWidget()
        self.aux_table.setColumnCount(2)
        self.aux_table.setHorizontalHeaderLabels(["Показатель", "Значение"])
        self.aux_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.aux_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.aux_table.verticalHeader().setVisible(False)
        self.aux_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.aux_table.setMaximumHeight(160)
        aux_layout.addWidget(self.aux_table)
        right_layout.addWidget(aux_group, stretch=1)

        # Поле вывода эксперта
        exp_group = QGroupBox("Вывод эксперта (формулируется экспертом)")
        exp_layout = QVBoxLayout(exp_group)
        self.expert_verdict = QTextEdit()
        self.expert_verdict.setPlaceholderText(
            "Здесь эксперт формулирует окончательный вывод на основе совокупности "
            "признаков и подсказки (программа решение не выносит).")
        self.expert_verdict.setMaximumHeight(90)
        exp_layout.addWidget(self.expert_verdict)
        right_layout.addWidget(exp_group, stretch=1)

        btn_export = QPushButton("📄 Экспорт в DOCX")
        btn_export.setObjectName("secondary")
        btn_export.clicked.connect(self.export_requested)
        right_layout.addWidget(btn_export)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # ── Ввод ──────────────────────────────────────────────────────────────
    def _load_file(self, num: int):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Открыть текст", "", "Тексты (*.txt *.docx);;Все файлы (*)")
        if not fp:
            return
        try:
            from analyzer.export import load_text_from_file
            text = load_text_from_file(fp)
            (self.text1 if num == 1 else self.text2).setPlainText(text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _request_compare(self):
        t1 = self.text1.toPlainText().strip()
        t2 = self.text2.toPlainText().strip()
        if not t1 or not t2:
            QMessageBox.warning(self, "Нет текстов", "Введите оба текста для сравнения.")
            return
        self.compare_requested.emit(t1, t2)

    # ── Отображение результата ────────────────────────────────────────────
    def show_result(self, structured, aux: dict):
        self._structured = structured
        self._aux = aux or {}

        # Признаки: сначала совпадающие, затем различающиеся; внутри — по уровням
        order = {"НН": 0, "НС": 1, "НСВ": 2}
        self._features = (
            sorted(structured.matches, key=lambda f: order.get(f.level, 9))
            + sorted(structured.diffs, key=lambda f: order.get(f.level, 9))
        )

        self._populating = True
        self.feat_table.setRowCount(len(self._features))
        for r, f in enumerate(self._features):
            is_match = (f.kind == "match")
            c0 = QTableWidgetItem("СОВПАД." if is_match else "РАЗЛИЧ.")
            c1 = QTableWidgetItem(f.level)
            c2 = QTableWidgetItem(f.name + (" ⟲" if f.stable else ""))
            if f.note:
                c2.setToolTip(f.note)
            c3 = QTableWidgetItem(f.value1)
            c4 = QTableWidgetItem(f.value2)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if f.high_informative
                              else Qt.CheckState.Unchecked)
            bg = _MATCH_BG if is_match else _DIFF_BG
            for c in (c0, c1, c2, c3, c4, chk):
                c.setBackground(bg)
            for c in (c0, c1, c2, c3, c4):
                c.setFlags(c.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.feat_table.setItem(r, 0, c0)
            self.feat_table.setItem(r, 1, c1)
            self.feat_table.setItem(r, 2, c2)
            self.feat_table.setItem(r, 3, c3)
            self.feat_table.setItem(r, 4, c4)
            self.feat_table.setItem(r, 5, chk)
        self._populating = False

        self._fill_aux()
        self._refresh_summary()

    def _fill_aux(self):
        labels = [
            ("Общее сходство (агрегат)", "overall"),
            ("Лексическое (Jaccard)", "jaccard"),
            ("Морфологическое (POS)", "pos_similarity"),
            ("Синтаксическое", "syntactic_similarity"),
            ("TTR-сходство", "ttr_similarity"),
            ("POS-биграммное", "bigram_similarity"),
            ("SBERT (семантическое)", "sbert_sim"),
        ]
        rows = [(lbl, self._aux[k]) for lbl, k in labels if k in self._aux]
        self.aux_table.setRowCount(len(rows))
        for i, (lbl, val) in enumerate(rows):
            ki = QTableWidgetItem(lbl)
            vi = QTableWidgetItem(f"{val:.1%}" if isinstance(val, (int, float)) else str(val))
            for it in (ki, vi):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.aux_table.setItem(i, 0, ki)
            self.aux_table.setItem(i, 1, vi)

    def _on_item_changed(self, item):
        if self._populating or item.column() != 5:
            return
        row = item.row()
        if 0 <= row < len(self._features):
            self._features[row].high_informative = (
                item.checkState() == Qt.CheckState.Checked)
            ce.recompute_hint(self._structured)
            # пересчитать счётчики высокоинформативных
            self._structured.high_informative_matches = sum(
                1 for f in self._structured.matches if f.high_informative)
            self._structured.high_informative_diffs = sum(
                1 for f in self._structured.diffs if f.high_informative)
            self._refresh_summary()

    def _refresh_summary(self):
        s = self._structured
        if s is None:
            return
        ls = s.level_summary
        lvl_txt = "  ".join(
            f"{lv}: +{ls.get(lv, {}).get('match', 0)}/−{ls.get(lv, {}).get('diff', 0)}"
            for lv in ("НН", "НС", "НСВ"))
        ok = s.high_informative_matches >= s.threshold
        basis = ("; ".join(s.hint_basis)) if s.hint_basis else "—"
        self.summary_lbl.setText(
            f"<b>Признаков всего:</b> {s.total_features}  "
            f"(совпадений {len(s.matches)}, различий {len(s.diffs)})<br>"
            f"<b>По уровням:</b> {lvl_txt}<br>"
            f"<b>Высокоинформативных совпадений:</b> {s.high_informative_matches} / "
            f"порог {s.threshold} "
            f"<span style='color:{'#6abf69' if ok else '#e8a030'}'>"
            f"({'порог достигнут' if ok else 'ниже порога'})</span><br>"
            f"<b>Подсказка (не вывод):</b> {s.hint}<br>"
            f"<span style='color:#8a8278; font-size:10px'>основание: {basis}. "
            f"Окончательный вывод формулирует эксперт.</span>")

    # ── API для main_window / экспорта ────────────────────────────────────
    def get_expert_verdict(self) -> str:
        return self.expert_verdict.toPlainText().strip()

    def get_last_comparison(self):
        return self._structured

    def get_texts(self):
        return self.text1.toPlainText(), self.text2.toPlainText()

    def clear(self):
        self.feat_table.setRowCount(0)
        self.aux_table.setRowCount(0)
        self.expert_verdict.clear()
        self.summary_lbl.setText("Выполните сравнение текстов.")
        self._structured = None
        self._aux = None
        self._features = []
