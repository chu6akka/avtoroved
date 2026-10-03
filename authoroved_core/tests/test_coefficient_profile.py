from authoroved_core.core.coefficient_profile import CoefficientProfile, default_profile
from authoroved_core.core.comparison import compare_results
from authoroved_core.core.models import AnalysisResult, Metric

PROFILE = CoefficientProfile({
    "Индекс 01. Существительные / объём текста": {"status": "stable", "auc": 0.63, "min_words_20": 100, "min_words_10": 300},
    "Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени": {"status": "topic", "auc": 0.56,
                                                                              "min_words_20": None, "min_words_10": None},
    "Коэффициент 11. Числительные / текст": {"status": "uninformative", "auc": 0.5, "min_words_20": None, "min_words_10": None},
    "Коэффициент 09. Существительные / глаголы": {"status": "stable", "auc": 0.61, "min_words_20": 200, "min_words_10": 1000},
}, source="тест", max_tested_words=1300)


def test_notes_explain_each_status():
    assert "устойчиво различает" in PROFILE.note("Индекс 01. Существительные / объём текста")
    assert "не интерпретировать" in PROFILE.note("Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени")
    assert "сведений об авторе не несёт" in PROFILE.note("Коэффициент 11. Числительные / текст")
    assert PROFILE.note("Показатель вне профиля") is None
    assert PROFILE.label("Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени") == "зависит от темы и жанра"


def test_volume_warning_depends_on_text_length():
    name = "Коэффициент 09. Существительные / глаголы"
    assert "устойчиво с ~200 слов" in PROFILE.volume_note(name, 150)
    assert PROFILE.volume_note(name, 450) is None
    assert "Даже на 1300 словах" in PROFILE.volume_note("Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени", 900)


def test_missing_profile_file_gives_no_notes(tmp_path):
    empty = CoefficientProfile.load(tmp_path / "нет.json")
    assert empty.note("Индекс 01. Существительные / объём текста", 300) is None
    assert empty.volume_summary(300) is None


def test_volume_summary_counts_informative_classic_coefficients():
    summary = PROFILE.volume_summary(150)
    assert "150 слов" in summary and "1 из 3" in summary   # устойчив только индекс 1; коэффициент 11 не считается


def test_comparison_adds_profile_notes_and_volume_limitation():
    def result(identifier, words, nouns):
        return AnalysisResult(identifier, metrics=[
            Metric("Слова", str(words), "", "Количественные показатели"),
            Metric("Предложения", "10", "", "Количественные показатели"),
            Metric("Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени", nouns, "", GROUP),
        ])
    GROUP = "Морфологические индексы идиостиля"
    comparison = compare_results(result("a", 222, "1,75 (21 / 12)"), result("b", 312, "26 (26 / 1)"), PROFILE)
    metric = next(item for item in comparison.metrics if item.name.startswith("Индекс 08"))
    assert metric.validity == "зависит от темы и жанра"
    assert "не интерпретировать" in metric.caution and "222 слов" in metric.caution
    assert any("Объём меньшего текста — 222 слов" in item for item in comparison.limitations)


def test_built_in_profile_is_present_and_marks_known_cases():
    profile = default_profile()
    assert profile.status("Коэффициент 11. Числительные / текст") == "uninformative"
    assert profile.status("Индекс 08. Глаголы настоящего и будущего времени / прошедшего времени") == "topic"
    assert profile.status("Средняя длина предложения") == "stable"
