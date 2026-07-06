"""Тесты карточки токена (protocol/token_card.py)."""
from protocol import token_card as tc


class _FakeFreq:
    """Фейковый частотный движок с интерфейсом lookup/_band_for."""
    def __init__(self, data):
        self._d = data
    def lookup(self, lemma):
        return self._d.get(lemma)
    def _band_for(self, rank):
        if rank <= 300: return "core"
        if rank <= 1500: return "high"
        if rank <= 7000: return "mid"
        if rank <= 30000: return "low"
        return "rare"


class _FakeSenti:
    def lookup(self, lemma):
        return {"дрянь": ("negative", "opinion", "NOUN")}.get(lemma)


def _tok(text="слово", lemma="слово", pos="NOUN", feats="Число: единственное",
         sent_idx=0):
    return {"text": text, "lemma": lemma, "pos": pos, "feats": feats,
            "sent_idx": sent_idx}


# ── ссылки на внешние словари ────────────────────────────────────────────────
def test_dictionary_links_encode_cyrillic():
    links = tc.dictionary_links("ёжику", "ёжик")
    names = [n for n, _u in links]
    assert names == ["Викисловарь", "Грамота.ру", "КартаСлов", "Академик"]
    wiki = links[0][1]
    assert wiki.startswith("https://ru.wiktionary.org/wiki/")
    assert "%D1%91" in wiki       # «ё» перекодирована в URL


# ── частотность ──────────────────────────────────────────────────────────────
def test_frequency_bands():
    freq = _FakeFreq({"дом": (150, 890.5, "s"), "чертёж": (25000, 3.2, "s")})
    core = tc.frequency_info(freq, "дом")
    assert core["band"] == "core" and core["rank"] == 150
    low = tc.frequency_info(freq, "чертёж")
    assert low["band"] == "low"
    absent = tc.frequency_info(freq, "витиеватость")
    assert absent["band"] == "absent"
    assert tc.frequency_info(None, "дом")["band"] == "absent"   # движка нет


# ── карточка целиком ─────────────────────────────────────────────────────────
def test_build_card_basic_and_hapax():
    counts = {"слово": 3, "уникум": 1}
    card = tc.build_card(_tok(), counts)
    assert card["word"] == "слово"
    assert card["count_in_doc"] == 3
    assert card["is_hapax"] is False
    assert len(card["links"]) == 4

    hapax = tc.build_card(_tok(text="уникум", lemma="уникум"), counts)
    assert hapax["is_hapax"] is True
    assert "hapax в документе" in hapax["badges"]


def test_build_card_idiostyle_marker():
    """Редкое + маркированный регистр → бейдж «маркер идиостиля»."""
    freq = _FakeFreq({})     # слова нет в НКРЯ → absent
    counts = {"движуха": 1}
    card = tc.build_card(
        _tok(text="движуха", lemma="движуха"), counts,
        freq_engine=freq, strat_lookup={"движуха": "common_jargon"}.get)
    assert "редкое слово" in card["badges"]
    assert "маркированный регистр" in card["badges"]
    assert card["badges"][0].startswith("★")


def test_build_card_sentiment():
    card = tc.build_card(_tok(text="дрянь", lemma="дрянь"), {"дрянь": 2},
                         senti_engine=_FakeSenti())
    assert card["sentiment"] == "negative"
    assert any("тональность" in b for b in card["badges"])


def test_build_card_survives_broken_engines():
    class Broken:
        def lookup(self, lemma):
            raise RuntimeError("сломан")
        _band_for = lookup
    card = tc.build_card(_tok(), {"слово": 1},
                         freq_engine=Broken(), senti_engine=Broken(),
                         strat_lookup=None)
    assert card["band"] == "absent"     # деградация без исключений
    assert card["sentiment"] == ""
