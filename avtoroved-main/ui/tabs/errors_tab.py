"""
Вкладка 3: Ошибки и навыки (по методике С.М. Вул).
Включает результаты собственного анализатора, pymorphy2 и LanguageTool.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QGridLayout, QFrame, QPushButton, QComboBox,
    QSplitter, QTextEdit, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QFont


SKILL_COLORS = {
    "высокая":  "#a6e3a1",
    "средняя":  "#fab387",
    "низкая":   "#f38ba8",
    "нулевая":  "#cba6f7",
}

SKILL_NAMES = [
    "Пунктуационные навыки",
    "Орфографические навыки",
    "Грамматические навыки",
    "Лексико-фразеологические навыки",
]

# Цвета фона строки по источнику
_SOURCE_ROW_COLORS = {
    "LT":    "#3d2d1e",   # тёмно-оранжевый — LanguageTool
    "MORPH": "#2a2040",   # тёмно-синий — морфословарь
    "TAUT":  "#1e3040",   # тёмно-голубой — тавтология
    "LEX":   "#1e2a1e",   # тёмно-зелёный — словарная орфография
    "GRAM":  "#2a1e2a",   # тёмно-фиолетовый — грамматика
    "REGEX": "#2a2020",   # тёмно-серый — прочее
}

_SOURCE_LABELS = {
    "LT":    "LanguageTool",
    "MORPH": "Морфословарь",
    "TAUT":  "Тавтология",
    "LEX":   "Словарь",
    "GRAM":  "Грамматика",
    "REGEX": "Правила",
}

_SOURCE_COLORS = {
    "LT":    "#fab387",
    "MORPH": "#cba6f7",
    "TAUT":  "#89dceb",
    "LEX":   "#a6e3a1",
    "GRAM":  "#f9e2af",
    "REGEX": "#cdd6f4",
}

# Цвета подсветки в тексте
HIGHLIGHT_COLORS = {
    "Пунктуационная": "#f9e2af",
    "Орфографическая": "#f38ba8",
    "Грамматическая":  "#cba6f7",
    "Лексическая":     "#89dceb",
    "Стилистическая":  "#a6e3a1",
}


class SkillBadge(QFrame):
    """Карточка уровня навыка."""

    def __init__(self, skill_name: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self.name_label = QLabel(skill_name.replace(" навыки", ""))
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.level_label = QLabel("—")
        self.level_label.setStyleSheet("font-size: 13px;")
        self.desc_label = QLabel("")
        self.desc_label.setStyleSheet("font-size: 11px; color: #a6adc8;")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.name_label)
        layout.addWidget(self.level_label)
        layout.addWidget(self.desc_label)

    def update_skill(self, level: str, description: str):
        color = SKILL_COLORS.get(level.lower(), "#cdd6f4")
        self.level_label.setText(level.upper())
        self.level_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
        self.desc_label.setText(description)


class ErrorsTab(QWidget):
    """Вкладка ошибок и степеней развития навыков."""

    error_selected = pyqtSignal(int, int)          # start, end — подсветить одну ошибку
    highlight_all_requested = pyqtSignal(list)     # [(start, end, type), ...] — подсветить все

    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors = []          # все ошибки (после фильтра)
        self._all_errors = []      # без фильтра
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Навыки ───────────────────────────────────────────────────────
        skills_group = QGroupBox("Степени развития языковых навыков (по С.М. Вул, 2007)")
        skills_layout = QGridLayout(skills_group)
        skills_layout.setSpacing(8)
        self.skill_badges = {}
        for i, name in enumerate(SKILL_NAMES):
            badge = SkillBadge(name)
            self.skill_badges[name] = badge
            skills_layout.addWidget(badge, i // 2, i % 2)
        layout.addWidget(skills_group)

        # ── Панель управления ────────────────────────────────────────────
        ctrl_row = QHBoxLayout()

        ctrl_row.addWidget(QLabel("Источник:"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("Все источники", "all")
        self.source_filter.addItem("LanguageTool",   "LT")
        self.source_filter.addItem("Морфословарь",   "MORPH")
        self.source_filter.addItem("Тавтология",     "TAUT")
        self.source_filter.addItem("Словарь",        "LEX")
        self.source_filter.addItem("Грамматика",     "GRAM")
        self.source_filter.currentIndexChanged.connect(self._apply_filter)
        ctrl_row.addWidget(self.source_filter)

        ctrl_row.addWidget(QLabel("  Тип:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("Все типы", "all")
        for t in ["Пунктуационная", "Орфографическая", "Грамматическая",
                  "Лексическая", "Стилистическая"]:
            self.type_filter.addItem(t, t)
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        ctrl_row.addWidget(self.type_filter)

        ctrl_row.addStretch()

        self.btn_highlight_all = QPushButton("🎨 Подсветить все в тексте")
        self.btn_highlight_all.setObjectName("secondary")
        self.btn_highlight_all.clicked.connect(self._emit_highlight_all)
        ctrl_row.addWidget(self.btn_highlight_all)

        layout.addLayout(ctrl_row)

        # ── Сплиттер: таблица + панель деталей ───────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Верхняя часть: таблица
        table_group = QGroupBox("Выявленные речевые ошибки  (ПКМ = контекстное меню)")
        table_layout = QVBoxLayout(table_group)

        self.errors_table = QTableWidget()
        self.errors_table.setColumnCount(5)
        self.errors_table.setHorizontalHeaderLabels(
            ["Источник", "Тип", "Подтип", "Фрагмент", "Описание"])
        hdr = self.errors_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.errors_table.setAlternatingRowColors(False)
        self.errors_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.errors_table.verticalHeader().setVisible(False)
        self.errors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.errors_table.itemSelectionChanged.connect(self._on_error_selected)
        # Контекстное меню по ПКМ
        self.errors_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.errors_table.customContextMenuRequested.connect(self._show_context_menu)
        table_layout.addWidget(self.errors_table)

        # Легенда источников
        legend_row = QHBoxLayout()
        legend_row.addWidget(QLabel("Источники:"))
        for src, label in _SOURCE_LABELS.items():
            color = _SOURCE_COLORS[src]
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 16px;")
            legend_row.addWidget(dot)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; margin-right: 6px;")
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        table_layout.addLayout(legend_row)

        self.count_label = QLabel("Ошибок не обнаружено")
        self.count_label.setObjectName("subtitle")
        table_layout.addWidget(self.count_label)

        splitter.addWidget(table_group)

        # Нижняя часть: панель деталей
        detail_group = QGroupBox("Подробная информация об ошибке")
        detail_layout = QVBoxLayout(detail_group)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(150)
        mono = QFont("Consolas", 10)
        self.detail_text.setFont(mono)
        self.detail_text.setPlaceholderText(
            "Выберите ошибку в таблице — здесь появятся подробности.\n"
            "Правая кнопка мыши → контекстное меню с действиями."
        )
        detail_layout.addWidget(self.detail_text)
        splitter.addWidget(detail_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    # ── Заполнение данными ────────────────────────────────────────────────

    def populate(self, error_result):
        """Заполнить вкладку результатами анализа ошибок."""
        self._all_errors = error_result.errors if error_result else []

        if error_result:
            for skill in error_result.skill_levels:
                if skill.skill_name in self.skill_badges:
                    self.skill_badges[skill.skill_name].update_skill(
                        skill.level, skill.description)

        self._apply_filter()

    def _get_source(self, err) -> str:
        """Определить источник ошибки."""
        src = getattr(err, 'source', 'REGEX')
        if src == 'REGEX' and getattr(err, 'rule_ref', '').startswith('LT:'):
            return 'LT'
        return src

    def _apply_filter(self):
        """Применить фильтры источника и типа."""
        source_key = self.source_filter.currentData()
        type_key   = self.type_filter.currentData()

        filtered = []
        for err in self._all_errors:
            src = self._get_source(err)
            if source_key != "all" and src != source_key:
                continue
            if type_key != "all" and err.error_type != type_key:
                continue
            filtered.append(err)

        self._errors = filtered
        self._fill_table(filtered)

    def _fill_table(self, errors: list):
        self.errors_table.setRowCount(len(errors))
        for row, err in enumerate(errors):
            src = self._get_source(err)
            src_label = _SOURCE_LABELS.get(src, src)
            src_color = _SOURCE_COLORS.get(src, "#cdd6f4")
            row_bg    = _SOURCE_ROW_COLORS.get(src, "#2a2020")

            frag = err.fragment
            if len(frag) > 40:
                frag = frag[:38] + "…"
            desc = err.description
            if len(desc) > 70:
                desc = desc[:68] + "…"

            vals = [src_label, err.error_type, err.subtype, frag, desc]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(QColor(row_bg))
                if col == 0:
                    item.setForeground(QColor(src_color))
                self.errors_table.setItem(row, col, item)

        # Счётчик по источникам
        by_src: dict = {}
        for e in self._all_errors:
            s = self._get_source(e)
            by_src[s] = by_src.get(s, 0) + 1
        shown = len(errors)
        total = len(self._all_errors)

        if total == 0:
            self.count_label.setText("Ошибок не обнаружено")
        else:
            parts = [f"{_SOURCE_LABELS.get(s, s)}: {c}" for s, c in sorted(by_src.items())]
            self.count_label.setText(
                f"Показано: {shown} из {total}  ·  {',  '.join(parts)}"
            )

    # ── Панель деталей (одиночный клик) ──────────────────────────────────

    def _on_error_selected(self):
        row = self.errors_table.currentRow()
        if 0 <= row < len(self._errors):
            err = self._errors[row]
            self._show_detail(err)
            if err.position != (0, 0):
                self.error_selected.emit(err.position[0], err.position[1])

    def _show_detail(self, err):
        """Показать полную информацию в нижней панели."""
        src = self._get_source(err)
        src_label = _SOURCE_LABELS.get(src, src)
        lines = [
            f"  Источник:    {src_label}",
            f"  Тип:         {err.error_type} / {err.subtype}",
            f"  Фрагмент:    «{err.fragment}»",
        ]
        ctx = getattr(err, 'context', '')
        if ctx:
            lines.append(f"  Контекст:    {ctx}")
        lines += [
            f"  Описание:    {err.description}",
            f"  Рекомендация: {err.suggestion}",
        ]
        ref = getattr(err, 'rule_ref', '')
        if ref:
            lines.append(f"  Правило:     {ref}")
        pos = err.position
        if pos != (0, 0):
            lines.append(f"  Позиция:     символы {pos[0]}–{pos[1]}")
        self.detail_text.setPlainText("\n".join(lines))

    # ── Контекстное меню (ПКМ) ────────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint):
        """Показать контекстное меню с полными данными ошибки."""
        row = self.errors_table.rowAt(pos.y())
        if row < 0 or row >= len(self._errors):
            return
        err = self._errors[row]
        src = self._get_source(err)
        src_label = _SOURCE_LABELS.get(src, src)

        menu = QMenu(self)
        menu.setMinimumWidth(400)

        # ── Заголовок ──
        title_action = menu.addAction(
            f"🔍  {err.error_type}  —  {err.subtype}"
        )
        title_action.setEnabled(False)
        font = title_action.font()
        font.setBold(True)
        title_action.setFont(font)

        menu.addSeparator()

        # ── Источник ──
        src_action = menu.addAction(f"📌  Источник: {src_label}")
        src_action.setEnabled(False)

        ref = getattr(err, 'rule_ref', '')
        if ref:
            rule_action = menu.addAction(f"📖  Правило: {ref}")
            rule_action.setEnabled(False)

        menu.addSeparator()

        # ── Фрагмент ──
        frag_action = menu.addAction(f"📝  Фрагмент: «{err.fragment}»")
        frag_action.setEnabled(False)

        ctx = getattr(err, 'context', '')
        if ctx:
            ctx_action = menu.addAction(f"💬  Контекст: {ctx[:80]}{'…' if len(ctx) > 80 else ''}")
            ctx_action.setEnabled(False)

        menu.addSeparator()

        # ── Описание (разбитое на строки ≤60 символов) ──
        desc = err.description
        words_d = desc.split()
        lines_d, cur = [], ""
        for w in words_d:
            if len(cur) + len(w) + 1 > 60:
                lines_d.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines_d.append(cur)
        for i, ln in enumerate(lines_d):
            prefix = "ℹ️  " if i == 0 else "     "
            a = menu.addAction(f"{prefix}{ln}")
            a.setEnabled(False)

        menu.addSeparator()

        # ── Рекомендация ──
        sugg = err.suggestion
        words_s = sugg.split()
        lines_s, cur = [], ""
        for w in words_s:
            if len(cur) + len(w) + 1 > 60:
                lines_s.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines_s.append(cur)
        for i, ln in enumerate(lines_s):
            prefix = "✏️  " if i == 0 else "     "
            a = menu.addAction(f"{prefix}{ln}")
            a.setEnabled(False)

        menu.addSeparator()

        # ── Действия ──
        if err.position != (0, 0):
            goto_action = menu.addAction("🎯  Перейти к ошибке в тексте")
            goto_action.triggered.connect(
                lambda: self.error_selected.emit(err.position[0], err.position[1])
            )

        copy_action = menu.addAction("📋  Скопировать описание")
        copy_action.triggered.connect(lambda: self._copy_error_to_clipboard(err))

        menu.exec(self.errors_table.viewport().mapToGlobal(pos))

    def _copy_error_to_clipboard(self, err):
        from PyQt6.QtWidgets import QApplication
        src = self._get_source(err)
        text = (
            f"Источник: {_SOURCE_LABELS.get(src, src)}\n"
            f"Тип: {err.error_type} / {err.subtype}\n"
            f"Фрагмент: «{err.fragment}»\n"
            f"Описание: {err.description}\n"
            f"Рекомендация: {err.suggestion}\n"
        )
        ref = getattr(err, 'rule_ref', '')
        if ref:
            text += f"Правило: {ref}\n"
        ctx = getattr(err, 'context', '')
        if ctx:
            text += f"Контекст: {ctx}\n"
        QApplication.clipboard().setText(text)

    def _emit_highlight_all(self):
        """Собрать позиции всех видимых ошибок и передать в main_window."""
        positions = []
        for err in self._errors:
            start, end = err.position
            if start < end:
                positions.append((start, end, err.error_type))
        self.highlight_all_requested.emit(positions)

    # ── Сброс ─────────────────────────────────────────────────────────────

    def clear(self):
        self.errors_table.setRowCount(0)
        self._errors = []
        self._all_errors = []
        self.count_label.setText("Ошибок не обнаружено")
        self.detail_text.clear()
        for badge in self.skill_badges.values():
            badge.level_label.setText("—")
            badge.desc_label.setText("")
