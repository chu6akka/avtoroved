#!/usr/bin/env python3
"""
Автороведческий анализатор v5
==============================
Инструмент судебно-автороведческой экспертизы текста.

Запуск:
    python main.py

Требования:
    pip install -r requirements.txt
"""
import os
import sys

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Автороведческий анализатор")
    app.setApplicationVersion("5.0")
    app.setOrganizationName("AutorovedAnalyzer")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
