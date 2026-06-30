"""
Тесты импорта protocol/ingest.py (Этап 1).

NLP-бэкенд не загружается: используется лёгкий фейковый backend с тем же
интерфейсом, что у StanzaBackend (.analyze(text) -> токены с атрибутами
text/lemma/pos/feats/char_start/char_end/sent_id). Тесты идут быстро.
"""
import re

import pytest

from protocol import db as protocol_db
from protocol import ingest


class _FakeToken:
    """Минимальный аналог analyzer.stanza_backend.TokenInfo для тестов."""
    def __init__(self, text, lemma, pos, feats, char_start, char_end, sent_id):
        self.text = text
        self.lemma = lemma
        self.pos = pos
        self.feats = feats
        self.char_start = char_start
        self.char_end = char_end
        self.sent_id = sent_id


class FakeBackend:
    """
    Игрушечный сегментатор: предложения — по . ! ?, токены — буквенные группы
    и одиночная финальная пунктуация. Координаты вычисляются по позиции в тексте.
    """
    _TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+|[.!?]")

    def analyze(self, text):
        tokens = []
        sent_id = 0
        for m in self._TOKEN_RE.finditer(text):
            tok = m.group(0)
            pos = "PUNCT" if tok in ".!?" else "NOUN"
            tokens.append(_FakeToken(
                text=tok, lemma=tok.lower(), pos=pos, feats="—",
                char_start=m.start(), char_end=m.end(), sent_id=sent_id))
            if tok in ".!?":
                sent_id += 1
        return tokens


@pytest.fixture()
def pdb(tmp_path):
    return protocol_db.ProtocolDB(str(tmp_path / "ingest.db"))


def test_file_sha256_stable(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("одинаковое содержимое", encoding="utf-8")
    h1 = ingest.file_sha256(str(f))
    h2 = ingest.file_sha256(str(f))
    assert h1 == h2 and len(h1) == 64


def test_clean_text_normalizes_without_losing_content():
    raw = "Пер-\nвое   слово.\r\n\n\n\nВторое\tслово."
    cleaned = ingest.clean_text(raw)
    assert "Первое слово." in cleaned     # склейка переноса + один пробел
    assert "Второе слово." in cleaned     # таб → пробел
    assert "\n\n\n" not in cleaned        # лишние пустые строки убраны


def test_count_words():
    assert ingest.count_words("раз два три, четыре!") == 4


def test_segment_builds_sentences_and_tokens():
    backend = FakeBackend()
    text = "Привет мир. Как дела?"
    sents = ingest.segment(backend, text)
    assert len(sents) == 2
    # Координаты предложения позволяют восстановить его текст из исходной строки.
    assert text[sents[0]["start_char"]:sents[0]["end_char"]].startswith("Привет")
    assert any(t["text"] == "Привет" for t in sents[0]["tokens"])
    assert sents[0]["tokens"][0]["lemma"] == "привет"


def test_import_document_end_to_end(tmp_path, pdb):
    f = tmp_path / "sporny.txt"
    f.write_text("Первое предложение. Второе предложение тут.", encoding="utf-8")

    pid = pdb.create_project("Дело", program_version="5.0")
    summary = ingest.import_document(
        pdb, pid, str(f), protocol_db.ROLE_DISPUTED, FakeBackend(),
        provenance="цифровой", genre="письмо", program_version="5.0")

    assert summary["sha256"] and len(summary["sha256"]) == 64
    assert summary["word_count"] == 5
    assert summary["sentence_count"] == 2
    assert summary["token_count"] > 0

    # Документ и слои записаны.
    docs = pdb.fetch_documents(pid)
    assert len(docs) == 1
    did = docs[0]["id"]
    assert pdb.get_layer(did, protocol_db.LAYER_ORIGINAL) is not None
    assert pdb.get_layer(did, protocol_db.LAYER_CLEANED) is not None
    assert pdb.count_sentences(did) == 2

    # Журнал содержит все значимые шаги.
    actions = [r["action"] for r in pdb.fetch_audit_log(pid)]
    assert "импортирован документ" in actions
    assert "построены слои текста" in actions
    assert "выполнена NLP-разметка" in actions


def test_pdf_disabled_without_pypdf(tmp_path, pdb):
    # Если pypdf не установлен, extract_text для .pdf даёт понятную ошибку.
    if ingest.PDF_AVAILABLE:
        pytest.skip("pypdf установлен — проверка fallback неактуальна")
    fake_pdf = tmp_path / "x.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 not a real pdf")
    with pytest.raises(ValueError, match="pypdf"):
        ingest.extract_text(str(fake_pdf))
