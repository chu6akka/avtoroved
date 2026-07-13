"""Тесты пунктуационных правил (analyzer/punct_checker.py)."""
from analyzer import punct_checker as pc


def _subtypes(text):
    return [e.subtype for e in pc.check(text)]


# ── базовые правила ──────────────────────────────────────────────────────────
def test_kotory_missing_comma():
    assert any("который" in s or "определительным" in s
               for s in _subtypes("Я знаю человека который живёт рядом."))


def test_adverse_conjunction():
    assert any("однако" in s for s in _subtypes("Он пришёл однако никого не застал."))


def test_clean_text_no_flags():
    assert pc.check("Я знаю человека, который живёт рядом. "
                    "Он устал, потому что работал.") == []


# ── расширенный словарь составных союзов ─────────────────────────────────────
def test_expanded_compound_conjunctions():
    for text, conj in (
        ("Он молчал так что все ушли.", "так что"),
        ("Он ушёл то есть исчез.", "то есть"),
        ("Все успели по мере того как темнело.", "по мере того как"),
        ("Он выиграл благодаря тому что готовился.", "благодаря тому что"),
        ("Успели перед тем как стемнело.", "перед тем как"),
        ("Дело закрыли в связи с тем что истёк срок.", "в связи с тем что"),
    ):
        assert any(conj in s for s in _subtypes(text)), text


def test_compound_conjunction_lookaround_guards():
    """«кто-то есть» и «так что-то» — не союзы, флага нет."""
    assert _subtypes("Кто-то есть в доме.") == []
    assert _subtypes("И так что-то пошло не так.") == []


# ── расширенный словарь вводных слов ─────────────────────────────────────────
def test_expanded_introductory_words():
    for text in ("К сожалению все ушли.", "Судя по всему дело закрыто.",
                 "Иными словами это провал.", "Как известно вода мокрая."):
        assert any("вводного" in s for s in _subtypes(text)), text


def test_intro_with_comma_not_flagged():
    assert _subtypes("К сожалению, все ушли.") == []


def test_homonymous_starters_not_flagged():
    """«Однако»/«Наконец» в начале предложения — союз/обстоятельство,
    запятая после не требуется («не навреди»)."""
    assert _subtypes("Однако он пришёл вовремя.") == []
    assert _subtypes("Наконец мы дома.") == []
