"""
Вкладка «Профиль автора» — диагностическое заключение по методике ИКЭ ФСБ России.

Диагностические задачи:
  1. Пол автора
  2. Возрастная группа
  3. Уровень образования
  4. Культура речи
  5. Маскировка письменной речи

Плюс: функциональный отпечаток (служебные слова).
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QTextEdit, QSplitter, QGroupBox,
    QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from analyzer.diagnostic_engine import DiagnosticResult, DiagnosticFinding, FunctionWordProfile


# ── Цвета уверенности ────────────────────────────────────────────────────────
_CONF_STYLE = {
    "вероятно":              "color:#6abf69; font-weight:600;",
    "предположительно":      "color:#e8a030; font-weight:600;",
    "данных недостаточно":   "color:#a09080; font-style:italic;",
    "":                      "color:#a09080;",
}

# ── Цвета блоков ──────────────────────────────────────────────────────────────
_BLOCK_COLORS = {
    "gender":    "#1565c0",   # синий
    "age":       "#6a1b9a",   # фиолетовый
    "education": "#2e7d32",   # зелёный
    "culture":   "#e65100",   # оранжевый
    "masquerade":"#b71c1c",   # красный
}


class _FindingBlock(QFrame):
    """Один диагностический блок (карточка)."""

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("finding_block")
        self.setStyleSheet(
            f"QFrame#finding_block {{ border-left: 3px solid {color}; "
            f"background: #181614; border-radius: 4px; padding: 2px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Заголовок
        hdr = QHBoxLayout()
        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(
            f"color:{color}; font-size:10px; font-weight:700; letter-spacing:1px;")
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()

        self._conf_lbl = QLabel("")
        self._conf_lbl.setStyleSheet("font-size:10px;")
        hdr.addWidget(self._conf_lbl)
        layout.addLayout(hdr)

        # Основной вывод
        self._verdict_lbl = QLabel("—")
        self._verdict_lbl.setStyleSheet("font-size:15px; font-weight:700; color:#f0ebe3;")
        self._verdict_lbl.setWordWrap(True)
        layout.addWidget(self._verdict_lbl)

        # Доказательная база
        self._evidence_lbl = QLabel("")
        self._evidence_lbl.setStyleSheet("font-size:11px; color:#a09080;")
        self._evidence_lbl.setWordWrap(True)
        self._evidence_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._evidence_lbl)

    def set_finding(self, finding: DiagnosticFinding | None):
        if finding is None:
            self._verdict_lbl.setText("—")
            self._conf_lbl.setText("")
            self._evidence_lbl.setText("")
            return

        conf_style = _CONF_STYLE.get(finding.confidence, _CONF_STYLE[""])
        self._conf_lbl.setStyleSheet(f"font-size:10px; {conf_style}")
        self._conf_lbl.setText(finding.confidence)
        self._verdict_lbl.setText(finding.label)

        lines = []
        for e in finding.evidence_for[:6]:
            lines.append(f"<span style='color:#6abf69'>✓</span> {e}")
        for e in finding.evidence_against[:3]:
            lines.append(f"<span style='color:#e06c6c'>✗</span> {e}")
        self._evidence_lbl.setText("<br>".join(lines) if lines else
                                   "<i>Признаки не выявлены</i>")

    def clear(self):
        self.set_finding(None)


class _FunctionWordPanel(QFrame):
    """Панель служебных слов (функциональный отпечаток)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("fw_panel")
        self.setStyleSheet(
            "QFrame#fw_panel { border: 1px solid #3a3630; "
            "background: #181614; border-radius: 4px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        hdr = QLabel("ФУНКЦИОНАЛЬНЫЙ ОТПЕЧАТОК  ·  Служебные слова")
        hdr.setStyleSheet("color:#e8a030; font-size:10px; font-weight:700; letter-spacing:1px;")
        layout.addWidget(hdr)

        sub = QLabel("Союзы, частицы, предлоги и вводные слова — "
                     "наиболее устойчивые идентификационные признаки (НСВ).")
        sub.setStyleSheet("font-size:10px; color:#6b6055;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        grid = QHBoxLayout()
        grid.setSpacing(8)

        self._conj_lbl  = self._make_section("СОЮЗЫ")
        self._part_lbl  = self._make_section("ЧАСТИЦЫ")
        self._prep_lbl  = self._make_section("ПРЕДЛОГИ")
        self._intro_lbl = self._make_section("ВВОДНЫЕ СЛОВА")

        for w in (self._conj_lbl, self._part_lbl,
                  self._prep_lbl, self._intro_lbl):
            grid.addWidget(w)
        layout.addLayout(grid)

        self._diversity_lbl = QLabel("")
        self._diversity_lbl.setStyleSheet("font-size:10px; color:#a09080;")
        layout.addWidget(self._diversity_lbl)

    @staticmethod
    def _make_section(title: str) -> QLabel:
        lbl = QLabel(f"<b style='color:#6b6055;font-size:9px;'>{title}</b><br>")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        return lbl

    def _format_items(self, d: dict, top: int = 10) -> str:
        items = sorted(d.items(), key=lambda x: -x[1])[:top]
        if not items:
            return "<i style='color:#6b6055;'>—</i>"
        parts = []
        for w, c in items:
            parts.append(f"<span style='color:#f0ebe3;'>{w}</span>"
                         f"<span style='color:#6b6055;'> ({c})</span>")
        return "<br>".join(parts)

    def set_profile(self, fw: FunctionWordProfile | None):
        if fw is None:
            for lbl in (self._conj_lbl, self._part_lbl,
                        self._prep_lbl, self._intro_lbl):
                lbl.setText(lbl.text().split("<br>")[0] + "<br>")
            self._diversity_lbl.setText("")
            return

        def _upd(lbl: QLabel, title: str, d: dict, top: int = 8):
            lbl.setText(
                f"<b style='color:#6b6055;font-size:9px;'>{title}</b><br>"
                + self._format_items(d, top)
            )

        _upd(self._conj_lbl,  "СОЮЗЫ",         fw.conjunctions,  8)
        _upd(self._part_lbl,  "ЧАСТИЦЫ",        fw.particles,     8)
        _upd(self._prep_lbl,  "ПРЕДЛОГИ",       fw.prepositions, 10)
        _upd(self._intro_lbl, "ВВОДНЫЕ СЛОВА",  fw.introductory,  6)

        self._diversity_lbl.setText(
            f"Служебных слов: {fw.total_function}  ·  "
            f"Индекс вариативности: {fw.diversity_index:.3f}"
        )

    def clear(self):
        self.set_profile(None)


class ProfileTab(QWidget):
    """Вкладка диагностического профиля автора."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: DiagnosticResult | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Заголовок ──────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        title = QLabel("Диагностический профиль автора")
        title.setObjectName("subtitle")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        self._volume_lbl = QLabel("")
        self._volume_lbl.setStyleSheet("font-size:11px; color:#a09080;")
        hdr_row.addWidget(self._volume_lbl)
        layout.addLayout(hdr_row)

        method_note = QLabel(
            "По методике диагностической авторовединой экспертизы (ИКЭ ФСБ России). "
            "Выводы носят вероятностный характер — подтверждаются комплексом признаков."
        )
        method_note.setStyleSheet("font-size:10px; color:#6b6055;")
        method_note.setWordWrap(True)
        layout.addWidget(method_note)

        # ── Сплиттер: карточки ↕ служебные слова ──────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)

        # Верхняя часть — 5 карточек диагностики
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        # Первый ряд: пол + возраст + образование
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._gender_block    = _FindingBlock("Пол автора",         _BLOCK_COLORS["gender"])
        self._age_block       = _FindingBlock("Возрастная группа",  _BLOCK_COLORS["age"])
        self._edu_block       = _FindingBlock("Образование",        _BLOCK_COLORS["education"])
        for b in (self._gender_block, self._age_block, self._edu_block):
            row1.addWidget(b)
        top_layout.addLayout(row1)

        # Второй ряд: культура речи + маскировка
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._culture_block   = _FindingBlock("Культура речи",      _BLOCK_COLORS["culture"])
        self._masq_block      = _FindingBlock("Маскировка речи",    _BLOCK_COLORS["masquerade"])
        row2.addWidget(self._culture_block, stretch=1)
        row2.addWidget(self._masq_block, stretch=1)
        top_layout.addLayout(row2)

        splitter.addWidget(top_widget)

        # Нижняя часть — функциональный отпечаток
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        fw_container = QWidget()
        fw_layout = QVBoxLayout(fw_container)
        fw_layout.setContentsMargins(0, 0, 0, 0)
        self._fw_panel = _FunctionWordPanel()
        fw_layout.addWidget(self._fw_panel)
        fw_layout.addStretch()

        scroll.setWidget(fw_container)
        splitter.addWidget(scroll)

        splitter.setSizes([420, 280])
        layout.addWidget(splitter, stretch=1)

        # ── Строка статуса / пустое состояние ──────────────────────
        self._empty_lbl = QLabel(
            "Выполните анализ текста (▶ Анализировать) — "
            "профиль будет сформирован автоматически."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color:#6b6055; font-size:12px; padding:20px;")
        layout.addWidget(self._empty_lbl)

    # ── Публичный API ────────────────────────────────────────────────────────

    def show_result(self, result: DiagnosticResult):
        self._result = result
        self._empty_lbl.setVisible(False)

        if not result.sufficient_volume:
            self._volume_lbl.setText(
                f"⚠ Объём текста ({result.word_count} слов) недостаточен "
                f"для диагностики (минимум 100 слов)"
            )
            self._volume_lbl.setStyleSheet("font-size:11px; color:#e8a030;")
            for b in (self._gender_block, self._age_block, self._edu_block,
                      self._culture_block, self._masq_block):
                b.clear()
            self._fw_panel.clear()
            return

        self._volume_lbl.setText(f"Объём: {result.word_count} слов")
        self._volume_lbl.setStyleSheet("font-size:11px; color:#6abf69;")

        self._gender_block.set_finding(result.gender)
        self._age_block.set_finding(result.age)
        self._edu_block.set_finding(result.education)
        self._culture_block.set_finding(result.speech_culture)
        self._masq_block.set_finding(result.masquerade)
        self._fw_panel.set_profile(result.function_words)

    def clear(self):
        self._result = None
        self._empty_lbl.setVisible(True)
        self._volume_lbl.setText("")
        for b in (self._gender_block, self._age_block, self._edu_block,
                  self._culture_block, self._masq_block):
            b.clear()
        self._fw_panel.clear()
