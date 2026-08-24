"""Виджеты прозрачности: инспектор признаков с подсветкой доказательств в тексте."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QLabel,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from aved.core.models import Category, Level, NavykModel
from aved.core.registry import Registry

_LEVEL_RU = {
    Level.NN: "НН — набор норм",
    Level.NS: "НС — набор свойств норм",
    Level.NSV: "НСВ — набор средств выражения",
}
_CATEGORY_RU = {
    Category.SMYSLOVYE: "Смысловые",
    Category.TEXTOLOGICAL: "Текстологические",
    Category.LANGUAGE: "Языковые",
    Category.LEXICAL: "Лексические",
    Category.STYLISTIC: "Стилистические",
    Category.SYNTACTIC: "Синтаксические",
    Category.PSYCHOLINGUISTIC: "Психолингвистические",
}
_SOURCE_RU = {
    "auto": "авто", "hybrid": "авто", "llm": "LLM",
    "aggregate": "агрегат", "expert": "эксперт",
}
_FID_ROLE = Qt.ItemDataRole.UserRole


def _guard(method):
    """Защита обработчика: исключение показывается диалогом, а не роняет приложение."""
    import functools

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            try:
                from aved.ui.app import _log_and_report

                _log_and_report(exc, self)
            except Exception:
                pass
    return wrapper


def _state_text(fv) -> str:
    if fv is None:
        return "не оценён"
    if not fv.present:
        return "не обнаружен"
    src = _SOURCE_RU.get(fv.source_kind, fv.source_kind)
    flag = " ✓подтв." if fv.expert_confirmed else ""
    return f"{src} ✓ {fv.note}{flag}"


class FeatureInspector(QWidget):
    """Дерево признаков по уровням + текст объекта с подсветкой доказательств."""

    def __init__(self, registry: Registry, on_toggle) -> None:
        super().__init__()
        self.registry = registry
        self.on_toggle = on_toggle
        self.object_id = ""
        self.model: NavykModel | None = None
        self._building = False

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Признак", "Состояние"])
        self.tree.setColumnWidth(0, 360)
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemChanged.connect(self._on_check)
        split.addWidget(self.tree)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Текст объекта (доказательства подсвечены):"))
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        rl.addWidget(self.text, 3)
        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(120)
        rl.addWidget(QLabel("Признак и доказательства:"))
        rl.addWidget(self.info, 1)
        split.addWidget(right)
        split.setSizes([430, 380])

        lay = QVBoxLayout(self)
        lay.addWidget(split)

    def set_model(self, object_id: str, model: NavykModel, text: str) -> None:
        self.object_id = object_id
        self.model = model
        self.text.setPlainText(text)
        self._build_tree()

    def _build_tree(self) -> None:
        self._building = True
        self.tree.clear()
        for level in (Level.NN, Level.NS, Level.NSV):
            feats = self.registry.by_level(level)
            present_n = sum(1 for f in feats
                            if (v := (self.model.values.get(f.id) if self.model else None)) and v.present)
            top = QTreeWidgetItem([f"{_LEVEL_RU[level]}  ({present_n}/{len(feats)})", ""])
            self.tree.addTopLevelItem(top)
            by_cat: dict = {}
            for f in feats:
                by_cat.setdefault(f.category, []).append(f)
            for cat, items in by_cat.items():
                cat_item = QTreeWidgetItem([_CATEGORY_RU.get(cat, cat.value), ""])
                top.addChild(cat_item)
                for f in items:
                    fv = self.model.values.get(f.id) if self.model else None
                    leaf = QTreeWidgetItem([f.name, _state_text(fv)])
                    leaf.setData(0, _FID_ROLE, f.id)
                    leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    leaf.setCheckState(
                        0, Qt.CheckState.Checked if (fv and fv.present) else Qt.CheckState.Unchecked
                    )
                    if fv is None:
                        leaf.setForeground(0, QColor("#999999"))
                    cat_item.addChild(leaf)
            top.setExpanded(True)
        self._building = False

    def _fid(self, item) -> str | None:
        return item.data(0, _FID_ROLE) if item else None

    @_guard
    def _on_check(self, item, column) -> None:
        if self._building:
            return
        fid = self._fid(item)
        if not fid:
            return
        present = item.checkState(0) == Qt.CheckState.Checked
        self.on_toggle(self.object_id, fid, present)
        fv = self.model.values.get(fid) if self.model else None
        item.setText(1, _state_text(fv))

    @_guard
    def _on_select(self, current, _previous) -> None:
        fid = self._fid(current)
        if not fid or self.model is None:
            self.text.setExtraSelections([])
            return
        feature = self.registry.get(fid)
        fv = self.model.values.get(fid)
        # подсветка доказательств
        selections = []
        quotes = []
        if fv and fv.evidence:
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#fff3a0"))
            for ev in fv.evidence:
                quotes.append(ev.quote)
                if ev.start is not None and ev.start >= 0 and ev.stop > ev.start:
                    cur = QTextCursor(self.text.document())
                    cur.setPosition(ev.start)
                    cur.setPosition(ev.stop, QTextCursor.MoveMode.KeepAnchor)
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = cur
                    sel.format = fmt
                    selections.append(sel)
        self.text.setExtraSelections(selections)
        if selections:
            self.text.setTextCursor(selections[0].cursor)
        info = (
            f"<b>{feature.name}</b><br>"
            f"уровень {feature.level.value}, значимость {feature.significance.value}, "
            f"способ {feature.method.value}, {feature.source}<br>"
        )
        if fv is None:
            info += "<i>не оценён автоматически — может быть отмечен экспертом.</i>"
        else:
            info += f"состояние: {_state_text(fv)}"
            if quotes:
                info += "<br>доказательства: " + "; ".join(f"«{q}»" for q in quotes)
            else:
                info += "<br><i>без текстовых доказательств (качественная оценка).</i>"
        self.info.setHtml(info)
