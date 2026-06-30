#!/usr/bin/env python3
"""
Авторовед — рабочее место эксперта (новый интерфейс).
=====================================================
Чистый пошаговый workflow поверх существующих движков analyzer/*.

Стадии (по методике Рубцовой 2007, ЭКЦ МВД):
    1. Материал           — ввод текста(ов) и проверка пригодности
    2. Раздельный анализ  — карточка(и) автора
    3. Сравнение / Профиль — идентификация (НН/НС/НСВ) или диагностика
    4. Заключение         — единый документ + экспорт DOCX

Запуск:
    python app2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Исправление WinError 1114 (DLL init) для PyTorch на Windows — как в main.py
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    try:
        import torch as _torch
        _lib = os.path.join(os.path.dirname(_torch.__file__), "lib")
        if os.path.isdir(_lib):
            os.add_dll_directory(_lib)
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication

from ui2.main_window2 import MainWindow2


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Авторовед — рабочее место эксперта")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Avtoroved")

    win = MainWindow2()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
