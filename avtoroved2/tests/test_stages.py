"""Проверка стадий S1 (пригодность) и S2 (раздельное исследование)."""

import pytest

from aved.core.models import ObjectText, Role
from aved.core.pipeline import analyze_objects, run_separate, run_suitability
from aved.core.registry import Registry

# ~18 слов; повторяется для набора нужного объёма
_BASE = (
    "В соответствии с достигнутой договорённостью направляю настоящее заявление "
    "и прошу принять меры в порядке оказания помощи населению района. "
)


@pytest.fixture(scope="module")
def reg() -> Registry:
    return Registry.load()


def _objects():
    return [
        ObjectText(id="Q1", role=Role.DISPUTED, title="спорный", text=_BASE * 7),
        ObjectText(id="S1", role=Role.SAMPLE, title="образец", text=_BASE * 72),
    ]


def test_suitability_passes_for_adequate_texts():
    objs = _objects()
    docs = analyze_objects(objs)
    report = run_suitability(objs, docs)

    assert report.can_proceed
    assert all(o.suitable for o in report.objects)
    assert report.disputed_words >= 100
    # объём образцов ≥ ×10 от спорного
    assert report.volume_ratio >= 10.0 and report.volume_ok
    assert report.style_consistent


def test_short_text_is_unsuitable():
    objs = [
        ObjectText(id="Q1", role=Role.DISPUTED, title="спорный", text="Короткая записка из нескольких слов."),
        ObjectText(id="S1", role=Role.SAMPLE, title="образец", text=_BASE * 20),
    ]
    docs = analyze_objects(objs)
    report = run_suitability(objs, docs)
    assert not report.can_proceed  # спорный текст слишком короткий


def test_reanalysis_after_adding_objects():
    # регресс: добавление объекта между запусками не должно ронять анализ (KeyError docs)
    from aved.ui.state import Session

    s = Session()
    s.add("обр1", _BASE * 30, Role.SAMPLE)
    s.add("обр2", _BASE * 30, Role.SAMPLE)
    s.run_analysis()
    s.add("спорный", _BASE * 10, Role.DISPUTED)  # станет Q3
    verdict = s.run_analysis()
    assert "Q3" in s.models
    assert verdict is not None


def test_separate_builds_navyk_model(reg):
    objs = _objects()
    docs = analyze_objects(objs)
    run_suitability(objs, docs)
    models = run_separate(objs, docs, reg)

    assert set(models) == {"Q1", "S1"}
    model = models["Q1"]
    # модель навыка содержит достаточно установленных признаков
    assert len(model.values) >= 40
    # официально-деловой стиль распознан
    assert "nn.lang.style_official_business" in model.present_ids()
    # признаки получили оценку устойчивости
    assert any(v.stable for v in model.values.values())
