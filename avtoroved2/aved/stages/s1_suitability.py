"""Стадия S1 — оценка пригодности объектов (методика, с. 80–83).

Проверяется: объём каждого текста (≥100–150 слов), язык, преобладающий
функциональный стиль и объём сравнительного материала (рекомендуется ×10–15 от
спорного). Непригодные объекты исключаются из дальнейшего исследования.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from aved.core.models import ObjectText, Role
from aved.features.extractors import ExtractorContext
from aved.features.extractors.style import dominant_style
from aved.nlp.backend import Document

MIN_WORDS = 100
RECOMMENDED_WORDS = 150
MIN_VOLUME_RATIO = 10.0


@dataclass
class ObjectSuitability:
    object_id: str
    role: str
    word_count: int
    suitable: bool
    style: str | None
    notes: list[str] = field(default_factory=list)


@dataclass
class SuitabilityReport:
    objects: list[ObjectSuitability]
    disputed_words: int
    sample_words: int
    volume_ratio: float
    volume_ok: bool
    style_consistent: bool
    language_consistent: bool
    notes: list[str] = field(default_factory=list)

    @property
    def can_proceed(self) -> bool:
        """Можно ли переходить к раздельному исследованию."""
        return (
            any(o.suitable and o.role == Role.DISPUTED.value for o in self.objects)
            and any(o.suitable and o.role == Role.SAMPLE.value for o in self.objects)
        )


def _cyrillic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё")
    return cyr / len(letters)


def assess(
    objects: list[ObjectText],
    docs: dict[str, Document],
    data_dir=None,
) -> SuitabilityReport:
    per: list[ObjectSuitability] = []
    disputed_words = sample_words = 0

    for obj in objects:
        doc = docs[obj.id]
        wc = doc.word_count()
        obj.word_count = wc
        notes: list[str] = []
        suitable = wc >= MIN_WORDS
        if wc < MIN_WORDS:
            notes.append(f"объём {wc} слов меньше минимума {MIN_WORDS}: непригоден")
        elif wc < RECOMMENDED_WORDS:
            notes.append(
                f"объём {wc} слов меньше рекомендуемых {RECOMMENDED_WORDS}: "
                "пригоден с ограничениями"
            )
        if _cyrillic_ratio(obj.text) < 0.5:
            notes.append("текст не на русском языке (кириллица < 50%)")
            suitable = False

        style = dominant_style(ExtractorContext(doc, data_dir))
        obj.suitable = suitable
        obj.suitability_notes = notes
        per.append(ObjectSuitability(obj.id, obj.role.value, wc, suitable, style, notes))

        if obj.role is Role.DISPUTED:
            disputed_words += wc
        else:
            sample_words += wc

    ratio = sample_words / disputed_words if disputed_words else 0.0
    volume_ok = ratio >= MIN_VOLUME_RATIO

    disp_styles = {o.style for o in per if o.role == Role.DISPUTED.value and o.style}
    samp_styles = {o.style for o in per if o.role == Role.SAMPLE.value and o.style}
    style_consistent = bool(disp_styles & samp_styles) if disp_styles and samp_styles else True
    language_consistent = all(_cyrillic_ratio(o.text) >= 0.5 for o in objects)

    notes = []
    if not volume_ok:
        notes.append(
            f"объём образцов {sample_words} слов даёт соотношение ×{ratio:.1f} "
            f"(методика рекомендует ≥×{MIN_VOLUME_RATIO:.0f} от спорного текста)"
        )
    if not style_consistent:
        notes.append(
            "преобладающий функциональный стиль спорного текста и образцов "
            "различается — сопоставимость снижена"
        )
    if not language_consistent:
        notes.append("язык изложения объектов различается")

    return SuitabilityReport(
        objects=per,
        disputed_words=disputed_words,
        sample_words=sample_words,
        volume_ratio=round(ratio, 1),
        volume_ok=volume_ok,
        style_consistent=style_consistent,
        language_consistent=language_consistent,
        notes=notes,
    )
