"""
Дизайн-система Автороведческого анализатора.
Тёмная тема: Warm Academic — тёплый чёрный фон, янтарный акцент.
Светлая тема: Professional Light (GitHub Light).
"""

# ─── Типографика ──────────────────────────────────────────────────────────────
_FONT      = '"Segoe UI Variable", "Segoe UI", "Inter", "Arial", sans-serif'
_FONT_MONO = '"Cascadia Code", "JetBrains Mono", "Consolas", monospace'

# ─── Warm Academic Dark ───────────────────────────────────────────────────────
_D = {
    "bg":       "#0e0d0b",   # глубокий тёплый чёрный
    "surface":  "#181614",   # тёплая тёмная поверхность
    "surface2": "#221f1b",   # приподнятые элементы
    "surface3": "#2e2b25",   # ховер / alt rows
    "border":   "#3a3630",   # рамки
    "border2":  "#5c5248",   # акцентные рамки
    "text":     "#f0ebe3",   # тёплый белый
    "text2":    "#a09080",   # вторичный текст
    "text3":    "#6b6055",   # третичный / плейсхолдеры
    "accent":   "#e8a030",   # янтарь — академическое золото
    "accent2":  "#f0c060",   # светлее янтарь (hover)
    "accent_bg":"#2a1e08",   # фон акцента
    "green":    "#6abf69",   # success
    "green_bg": "#142214",
    "orange":   "#d4883a",   # warning
    "orange_bg":"#271a08",
    "red":      "#e06c6c",   # danger
    "red_bg":   "#2c1414",
    "purple":   "#b888e8",   # secondary accent
    "purple_bg":"#201430",
    "teal":     "#4db8b8",   # highlight
    "teal_bg":  "#0e2828",
    "blue":     "#5aa0e8",   # info
    "blue_bg":  "#0e1e30",
    "sidebar":  "#120f0d",
    "sidebar_hover":        "#1e1c17",
    "sidebar_active_bg":    "#241c0a",
    "sidebar_active_border":"#e8a030",
}

DARK_STYLESHEET = f"""
/* ── Base ── */
QMainWindow, QDialog, QWidget {{
    background-color: {_D['bg']};
    color: {_D['text']};
    font-family: {_FONT};
    font-size: 13px;
}}

/* ── Sidebar ── */
QWidget#sidebar {{
    background-color: {_D['sidebar']};
    border-right: 1px solid {_D['border']};
}}
QLabel#sidebar_title {{
    color: {_D['accent']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 18px 16px 8px 16px;
    background-color: transparent;
}}
QLabel#sidebar_subtitle {{
    color: {_D['text3']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    padding: 12px 16px 4px 16px;
    background-color: transparent;
}}
QLabel#lt_status {{
    color: {_D['text3']};
    font-size: 11px;
    padding: 4px 12px;
    background-color: transparent;
}}
QPushButton#nav_btn {{
    background-color: transparent;
    color: {_D['text2']};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 9px 14px 9px 13px;
    font-size: 13px;
    font-weight: 400;
}}
QPushButton#nav_btn:hover {{
    background-color: {_D['sidebar_hover']};
    color: {_D['text']};
    border-left: 3px solid {_D['border2']};
}}
QPushButton#nav_btn[active="true"] {{
    background-color: {_D['sidebar_active_bg']};
    color: {_D['accent']};
    border-left: 3px solid {_D['sidebar_active_border']};
    font-weight: 600;
}}
QFrame#sidebar_divider {{
    background-color: {_D['border']};
    max-height: 1px;
    margin: 4px 12px;
}}

/* ── Кнопка «Анализировать» ── */
QPushButton#analyze_btn {{
    background-color: {_D['accent']};
    color: #0e0d0b;
    border: none;
    border-radius: 8px;
    padding: 11px 16px;
    font-size: 14px;
    font-weight: 700;
    margin: 8px 12px;
    text-align: center;
    letter-spacing: 0.3px;
}}
QPushButton#analyze_btn:hover {{
    background-color: {_D['accent2']};
}}
QPushButton#analyze_btn:pressed {{
    background-color: #c07820;
}}
QPushButton#analyze_btn:disabled {{
    background-color: {_D['surface3']};
    color: {_D['text3']};
}}

/* ── Util-кнопки сайдбара ── */
QPushButton#sidebar_btn {{
    background-color: transparent;
    color: {_D['text2']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    margin: 1px 4px;
}}
QPushButton#sidebar_btn:hover {{
    background-color: {_D['surface3']};
    color: {_D['text']};
    border-color: {_D['border2']};
}}

/* ── Content ── */
QWidget#content_area {{
    background-color: {_D['bg']};
}}

/* ── Поле ввода текста ── */
QTextEdit#text_input {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 8px;
    font-family: {_FONT};
    font-size: 13px;
    padding: 8px 10px;
    selection-background-color: {_D['accent_bg']};
    selection-color: {_D['accent2']};
    line-height: 1.5;
}}
QTextEdit#text_input:focus {{
    border-color: {_D['accent']};
    border-width: 1px;
}}

/* ── Прочие текстовые редакторы ── */
QTextEdit, QPlainTextEdit {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    font-family: {_FONT_MONO};
    font-size: 12px;
    padding: 4px 6px;
}}

/* ── Таблицы ── */
QTableWidget, QTreeWidget {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    gridline-color: {_D['border']};
    alternate-background-color: {_D['surface2']};
    selection-background-color: {_D['accent_bg']};
    selection-color: {_D['text']};
    outline: none;
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {_D['accent_bg']};
    color: {_D['accent2']};
}}
QHeaderView::section {{
    background-color: {_D['surface2']};
    color: {_D['text3']};
    border: none;
    border-bottom: 1px solid {_D['border']};
    border-right: 1px solid {_D['border']};
    padding: 5px 8px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── Кнопки ── */
QPushButton {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {_D['surface3']};
    border-color: {_D['border2']};
    color: {_D['text']};
}}
QPushButton:pressed {{
    background-color: {_D['surface']};
}}
QPushButton:disabled {{
    background-color: {_D['surface']};
    color: {_D['text3']};
    border-color: {_D['border']};
}}
QPushButton#primary {{
    background-color: {_D['accent']};
    color: #0e0d0b;
    border: none;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
QPushButton#primary:hover {{
    background-color: {_D['accent2']};
}}
QPushButton#primary:disabled {{
    background-color: {_D['surface3']};
    color: {_D['text3']};
}}
QPushButton#secondary {{
    background-color: transparent;
    color: {_D['text2']};
    border: 1px solid {_D['border']};
}}
QPushButton#secondary:hover {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border-color: {_D['border2']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {_D['red']};
    border: 1px solid {_D['red_bg']};
}}
QPushButton#danger:hover {{
    background-color: {_D['red_bg']};
    border-color: {_D['red']};
}}
QPushButton#success {{
    background-color: {_D['green']};
    color: #0e0d0b;
    border: none;
    font-weight: 600;
}}
QPushButton#success:hover {{
    background-color: #7dce7c;
}}

/* ── Поля ввода ── */
QLineEdit {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
}}
QLineEdit:focus {{
    border-color: {_D['accent']};
}}
QComboBox {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
    min-height: 28px;
}}
QComboBox:hover {{
    border-color: {_D['border2']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {_D['text2']};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    selection-background-color: {_D['accent_bg']};
    selection-color: {_D['accent2']};
    outline: none;
}}

/* ── GroupBox — базовый ── */
QGroupBox {{
    border: 1px solid {_D['border2']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background-color: {_D['surface']};
    color: {_D['text2']};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: {_D['surface']};
    color: {_D['text2']};
}}

/* ── GroupBox — акцентные (цвет по секции) ── */
QGroupBox#corpus_box {{
    border-color: {_D['accent']};
}}
QGroupBox#corpus_box::title {{
    color: {_D['accent']};
}}
QGroupBox#model_box {{
    border-color: {_D['blue']};
}}
QGroupBox#model_box::title {{
    color: {_D['blue']};
}}
QGroupBox#vec_box {{
    border-color: {_D['teal']};
}}
QGroupBox#vec_box::title {{
    color: {_D['teal']};
}}
QGroupBox#result_box {{
    border-color: {_D['border2']};
}}
QGroupBox#ann_box {{
    border-color: {_D['purple']};
}}
QGroupBox#ann_box::title {{
    color: {_D['purple']};
}}
QGroupBox#ud_box {{
    border-color: {_D['green']};
}}
QGroupBox#ud_box::title {{
    color: {_D['green']};
}}

/* ── Скролл ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {_D['surface3']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_D['border2']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {_D['surface3']};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_D['border2']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Метки ── */
QLabel {{
    color: {_D['text']};
    background-color: transparent;
}}
QLabel#title {{
    font-size: 16px;
    font-weight: 700;
    color: {_D['text']};
    letter-spacing: 0.5px;
}}
QLabel#subtitle {{
    font-size: 12px;
    color: {_D['text2']};
}}
QLabel#caption {{
    font-size: 11px;
    color: {_D['text3']};
}}
QLabel#badge_ok {{
    color: {_D['green']};
    font-weight: 600;
}}
QLabel#badge_warn {{
    color: {_D['orange']};
    font-weight: 600;
}}
QLabel#badge_err {{
    color: {_D['red']};
    font-weight: 600;
}}
/* Большое значение в карточке статистики */
QLabel#stat_val {{
    font-size: 22px;
    font-weight: 700;
    color: {_D['accent']};
    font-family: {_FONT_MONO};
}}
QLabel#stat_label {{
    font-size: 10px;
    font-weight: 600;
    color: {_D['text3']};
    letter-spacing: 1px;
    text-transform: uppercase;
}}
/* Статусная строка внутри секции */
QLabel#section_status {{
    font-size: 12px;
    color: {_D['text2']};
    padding: 3px 0;
}}

/* ── Статус-бар ── */
QStatusBar {{
    background-color: {_D['surface']};
    color: {_D['text2']};
    border-top: 1px solid {_D['border']};
    font-size: 12px;
}}
QStatusBar QLabel {{
    color: {_D['text2']};
    padding: 0 8px;
}}

/* ── Прогресс-бар ── */
QProgressBar {{
    background-color: {_D['surface2']};
    border: 1px solid {_D['border']};
    border-radius: 5px;
    text-align: center;
    color: {_D['text']};
    font-size: 11px;
    font-family: {_FONT_MONO};
    min-height: 18px;
    max-height: 18px;
}}
QProgressBar::chunk {{
    background-color: {_D['accent']};
    border-radius: 4px;
}}
QProgressBar#ready::chunk {{
    background-color: {_D['green']};
}}

/* ── Разделитель ── */
QSplitter::handle {{
    background-color: {_D['border']};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:horizontal:hover {{
    background-color: {_D['accent']};
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 6px;
    background-color: {_D['surface2']};
    border-top: 1px solid {_D['border2']};
    border-bottom: 1px solid {_D['border2']};
}}
QSplitter::handle:vertical:hover {{
    border-top: 2px solid {_D['accent']};
}}
QSplitter#text_splitter::handle:vertical {{
    background-color: {_D['surface2']};
    border-top: 2px solid {_D['accent']};
}}

/* ── Меню ── */
QMenuBar {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border-bottom: 1px solid {_D['border']};
    padding: 2px;
    font-size: 13px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    background-color: transparent;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {_D['surface2']};
}}
QMenu {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border: 1px solid {_D['border2']};
    border-radius: 8px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px 6px 14px;
    font-size: 13px;
}}
QMenu::item:selected {{
    background-color: {_D['accent_bg']};
    color: {_D['accent2']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_D['border']};
    margin: 4px 0;
}}

/* ── Подсказка ── */
QToolTip {{
    background-color: {_D['surface3']};
    color: {_D['text']};
    border: 1px solid {_D['border2']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Stack / Tab ── */
QStackedWidget {{
    background-color: {_D['bg']};
    border: none;
}}
QTabWidget::pane {{
    border: 1px solid {_D['border2']};
    border-radius: 6px;
    background-color: {_D['surface']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {_D['surface2']};
    color: {_D['text3']};
    border: 1px solid {_D['border']};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 5px 14px;
    font-size: 12px;
    margin-right: 2px;
    letter-spacing: 0.3px;
}}
QTabBar::tab:selected {{
    background-color: {_D['surface']};
    color: {_D['accent']};
    border-color: {_D['accent']};
    font-weight: 700;
}}
QTabBar::tab:hover:!selected {{
    background-color: {_D['surface3']};
    color: {_D['text']};
}}

/* ── ScrollArea прозрачный фон ── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
"""


# ─── Professional Light ───────────────────────────────────────────────────────
_L = {
    "bg":       "#ffffff",
    "surface":  "#f6f8fa",
    "surface2": "#eaeef2",
    "surface3": "#d0d7de",
    "border":   "#d0d7de",
    "border2":  "#0969da",
    "text":     "#1f2328",
    "text2":    "#636c76",
    "text3":    "#9198a1",
    "accent":   "#0969da",
    "accent2":  "#218bff",
    "accent_bg":"#ddf4ff",
    "green":    "#1a7f37",
    "green_bg": "#dafbe1",
    "orange":   "#9a6700",
    "orange_bg":"#fff8c5",
    "red":      "#cf222e",
    "red_bg":   "#ffebe9",
    "purple":   "#8250df",
    "purple_bg":"#fbefff",
    "teal":     "#0a7d8c",
    "teal_bg":  "#e6f7f8",
    "blue":     "#0969da",
    "blue_bg":  "#ddf4ff",
    "sidebar":  "#f6f8fa",
    "sidebar_hover":        "#eaeef2",
    "sidebar_active_bg":    "#ddf4ff",
    "sidebar_active_border":"#0969da",
}

LIGHT_STYLESHEET = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {_L['bg']};
    color: {_L['text']};
    font-family: {_FONT};
    font-size: 13px;
}}
QWidget#sidebar {{
    background-color: {_L['sidebar']};
    border-right: 1px solid {_L['border']};
}}
QLabel#sidebar_title {{
    color: {_L['accent']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 18px 16px 8px 16px;
    background-color: transparent;
}}
QLabel#sidebar_subtitle {{
    color: {_L['text3']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    padding: 12px 16px 4px 16px;
    background-color: transparent;
}}
QPushButton#nav_btn {{
    background-color: transparent;
    color: {_L['text2']};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 9px 14px 9px 13px;
    font-size: 13px;
    font-weight: 400;
}}
QPushButton#nav_btn:hover {{
    background-color: {_L['sidebar_hover']};
    color: {_L['text']};
    border-left: 3px solid {_L['border2']};
}}
QPushButton#nav_btn[active="true"] {{
    background-color: {_L['sidebar_active_bg']};
    color: {_L['accent']};
    border-left: 3px solid {_L['sidebar_active_border']};
    font-weight: 600;
}}
QFrame#sidebar_divider {{
    background-color: {_L['border']};
    max-height: 1px;
    margin: 4px 12px;
}}
QPushButton#analyze_btn {{
    background-color: {_L['accent']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 11px 16px;
    font-size: 14px;
    font-weight: 700;
    margin: 8px 12px;
    text-align: center;
}}
QPushButton#analyze_btn:hover {{
    background-color: #0860c7;
}}
QPushButton#analyze_btn:disabled {{
    background-color: {_L['surface3']};
    color: {_L['text3']};
}}
QPushButton#sidebar_btn {{
    background-color: transparent;
    color: {_L['text2']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    margin: 1px 4px;
}}
QPushButton#sidebar_btn:hover {{
    background-color: {_L['surface2']};
    color: {_L['text']};
}}
QWidget#content_area {{
    background-color: {_L['bg']};
}}
QTextEdit#text_input {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 8px;
    font-family: {_FONT};
    font-size: 13px;
    padding: 8px 10px;
}}
QTextEdit#text_input:focus {{
    border-color: {_L['accent']};
}}
QTextEdit, QPlainTextEdit {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    font-family: {_FONT_MONO};
    font-size: 12px;
    padding: 4px 6px;
}}
QTableWidget, QTreeWidget {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    gridline-color: {_L['border']};
    alternate-background-color: {_L['surface2']};
    selection-background-color: {_L['accent_bg']};
    selection-color: {_L['text']};
    outline: none;
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QHeaderView::section {{
    background-color: {_L['surface2']};
    color: {_L['text3']};
    border: none;
    border-bottom: 1px solid {_L['border']};
    border-right: 1px solid {_L['border']};
    padding: 5px 8px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
}}
QPushButton {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {_L['surface2']};
    border-color: {_L['border2']};
}}
QPushButton#primary {{
    background-color: {_L['accent']};
    color: #ffffff;
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background-color: #0860c7;
}}
QPushButton#secondary {{
    background-color: transparent;
    color: {_L['text2']};
    border: 1px solid {_L['border']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {_L['red']};
    border: 1px solid {_L['red_bg']};
}}
QPushButton#danger:hover {{
    background-color: {_L['red_bg']};
    border-color: {_L['red']};
}}
QPushButton#success {{
    background-color: {_L['green']};
    color: #ffffff;
    border: none;
    font-weight: 600;
}}
QLineEdit {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 5px 10px;
}}
QLineEdit:focus {{
    border-color: {_L['accent']};
}}
QComboBox {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 28px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    selection-background-color: {_L['accent_bg']};
}}
QGroupBox {{
    border: 1px solid {_L['border2']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background-color: {_L['surface']};
    color: {_L['text2']};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: {_L['surface']};
}}
QGroupBox#corpus_box::title {{ color: {_L['orange']}; }}
QGroupBox#model_box::title  {{ color: {_L['accent']}; }}
QGroupBox#vec_box::title    {{ color: {_L['teal']};   }}
QGroupBox#ann_box::title    {{ color: {_L['purple']}; }}
QGroupBox#ud_box::title     {{ color: {_L['green']};  }}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {_L['surface3']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_L['border2']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {_L['surface3']};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QLabel {{
    color: {_L['text']};
    background-color: transparent;
}}
QLabel#title       {{ font-size: 16px; font-weight: 700; }}
QLabel#subtitle    {{ font-size: 12px; color: {_L['text2']}; }}
QLabel#caption     {{ font-size: 11px; color: {_L['text3']}; }}
QLabel#stat_val    {{ font-size: 22px; font-weight: 700; color: {_L['orange']}; font-family: {_FONT_MONO}; }}
QLabel#stat_label  {{ font-size: 10px; font-weight: 600; color: {_L['text3']}; letter-spacing: 1px; }}
QStatusBar {{
    background-color: {_L['surface']};
    color: {_L['text2']};
    border-top: 1px solid {_L['border']};
    font-size: 12px;
}}
QProgressBar {{
    background-color: {_L['surface2']};
    border: 1px solid {_L['border']};
    border-radius: 5px;
    text-align: center;
    color: {_L['text']};
    font-size: 11px;
    font-family: {_FONT_MONO};
    min-height: 18px;
    max-height: 18px;
}}
QProgressBar::chunk {{
    background-color: {_L['accent']};
    border-radius: 4px;
}}
QProgressBar#ready::chunk {{
    background-color: {_L['green']};
}}
QSplitter::handle {{ background-color: {_L['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:horizontal:hover {{ background-color: {_L['accent']}; }}
QSplitter::handle:vertical {{
    height: 6px;
    background-color: {_L['surface2']};
    border-top: 1px solid {_L['border2']};
    border-bottom: 1px solid {_L['border2']};
}}
QSplitter#text_splitter::handle:vertical {{
    background-color: {_L['surface2']};
    border-top: 2px solid {_L['accent']};
}}
QMenuBar {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border-bottom: 1px solid {_L['border']};
    padding: 2px;
}}
QMenuBar::item {{ padding: 4px 10px; background-color: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {_L['surface2']}; }}
QMenu {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 8px;
    padding: 4px 0;
}}
QMenu::item {{ padding: 6px 24px 6px 14px; }}
QMenu::item:selected {{ background-color: {_L['accent_bg']}; color: {_L['accent']}; }}
QMenu::separator {{ height: 1px; background-color: {_L['border']}; margin: 4px 0; }}
QToolTip {{
    background-color: {_L['surface2']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
QStackedWidget {{ background-color: {_L['bg']}; border: none; }}
QTabWidget::pane {{
    border: 1px solid {_L['border2']};
    border-radius: 6px;
    background-color: {_L['surface']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {_L['surface2']};
    color: {_L['text3']};
    border: 1px solid {_L['border']};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 5px 14px;
    font-size: 12px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {_L['surface']};
    color: {_L['accent']};
    border-color: {_L['accent']};
    font-weight: 700;
}}
QTabBar::tab:hover:!selected {{
    background-color: {_L['surface3']};
    color: {_L['text']};
}}
QScrollArea {{ background-color: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background-color: transparent; }}
"""
