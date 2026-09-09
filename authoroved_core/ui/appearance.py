"""Только оформление окна. Не связано с анализом текста."""

ACCENT = "#4356c8"
INK = "#1d2940"
MUTED = "#5f6b80"
HIGHLIGHT = "#ffe7ac"
METRIC_HIGHLIGHT = "#e0e6ff"

STYLE = """
QMainWindow, QDialog { background: #edf0f6; }
QWidget { color: #1d2940; font-family: 'Segoe UI'; font-size: 14px; }
QLabel { background: transparent; }
QWidget#reviewPage { background: #ffffff; }
QWidget#comparisonPage { background: #edf0f6; }
QLabel#brand { font-size: 28px; font-weight: 700; letter-spacing: -1px; }
QLabel#brandMark { background: #4356c8; color: white; border-radius: 14px; font-size: 28px; font-weight: 600; }
QLabel#muted { color: #5f6b80; font-size: 12px; }
QLabel#eyebrow { color: #66738b; font-size: 11px; font-weight: 600; letter-spacing: 2px; }
QLabel#sectionTitle { font-size: 21px; font-weight: 600; }
QLabel#comparisonTitle { font-size: 16px; font-weight: 600; }
QLabel#notice { background: #e4e8f2; color: #536079; border-radius: 9px; padding: 8px 12px; font-size: 12px; }
QLabel#metricHelp { background: #f1f3fa; color: #4a5770; border-radius: 10px; padding: 12px; font-size: 13px; }
QLabel#error { background: #fff0d8; padding: 12px; border: 1px solid #eacb95; border-radius: 10px; color: #704813; }
QLabel#candidateDetail { color: #35466a; font-weight: 600; padding-top: 4px; }
QPushButton { background: white; border: 1px solid #d8deeb; border-radius: 9px; padding: 9px 15px; font-weight: 500; }
QPushButton:hover { background: #f1f3ff; border-color: #a9b4df; }
QPushButton:pressed { background: #e1e6fa; }
QPushButton:focus { border: 2px solid #4356c8; padding: 8px 14px; }
QPushButton:disabled { color: #8a94a7; background: #edf0f6; border-color: #e2e6ee; }
QPushButton#primary { color: white; background: #4356c8; border-color: #4356c8; font-weight: 600; }
QPushButton#primary:hover { background: #3548b5; border-color: #3548b5; }
QPushButton#primary:pressed { background: #2e3d99; }
QPushButton#primary:focus { border-color: #1d2940; }
QPushButton#primary:disabled { color: #f4f5fa; background: #919bc9; border-color: #919bc9; }
QPushButton#quiet { background: transparent; border-color: transparent; color: #56647e; padding: 5px 12px; font-size: 12px; }
QPushButton#quiet:hover { color: #3548b5; background: #eef1fa; }
QPushButton#stage { border: 1px solid transparent; background: transparent; color: #56647e; padding: 9px 18px; }
QPushButton#stage:checked { color: #3548b5; background: #e9edff; font-weight: 600; }
QPushButton#stage:focus { border-color: #4356c8; }
QPushButton#stage:disabled { color: #939caf; }
QFrame#navigation { background: #ffffff; border: 1px solid #e0e5f0; border-radius: 13px; }
QFrame#panel { background: #ffffff; border: 1px solid #dfe4ee; border-radius: 16px; }
QFrame#reviewCard { background: #f5f7fc; border: 1px solid #e3e8f2; border-radius: 12px; }
QTextEdit, QListWidget, QLineEdit, QComboBox { background: #ffffff; color: #26344e; border: 1px solid #dbe1ed; border-radius: 9px; padding: 8px; selection-background-color: #dde4ff; selection-color: #233364; }
QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: #4356c8; }
QTextEdit#sourceText { border: none; background: #ffffff; font-family: 'Georgia'; font-size: 17px; color: #263146; padding: 0px; }
QTextEdit#explanation { background: transparent; border: none; padding: 0px; font-size: 13px; }
QTextEdit#comment { background: #fafbfe; font-size: 13px; }
QListWidget { border: none; padding: 0px; outline: none; }
QListWidget::item { background: #f5f7fc; border: 1px solid #e8ecf4; border-radius: 9px; padding: 10px 12px; margin: 3px 0px; }
QListWidget::item:hover { background: #eff2ff; border-color: #c8d1f2; }
QListWidget::item:selected { color: #2f4196; background: #eaf0ff; border-color: #9cace5; }
QListWidget::item:focus { border-color: #4356c8; }
QComboBox { padding: 8px 12px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e9edff; selection-color: #233364; }
QToolBox::tab { background: #f0f3fa; border-radius: 8px; padding: 2px 12px; color: #53617c; }
QToolBox::tab:selected { background: #e8edff; color: #3548b5; font-weight: 600; }
QScrollArea, QToolBox { border: none; background: #ffffff; }
QScrollBar:vertical { background: #f5f7fb; width: 9px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #c6cede; min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #95a3c0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSplitter::handle { background: transparent; }
QToolTip { background: #24334f; color: white; border: none; padding: 8px; }
QProgressBar { border: none; background: #e1e6f3; max-height: 4px; }
QProgressBar::chunk { background: #4356c8; }
"""
