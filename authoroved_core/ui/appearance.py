"""Только оформление окна. Не связано с анализом текста.

Стиль «E» из макета: тёмная шапка и лента кандидатов, исследуемый текст — лист бумаги,
рабочая панель — карточка над столом, кнопки — клавиши с нижней гранью, переключатели
этапов — утопленные. Шрифты встроены: Golos Text (интерфейс), PT Serif (текст).
Тени у листа и карточки дают отдельные подложки (ui/main_window.elevated), а не QSS.
"""

ACCENT = "#4356c8"
INK = "#161d33"
MUTED = "#556079"
HIGHLIGHT = "#fcd77a"
METRIC_HIGHLIGHT = "#dfe5ff"
UI_FONT = "Golos Text"
TEXT_FONT = "PT Serif"

STYLE = """
QMainWindow, QDialog { background: #e3e6ee; }
QWidget { color: #161d33; font-family: 'Golos Text', 'Segoe UI'; font-size: 14px; }
QLabel { background: transparent; }
QWidget#desk { background: qradialgradient(cx:0.5, cy:0, radius:1.15, fx:0.5, fy:0,
    stop:0 #f5f6fa, stop:0.65 #e4e7ef, stop:1 #d8dce7); }
QWidget#reviewPage { background: transparent; }
QWidget#comparisonPage, QWidget#finalPage { background: transparent; }

QFrame#topBar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #232c4c, stop:1 #141a30);
    border-bottom: 1px solid #090d1b; }
QFrame#topBar QLabel { color: #ffffff; }
QLabel#brand { font-size: 17px; font-weight: 600; }
QLabel#headerNote { color: #9aa3bd; font-size: 12px; }
QLabel#brandMark { background: transparent; }
QPushButton#headerButton { color: #e6e9f2; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #343e66, stop:1 #262f50);
    border: 1px solid #0d1222; border-bottom: 3px solid #0a0e1b; border-radius: 8px; padding: 6px 12px; font-weight: 500; }
QPushButton#headerButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d4874, stop:1 #2d375c); }
QPushButton#headerButton:pressed { border-bottom-width: 1px; padding: 8px 12px 6px 12px; }
QPushButton#headerButton:disabled { color: #6f7896; background: #232b49; }
QPushButton#headerButton:focus { border-color: #f5b83d; }
QPushButton#headerAccent { color: #1d1606; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffd581, stop:1 #f3b53a);
    border: 1px solid #a8770f; border-bottom: 3px solid #8a610b; border-radius: 8px; padding: 6px 14px; font-weight: 600; }
QPushButton#headerAccent:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffdc95, stop:1 #f6bd4d); }
QPushButton#headerAccent:pressed { border-bottom-width: 1px; padding: 8px 14px 6px 14px; }
QPushButton#headerAccent:focus { border-color: #ffffff; }
QFrame#navigation { background: #0f1428; border: 1px solid #070a15; border-top: 2px solid #04060d; border-radius: 9px; }
QPushButton#stage { border: 1px solid transparent; border-radius: 6px; background: transparent; color: #b4bbd0; padding: 6px 14px; font-weight: 500; }
QPushButton#stage:hover { color: #ffffff; background: #1b2240; }
QPushButton#stage:checked { color: #ffffff; font-weight: 600; border: 1px solid #2c3878;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5061b3, stop:1 #3a4890); }
QPushButton#stage:focus { border-color: #f5b83d; }
QPushButton#stage:disabled { color: #59627e; }

QFrame#paper, QFrame#paperShadow { background: #fffdf8; border: 1px solid #e7e1d1; border-radius: 6px; }
QFrame#paper QLabel#eyebrow { color: #7a725c; }
QFrame#paper QLabel#muted { color: #6b6450; }
QFrame#card, QFrame#cardShadow { background: #ffffff; border: 1px solid #dde2ec; border-radius: 14px; }
QFrame#panel { background: #ffffff; border: 1px solid #dde2ec; border-bottom: 3px solid #cdd3df; border-radius: 14px; }
QFrame#reviewCard { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8f9fc, stop:1 #eef1f7);
    border: 1px solid #e0e4ed; border-radius: 12px; }

QLabel#muted { color: #556079; font-size: 12px; }
QLabel#eyebrow { color: #66738b; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; }
QLabel#sectionTitle { font-size: 20px; font-weight: 600; }
QLabel#paperTitle { font-family: 'PT Serif'; font-size: 22px; font-weight: 700; color: #262217; }
QLabel#comparisonTitle { font-size: 16px; font-weight: 600; }
QLabel#notice { background: #eef0f6; color: #4c5873; border: 1px solid #dfe3ec; border-top: 2px solid #d3d8e3; border-radius: 9px; padding: 7px 12px; font-size: 12px; }
QLabel#metricHelp { background: #f1f3f8; color: #3b4560; border: 1px solid #e3e7ef; border-top: 2px solid #d6dbe6; border-radius: 10px; padding: 12px; font-size: 13px; }
QLabel#error { background: #fff3dc; padding: 12px; border: 1px solid #eacb95; border-bottom: 3px solid #dcb873; border-radius: 10px; color: #704813; }
QLabel#candidateDetail { color: #2b3657; font-weight: 600; padding-top: 2px; }
QLabel#candidateWord { font-family: 'PT Serif'; font-size: 26px; font-weight: 700; color: #161d33; }
QLabel#ribbonLabel { color: #9aa3bd; font-size: 12px; }

QPushButton { color: #161d33; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #eff1f6);
    border: 1px solid #c9cfdc; border-bottom: 3px solid #b6bdcd; border-radius: 9px; padding: 8px 14px; font-weight: 500; }
QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #e6e9f2); border-color: #aeb7cc; }
QPushButton:pressed { border-bottom-width: 1px; padding: 10px 14px 8px 14px; background: #e6e9f2; }
QPushButton:focus { border-color: #4356c8; }
QPushButton:disabled { color: #8a94a7; background: #edf0f6; border-color: #dfe3ec; border-bottom-color: #d3d8e2; }
QPushButton:checked { color: #ffffff; border: 1px solid #3443a8; border-bottom: 3px solid #283591;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5b6bd8, stop:1 #4356c8); }
QPushButton#primary { color: #ffffff; border: 1px solid #3443a8; border-bottom: 3px solid #283591; font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5b6bd8, stop:1 #4356c8); }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6676e0, stop:1 #4a5dd0); }
QPushButton#primary:pressed { border-bottom-width: 1px; padding: 10px 14px 8px 14px; }
QPushButton#primary:focus { border-color: #161d33; }
QPushButton#primary:disabled { color: #eef0fa; background: #98a2cf; border-color: #8a94c4; border-bottom-color: #7e88b8; }
QPushButton#typo { color: #6b4708; border: 1px solid #d7a542; border-bottom: 3px solid #b98a2c;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fff9ec, stop:1 #fdeccb); font-weight: 600; }
QPushButton#typo:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fffaf0, stop:1 #fbe3b3); }
QPushButton#typo:pressed { border-bottom-width: 1px; padding: 10px 14px 8px 14px; }
QPushButton#chip { border-radius: 15px; padding: 5px 12px; font-size: 13px; }
QPushButton#chip:pressed { padding: 7px 12px 5px 12px; }
QPushButton#quiet { background: transparent; border: 1px solid transparent; color: #56647e; padding: 4px 12px; font-size: 12px; }
QPushButton#quiet:hover { color: #3548b5; background: #eef1fa; }

QTextEdit, QListWidget, QLineEdit, QComboBox { background: #fbfcfe; color: #1f2a44; border: 1px solid #cdd3df; border-top: 2px solid #bfc6d4;
    border-radius: 8px; padding: 7px; selection-background-color: #dde4ff; selection-color: #233364; }
QTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: #4356c8; }
QTextEdit#sourceText { border: none; background: #fffdf8; font-family: 'PT Serif'; font-size: 18px; color: #262217; padding: 0px;
    selection-background-color: #f6e3ad; selection-color: #262217; }
QTextEdit#explanation { background: transparent; border: none; padding: 0px; font-size: 13px; }
QTextEdit#comment { font-size: 13px; }
QComboBox { padding: 6px 12px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #cdd3df; selection-background-color: #e9edff; selection-color: #233364; }
QFrame#paper QComboBox { background: #fbf8ef; border-color: #ddd5c0; border-top-color: #cfc6ae; color: #3d3829; }

QListWidget { border: none; padding: 0px; outline: none; background: transparent; }
QListWidget::item { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f4f6fa);
    border: 1px solid #e1e5ee; border-bottom: 2px solid #d4d9e4; border-radius: 9px; padding: 9px 12px; margin: 3px 0px; }
QListWidget::item:hover { background: #f1f4ff; border-color: #c4cdee; }
QListWidget::item:selected { color: #2b3790; background: #e9edfc; border-color: #98a6e3; border-bottom-color: #8494da; }
QListWidget#compactList::item { padding: 5px 10px; margin: 1px 0px; border-radius: 6px; border-bottom-width: 1px; }

QFrame#ribbon { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1c2342, stop:1 #111630); border-top: 1px solid #090d1b; }
QFrame#ribbon QComboBox { background: #262f50; color: #e6e9f2; border: 1px solid #0d1222; border-top: 1px solid #3a4570; }
QFrame#ribbon QComboBox QAbstractItemView { background: #262f50; color: #e6e9f2; selection-background-color: #3a4890; selection-color: #ffffff; }
QListWidget#ribbonList { background: #0c1022; border: 1px solid #060912; border-top: 2px solid #03050b; border-radius: 10px; padding: 4px; }
QListWidget#ribbonList::item { color: #c9cfe0; background: #1f2747; border: 1px solid #2c3556; border-bottom: 2px solid #121831;
    border-radius: 7px; padding: 3px 10px; margin: 2px 3px; }
QListWidget#ribbonList::item:hover { background: #29325a; }
QListWidget#ribbonList::item:selected { color: #ffffff; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5b6bd8, stop:1 #4356c8);
    border: 2px solid #f5b83d; }

QToolBox::tab { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #eef1f6);
    border: 1px solid #dde2ec; border-bottom: 2px solid #cfd5e1; border-radius: 8px; padding: 4px 12px; min-height: 22px; color: #3b4560; }
QToolBox::tab:selected { background: #e9edfc; color: #2b3790; font-weight: 600; border-color: #b9c3ec; }
QScrollArea, QToolBox { border: none; background: #ffffff; }
QToolBox > QScrollArea > QWidget > QWidget { background: #ffffff; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #c3cad9; min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #95a3c0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 1px 6px; }
QScrollBar::handle:horizontal { background: #3a4466; min-width: 28px; border-radius: 3px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: transparent; }
QToolTip { background: #1b2240; color: #ffffff; border: 1px solid #0d1222; padding: 8px; }
QProgressBar { border: none; background: #d6dbe6; max-height: 4px; }
QProgressBar::chunk { background: #4356c8; }
"""
