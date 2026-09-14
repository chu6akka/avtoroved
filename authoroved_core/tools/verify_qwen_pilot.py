"""Реальная офлайн-проверка пилотного окна Qwen с контрольным снимком."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import monotonic, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from authoroved_core.ui.appearance import STYLE  # noqa: E402
from authoroved_core.ui.qwen_pilot import (  # noqa: E402
    DEFAULT_QWEN_MODEL, DEFAULT_QWEN_RUNTIME, QwenPilotDialog,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=DEFAULT_QWEN_RUNTIME)
    parser.add_argument("--model", type=Path, default=DEFAULT_QWEN_MODEL)
    parser.add_argument(
        "--screenshot", type=Path,
        default=Path("authoroved_core/artifacts/qwen_pilot_theme.png"),
    )
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "georgia.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setStyleSheet(STYLE)
    text = (
        "Городские службы начали ремонт дороги. "
        "Рабочие снимают старый асфальт и готовят новое покрытие."
    )
    dialog = QwenPilotDialog(
        text, "Контрольная тематическая проверка.txt",
        runtime=args.runtime, model=args.model,
    )
    dialog.profile.setCurrentIndex(dialog.profile.findData("theme_assistance"))
    dialog.show()
    dialog.start()
    deadline = monotonic() + 300
    while dialog.worker and dialog.worker.isRunning() and monotonic() < deadline:
        app.processEvents()
        sleep(0.02)
    app.processEvents()
    if dialog.worker and dialog.worker.isRunning():
        raise TimeoutError("Пилотное окно не завершило локальную проверку.")
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    if not dialog.grab().save(str(args.screenshot)):
        raise RuntimeError("Не удалось сохранить контрольный снимок пилотного окна.")
    print(json.dumps({
        "summary": dialog.result_summary.text(),
        "candidate_count": dialog.candidate_list.count(),
        "first_candidate": (
            dialog.candidate_list.item(0).text() if dialog.candidate_list.count() else ""
        ),
        "screenshot": str(args.screenshot.resolve()),
    }, ensure_ascii=False))
    dialog.close()
    app.processEvents()


if __name__ == "__main__":
    main()
