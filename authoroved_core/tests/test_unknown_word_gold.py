"""Эталонный набор словоформ: структура и то, что он уже опроверг."""
import json
from pathlib import Path

from authoroved_core.core.lt_grouping import UNKNOWN_WORD_CLASSIFICATIONS
from authoroved_core.core.word_evidence import is_space_split

GOLD = Path(__file__).parent / "fixtures" / "unknown_word_gold.json"
ALLOWED = {key for key, _ in UNKNOWN_WORD_CLASSIFICATIONS}


def items():
    return json.loads(GOLD.read_text(encoding="utf-8"))["items"]


def test_every_label_is_one_of_the_expert_classifications():
    for item in items():
        assert item["gold_label"] in ALLOWED or item["gold_label"] == ""
        if not item["gold_label"]:
            assert item["note"], "пустая метка обязана быть объяснена"


def test_gold_set_is_large_enough_to_measure_on():
    values = items()
    labelled = [item for item in values if item["gold_label"]]

    assert len(values) >= 100 and len(labelled) >= 100
    # Набор должен покрывать разные метки, а не одну.
    assert len({item["gold_label"] for item in labelled}) >= 6


def test_repetition_does_not_rule_out_a_spelling_error():
    """Именно этот случай снял сужение меток по повторяемости."""
    quoted = next(item for item in items() if item["word"] == "Мисной")

    assert quoted["gold_label"] == "spelling_error"
    assert quoted["repeats_in_document"] > 1


def test_languagetool_offers_corrections_for_words_that_are_not_typos():
    """Причина, по которой автоматический вердикт об опечатке снят."""
    values = [item for item in items()
              if item["edits"] is not None and item["gold_label"]]
    not_typos = [item for item in values if item["gold_label"] != "spelling_error"]

    assert len(not_typos) > len(values) / 2
    # Среди них есть и фамилии, и жаргонизмы: близость к подсказке не довод.
    assert {"name", "colloquial"} <= {item["gold_label"] for item in not_typos}


def test_no_space_split_survives_in_the_gold_set():
    """Вторая причина ложных вердиктов: LanguageTool разбивает слово пробелом.

    «вахтовика» превращалось в «вахт овика», стояло в одной правке и давало
    ложную «орфографическую ошибку» на нормальном слове.
    """
    split = [item for item in items()
             if item["nearest_correction"]
             and is_space_split(item["word"], item["nearest_correction"])]

    assert not split
