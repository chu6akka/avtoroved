"""
ui/tabs/separate_research_tab.py — вкладка «Раздельное исследование».

Стадия построения профиля КАЖДОГО текста по отдельности (Огорелков/Моисеева:
раздельное исследование предшествует сравнительному). Профиль группируется по
четырём группам признаков и подгруппам; методические признаки, вспомогательные
метрики, наблюдения-доказательства и общие навыки показаны раздельно. Здесь
нет автоматической экспертной идентификационной оценки. Сравнений между
документами здесь НЕТ — это будущий этап.
Расчёт — protocol/profile.py, запись — feature_candidates + audit_log.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox, QTextEdit, QSplitter,
    QCheckBox,
)

from protocol import db as protocol_db
from protocol import feature_model as model
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
_ROLE_COLOR = {
    model.METHOD_FEATURE: "#a6e3a1",
    model.AUX_METRIC: "#89b4fa",
    model.EVIDENCE: "#f9e2af",
    model.GENERAL_SKILL: "#cba6f7",
}


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
        # Фильтр сомнительных кандидатов (надёжность «низкая») — по умолчанию скрыты.
        self.chk_hide_low = QCheckBox("Скрывать низконадёжные")
        self.chk_hide_low.setChecked(True)
        self.chk_hide_low.setToolTip(
            "Кандидаты с надёжностью «низкая» (сомнительные правила детектора, "
            "автокоррекция) скрыты. Снимите галочку, чтобы показать их.")
        self.chk_hide_low.toggled.connect(self._reload_tree)
        top.addWidget(self.chk_hide_low)
        # Сырые срабатывания, подавленные фильтром детектора, — для
        # воспроизводимости: видно, что и почему убрал фильтр.
        self.chk_show_suppressed = QCheckBox("Показать подавленные фильтром")
        self.chk_show_suppressed.setChecked(False)
        self.chk_show_suppressed.toggled.connect(self._reload_tree)
        top.addWidget(self.chk_show_suppressed)
        top.addStretch()
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(8)
        self.tree.setHeaderLabels(
            ["Элемент профиля", "Роль", "Значение", "Фрагмент", "Источник",
             "Методический ID", "Справ. информ.", "Надёжн. детектора"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(20)
        self.tree.setUniformRowHeights(False)
        self.tree.setWordWrap(True)
        # Просторные строки: без этого дерево сливается в нечитаемую простыню.
        self.tree.setStyleSheet(
            "QTreeWidget::item { padding: 6px 8px; }"
            "QTreeWidget { font-size: 13px; }")
        hh = self.tree.header()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(0, 340)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(2, 280)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._on_selection)

        # Панель деталей: полный текст значения/фрагмента выбранной строки —
        # решает проблему обрезанных колонок.
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText(
            "Выберите строку профиля — здесь появится полное значение и фрагмент.")
        self.detail.setMaximumHeight(160)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(self.tree)
        split.addWidget(self.detail)
        split.setSizes([560, 130])
        layout.addWidget(split, stretch=1)

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
    # Русские названия групп для заголовков с пояснением.
    _GROUP_TITLES = {
        profile_mod.GROUP_SEMANTIC: "📚 Смысловые (тематика — слабый признак автора)",
        profile_mod.GROUP_TEXTOLOGICAL: "📐 Текстологические (архитектоника текста)",
        profile_mod.GROUP_LINGUISTIC: "🔤 Языковые",
        profile_mod.GROUP_PSYCHO: "🧠 Психолингвистические (интерпретация — эксперту)",
    }
    def _reload_tree(self):
        self.tree.clear()
        self.detail.clear()
        if self._document_id is None:
            return
        all_rows = self._pdb.fetch_feature_candidates(self._document_id)
        if not all_rows:
            self.status_label.setText("Профиль не построен. Нажмите «Построить профиль».")
            return

        # Скрытие низконадёжных (по умолчанию) и подавленных (по умолчанию).
        hide_low = self.chk_hide_low.isChecked()
        show_suppressed = self.chk_show_suppressed.isChecked()
        rows = []
        hidden = 0
        hidden_suppressed = 0
        for r in all_rows:
            rel = r["detection_reliability"] or r["reliability"] or ""
            if rel == "подавлен" and not show_suppressed:
                hidden_suppressed += 1
                continue
            if hide_low and rel == "низкая":
                hidden += 1
                continue
            rows.append(r)
        if not rows and (hidden or hidden_suppressed):
            self.status_label.setText(
                f"⚠ Все кандидаты скрыты (низконадёжных: {hidden}, подавленных: "
                f"{hidden_suppressed}) — снимите галочку «Скрывать низконадёжные» "
                "или включите «Показать подавленные фильтром».")
            return

        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(bold.pointSize() + 1)
        sub_bold = QFont()
        sub_bold.setBold(True)

        # группа → подгруппа → элементы
        by_group: dict[str, dict[str, list]] = {}
        for r in rows:
            by_group.setdefault(r["group_name"], {}).setdefault(r["subgroup"] or "—", []).append(r)

        for group in _GROUP_ORDER + [g for g in by_group if g not in _GROUP_ORDER]:
            if group not in by_group:
                continue
            n_in_group = sum(len(v) for v in by_group[group].values())
            title = self._GROUP_TITLES.get(group, group.upper())
            g_item = QTreeWidgetItem([f"{title}  —  {n_in_group}"])
            g_item.setFont(0, bold)
            g_item.setBackground(0, QColor("#313244"))
            self.tree.addTopLevelItem(g_item)
            g_item.setFirstColumnSpanned(True)
            for subgroup, items in by_group[group].items():
                parent = g_item
                if subgroup != "—":
                    parent = QTreeWidgetItem([f"{subgroup}  ({len(items)})"])
                    parent.setFont(0, sub_bold)
                    g_item.addChild(parent)
                    parent.setFirstColumnSpanned(True)
                for r in items:
                    self._add_row(parent, r)
                parent.setExpanded(True)
            g_item.setExpanded(True)
        notes = []
        if hidden:
            notes.append(f"⚠ скрыто низконадёжных: {hidden} (галочка выше)")
        if hidden_suppressed:
            notes.append(f"подавлено фильтром: {hidden_suppressed}")
        hidden_note = (" " + "; ".join(notes) + ".") if notes else ""
        self.status_label.setText(
            f"Элементов профиля: {len(rows)}.{hidden_note} "
            "Клик по строке — полный текст внизу.")

    def _add_row(self, parent: QTreeWidgetItem, r):
        value = r["value"] or ""
        role = model.normalized_role(r)
        role_badge = model.ROLE_LABELS.get(role, role)
        if r["source_kind"] == model.EXPERIMENTAL:
            role_badge += " · [ЭКСПЕРИМЕНТАЛЬНО]"
        reliability = r["detection_reliability"] or r["reliability"] or ""
        source = r["source"] or ""
        if r["source_kind"]:
            source = f"{model.SOURCE_KIND_LABELS.get(r['source_kind'], r['source_kind'])}: {source}"
        item = QTreeWidgetItem([
            r["label"], role_badge, value, r["fragment"] or "",
            source, r["method_feature_id"] or "",
            r["method_reference_informativeness"] or "", reliability])
        if reliability == "низкая":
            item.setForeground(7, QColor(_UNRELIABLE_COLOR))
        # Полный текст каждой ячейки — во всплывающей подсказке.
        for col, text in ((0, r["label"]), (2, value), (3, r["fragment"] or ""),
                          (4, source), (5, r["method_feature_id"] or "")):
            if text:
                item.setToolTip(col, text)
        if profile_mod.NOTE_UNRELIABLE_AUTOCORRECT in value:
            for col in range(item.columnCount()):
                item.setForeground(col, QColor(_UNRELIABLE_COLOR))
            item.setToolTip(2, "Ненадёжен: происхождение текста предполагает автокоррекцию")
        else:
            item.setForeground(1, QColor(_ROLE_COLOR.get(role, "#cdd6f4")))
        # Данные строки для панели деталей.
        item.setData(0, Qt.ItemDataRole.UserRole, dict(r))
        parent.addChild(item)

    def _on_selection(self):
        """Показать полное значение и фрагмент выбранной строки внизу."""
        items = self.tree.selectedItems()
        if not items:
            return
        r = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not r:
            self.detail.clear()
            return
        parts = [f"<b>{r['label']}</b>"]
        role = model.normalized_role(r)
        meta = " · ".join(x for x in (
            model.ROLE_LABELS.get(role, role), r.get("subgroup"),
            model.SOURCE_KIND_LABELS.get(r.get("source_kind"), r.get("source_kind")),
            r.get("source"),
            f"методический ID: {r['method_feature_id']}" if r.get("method_feature_id") else "",
            (f"справочная информативность: {r['method_reference_informativeness']}"
             if r.get("method_reference_informativeness") else ""),
            (f"надёжность детектора: {r['detection_reliability'] or r['reliability']}"
             if r.get("detection_reliability") or r.get("reliability") else "")) if x)
        if meta:
            parts.append(f"<span style='color:#a6adc8'>{meta}</span>")
        if r.get("value"):
            parts.append(f"<b>Значение:</b> {r['value']}")
        if r.get("fragment"):
            parts.append(f"<b>Фрагмент:</b> {r['fragment']}")
        self.detail.setHtml("<br>".join(parts))

    def _update_buttons(self):
        self.btn_build.setEnabled(self._document_id is not None)
