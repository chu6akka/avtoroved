"""
Главное окно нового интерфейса «Авторовед».
Пошаговый workflow: слева степпер из 4 стадий, справа — текущая стадия.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QStackedWidget, QButtonGroup, QFrame, QStatusBar
)
from PyQt6.QtCore import Qt

from ui2.state import AppState
from ui2.analysis import Engines
from ui2.stages import MaterialStage, AnalysisStage, CompareStage, ConclusionStage


APP_QSS = """
QWidget { font-family: 'Segoe UI', Arial; font-size: 13px; color: #1f2328; }
QMainWindow, #central { background: #f4f5f7; }
#sidebar { background: #1f2633; }
#appTitle { color: #f0f3f7; font-size: 15px; font-weight: 700; padding: 14px 12px 6px 12px; }
#appSub  { color: #8b97a8; font-size: 10px; padding: 0 12px 12px 12px; }
QPushButton#mode {
    color: #c7d0dc; background: transparent; border: 1px solid #38465a;
    border-radius: 6px; padding: 7px; text-align: center; font-size: 12px;
}
QPushButton#mode:checked { background: #2d6cdf; color: white; border-color: #2d6cdf; }
QPushButton#step {
    color: #c7d0dc; background: transparent; border: none;
    padding: 11px 12px; text-align: left; font-size: 13px; border-radius: 0;
}
QPushButton#step:checked { background: #2b3445; color: #ffffff; font-weight: 600; }
QPushButton#step:disabled { color: #5a6577; }
QPushButton#step:hover:!checked:!disabled { background: #28303f; }
#stageTitle { font-size: 20px; font-weight: 700; color: #1f2328; }
#stageHint { font-size: 12px; color: #6b7280; }
.card { background: white; border: 1px solid #e3e6ea; border-radius: 10px; }
QPushButton#primary {
    background: #2d6cdf; color: white; border: none; border-radius: 7px;
    padding: 9px 18px; font-size: 13px; font-weight: 600;
}
QPushButton#primary:disabled { background: #b9c4d4; }
QPushButton#ghost {
    background: white; color: #2d6cdf; border: 1px solid #b9c4d4;
    border-radius: 7px; padding: 8px 16px; font-size: 13px;
}
QTextEdit { background: white; border: 1px solid #d8dce1; border-radius: 8px; padding: 8px; }
"""


class MainWindow2(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Авторовед — рабочее место эксперта")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 820)
        self.setStyleSheet(APP_QSS)

        self.state = AppState()
        self.engines = Engines()

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        # Стек стадий
        self.stack = QStackedWidget()
        self.stages = [
            MaterialStage(self),
            AnalysisStage(self),
            CompareStage(self),
            ConclusionStage(self),
        ]
        for s in self.stages:
            self.stack.addWidget(s)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(28, 24, 28, 20)
        wl.addWidget(self.stack)
        root.addWidget(wrap, stretch=1)

        self.setStatusBar(QStatusBar())
        self._update_step_labels()
        self.go_to(0)

    # ── Сайдбар ───────────────────────────────────────────────────────────
    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(230)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        title = QLabel("АВТОРОВЕД")
        title.setObjectName("appTitle")
        lay.addWidget(title)
        sub = QLabel("рабочее место эксперта")
        sub.setObjectName("appSub")
        lay.addWidget(sub)

        # Режим задачи
        mode_box = QVBoxLayout()
        mode_box.setContentsMargins(12, 4, 12, 12)
        mode_box.setSpacing(6)
        self.btn_ident = QPushButton("Идентификация · 2 текста")
        self.btn_diag = QPushButton("Диагностика · 1 текст")
        for b, m in ((self.btn_ident, "identification"), (self.btn_diag, "diagnostic")):
            b.setObjectName("mode")
            b.setCheckable(True)
            b.clicked.connect(lambda _, mode=m: self._set_mode(mode))
            mode_box.addWidget(b)
        self.btn_ident.setChecked(True)
        lay.addLayout(mode_box)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#38465a;")
        lay.addWidget(sep)

        # Шаги
        self.step_buttons = []
        self.step_group = QButtonGroup(self)
        self.step_group.setExclusive(True)
        for i in range(4):
            b = QPushButton()
            b.setObjectName("step")
            b.setCheckable(True)
            b.clicked.connect(lambda _, idx=i: self.go_to(idx))
            self.step_group.addButton(b, i)
            self.step_buttons.append(b)
            lay.addWidget(b)

        lay.addStretch()
        return bar

    def _step_labels(self):
        third = "Сравнение" if self.state.mode == "identification" else "Профиль автора"
        return [f"1.  Материал", f"2.  Раздельный анализ",
                f"3.  {third}", f"4.  Заключение"]

    def _update_step_labels(self):
        for b, lbl in zip(self.step_buttons, self._step_labels()):
            b.setText(lbl)

    # ── Режим ─────────────────────────────────────────────────────────────
    def _set_mode(self, mode: str):
        self.state.mode = mode
        self.btn_ident.setChecked(mode == "identification")
        self.btn_diag.setChecked(mode == "diagnostic")
        self._update_step_labels()
        # сбросить дальнейшие стадии при смене режима
        self.go_to(0)
        for s in self.stages:
            if hasattr(s, "on_mode_changed"):
                s.on_mode_changed()

    # ── Навигация ─────────────────────────────────────────────────────────
    def go_to(self, index: int):
        index = max(0, min(index, len(self.stages) - 1))
        # Блокировка шагов, пока не выполнены предыдущие
        for i in range(1, len(self.stages)):
            prev_ok = self.stages[i - 1].is_complete()
            self.step_buttons[i].setEnabled(prev_ok or self.stack.currentIndex() >= i)
        self.step_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        self.stages[index].on_enter()

    def refresh_steps_enabled(self):
        if not hasattr(self, "stages"):
            return
        for i in range(1, len(self.stages)):
            self.step_buttons[i].setEnabled(self.stages[i - 1].is_complete())

    def set_status(self, text: str):
        self.statusBar().showMessage(text)
