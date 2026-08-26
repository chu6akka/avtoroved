"""
protocol/ingest.py — импорт материалов и построение слоёв текста (Этап 1).

Читает TXT/DOCX/PDF, считает sha256 файла, строит слои `original` и `cleaned`,
считает объём в словоформах, затем разбивает текст на предложения и токены,
ПЕРЕИСПОЛЬЗУЯ уже инициализированный в приложении NLP-бэкенд (StanzaBackend
или SpacyBackend — любой объект с методом .analyze(text), возвращающим список
токенов с атрибутами text/lemma/pos/feats/char_start/char_end/sent_id).

Тяжёлых зависимостей не добавляем:
  • TXT/DOCX — через analyzer.export.load_text_from_file (python-docx уже есть);
  • PDF — опционально через pypdf, при отсутствии библиотеки даётся понятная
    ошибка, а UI отключает PDF-кнопку (см. PDF_AVAILABLE).
Разбиение на предложения берём из самого бэкенда (Stanza сегментирует текст),
поэтому razdel и прочие зависимости не нужны.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Callable, Optional

from protocol import db as protocol_db

# Словоформа = последовательность буквенных символов (рус./лат.).
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")

# Доступность PDF определяется наличием pypdf (мягкая зависимость).
try:
    import pypdf  # noqa: F401
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

SUPPORTED_EXTS = (".txt", ".docx") + ((".pdf",) if PDF_AVAILABLE else tuple())

StatusCb = Optional[Callable[[str], None]]

# ── Оценка извлечения текста (защита от пустого/мизерного импорта) ────────────
# Это НЕ полный гейт пригодности (он будет на следующем этапе), а лишь сигнал,
# что из файла не извлёкся осмысленный текст.
MIN_WORDS_EMPTY = 20    # ниже этого (или 0 токенов) — считаем «пусто»
MIN_WORDS_SAMPLE = 100  # ниже методического минимума образца — «мало» (не блокируем)

STATUS_EMPTY = "пусто"
STATUS_LOW = "мало"
STATUS_OK = "ок"


def assess_extraction(filename: str, word_count: Optional[int],
                      token_count: int) -> tuple[str, str]:
    """
    Оценить результат извлечения текста документа.

    Возвращает (статус, причина):
      • STATUS_EMPTY — текст не извлечён (0 токенов) или объём < MIN_WORDS_EMPTY;
        для PDF с пустым/мизерным текстом причина указывает на необходимость OCR;
      • STATUS_LOW   — извлечено, но объём < MIN_WORDS_SAMPLE (помечаем, не блокируем);
      • STATUS_OK    — иначе.
    """
    wc = word_count or 0
    ext = os.path.splitext(filename)[1].lower()
    if token_count <= 0 or wc < MIN_WORDS_EMPTY:
        if ext == ".pdf":
            reason = "PDF без текстового слоя — вероятно скан, требуется OCR"
        elif token_count <= 0:
            reason = "текст не извлечён"
        else:
            reason = f"извлечено менее {MIN_WORDS_EMPTY} словоформ"
        return STATUS_EMPTY, reason
    if wc < MIN_WORDS_SAMPLE:
        return STATUS_LOW, f"объём ниже методического минимума образца ({MIN_WORDS_SAMPLE} словоформ)"
    return STATUS_OK, "извлечение в норме"


# ── хэш и извлечение текста ──────────────────────────────────────────────────
def file_sha256(filepath: str) -> str:
    """SHA-256 файла (потоковое чтение, для больших файлов)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(filepath: str) -> str:
    """
    Извлечь исходный текст (слой `original`) из TXT/DOCX/PDF.

    TXT/DOCX делегируются analyzer.export.load_text_from_file (там перебор
    кодировок и python-docx). PDF читается через pypdf, если он установлен.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        if not PDF_AVAILABLE:
            raise ValueError(
                "Чтение PDF недоступно: не установлен pypdf "
                "(pip install pypdf). Используйте TXT или DOCX."
            )
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages)
    # TXT/DOCX — переиспользуем существующий загрузчик приложения.
    from analyzer.export import load_text_from_file
    return load_text_from_file(filepath)


# ── слой cleaned ─────────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    """
    Нормализация без потери содержания: единый перенос строки, склейка слов,
    разорванных переносом (сло-\\nво → слово), схлопывание пробелов и лишних
    пустых строк. Абзацная структура сохраняется.
    """
    # Унифицируем переносы строк.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Склейка слова, разорванного дефисом-переносом в конце строки.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Табы и неразрывные пробелы → обычный пробел.
    text = text.replace("\t", " ").replace(" ", " ")
    # Несколько пробелов подряд → один.
    text = re.sub(r"[ ]{2,}", " ", text)
    # Пробелы по краям строк.
    text = "\n".join(line.strip() for line in text.split("\n"))
    # Три+ пустые строки → одна пустая (граница абзаца).
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_words(text: str) -> int:
    """Объём текста в словоформах."""
    return len(_WORD_RE.findall(text))


# ── сегментация через NLP-бэкенд ─────────────────────────────────────────────
def segment(backend: Any, text: str, status_cb: StatusCb = None) -> list[dict]:
    """
    Разбить текст на предложения и токены, переиспользуя NLP-бэкенд приложения.

    backend — объект с методом .analyze(text) -> список токенов с атрибутами
    text, lemma, pos, feats, char_start, char_end, sent_id (как TokenInfo).
    Координаты предложений выводятся из координат входящих в них токенов.
    """
    if status_cb:
        status_cb("NLP-разметка (предложения, леммы, части речи)...")
    tokens = backend.analyze(text)

    # Группируем токены по предложениям, сохраняя порядок появления sent_id.
    order: list[int] = []
    groups: dict[int, list] = {}
    for tok in tokens:
        sid = getattr(tok, "sent_id", 0)
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append(tok)

    sentences: list[dict] = []
    for new_idx, sid in enumerate(order):
        toks = groups[sid]
        starts = [t.char_start for t in toks if getattr(t, "char_start", 0) or t.char_start == 0]
        ends = [t.char_end for t in toks if getattr(t, "char_end", 0) or t.char_end == 0]
        s_start = min(starts) if starts else None
        s_end = max(ends) if ends else None
        if s_start is not None and s_end is not None and s_end > s_start:
            s_text = text[s_start:s_end]
        else:
            s_text = " ".join(t.text for t in toks)
        tok_dicts = [
            {
                "idx": i,
                "text": t.text,
                "lemma": getattr(t, "lemma", None),
                "pos": getattr(t, "pos", None),
                "feats": getattr(t, "feats", None),
                "start_char": getattr(t, "char_start", None),
                "end_char": getattr(t, "char_end", None),
            }
            for i, t in enumerate(toks)
        ]
        sentences.append({
            "idx": new_idx,
            "start_char": s_start,
            "end_char": s_end,
            "text": s_text,
            "tokens": tok_dicts,
        })
    return sentences


# ── основной сценарий импорта ────────────────────────────────────────────────
def import_document(
    pdb: protocol_db.ProtocolDB,
    project_id: int,
    filepath: str,
    role: str,
    backend: Any,
    provenance: Optional[str] = None,
    genre: Optional[str] = None,
    document_date: Optional[str] = None,
    communicative_situation: Optional[str] = None,
    note: Optional[str] = None,
    program_version: Optional[str] = None,
    status_cb: StatusCb = None,
) -> dict:
    """
    Полный импорт одного документа в проект:
      1. sha256 файла, извлечение слоя original;
      2. построение слоя cleaned, подсчёт словоформ;
      3. регистрация документа (documents) + запись слоёв (document_layers);
      4. NLP-разметка: предложения и токены (sentences/tokens);
      5. записи в журнал (audit_log) на каждом значимом шаге.

    Возвращает словарь со сводкой:
      {document_id, filename, sha256, word_count, sentence_count, token_count}.
    """
    filename = os.path.basename(filepath)

    if status_cb:
        status_cb(f"Чтение файла: {filename}")
    sha = file_sha256(filepath)
    original = extract_text(filepath)
    cleaned = clean_text(original)
    wc = count_words(cleaned)

    document_id = pdb.add_document(
        project_id=project_id,
        filename=filename,
        role=role,
        file_sha256=sha,
        provenance=provenance,
        genre=genre,
        document_date=document_date,
        communicative_situation=communicative_situation,
        word_count=wc,
        note=note,
    )
    pdb.log_action(
        action="импортирован документ",
        project_id=project_id,
        details={"document_id": document_id, "filename": filename,
                 "role": role, "sha256": sha, "word_count": wc},
        program_version=program_version,
    )

    if status_cb:
        status_cb("Построение слоёв текста (original, cleaned)...")
    pdb.save_layers(document_id, {
        protocol_db.LAYER_ORIGINAL: original,
        protocol_db.LAYER_CLEANED: cleaned,
    })
    pdb.log_action(
        action="построены слои текста",
        project_id=project_id,
        details={"document_id": document_id,
                 "layers": [protocol_db.LAYER_ORIGINAL, protocol_db.LAYER_CLEANED]},
        program_version=program_version,
    )

    # NLP-разметка идёт по слою cleaned (координаты ссылаются на него).
    sentences = segment(backend, cleaned, status_cb=status_cb)
    n_sent, n_tok = pdb.save_parsed(document_id, sentences)
    pdb.log_action(
        action="выполнена NLP-разметка",
        project_id=project_id,
        details={"document_id": document_id,
                 "sentence_count": n_sent, "token_count": n_tok},
        program_version=program_version,
    )

    # Оценка извлечения: защита от пустого/мизерного текста (не блокирует импорт).
    status, reason = assess_extraction(filename, wc, n_tok)
    pdb.log_action(
        action="оценка извлечения",
        project_id=project_id,
        details={"document_id": document_id, "статус": status,
                 "word_count": wc, "token_count": n_tok, "причина": reason},
        program_version=program_version,
    )

    return {
        "document_id": document_id,
        "filename": filename,
        "sha256": sha,
        "word_count": wc,
        "sentence_count": n_sent,
        "token_count": n_tok,
        "extraction_status": status,
        "extraction_reason": reason,
    }
