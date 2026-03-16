"""
Вкладка 3: Ошибки и навыки (по методике С.М. Вул).
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QGridLayout, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor


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

    error_selected = pyqtSignal(int, int)  # position start, end

    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Навыки
        skills_group = QGroupBox("Степени развития языковых навыков (по С.М. Вул, 2007)")
        skills_layout = QGridLayout(skills_group)
        skills_layout.setSpacing(8)
        self.skill_badges = {}
        for i, name in enumerate(SKILL_NAMES):
            badge = SkillBadge(name)
            self.skill_badges[name] = badge
            skills_layout.addWidget(badge, i // 2, i % 2)
        layout.addWidget(skills_group)

        # Ошибки
        errors_group = QGroupBox("Выявленные речевые ошибки")
        errors_layout = QVBoxLayout(errors_group)

        self.errors_table = QTableWidget()
        self.errors_table.setColumnCount(5)
        self.errors_table.setHorizontalHeaderLabels(
            ["Тип", "Подтип", "Фрагмент", "Описание", "Рекомендация"])
        header = self.errors_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.errors_table.setAlternatingRowColors(True)
        self.errors_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.errors_table.verticalHeader().setVisible(False)
        self.errors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.errors_table.itemSelectionChanged.connect(self._on_error_selected)
        errors_layout.addWidget(self.errors_table)

        self.count_label = QLabel("Ошибок не обнаружено")
        self.count_label.setObjectName("subtitle")
        errors_layout.addWidget(self.count_label)
        layout.addWidget(errors_group)

    def populate(self, error_result):
        """Заполнить вкладку результатами анализа ошибок."""
        self._errors = error_result.errors if error_result else []

        # Обновляем навыки
        if error_result:
            for skill in error_result.skill_levels:
                if skill.skill_name in self.skill_badges:
                    self.skill_badges[skill.skill_name].update_skill(
                        skill.level, skill.description)

        # Заполняем таблицу
        self.errors_table.setRowCount(len(self._errors))
        for row, err in enumerate(self._errors):
            vals = [
                err.error_type,
                err.subtype,
                err.fragment[:35] + "…" if len(err.fragment) > 35 else err.fragment,
                err.description[:60] + "…" if len(err.description) > 60 else err.description,
                err.suggestion[:35] + "…" if len(err.suggestion) > 35 else err.suggestion,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.errors_table.setItem(row, col, item)

        n = len(self._errors)
        self.count_label.setText(
            f"Обнаружено ошибок: {n}" if n > 0 else "Ошибок не обнаружено")

    def _on_error_selected(self):
        rows = self.errors_table.selectedItems()
        if not rows or not self._errors:
            return
        row = self.errors_table.currentRow()
        if 0 <= row < len(self._errors):
            err = self._errors[row]
            if err.position != (0, 0):
                self.error_selected.emit(err.position[0], err.position[1])

    def clear(self):
        self.errors_table.setRowCount(0)
        self._errors = []
        self.count_label.setText("Ошибок не обнаружено")
        for badge in self.skill_badges.values():
            badge.level_label.setText("—")
            badge.desc_label.setText("")
