from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QTextCursor, QTextBlockFormat
from PyQt6.QtWidgets import QTextEdit

from authoroved_core.core.models import Span
from authoroved_core.ui.appearance import HIGHLIGHT


def display_text_and_positions(text: str) -> tuple[str, list[int]]:
    """Qt нормализует переводы строк и индексирует UTF-16. Исходник не меняем."""
    parts, positions = [], [0]
    offset = 0
    for index, char in enumerate(text):
        if char == "\n" and index > 0 and text[index - 1] == "\r":
            positions.append(offset)
            continue
        display = "\n" if char in {"\r", "\u2028", "\u2029"} else char
        parts.append(display)
        offset += len(display.encode("utf-16-le")) // 2
        positions.append(offset)
    return "".join(parts), positions


class SourceTextView(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setObjectName("sourceText")
        self.source = ""
        self.positions = [0]
        self.document().setDocumentMargin(18)
        self.setPlaceholderText("Здесь появится исходный текст документа")

    def set_source(self, text: str):
        self.source = text
        display, self.positions = display_text_and_positions(text)
        self.setPlainText(display)
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        paragraph_format = QTextBlockFormat()
        paragraph_format.setLineHeight(140, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        paragraph_format.setBottomMargin(5)
        cursor.mergeBlockFormat(paragraph_format)
        self.highlight(())

    def highlight(self, spans: tuple[Span, ...], color=HIGHLIGHT):
        selections = []
        for span in spans:
            if not span.valid_for(self.source):
                raise ValueError("Диапазон выходит за границы исходного текста.")
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(self.positions[span.start])
            cursor.setPosition(self.positions[span.end], QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selection.format.setBackground(QColor(color))
            selections.append(selection)
        self.setExtraSelections(selections)
        if selections:
            cursor = QTextCursor(selections[0].cursor)
            cursor.clearSelection()
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
