"""
ui/tabs/suitability_tab.py — вкладка «Пригодность» раздела «Экспертный протокол».

Стадия оценки пригодности (гейт перед анализом): по каждому документу и каждой
паре спорный↔образец показывает вердикт с цветом, список красных флагов и
ключевые метрики. Кнопка «Пересчитать» перезапускает оценку и пишет результат
в таблицу suitability и в журнал. Сам расчёт — в protocol/suitability.py.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
)

from protocol import db as protocol_db
from protocol import suitability
from protocol import PROGRAM_VERSION

# Цвета вердикта: непригоден — красный, с ограничениями — жёлтый, пригоден — обычный.
_VERDICT_COLOR = {
    suitability.VERDICT_UNFIT: "#f38ba8",
    suitability.VERDICT_LIMITED: "#f9e2af",
    suitability.VERDICT_FIT: None,
}


class SuitabilityTab(QWidget):
    """Вкладка «Пригодность»: вердикты по документам и парам."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._build_ui()
        self._reload_projects()

    # ── построение UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Оценка пригодности материалов")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(280)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo)
        self.btn_recalc = QPushButton("🔄 Пересчитать пригодность")
        self.btn_recalc.clicked.connect(self._recalculate)
        top.addWidget(self.btn_recalc)
        top.addStretch()
        layout.addLayout(top)

        # ── Документы ────────────────────────────────────────────────────────
        layout.addWidget(QLabel("Документы"))
        self.doc_table = QTableWidget(0, 8)
        self.doc_table.setHorizontalHeaderLabels(
            ["Имя файла", "Роль", "Вердикт", "Флаги", "Слов", "Предлож.", "Цитаты", "Повторы"])
        self._tune_table(self.doc_table, stretch_col=3)
        layout.addWidget(self.doc_table, stretch=1)

        # ── Пары ─────────────────────────────────────────────────────────────
        layout.addWidget(QLabel("Пары: спорный ↔ образец"))
        self.pair_table = QTableWidget(0, 4)
        self.pair_table.setHorizontalHeaderLabels(
            ["Спорный", "Образец", "Вердикт", "Флаги"])
        self._tune_table(self.pair_table, stretch_col=3)
        layout.addWidget(self.pair_table, stretch=1)

        self.status_label = QLabel("Создайте проект и материалы во вкладке «Материалы».")
        self.status_label.setObjectName("caption")
        layout.addWidget(self.status_label)

    def _tune_table(self, table: QTableWidget, stretch_col: int):
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = table.horizontalHeader()
        for c in range(table.columnCount()):
            mode = (QHeaderView.ResizeMode.Stretch if c == stretch_col
                    else QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(c, mode)

    # ── проекты ──────────────────────────────────────────────────────────────
    def _reload_projects(self):
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = self._pdb.fetch_projects()
        for p in projects:
            self.project_combo.addItem(f"{p['name']} (#{p['id']})", p["id"])
        self.project_combo.blockSignals(False)
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._project_id = projects[0]["id"]
            self._reload_views()
        else:
            self._project_id = None
        self.btn_recalc.setEnabled(self._project_id is not None)

    def _on_project_changed(self, index: int):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self.btn_recalc.setEnabled(self._project_id is not None)
        self._reload_views()

    def showEvent(self, event):
        # Подхватываем проекты, созданные во вкладке «Материалы» уже после открытия.
        super().showEvent(event)
        self._reload_projects()

    # ── пересчёт ─────────────────────────────────────────────────────────────
    def _recalculate(self):
        if self._project_id is None:
            return
        docs = self._pdb.fetch_documents(self._project_id)
        if not docs:
            QMessageBox.information(self, "Нет материалов",
                                    "В проекте нет документов. Добавьте их во вкладке «Материалы».")
            return
        try:
            suitability.run_for_project(self._pdb, self._project_id, PROGRAM_VERSION)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка расчёта", str(e))
            return
        self._reload_views()
        self.status_label.setText("Пригодность пересчитана.")

    # ── отображение сохранённых оценок ───────────────────────────────────────
    def _reload_views(self):
        self.doc_table.setRowCount(0)
        self.pair_table.setRowCount(0)
        if self._project_id is None:
            return
        name_by_id = {d["id"]: d["filename"] for d in self._pdb.fetch_documents(self._project_id)}
        role_by_id = {d["id"]: d["role"] for d in self._pdb.fetch_documents(self._project_id)}
        rows = self._pdb.fetch_suitability(self._project_id)
        if not rows:
            self.status_label.setText("Нажмите «Пересчитать пригодность».")
            return

        for row in rows:
            flags = json.loads(row["flags"]) if row["flags"] else []
            metrics = json.loads(row["metrics"]) if row["metrics"] else {}
            flag_text = "; ".join(f["message"] for f in flags) or "—"
            if row["document_id"] is not None:
                self._add_doc_row(name_by_id, role_by_id, row, flag_text, metrics)
            else:
                self._add_pair_row(name_by_id, row, flag_text)

    def _add_doc_row(self, name_by_id, role_by_id, row, flag_text, metrics):
        did = row["document_id"]
        r = self.doc_table.rowCount()
        self.doc_table.insertRow(r)
        self._cell(self.doc_table, r, 0, name_by_id.get(did, f"#{did}"))
        self._cell(self.doc_table, r, 1, role_by_id.get(did, ""))
        self._verdict_cell(self.doc_table, r, 2, row["verdict"], bool(row["blocks_strong_conclusion"]))
        self._cell(self.doc_table, r, 3, flag_text)
        self._cell(self.doc_table, r, 4, str(metrics.get("word_count", "—")), right=True)
        self._cell(self.doc_table, r, 5, str(metrics.get("sentence_count", "—")), right=True)
        self._cell(self.doc_table, r, 6, f"{metrics.get('quote_share', 0):.0%}", right=True)
        self._cell(self.doc_table, r, 7, f"{metrics.get('repeat_share', 0):.0%}", right=True)

    def _add_pair_row(self, name_by_id, row, flag_text):
        r = self.pair_table.rowCount()
        self.pair_table.insertRow(r)
        self._cell(self.pair_table, r, 0, name_by_id.get(row["pair_doc_a"], f"#{row['pair_doc_a']}"))
        self._cell(self.pair_table, r, 1, name_by_id.get(row["pair_doc_b"], f"#{row['pair_doc_b']}"))
        self._verdict_cell(self.pair_table, r, 2, row["verdict"], bool(row["blocks_strong_conclusion"]))
        self._cell(self.pair_table, r, 3, flag_text)

    # ── ячейки ───────────────────────────────────────────────────────────────
    def _cell(self, table, row, col, text, right=False):
        item = QTableWidgetItem(text)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    def _verdict_cell(self, table, row, col, verdict, blocks):
        item = QTableWidgetItem(verdict)
        color = _VERDICT_COLOR.get(verdict)
        if color:
            item.setForeground(QColor(color))
        if blocks:
            item.setToolTip("Блокирует категорический вывод на следующих этапах "
                            "(blocks_strong_conclusion = 1)")
        table.setItem(row, col, item)
