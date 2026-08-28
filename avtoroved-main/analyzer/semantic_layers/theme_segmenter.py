"""Сегментация текста для ThemeEngineV2 с сохранением исходных offsets."""
from __future__ import annotations

import re
from dataclasses import dataclass


# Инженерные параметры Patch B. Они не являются методическими порогами.
ENGINEERING_MIN_SEGMENT_TOKENS = 8
ENGINEERING_TARGET_SEGMENT_TOKENS = 100
ENGINEERING_MAX_SEGMENT_TOKENS = 180

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-'][A-Za-zА-Яа-яЁё0-9]+)*")
_PARAGRAPH_BREAK_RE = re.compile(r"\r?\n[ \t]*\r?\n")
_SENTENCE_RE = re.compile(r"\S.*?(?:[.!?…]+(?=\s|\Z)|\Z)", re.DOTALL)


@dataclass(frozen=True)
class ThemeSegment:
    segment_id: str
    text: str
    start: int
    end: int
    sentence_count: int
    token_count: int


@dataclass(frozen=True)
class SegmentationParameters:
    min_tokens: int = ENGINEERING_MIN_SEGMENT_TOKENS
    target_tokens: int = ENGINEERING_TARGET_SEGMENT_TOKENS
    max_tokens: int = ENGINEERING_MAX_SEGMENT_TOKENS


@dataclass(frozen=True)
class _Span:
    start: int
    end: int


def _token_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _sentence_count(text: str) -> int:
    return max(1, sum(1 for _ in _SENTENCE_RE.finditer(text))) if text.strip() else 0


def _word_windows(text: str, start: int, end: int, max_tokens: int) -> list[_Span]:
    """Разрезать аномально длинное предложение без overlap по границам слов."""
    matches = list(_WORD_RE.finditer(text, start, end))
    if not matches:
        return []
    spans: list[_Span] = []
    for index in range(0, len(matches), max_tokens):
        batch = matches[index:index + max_tokens]
        chunk_start = batch[0].start()
        chunk_end = batch[-1].end()
        spans.append(_Span(chunk_start, chunk_end))
    return spans


def _paragraph_spans(text: str) -> list[_Span]:
    """Вернуть непустые абзацы, не теряя координаты при trailing whitespace."""
    boundaries = list(_PARAGRAPH_BREAK_RE.finditer(text))
    raw: list[tuple[int, int]] = []
    cursor = 0
    for boundary in boundaries:
        raw.append((cursor, boundary.start()))
        cursor = boundary.end()
    raw.append((cursor, len(text)))

    spans: list[_Span] = []
    for raw_start, raw_end in raw:
        start = raw_start
        end = raw_end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append(_Span(start, end))
    return spans


def _split_long_paragraph(text: str, span: _Span,
                          parameters: SegmentationParameters) -> list[_Span]:
    paragraph = text[span.start:span.end]
    if _token_count(paragraph) <= parameters.max_tokens:
        return [span]

    sentences = [
        _Span(span.start + match.start(), span.start + match.end())
        for match in _SENTENCE_RE.finditer(paragraph)
        if match.group().strip()
    ]
    if not sentences:
        return _word_windows(text, span.start, span.end, parameters.max_tokens)

    expanded: list[_Span] = []
    for sentence in sentences:
        if _token_count(text[sentence.start:sentence.end]) > parameters.max_tokens:
            expanded.extend(_word_windows(
                text, sentence.start, sentence.end, parameters.max_tokens))
        else:
            expanded.append(sentence)

    windows: list[_Span] = []
    current: _Span | None = None
    current_tokens = 0
    for sentence in expanded:
        count = _token_count(text[sentence.start:sentence.end])
        would_exceed_target = (
            current is not None
            and current_tokens >= parameters.min_tokens
            and current_tokens + count > parameters.target_tokens
        )
        would_exceed_max = current is not None and current_tokens + count > parameters.max_tokens
        if current is not None and (would_exceed_target or would_exceed_max):
            windows.append(current)
            current = None
            current_tokens = 0
        if current is None:
            current = sentence
            current_tokens = count
        else:
            current = _Span(current.start, sentence.end)
            current_tokens += count
    if current is not None:
        windows.append(current)
    return windows


def _merge_short_spans(text: str, spans: list[_Span],
                       parameters: SegmentationParameters) -> list[_Span]:
    if len(spans) < 2:
        return spans
    merged: list[_Span] = []
    index = 0
    while index < len(spans):
        current = spans[index]
        current_tokens = _token_count(text[current.start:current.end])
        if current_tokens < parameters.min_tokens and index + 1 < len(spans):
            following = spans[index + 1]
            combined_tokens = _token_count(text[current.start:following.end])
            if combined_tokens <= parameters.max_tokens:
                merged.append(_Span(current.start, following.end))
                index += 2
                continue
        if current_tokens < parameters.min_tokens and merged:
            previous = merged[-1]
            combined_tokens = _token_count(text[previous.start:current.end])
            if combined_tokens <= parameters.max_tokens:
                merged[-1] = _Span(previous.start, current.end)
                index += 1
                continue
        merged.append(current)
        index += 1
    return merged


def segment_text(text: str, parameters: SegmentationParameters | None = None
                 ) -> tuple[ThemeSegment, ...]:
    """Разбить текст на неперекрывающиеся тематические сегменты."""
    parameters = parameters or SegmentationParameters()
    if parameters.min_tokens < 1:
        raise ValueError("min_tokens должен быть положительным")
    if not (parameters.min_tokens <= parameters.target_tokens <= parameters.max_tokens):
        raise ValueError("ожидается min_tokens <= target_tokens <= max_tokens")
    if not text or not text.strip():
        return ()

    paragraphs = _paragraph_spans(text)
    units: list[_Span] = []
    for paragraph in paragraphs:
        units.extend(_split_long_paragraph(text, paragraph, parameters))
    units = _merge_short_spans(text, units, parameters)

    return tuple(
        ThemeSegment(
            segment_id=f"segment-{index:04d}",
            text=text[span.start:span.end],
            start=span.start,
            end=span.end,
            sentence_count=_sentence_count(text[span.start:span.end]),
            token_count=_token_count(text[span.start:span.end]),
        )
        for index, span in enumerate(units, start=1)
    )
