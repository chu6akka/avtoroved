"""Проверка авто-экстракторов на образце текста с известными признаками."""

import pytest

from aved.core.registry import Registry
from aved.features.extractors import ExtractorContext, run
from aved.nlp import analyze

SAMPLE = (
    "В соответствии с достигнутой договорённостью направляю настоящее заявление. "
    "В частности, прошу принять меры в порядке оказания помощи. "
    "Дом строится рабочими, и работа осуществляется в установленные сроки. "
    "Несомненно, данный вопрос требует решения. "
    "Если бы он был бы рассмотрен, всё бы решилось. "
    "МИД и ГОСТ упомянуты в гор. Москве."
)


@pytest.fixture(scope="module")
def ctx() -> ExtractorContext:
    return ExtractorContext(analyze(SAMPLE))


@pytest.fixture(scope="module")
def reg() -> Registry:
    return Registry.load()


def _present(reg, ctx, fid) -> bool:
    fv = run(reg.get(fid), ctx)
    assert fv is not None, f"экстрактор для {fid} не вернул значение"
    return fv.present


@pytest.mark.parametrize("fid", [
    "nsv.style.ob.stamps",            # «в соответствии с», «принять меры», «в порядке»
    "nsv.style.ob.substitutes",       # «настоящий», «данный»
    "nsv.text.logic_markers",         # «в частности»
    "nsv.lex.attitude_words",         # «несомненно»
    "nsv.style.ob.initial_abbr",      # МИД, ГОСТ
    "nsv.style.ob.sya_verbs",         # строится, осуществляется, решилось
    "nsv.style.ob.verbal_nouns",      # заявление, решение
    "nsv.synt.err.double_by",         # «Если бы … был бы … бы решилось»
    "nsv.style.ob.territorial_abbr",  # «гор.»
])
def test_known_features_present(reg, ctx, fid):
    assert _present(reg, ctx, fid), f"ожидался признак {fid}"


def test_absent_feature_on_clean_marker(reg, ctx):
    # нецензурной лексики в образце нет
    assert not _present(reg, ctx, "nsv.psy.obscene")


def test_unimplemented_extractor_returns_none(reg, ctx):
    # экстрактор «identity_constructs» ещё не реализован — должно быть None, без падения
    assert run(reg.get("nsv.style.sci.identity_constructs"), ctx) is None


def test_style_profile_detects_official_business(reg, ctx):
    fv = run(reg.get("nn.lang.style_official_business"), ctx)
    assert fv is not None and fv.present  # образец насыщен штампами ОДС


def test_conjunctions_links_present(reg, ctx):
    # союзы/союзные слова как средство связи (и, в, что …)
    assert _present(reg, ctx, "nsv.text.conjunction_links")
