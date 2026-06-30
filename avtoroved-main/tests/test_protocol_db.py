"""Тесты слоя данных protocol/db.py (Этап 1)."""
import json

import pytest

from protocol import db as protocol_db


@pytest.fixture()
def pdb(tmp_path):
    """Чистая база во временном файле."""
    return protocol_db.ProtocolDB(str(tmp_path / "test_protocol.db"))


def test_init_creates_tables(pdb):
    # Все шесть таблиц среза должны существовать.
    with pdb._connect() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"projects", "documents", "document_layers",
            "sentences", "tokens", "audit_log"} <= names


def test_create_and_fetch_project(pdb):
    pid = pdb.create_project("Дело №1", expert_name="Эксперт И.И.",
                             program_version="5.0", note="тест")
    assert isinstance(pid, int)
    projects = pdb.fetch_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "Дело №1"
    assert projects[0]["expert_name"] == "Эксперт И.И."
    assert projects[0]["created_at"]  # ISO-метка проставлена


def test_add_document_and_fetch(pdb):
    pid = pdb.create_project("Дело")
    did = pdb.add_document(
        pid, "sporny.txt", protocol_db.ROLE_DISPUTED,
        file_sha256="abc123", provenance="цифровой",
        genre="письмо", word_count=42, note="спорный текст")
    docs = pdb.fetch_documents(pid)
    assert len(docs) == 1
    assert docs[0]["id"] == did
    assert docs[0]["role"] == protocol_db.ROLE_DISPUTED
    assert docs[0]["file_sha256"] == "abc123"
    assert docs[0]["word_count"] == 42
    assert docs[0]["imported_at"]


def test_save_and_get_layers(pdb):
    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "f.txt", protocol_db.ROLE_SAMPLE, file_sha256="h")
    pdb.save_layers(did, {
        protocol_db.LAYER_ORIGINAL: "Исходный  текст.",
        protocol_db.LAYER_CLEANED: "Исходный текст.",
    })
    assert pdb.get_layer(did, protocol_db.LAYER_ORIGINAL) == "Исходный  текст."
    assert pdb.get_layer(did, protocol_db.LAYER_CLEANED) == "Исходный текст."
    assert pdb.get_layer(did, protocol_db.LAYER_NORMALIZED) is None


def test_save_parsed_sentences_and_tokens(pdb):
    pid = pdb.create_project("Дело")
    did = pdb.add_document(pid, "f.txt", protocol_db.ROLE_DISPUTED, file_sha256="h")
    sentences = [
        {"idx": 0, "start_char": 0, "end_char": 12, "text": "Привет мир.",
         "tokens": [
             {"idx": 0, "text": "Привет", "lemma": "привет", "pos": "NOUN",
              "feats": "—", "start_char": 0, "end_char": 6},
             {"idx": 1, "text": "мир", "lemma": "мир", "pos": "NOUN",
              "feats": "—", "start_char": 7, "end_char": 10},
             {"idx": 2, "text": ".", "lemma": ".", "pos": "PUNCT",
              "feats": "—", "start_char": 10, "end_char": 11},
         ]},
        {"idx": 1, "start_char": 13, "end_char": 20, "text": "Как дела",
         "tokens": [
             {"idx": 0, "text": "Как", "lemma": "как", "pos": "ADV",
              "feats": "—", "start_char": 13, "end_char": 16},
             {"idx": 1, "text": "дела", "lemma": "дело", "pos": "NOUN",
              "feats": "—", "start_char": 17, "end_char": 21},
         ]},
    ]
    n_sent, n_tok = pdb.save_parsed(did, sentences)
    assert n_sent == 2
    assert n_tok == 5
    assert pdb.count_sentences(did) == 2
    assert pdb.count_tokens(did) == 5


def test_audit_log_json_roundtrip(pdb):
    pid = pdb.create_project("Дело")
    pdb.log_action("импортирован документ", project_id=pid,
                   details={"filename": "f.txt", "sha256": "deadbeef"},
                   program_version="5.0")
    rows = pdb.fetch_audit_log(pid)
    assert len(rows) == 1
    assert rows[0]["action"] == "импортирован документ"
    assert rows[0]["program_version"] == "5.0"
    parsed = json.loads(rows[0]["details"])
    assert parsed["filename"] == "f.txt"
    assert rows[0]["ts"]
