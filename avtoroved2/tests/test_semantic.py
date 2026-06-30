"""Проверка семантического определения тематики (Navec, оффлайн)."""

from aved.core.registry import Registry
from aved.features.extractors import ExtractorContext, run
from aved.nlp import analyze

_MILITARY = (
    "Военнослужащие подразделения заняли оборону на рубеже. Командование отдало "
    "приказ открыть огонь из артиллерии по позициям неприятеля. Бойцы отразили атаку."
)
_COOKING = (
    "Я обжарил лук на сковороде, добавил морковь и специи, затем влил горячий "
    "бульон и тушил овощи до готовности под крышкой."
)


def test_semantic_theme_separates_topics():
    reg = Registry.load()
    mil = run(reg.get("nn.smysl.military"), ExtractorContext(analyze(_MILITARY)))
    cook = run(reg.get("nn.smysl.military"), ExtractorContext(analyze(_COOKING)))
    assert mil.present
    assert mil.value > cook.value
    # семантика ловит контекст даже сверх дословных совпадений
    assert mil.value >= 0.35
