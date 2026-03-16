"""
Вкладка 4: Профиль интернет-коммуникации.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QFrame, QGroupBox, QProgressBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class InternetTab(QWidget):
    """Анализ признаков сетевого идиолекта."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Шапка со score
        header = QGroupBox("Степень интернет-коммуникативности")
        header_layout = QHBoxLayout(header)

        left = QVBoxLayout()
        self.score_label = QLabel("—")
        self.score_label.setStyleSheet("font-size: 32px; font-weight: bold;")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.assess_label = QLabel("Нет данных")
        self.assess_label.setStyleSheet("font-size: 14px;")
        self.assess_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.score_label)
        left.addWidget(self.assess_label)
        header_layout.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Уровень:"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(300)
        right.addWidget(self.progress)
        right.addStretch()
        header_layout.addLayout(right)

        layout.addWidget(header)

        # Детальный профиль
        detail_group = QGroupBox("Детальный профиль интернет-маркеров")
        detail_layout = QVBoxLayout(detail_group)
        self.profile_text = QTextEdit()
        self.profile_text.setReadOnly(True)
        self.profile_text.setFont(self.font())
        detail_layout.addWidget(self.profile_text)
        layout.addWidget(detail_group)

    def populate(self, internet_profile):
        """Обновить вкладку по профилю интернет-коммуникации."""
        if internet_profile is None:
            return

        score = round(internet_profile.internet_comm_score * 100, 1)

        if score >= 50:
            assess = "ВЫСОКАЯ степень"
            color = "#f38ba8"
        elif score >= 25:
            assess = "СРЕДНЯЯ степень"
            color = "#fab387"
        elif score >= 10:
            assess = "НИЗКАЯ степень"
            color = "#89b4fa"
        else:
            assess = "МИНИМАЛЬНАЯ степень"
            color = "#a6e3a1"

        self.score_label.setText(f"{score}%")
        self.score_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")
        self.assess_label.setText(assess)
        self.assess_label.setStyleSheet(f"font-size: 14px; color: {color};")
        self.progress.setValue(int(score))
        self.progress.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")

        from analyzer.errors import format_internet_profile
        self.profile_text.setPlainText(format_internet_profile(internet_profile))

    def clear(self):
        self.score_label.setText("—")
        self.assess_label.setText("Нет данных")
        self.progress.setValue(0)
        self.profile_text.clear()
