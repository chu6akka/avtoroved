from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BlindDocument:
    """Единственный объект, передаваемый анализатору.

    Идентификатор автора, ожидаемое отношение пары и gold-аннотации здесь
    конструктивно отсутствуют.
    """

    document_id: str
    text: str
    sample_type: str
    genre: str
    source_type: str
    creation_context: str
    year_or_period: str
    region_optional: str | None
    word_count: int
    character_count: int
    pair_group_id: str | None
    input_sha256: str


def make_blind_document(item: dict, text: str) -> BlindDocument:
    return BlindDocument(
        document_id=item["document_id"], text=text,
        sample_type=item["sample_type"], genre=item["genre"],
        source_type=item["source_type"],
        creation_context=item["creation_context"],
        year_or_period=str(item["year_or_period"]),
        region_optional=item.get("region_optional"),
        word_count=item["word_count"],
        character_count=item["character_count"],
        pair_group_id=item.get("pair_group_id"),
        input_sha256=item["input_sha256"],
    )
