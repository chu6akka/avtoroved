"""
Дизайн-система Автороведческого анализатора.
Цветовая схема: Professional Dark (GitHub Dark Premium) + Professional Light.
"""

# ─── Общая типографика ────────────────────────────────────────────────────────
_FONT = '"Segoe UI", "Inter", "Arial", sans-serif'
_FONT_MONO = '"Cascadia Code", "Consolas", "Courier New", monospace'

# ─── Dark palette ─────────────────────────────────────────────────────────────
_D = {
    "bg":       "#0d1117",   # основной фон
    "surface":  "#161b22",   # поверхность (редакторы, таблицы)
    "surface2": "#21262d",   # приподнятые элементы (сайдбар, шапки)
    "surface3": "#2d333b",   # ещё выше (hover, alt rows)
    "border":   "#30363d",   # рамки
    "border2":  "#484f58",   # акцентные рамки (focus)
    "text":     "#e6edf3",   # основной текст
    "text2":    "#8b949e",   # вторичный текст
    "text3":    "#6e7681",   # третичный / плейсхолдеры
    "accent":   "#58a6ff",   # primary action (синий)
    "accent_bg":"#1f3250",   # faint accent background
    "green":    "#3fb950",   # success / positive
    "green_bg": "#1a3228",
    "orange":   "#d29922",   # warning
    "orange_bg":"#2d2209",
    "red":      "#f85149",   # danger / error
    "red_bg":   "#3d1c1c",
    "purple":   "#bc8cff",   # secondary accent
    "purple_bg":"#2d1f4a",
    "teal":     "#39c5cf",   # highlight
    "sidebar":  "#161b22",   # sidebar bg
    "sidebar_hover": "#21262d",
    "sidebar_active_bg": "#1f3250",
    "sidebar_active_border": "#58a6ff",
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
    color: {_D['text']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 18px 16px 8px 16px;
    background-color: transparent;
}}
QLabel#sidebar_subtitle {{
    color: {_D['text3']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 12px 16px 4px 16px;
    background-color: transparent;
}}
QLabel#lt_status {{
    color: {_D['text2']};
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

/* ── Main analyze button (sidebar) ── */
QPushButton#analyze_btn {{
    background-color: {_D['accent']};
    color: #0d1117;
    border: none;
    border-radius: 8px;
    padding: 11px 16px;
    font-size: 14px;
    font-weight: 700;
    margin: 8px 12px;
    text-align: center;
}}
QPushButton#analyze_btn:hover {{
    background-color: #79b8ff;
}}
QPushButton#analyze_btn:pressed {{
    background-color: #388bfd;
}}
QPushButton#analyze_btn:disabled {{
    background-color: {_D['surface3']};
    color: {_D['text3']};
}}

/* ── Util buttons in sidebar ── */
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

/* ── Content area ── */
QWidget#content_area {{
    background-color: {_D['bg']};
}}

/* ── Text input ── */
QTextEdit#text_input {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 8px;
    font-family: {_FONT};
    font-size: 13px;
    padding: 8px 10px;
    selection-background-color: {_D['accent_bg']};
}}
QTextEdit#text_input:focus {{
    border-color: {_D['accent']};
}}

/* ── Generic QTextEdit / QPlainTextEdit ── */
QTextEdit, QPlainTextEdit {{
    background-color: {_D['surface']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 6px;
    font-family: {_FONT_MONO};
    font-size: 12px;
    padding: 4px 6px;
}}

/* ── Tables ── */
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
}}
QTableWidget::item {{
    padding: 3px 6px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {_D['accent_bg']};
    color: {_D['text']};
}}
QHeaderView::section {{
    background-color: {_D['surface2']};
    color: {_D['text2']};
    border: none;
    border-bottom: 1px solid {_D['border']};
    border-right: 1px solid {_D['border']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 12px;
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── Generic Buttons ── */
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
    color: #0d1117;
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background-color: #79b8ff;
}}
QPushButton#secondary {{
    background-color: transparent;
    color: {_D['text2']};
    border: 1px solid {_D['border']};
}}
QPushButton#secondary:hover {{
    background-color: {_D['surface2']};
    color: {_D['text']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {_D['red']};
    border: 1px solid {_D['red']};
}}
QPushButton#danger:hover {{
    background-color: {_D['red_bg']};
}}
QPushButton#success {{
    background-color: {_D['green']};
    color: #0d1117;
    border: none;
    font-weight: 600;
}}
QPushButton#success:hover {{
    background-color: #56d364;
}}

/* ── Inputs ── */
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
    selection-color: {_D['text']};
    outline: none;
}}

/* ── Group boxes ── */
QGroupBox {{
    border: 1px solid {_D['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    color: {_D['text2']};
    font-weight: 600;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: {_D['bg']};
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {_D['surface3']};
    border-radius: 4px;
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
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {_D['surface3']};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_D['border2']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Labels ── */
QLabel {{
    color: {_D['text']};
    background-color: transparent;
}}
QLabel#title {{
    font-size: 16px;
    font-weight: 700;
    color: {_D['text']};
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

/* ── Status bar ── */
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

/* ── Progress bar ── */
QProgressBar {{
    background-color: {_D['surface2']};
    border: 1px solid {_D['border']};
    border-radius: 4px;
    text-align: center;
    color: {_D['text']};
    font-size: 11px;
    max-height: 16px;
}}
QProgressBar::chunk {{
    background-color: {_D['accent']};
    border-radius: 3px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {_D['border']};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 6px;
    background-color: {_D['surface2']};
    border-top: 1px solid {_D['border']};
    border-bottom: 1px solid {_D['border']};
}}
QSplitter#text_splitter::handle:vertical {{
    background-color: {_D['surface2']};
    border-top: 2px solid {_D['accent']};
}}

/* ── Menu ── */
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
    border: 1px solid {_D['border']};
    border-radius: 6px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
}}
QMenu::item:selected {{
    background-color: {_D['accent_bg']};
    color: {_D['accent']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_D['border']};
    margin: 4px 0;
}}

/* ── Tooltip ── */
QToolTip {{
    background-color: {_D['surface2']};
    color: {_D['text']};
    border: 1px solid {_D['border']};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}}

/* ── Stacked / Tab content ── */
QStackedWidget {{
    background-color: {_D['bg']};
    border: none;
}}
"""


# ─── Light palette ────────────────────────────────────────────────────────────
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
    "sidebar":  "#f6f8fa",
    "sidebar_hover": "#eaeef2",
    "sidebar_active_bg": "#ddf4ff",
    "sidebar_active_border": "#0969da",
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
    color: {_L['text']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 18px 16px 8px 16px;
    background-color: transparent;
}}
QLabel#sidebar_subtitle {{
    color: {_L['text3']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
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
}}
QTableWidget::item {{
    padding: 3px 6px;
}}
QHeaderView::section {{
    background-color: {_L['surface2']};
    color: {_L['text2']};
    border: none;
    border-bottom: 1px solid {_L['border']};
    border-right: 1px solid {_L['border']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 12px;
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
    font-weight: 600;
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
    border: 1px solid {_L['red']};
}}
QPushButton#danger:hover {{
    background-color: {_L['red_bg']};
}}
QPushButton#success {{
    background-color: {_L['green']};
    color: #ffffff;
    border: none;
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
    border: 1px solid {_L['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    color: {_L['text2']};
    font-weight: 600;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background-color: {_L['bg']};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {_L['surface3']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_L['border2']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {_L['surface3']};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QLabel {{
    color: {_L['text']};
    background-color: transparent;
}}
QLabel#title {{
    font-size: 16px;
    font-weight: 700;
}}
QLabel#subtitle {{
    font-size: 12px;
    color: {_L['text2']};
}}
QLabel#caption {{
    font-size: 11px;
    color: {_L['text3']};
}}
QStatusBar {{
    background-color: {_L['surface']};
    color: {_L['text2']};
    border-top: 1px solid {_L['border']};
    font-size: 12px;
}}
QProgressBar {{
    background-color: {_L['surface2']};
    border: 1px solid {_L['border']};
    border-radius: 4px;
    text-align: center;
    color: {_L['text']};
    font-size: 11px;
    max-height: 16px;
}}
QProgressBar::chunk {{
    background-color: {_L['accent']};
    border-radius: 3px;
}}
QSplitter::handle {{
    background-color: {_L['border']};
}}
QSplitter::handle:vertical {{
    height: 6px;
    background-color: {_L['surface2']};
    border-top: 1px solid {_L['border']};
    border-bottom: 1px solid {_L['border']};
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
QMenuBar::item {{
    padding: 4px 10px;
    background-color: transparent;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {_L['surface2']};
}}
QMenu {{
    background-color: {_L['surface']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 6px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
}}
QMenu::item:selected {{
    background-color: {_L['accent_bg']};
    color: {_L['accent']};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_L['border']};
    margin: 4px 0;
}}
QToolTip {{
    background-color: {_L['surface2']};
    color: {_L['text']};
    border: 1px solid {_L['border']};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}}
QStackedWidget {{
    background-color: {_L['bg']};
    border: none;
}}
"""
