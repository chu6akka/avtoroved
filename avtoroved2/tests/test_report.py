"""Проверка генерации заключения эксперта (DOCX)."""

from docx import Document as Docx

from aved.core.models import ObjectText, Role
from aved.core.pipeline import identify
from aved.core.registry import Registry
from aved.report import ReportMeta, generate

_BASE = (
    "В соответствии с достигнутой договорённостью направляю настоящее заявление "
    "и прошу принять меры в порядке оказания помощи населению района. "
)


def test_report_generates_valid_docx(tmp_path):
    reg = Registry.load()
    objects = [
        ObjectText(id="Q1", role=Role.DISPUTED, title="спорное письмо", text=_BASE * 8),
        ObjectText(id="S1", role=Role.SAMPLE, title="образец 1", text=_BASE * 40),
    ]
    result = identify(objects, reg)
    out = generate(result, objects, reg, tmp_path / "zakl.docx", ReportMeta(number="123"))

    assert out.exists() and out.stat().st_size > 0

    doc = Docx(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ЗАКЛЮЧЕНИЕ ЭКСПЕРТА № 123" in text
    assert "ИССЛЕДОВАНИЕ" in text
    assert "ВЫВОДЫ" in text
    # уровни индивидуализации присутствуют
    assert "НСВ" in text
    # таблица сравнения по уровням
    assert len(doc.tables) >= 1
