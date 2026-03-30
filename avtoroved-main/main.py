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

# ── Исправление WinError 1114 (DLL init failure) для PyTorch на Windows ──────
# os.add_dll_directory() регистрирует путь для поиска DLL во ВСЕХ потоках,
# включая QThread. Простой import torch в main-потоке не решает проблему,
# так как DLL search path не наследуется дочерними потоками через PATH.
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    try:
        import torch as _torch
        _torch_lib = os.path.join(os.path.dirname(_torch.__file__), "lib")
        if os.path.isdir(_torch_lib):
            os.add_dll_directory(_torch_lib)
    except Exception:
        pass

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
