"""Исходные байты и извлечённый текст — разные, неизменяемые объекты."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4


class EncodingChoiceRequired(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    text: str
    original_bytes: bytes
    file_sha256: str
    text_sha256: str
    encoding: str
    import_note: str


def _docx_text(data: bytes) -> str:
    # Из legacy перенесён только порядок обхода абзацев/таблиц, не отчёты.
    from docx import Document as WordDocument
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = WordDocument(BytesIO(data))
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(Paragraph(child, doc).text)
        elif child.tag == qn("w:tbl"):
            seen = set()
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    if cell._tc not in seen:
                        seen.add(cell._tc)
                        cells.append(cell.text)
                blocks.append("\t".join(cells))
    return "\n".join(blocks)


def load_document(path: str | Path, encoding: str | None = None) -> Document:
    path = Path(path)
    if path.suffix.lower() not in {".txt", ".docx"}:
        raise ValueError("Поддерживаются только файлы TXT и DOCX.")
    data = path.read_bytes()
    if path.suffix.lower() == ".txt":
        encoding = encoding or "utf-8-sig"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as exc:
            raise EncodingChoiceRequired("Файл не удалось прочитать в выбранной кодировке.") from exc
        note = "Пробелы и переносы сохранены. Метка кодировки BOM не является частью текста."
    else:
        text = _docx_text(data)
        encoding = "docx"
        note = ("Извлечены абзацы и таблицы основного текста. Оформление, колонтитулы, "
                "сноски и текст в изображениях не анализируются. Проверьте извлечение.")
    if not text.strip():
        raise ValueError("В файле нет доступного текста. Выберите другой материал.")
    return Document(str(uuid4()), path.name, text, data, sha256_bytes(data),
                    sha256_bytes(text.encode("utf-8")), encoding, note)
