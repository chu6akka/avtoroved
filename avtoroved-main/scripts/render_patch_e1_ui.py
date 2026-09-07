"""Воспроизводимый снимок before/after интерфейса Patch E.1 на Pilot 01."""
from __future__ import annotations

import os
import sys
import tempfile
import gc
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("AVTOROVED_SOURCE_ROOT", SCRIPT_ROOT))
CONTENT_ROOT = Path(os.environ.get("AVTOROVED_CONTENT_ROOT", SCRIPT_ROOT))
OUTPUT_ROOT = Path(os.environ.get("AVTOROVED_OUTPUT_ROOT", SCRIPT_ROOT))
SCREENSHOT_NAME = os.environ.get("AVTOROVED_SCREENSHOT_NAME", "patch_e1_before.png")
sys.path.insert(0, str(SOURCE_ROOT))

from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from protocol import comparison, db as protocol_db, feature_model  # noqa: E402
from tests.method_feature_helpers import qualified_feature  # noqa: E402
from ui.tabs.comparative_research_tab import ComparativeResearchTab  # noqa: E402


def main() -> None:
    output = OUTPUT_ROOT / "docs" / "screenshots" / SCREENSHOT_NAME
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix="avtoroved-e1-before-", ignore_cleanup_errors=True) as temp:
        pdb = protocol_db.ProtocolDB(str(Path(temp) / "case.db"))
        project = pdb.create_project("Pilot 01 — Case 001", expert_name="Эксперт")
        text_a = (CONTENT_ROOT / "artifacts" / "pilot01_corpus" / "blind" /
                  "CASE_001" / "TEXT_A.txt").read_text(encoding="utf-8")
        text_b = (CONTENT_ROOT / "artifacts" / "pilot01_corpus" / "blind" /
                  "CASE_001" / "TEXT_B.txt").read_text(encoding="utf-8")
        a = pdb.add_document(project, "TEXT_A.txt", protocol_db.ROLE_DISPUTED,
                             "a", word_count=len(text_a.split()))
        b = pdb.add_document(project, "TEXT_B.txt", protocol_db.ROLE_SAMPLE,
                             "b", word_count=len(text_b.split()))
        pdb.save_layer(a, protocol_db.LAYER_ORIGINAL, text_a)
        pdb.save_layer(b, protocol_db.LAYER_ORIGINAL, text_b)
        for label in ("Политическая направленность текста",
                      "Авторская лексическая особенность",
                      "Синтаксическая конструкция"):
            qualified_feature(pdb, project, a, label, value="наблюдается")
            qualified_feature(pdb, project, b, label, value="наблюдается")
        for label, fragment in (
            ("Криминальный жаргон: «капуста»",
             "Сверху лук, морковь, картошка, капуста, лавровый лист, соль, перец."),
            ("Обсценная лексика: «скотину»",
             "Почти все в те годы держали скотину, коров, овец, коз, свиней."),
            ("Просторечие: «туда»",
             "Рано утром в 5-6 часов, топилась русская печь, и кастрюля отправлялась туда."),
        ):
            pdb.save_feature_candidates(b, [{
                "group_name": "языковые", "subgroup": "лексические",
                "kind": "кандидат_признак", "label": label,
                "value": "машинный кандидат; проверить контекст",
                "fragment": fragment, "source": "stratification_engine",
                "role": feature_model.EVIDENCE,
                "source_kind": feature_model.SOURCE_ENGINEERING,
                "id_value": "", "reliability": "",
            }])
        for did, value in ((a, "5.8"), (b, "10.7")):
            pdb.save_feature_candidates(did, [{
                "group_name": "текстологические", "subgroup": "архитектоника",
                "kind": "счётчик", "label": "Средняя длина предложения (слов)",
                "value": value, "fragment": None, "source": "statistics",
                "role": feature_model.AUX_METRIC,
                "source_kind": feature_model.SOURCE_ENGINEERING,
                "id_value": "", "reliability": "",
            }])
        comparison.auto_match(pdb, project, a, b)

        original_init = protocol_db.ProtocolDB.__init__
        protocol_db.ProtocolDB.__init__ = lambda self: original_init(self, pdb.path)
        try:
            app = QApplication.instance() or QApplication([])
            QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\arial.ttf")
            app.setFont(QFont("Arial", 9))
            widget = ComparativeResearchTab()
            widget.resize(1760, 1040)
            widget.show()
            app.processEvents()
            if hasattr(widget, "summary_label"):
                selected = {}
                for term in ("капуста", "скотину", "туда"):
                    for row in range(widget.table.rowCount()):
                        if term in widget.table.item(row, 0).text().casefold():
                            widget.table.selectRow(row); app.processEvents()
                            selected[term] = widget.text_b._spans[0].context
                            break
                assert "морковь" in selected["капуста"]
                assert "коров" in selected["скотину"]
                assert "печ" in selected["туда"]
                for row in range(widget.table.rowCount()):
                    if "капуста" in widget.table.item(row, 0).text().casefold():
                        widget.table.selectRow(row); break
                app.processEvents()
            widget.grab().save(str(output))
            widget.close()
            widget.deleteLater()
            app.processEvents()
        finally:
            protocol_db.ProtocolDB.__init__ = original_init
        pdb = None
        gc.collect()
    print(output)


if __name__ == "__main__":
    main()
