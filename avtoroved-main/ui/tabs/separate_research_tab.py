"""
ui/tabs/separate_research_tab.py — вкладка «Раздельное исследование».

Стадия построения профиля КАЖДОГО текста по отдельности (Огорелков/Моисеева:
раздельное исследование предшествует сравнительному). Профиль группируется по
четырём группам признаков и подгруппам; видно, что счётчик, а что
кандидат-признак; видна идентификационная ценность и пометка ненадёжности
(автокоррекция). Сравнений между документами здесь НЕТ — это будущий этап.
Расчёт — protocol/profile.py, запись — feature_candidates + audit_log.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
)

from protocol import db as protocol_db
from protocol import profile as profile_mod
from protocol import PROGRAM_VERSION

# Порядок групп в дереве — по методике.
_GROUP_ORDER = [
    profile_mod.GROUP_SEMANTIC,
    profile_mod.GROUP_TEXTOLOGICAL,
    profile_mod.GROUP_LINGUISTIC,
    profile_mod.GROUP_PSYCHO,
]

_UNRELIABLE_COLOR = "#f9e2af"   # жёлтый — ненадёжные кандидаты (автокоррекция)
_CANDIDATE_COLOR = "#89dceb"    # голубой — кандидат-признак (в отличие от счётчика)


class _ProfileThread(QThread):
    """Фоновая пересборка профиля документа (Stanza переиспользуется)."""
    status = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, pdb, project_id, document_id, backend, parent=None):
        super().__init__(parent)
        self.pdb = pdb
        self.project_id = project_id
        self.document_id = document_id
        self.backend = backend

    def run(self):
        try:
            summary = profile_mod.run_for_document(
                self.pdb, self.project_id, self.document_id, self.backend,
                program_version=PROGRAM_VERSION, status_cb=self.status.emit)
            self.done.emit(summary)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SeparateResearchTab(QWidget):
    """Вкладка «Раздельное исследование»: профиль одного текста, без сравнения."""

    def __init__(self, nlp_backend, parent=None):
        super().__init__(parent)
        self._backend = nlp_backend
        self._pdb = protocol_db.ProtocolDB()
        self._project_id: int | None = None
        self._document_id: int | None = None
        self._thread: _ProfileThread | None = None
        self._build_ui()
        self._reload_projects()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Раздельное исследование: профиль текста (без сравнения)")
        title.setObjectName("subtitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Проект:"))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(240)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo)
        top.addWidget(QLabel("Документ:"))
        self.doc_combo = QComboBox()
        self.doc_combo.setMinimumWidth(240)
        self.doc_combo.currentIndexChanged.connect(self._on_document_changed)
        top.addWidget(self.doc_combo)
        self.btn_build = QPushButton("🧩 Построить профиль")
        self.btn_build.clicked.connect(self._build_profile)
        top.addWidget(self.btn_build)
        top.addStretch()
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            ["Группа / элемент", "Вид", "Значение", "Фрагмент", "Источник", "Ид. ценность"])
        hh = self.tree.header()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tree, stretch=1)

        self.status_label = QLabel("Выберите документ и постройте профиль.")
        self.status_label.setObjectName("caption")
        layout.addWidget(self.status_label)

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
        self._update_buttons()

    def _on_project_changed(self, index: int):
        self._project_id = self.project_combo.itemData(index) if index >= 0 else None
        self._reload_documents()
        self._update_buttons()

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
            self._reload_tree()
        else:
            self._document_id = None
            self.tree.clear()
        self._update_buttons()

    def _on_document_changed(self, index: int):
        self._document_id = self.doc_combo.itemData(index) if index >= 0 else None
        self._reload_tree()
        self._update_buttons()

    def showEvent(self, event):
        # Подхватить проекты/документы, добавленные в других вкладках.
        super().showEvent(event)
        self._reload_projects()

    # ── пересборка профиля ───────────────────────────────────────────────────
    def _build_profile(self):
        if self._project_id is None or self._document_id is None:
            QMessageBox.information(self, "Нет документа",
                                    "Добавьте материалы во вкладке «Материалы».")
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self.btn_build.setEnabled(False)
        self._thread = _ProfileThread(
            self._pdb, self._project_id, self._document_id, self._backend, parent=self)
        self._thread.status.connect(self.status_label.setText)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_done(self, summary: dict):
        self.btn_build.setEnabled(True)
        note = " — орфогр./пункт. кандидаты помечены ненадёжными (автокоррекция)" \
            if summary.get("autocorrect_unreliable") else ""
        self.status_label.setText(
            f"Профиль построен: {summary['count']} элементов{note}.")
        self._reload_tree()

    def _on_failed(self, msg: str):
        self.btn_build.setEnabled(True)
        self.status_label.setText("Ошибка построения профиля.")
        QMessageBox.critical(self, "Ошибка", msg)

    # ── отображение сохранённого профиля ─────────────────────────────────────
    def _reload_tree(self):
        self.tree.clear()
        if self._document_id is None:
            return
        rows = self._pdb.fetch_feature_candidates(self._document_id)
        if not rows:
            self.status_label.setText("Профиль не построен. Нажмите «Построить профиль».")
            return

        # группа → подгруппа → элементы
        by_group: dict[str, dict[str, list]] = {}
        for r in rows:
            by_group.setdefault(r["group_name"], {}).setdefault(r["subgroup"] or "—", []).append(r)

        for group in _GROUP_ORDER + [g for g in by_group if g not in _GROUP_ORDER]:
            if group not in by_group:
                continue
            g_item = QTreeWidgetItem([group.upper()])
            self.tree.addTopLevelItem(g_item)
            for subgroup, items in by_group[group].items():
                parent = g_item
                if subgroup != "—":
                    parent = QTreeWidgetItem([subgroup])
                    g_item.addChild(parent)
                for r in items:
                    self._add_row(parent, r)
            g_item.setExpanded(True)
        self.status_label.setText(f"Элементов профиля: {len(rows)}.")

    def _add_row(self, parent: QTreeWidgetItem, r):
        value = r["value"] or ""
        item = QTreeWidgetItem([
            r["label"], r["kind"], value, r["fragment"] or "",
            r["source"] or "", r["id_value"] or ""])
        if profile_mod.NOTE_UNRELIABLE_AUTOCORRECT in value:
            for col in range(item.columnCount()):
                item.setForeground(col, QColor(_UNRELIABLE_COLOR))
            item.setToolTip(2, "Ненадёжен: происхождение текста предполагает автокоррекцию")
        elif r["kind"] == profile_mod.KIND_CANDIDATE:
            item.setForeground(1, QColor(_CANDIDATE_COLOR))
        parent.addChild(item)

    def _update_buttons(self):
        self.btn_build.setEnabled(self._document_id is not None)
