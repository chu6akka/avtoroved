"""Запуск: python -m authoroved_core.app из корня репозитория."""
import logging
import sys
from pathlib import Path


def main():
    from PyQt6.QtWidgets import QApplication
    from authoroved_core.ui.main_window import MainWindow

    local = Path(__file__).parent / ".local"
    local.mkdir(exist_ok=True)
    logging.basicConfig(filename=local / "technical.log", encoding="utf-8",
                        level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Авторовед Core")
    app.setOrganizationName("Авторовед")
    window = MainWindow()
    window.show()
    if len(sys.argv) == 2:
        window.load_path(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
