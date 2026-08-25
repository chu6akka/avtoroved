"""
ui/tabs/feature_map_tab.py — вкладка «Карта признаков»: рабочее место эксперта.

Кандидаты признаков (из раздельного исследования) проверяются и получают
решение: принят / отклонён / сомнителен / не_учитывать. Решения хранятся
append-only (feature_decisions) + текущее состояние (features) и переживают
пересборку профиля (привязка по стабильному ключу содержимого).
Сравнительного исследования здесь нет — только отбор.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QTextEdit, QSplitter,
)

from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model
from protocol import PROGRAM_VERSION

# Цвета статусов.
_STATUS_COLOR = {
    fm.STATUS_ACCEPTED: "#a6e3a1",   # зелёный
    fm.STATUS_REJECTED: "#f38ba8",   # красный
    fm.STATUS_DOUBTFUL: "#f9e2af",   # жёлтый
    fm.STATUS_IGNORED: "#7f849c",    # приглушённый серый
}


class _AcceptDialog(QDialog):
    """Диалог принятия признака: ид. ценность + примечание эксперта."""

    def __init__(self, reference_value: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Принять признак")
        self.resize(440, 220)
        form = QFormLayout(self)
        self.id_combo = QComboBox()
        self.id_combo.addItem("— эксперт не оценил —", "")
        for value in fm.ID_VALUES:
            self.id_combo.addItem(value, value)
        form.addRow("Экспертная идентификационная ценность:", self.id_combo)
        ref = QLabel(reference_value or "не установлена источником")
        ref.setToolTip("Справочное значение источника не является решением эксперта")
        form.addRow("Справочно по источнику:", ref)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("Примечание эксперта (необязательно)…")
        self.note_edit.setMaximumHeight(90)
        form.addRow("Примечание:", self.note_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> tuple[str, str]:
        return self.id_combo.currentData() or "", self.note_edit.toPlainText().strip()


class FeatureMapTab(QWidget):
    """Вкладка «Карта признаков»: отбор кандидатов в признаки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._document_id: int | None = None
        self._pairs: list = []          # [(candidate_row, feature_row|None)] в порядке таблицы
        self._build_ui()
        self._reload_projects()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Карта признаков: экспертный отбор (без сравнения)")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(220)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo)
        top.addWidget(QLabel("Документ:"))
        self.doc_combo = QComboBox()
        self.doc_combo.setMinimumWidth(220)
        self.doc_combo.currentIndexChanged.connect(self._on_document_changed)
        top.addWidget(self.doc_combo)
        top.addStretch()
        layout.addLayout(top)

        # Фильтры отображения.
        filt = QHBoxLayout()
        self.chk_undecided = QCheckBox("Только нерешённые")
        self.chk_undecided.toggled.connect(self._reload_table)
        filt.addWidget(self.chk_undecided)
        self.chk_hide_low = QCheckBox("Скрывать низконадёжные")
        self.chk_hide_low.setChecked(True)
        self.chk_hide_low.toggled.connect(self._reload_table)
        filt.addWidget(self.chk_hide_low)
        filt.addWidget(QLabel("Группа:"))
        self.group_combo = QComboBox()
        self.group_combo.addItem("все группы", None)
        self.group_combo.currentIndexChanged.connect(self._reload_table)
        filt.addWidget(self.group_combo)
        filt.addStretch()
        layout.addLayout(filt)

        # Таблица кандидатов.
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Кандидат", "Группа", "Фрагмент", "Источник", "Методический ID",
             "Надёжн. детектора", "Справ. информ.", "Экспертная ценность", "Статус"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget::item { padding: 5px 7px; }")
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(0, 280)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for c in (1, 3, 4, 5, 6, 7, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection)

        # Панель деталей выбранного кандидата.
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        self.detail.setPlaceholderText("Выберите кандидата — здесь полный текст и решение.")

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([520, 120])
        layout.addWidget(split, stretch=1)

        # Кнопки решений (работают по выделенным строкам).
        btns = QHBoxLayout()
        self.btn_accept = QPushButton("✔ Принять")
        self.btn_accept.clicked.connect(self._accept_selected)
        btns.addWidget(self.btn_accept)
        self.btn_doubt = QPushButton("？ Сомнителен")
        self.btn_doubt.clicked.connect(lambda: self._decide_selected(fm.STATUS_DOUBTFUL))
        btns.addWidget(self.btn_doubt)
        self.btn_reject = QPushButton("✘ Отклонить")
        self.btn_reject.clicked.connect(lambda: self._decide_selected(fm.STATUS_REJECTED))
        btns.addWidget(self.btn_reject)
        self.btn_ignore = QPushButton("∅ Не учитывать")
        self.btn_ignore.clicked.connect(lambda: self._decide_selected(fm.STATUS_IGNORED))
        btns.addWidget(self.btn_ignore)
        self.btn_reset = QPushButton("↺ Сбросить решение")
        self.btn_reset.clicked.connect(lambda: self._decide_selected(fm.STATUS_RESET))
        btns.addWidget(self.btn_reset)
        btns.addStretch()
        layout.addLayout(btns)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("caption")
        layout.addWidget(self.progress_label)

    # ── выбор проекта/документа ──────────────────────────────────────────────
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
            self._reload_documents()
        else:
            self._project_id = None
            self.doc_combo.clear()

    def _on_project_changed(self, index: int):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self._reload_documents()

    def _reload_documents(self):
        self.doc_combo.blockSignals(True)
        self.doc_combo.clear()
        if self._project_id is not None:
            for d in self._pdb.fetch_documents(self._project_id):
                self.doc_combo.addItem(f"{d['filename']} ({d['role']})", d["id"])
        self.doc_combo.blockSignals(False)
        if self.doc_combo.count():
            self.doc_combo.setCurrentIndex(0)
            self._document_id = self.doc_combo.itemData(0)
        else:
            self._document_id = None
        self._reload_table()

    def _on_document_changed(self, index: int):
        self._document_id = self.doc_combo.itemData(index) if index >= 0 else None
        self._reload_table()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload_projects()

    # ── таблица ──────────────────────────────────────────────────────────────
    def _reload_table(self):
        self.table.setRowCount(0)
        self.detail.clear()
        self._pairs = []
        if self._document_id is None:
            self.progress_label.setText("Нет документа. Постройте профиль в «Раздельном исслед.».")
            return

        all_pairs = fm.candidates_with_state(self._pdb, self._document_id)
        st = fm.stats(all_pairs)

        # Обновить список групп (не сбрасывая выбор).
        current_group = self.group_combo.currentData()
        groups = sorted({c["group_name"] for c, _f in all_pairs})
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("все группы", None)
        for g in groups:
            self.group_combo.addItem(g, g)
        idx = self.group_combo.findData(current_group)
        self.group_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.group_combo.blockSignals(False)

        hide_low = self.chk_hide_low.isChecked()
        only_undecided = self.chk_undecided.isChecked()
        group_filter = self.group_combo.currentData()
        hidden_low = 0

        for cand, feat in all_pairs:
            if group_filter and cand["group_name"] != group_filter:
                continue
            if only_undecided and feat is not None:
                continue
            # Низконадёжные скрываем только среди нерешённых: решённые эксперт
            # уже видел, прятать их странно.
            if hide_low and feat is None and (cand["reliability"] or "") == "низкая":
                hidden_low += 1
                continue
            self._add_row(cand, feat)
            self._pairs.append((cand, feat))

        hid = f" Скрыто низконадёжных: {hidden_low}." if hidden_low else ""
        self.progress_label.setText(
            f"Решено {st['решено']} из {st['всего']} "
            f"(принято {st[fm.STATUS_ACCEPTED]}, отклонено {st[fm.STATUS_REJECTED]}, "
            f"сомнительно {st[fm.STATUS_DOUBTFUL]}, не учитывать {st[fm.STATUS_IGNORED]}, "
            f"нерешённых {st['нерешённые']}).{hid}")

    def _add_row(self, cand, feat):
        row = self.table.rowCount()
        self.table.insertRow(row)
        status = feat["status"] if feat is not None else "—"
        id_val = ((feat["expert_identification_value"] or feat["expert_id_value"])
                  if feat is not None else "")
        cells = [
            cand["label"], cand["group_name"], cand["fragment"] or "",
            cand["source"] or "", cand["method_feature_id"] or "",
            cand["detection_reliability"] or cand["reliability"] or "",
            cand["method_reference_informativeness"] or "", id_val, status,
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            if text:
                item.setToolTip(str(text))
            if col == 8 and status in _STATUS_COLOR:
                item.setForeground(QColor(_STATUS_COLOR[status]))
            if col == 5 and text == "низкая":
                item.setForeground(QColor("#f9e2af"))
            self.table.setItem(row, col, item)

    def _selected_pairs(self) -> list:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [self._pairs[r] for r in rows if 0 <= r < len(self._pairs)]

    def _on_selection(self):
        sel = self._selected_pairs()
        if not sel:
            self.detail.clear()
            return
        cand, feat = sel[0]
        parts = [f"<b>{cand['label']}</b>",
                 f"<span style='color:#a6adc8'>{cand['group_name']} · "
                 f"{cand['subgroup'] or ''} · {model.ROLE_LABELS[model.METHOD_FEATURE]} · "
                 f"{cand['source_kind'] or ''} · {cand['source'] or ''} · "
                 f"надёжность детектора: {cand['detection_reliability'] or cand['reliability'] or '—'}</span>",
                 f"<b>Методический ID:</b> {cand['method_feature_id'] or '—'}",
                 f"<b>Справочная информативность источника:</b> "
                 f"{cand['method_reference_informativeness'] or '—'} "
                 "(не решение эксперта)"]
        if cand["value"]:
            parts.append(f"<b>Значение:</b> {cand['value']}")
        if cand["fragment"]:
            parts.append(f"<b>Фрагмент:</b> {cand['fragment']}")
        if feat is not None:
            note = f" · примечание: {feat['expert_note']}" if feat["expert_note"] else ""
            parts.append(
                f"<b>Решение:</b> {feat['status']} ({feat['decided_at']})"
                f" · экспертная ид. ценность: "
                f"{feat['expert_identification_value'] or feat['expert_id_value'] or '—'}{note}")
        self.detail.setHtml("<br>".join(parts))

    # ── решения ──────────────────────────────────────────────────────────────
    def _accept_selected(self):
        sel = self._selected_pairs()
        if not sel:
            QMessageBox.information(self, "Нет выбора", "Выделите кандидатов в таблице.")
            return
        # Ид. ценность/примечание запрашиваем один раз для всей выборки.
        dlg = _AcceptDialog(
            sel[0][0]["method_reference_informativeness"] or "", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        id_value, note = dlg.values()
        for cand, _f in sel:
            fm.decide(self._pdb, self._project_id, self._document_id, cand,
                      fm.STATUS_ACCEPTED, expert_id_value=id_value,
                      expert_note=note, program_version=PROGRAM_VERSION)
        self._reload_table()

    def _decide_selected(self, status: str):
        sel = self._selected_pairs()
        if not sel:
            QMessageBox.information(self, "Нет выбора", "Выделите кандидатов в таблице.")
            return
        for cand, _f in sel:
            fm.decide(self._pdb, self._project_id, self._document_id, cand,
                      status, program_version=PROGRAM_VERSION)
        self._reload_table()
