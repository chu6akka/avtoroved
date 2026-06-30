"""Smoke-тест NLP-фасада: сегментация, морфология, синтаксис на русском тексте."""

from aved.nlp import analyze


def test_analyze_segments_and_parses():
    text = (
        "Уважаемый Иван Иванович! Прошу принять срочные меры "
        "в порядке оказания помощи населению района."
    )
    doc = analyze(text)

    # две фразы
    assert len(doc.sentences) == 2
    # достаточно слов
    assert doc.word_count() >= 10

    # есть корневой глагол (синтаксис распарсился)
    roots = [t for s in doc.sentences for t in s.tokens if t.head == -1]
    assert roots, "не найден корень предложения"
    assert any(t.pos == "VERB" for t in roots)

    # леммы приведены к начальной форме
    lemmas = {t.lemma for t in doc.words}
    assert "мера" in lemmas
    assert "принять" in lemmas

    # морфопризнаки заполнены хотя бы у части слов
    assert any(t.feats for t in doc.words)


def test_token_offsets_match_source():
    text = "Прошу принять меры."
    doc = analyze(text)
    for t in doc.tokens:
        assert text[t.start:t.stop] == t.text
