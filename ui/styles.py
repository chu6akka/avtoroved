"""
Стили и темы для PyQt6 UI.
"""

DARK_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Arial";
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px 16px;
    border: 1px solid #45475a;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    min-width: 110px;
}
QTabBar::tab:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #45475a;
}
QTextEdit, QPlainTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: "Consolas", "Courier New";
    font-size: 12px;
    padding: 4px;
}
QTableWidget, QTreeWidget {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    gridline-color: #313244;
    alternate-background-color: #1e1e2e;
}
QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    border: 1px solid #45475a;
    padding: 4px;
    font-weight: bold;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #b4d0ff;
}
QPushButton:pressed {
    background-color: #7ba3e8;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#secondary {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QPushButton#secondary:hover {
    background-color: #45475a;
}
QPushButton#danger {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#danger:hover {
    background-color: #f5a0b5;
}
QLineEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #89b4fa;
}
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox:drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QScrollBar:vertical {
    background: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #89b4fa;
}
QScrollBar:horizontal {
    background: #181825;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 5px;
    min-width: 20px;
}
QLabel {
    color: #cdd6f4;
}
QLabel#title {
    font-size: 16px;
    font-weight: bold;
    color: #89b4fa;
}
QLabel#subtitle {
    font-size: 12px;
    color: #a6adc8;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    color: #89b4fa;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #45475a;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #45475a;
}
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
}
QMenuBar::item:selected {
    background-color: #313244;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QMenu::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #eff1f5;
    color: #4c4f69;
}
QWidget {
    background-color: #eff1f5;
    color: #4c4f69;
    font-family: "Segoe UI", "Arial";
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #ccd0da;
    background-color: #eff1f5;
}
QTabBar::tab {
    background-color: #dce0e8;
    color: #4c4f69;
    padding: 6px 16px;
    border: 1px solid #ccd0da;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    min-width: 110px;
}
QTabBar::tab:selected {
    background-color: #1e66f5;
    color: #eff1f5;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #ccd0da;
}
QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    font-family: "Consolas", "Courier New";
    font-size: 12px;
    padding: 4px;
}
QTableWidget, QTreeWidget {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    gridline-color: #e6e9ef;
    alternate-background-color: #eff1f5;
}
QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: #1e66f5;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #dce0e8;
    color: #1e66f5;
    border: 1px solid #ccd0da;
    padding: 4px;
    font-weight: bold;
}
QPushButton {
    background-color: #1e66f5;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #3d7af5;
}
QPushButton:pressed {
    background-color: #1558d6;
}
QPushButton:disabled {
    background-color: #ccd0da;
    color: #acb0be;
}
QPushButton#secondary {
    background-color: #dce0e8;
    color: #4c4f69;
    border: 1px solid #ccd0da;
}
QPushButton#secondary:hover {
    background-color: #ccd0da;
}
QPushButton#danger {
    background-color: #d20f39;
    color: #ffffff;
}
QLineEdit {
    background-color: #ffffff;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    padding: 4px 8px;
}
QLineEdit:focus {
    border-color: #1e66f5;
}
QGroupBox {
    border: 1px solid #ccd0da;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    color: #1e66f5;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QProgressBar {
    background-color: #dce0e8;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    text-align: center;
    color: #4c4f69;
}
QProgressBar::chunk {
    background-color: #1e66f5;
    border-radius: 4px;
}
QScrollBar:vertical {
    background: #e6e9ef;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #ccd0da;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #1e66f5;
}
QStatusBar {
    background-color: #dce0e8;
    color: #6c6f85;
    border-top: 1px solid #ccd0da;
}
"""
