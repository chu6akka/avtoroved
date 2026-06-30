"""Проверка частотного словаря и оценки информативности."""

from aved.nlp.frequency import informativeness, ipm


def test_common_more_frequent_than_term():
    assert ipm("и") > ipm("артиллерия")


def test_rare_more_informative_than_common():
    assert informativeness("артиллерия") > informativeness("и")


def test_unknown_word_is_max_informative():
    assert informativeness("кваркоглюонный") == 1.0
