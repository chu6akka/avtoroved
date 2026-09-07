"""Методически нейтральная UI-модель сравнительного исследования.

Модуль не извлекает признаки и не меняет результаты ``comparison.py``. Он
только объединяет уже сохранённые позиции, кандидаты, evidence-связи и исходные
тексты в представление, пригодное для проверки экспертом.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable

from protocol import comparison as cmp
from protocol import db as protocol_db
from protocol import feature_map as fm
from protocol import feature_model as model
from protocol.expert_features import EvidenceLinkService

METHOD_FEATURE = model.METHOD_FEATURE
AUX_METRIC = model.AUX_METRIC
EVIDENCE = model.EVIDENCE
GENERAL_SKILL = model.GENERAL_SKILL

INFO_LOW = "LOW"
INFO_MEDIUM = "MEDIUM"
INFO_HIGH = "HIGH"
INFO_NOT_SPECIFIED = "NOT_SPECIFIED"

VALUE_LOW = "LOW"
VALUE_MEDIUM = "MEDIUM"
VALUE_HIGH = "HIGH"
VALUE_NOT_SET = "NOT_SET"

ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
NOT_REVIEWED = "NOT_REVIEWED"

COINCIDENCE = "COINCIDENCE"
DIFFERENCE = "DIFFERENCE"
PRESENT_ONLY_TEXT1 = "PRESENT_ONLY_TEXT1"
PRESENT_ONLY_TEXT2 = "PRESENT_ONLY_TEXT2"
AUXILIARY = "AUXILIARY"

_INFO_MAP = {"низкая": INFO_LOW, "средняя": INFO_MEDIUM, "высокая": INFO_HIGH}
_LEVEL_MAP = {"НН": "NN", "НС": "NS", "НСВ": "NSV"}
_VALUE_MAP = {"низкая": VALUE_LOW, "средняя": VALUE_MEDIUM, "высокая": VALUE_HIGH}
_RELATION_MAP = {
    cmp.MATCH_COINCIDENCE: COINCIDENCE,
    cmp.MATCH_DIFFERENCE: DIFFERENCE,
    cmp.MATCH_ONLY_A: PRESENT_ONLY_TEXT1,
    cmp.MATCH_ONLY_B: PRESENT_ONLY_TEXT2,
    cmp.GEN_EQUAL: COINCIDENCE,
    cmp.GEN_HIGHER: DIFFERENCE,
    cmp.GEN_LOWER: DIFFERENCE,
}


@dataclass(frozen=True)
class EvidenceSpan:
    document_id: int
    start: int
    end: int
    text: str
    context: str


@dataclass(frozen=True)
class MethodTrace:
    title: str = ""
    short: str = ""
    section: str = ""
    subsection: str = ""
    page: str = ""
    quote_or_summary: str = ""


@dataclass
class ComparisonFeatureView:
    feature_id: str
    feature_name: str
    method_group: str
    method_subgroup: str
    individualization_level: str
    source_kind: str
    role: str
    method_trace: MethodTrace
    method_informativeness: str
    expert_identification_value: str
    expert_status: str
    comparison_relation: str
    evidence_spans_text1: list[EvidenceSpan] = field(default_factory=list)
    evidence_spans_text2: list[EvidenceSpan] = field(default_factory=list)
    value_text1: str = ""
    value_text2: str = ""
    comparison_explanation: str = ""
    notes: str = ""
    position_key: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def has_local_evidence(self) -> bool:
        return bool(self.evidence_spans_text1 or self.evidence_spans_text2)


def _method_trace(registry: dict | None, fallback: Any = None) -> MethodTrace:
    registry = registry or {}
    source = registry.get("source") or model.get_field(fallback, "source", "")
    source_section = (registry.get("source_section")
                      or model.get_field(fallback, "source_section", ""))
    page = registry.get("method_page", "")
    if not page and re.fullmatch(r"с\.\s*.+", source_section or ""):
        page = source_section
    section = registry.get("method_section", "")
    if not section and source_section and not page:
        section = source_section
    return MethodTrace(
        title=registry.get("method_source_title") or source or "",
        short=registry.get("method_source_short") or (source.split(",")[0] if source else ""),
        section=section,
        subsection=registry.get("method_subsection", ""),
        page=page,
        quote_or_summary=(registry.get("method_quote_or_summary")
                          or registry.get("source_wording") or ""),
    )


def _source_informativeness(registry: dict | None) -> str:
    """Только прямое поле реестра; никакой инженерной эвристики."""
    return _INFO_MAP.get((registry or {}).get("reference_informativeness"),
                         INFO_NOT_SPECIFIED)


def _sentence_context(text: str, start: int, end: int) -> str:
    left = max(text.rfind(mark, 0, start) for mark in ("\n", ".", "!", "?"))
    candidates = [pos for mark in ("\n", ".", "!", "?")
                  if (pos := text.find(mark, end)) >= 0]
    right = min(candidates) + 1 if candidates else len(text)
    return text[left + 1:right].strip()


def locate_evidence_spans(document_id: int, text: str,
                          fragments: Iterable[str]) -> list[EvidenceSpan]:
    """Найти все точные реализации сохранённых evidence-фрагментов."""
    spans: list[EvidenceSpan] = []
    occupied: set[tuple[int, int]] = set()
    folded = text.casefold()
    for raw in fragments:
        fragment = (raw or "").strip()
        if not fragment:
            continue
        needle = fragment.casefold()
        offset = 0
        while (start := folded.find(needle, offset)) >= 0:
            end = start + len(fragment)
            if (start, end) not in occupied:
                occupied.add((start, end))
                spans.append(EvidenceSpan(
                    document_id, start, end, text[start:end],
                    _sentence_context(text, start, end)))
            offset = max(end, start + 1)
    return sorted(spans, key=lambda span: (span.start, span.end))


def _candidate_maps(pdb, document_id: int) -> tuple[dict[str, Any], list[Any]]:
    candidates = pdb.fetch_feature_candidates(document_id)
    return {fm.candidate_key(row): row for row in candidates}, candidates


def _evidence_fragments(pdb, document_id: int, feature_key: str,
                        fallback: Any = None) -> list[str]:
    rows = EvidenceLinkService.linked_evidence(pdb, document_id, feature_key)
    fragments = [row["fragment"] for row in rows if row["fragment"]]
    if not fragments and fallback is not None and model.get_field(fallback, "fragment", ""):
        fragments.append(model.get_field(fallback, "fragment", ""))
    return fragments


def _review_status(status: str) -> str:
    if status == cmp.STATUS_CONFIRMED:
        return ACCEPTED
    if status == cmp.STATUS_REJECTED:
        return REJECTED
    return NOT_REVIEWED


def _position_explanation(relation: str) -> str:
    return {
        COINCIDENCE: "Признак представлен в обоих текстах; квалификацию подтверждает эксперт.",
        DIFFERENCE: "Зафиксировано различие; существенность и объяснимость оценивает эксперт.",
        PRESENT_ONLY_TEXT1: "Признак найден только в тексте 1; отсутствие учитывается лишь при достаточной возможности проявления.",
        PRESENT_ONLY_TEXT2: "Признак найден только в тексте 2; отсутствие учитывается лишь при достаточной возможности проявления.",
        AUXILIARY: "Вспомогательный объективизирующий показатель; в методический комплекс не засчитывается.",
    }.get(relation, "")


def _comparison_views(pdb, doc_a: int, doc_b: int, text_a: str,
                      text_b: str, cand_a: dict, cand_b: dict) -> list[ComparisonFeatureView]:
    features_a = {r["candidate_key"]: r for r in pdb.fetch_features(document_id=doc_a)}
    features_b = {r["candidate_key"]: r for r in pdb.fetch_features(document_id=doc_b)}
    views = []
    for row in pdb.fetch_comparisons(doc_a, doc_b):
        fa = features_a.get(row["feature_key_a"] or "") or cand_a.get(row["feature_key_a"] or "")
        fb = features_b.get(row["feature_key_b"] or "") or cand_b.get(row["feature_key_b"] or "")
        exemplar = fa or fb
        role = GENERAL_SKILL if row["match_type"] in cmp.GEN_TYPES else model.normalized_role(exemplar)
        registry = model.registered_method_feature(
            model.get_field(exemplar, "method_feature_id", None)) if role == METHOD_FEATURE else None
        relation = _RELATION_MAP.get(row["match_type"], DIFFERENCE)
        spans_a = locate_evidence_spans(
            doc_a, text_a, _evidence_fragments(
                pdb, doc_a, row["feature_key_a"], fa) if row["feature_key_a"] else [])
        spans_b = locate_evidence_spans(
            doc_b, text_b, _evidence_fragments(
                pdb, doc_b, row["feature_key_b"], fb) if row["feature_key_b"] else [])
        views.append(ComparisonFeatureView(
            feature_id=(model.get_field(exemplar, "method_feature_id", "")
                        or row["position_key"]),
            feature_name=row["label"] or "",
            method_group=row["group_name"] or "",
            method_subgroup=row["subgroup"] or "",
            individualization_level=_LEVEL_MAP.get(row["level"], "NOT_APPLICABLE"),
            source_kind=(model.get_field(exemplar, "source_kind", "")
                         or (model.SOURCE_METHOD if role == GENERAL_SKILL else model.SOURCE_ENGINEERING)),
            role=role,
            method_trace=_method_trace(registry, exemplar),
            method_informativeness=(_source_informativeness(registry)
                                    if role == METHOD_FEATURE else INFO_NOT_SPECIFIED),
            expert_identification_value=_VALUE_MAP.get(
                row["identification_value"], VALUE_NOT_SET),
            expert_status=_review_status(row["status"]),
            comparison_relation=relation,
            evidence_spans_text1=spans_a,
            evidence_spans_text2=spans_b,
            value_text1=row["value_a"] or "",
            value_text2=row["value_b"] or "",
            comparison_explanation=_position_explanation(relation),
            notes=row["expert_note"] or "",
            position_key=row["position_key"],
        ))
    return views


def _candidate_views(pdb, doc_a: int, doc_b: int, text_a: str, text_b: str,
                     rows_a: list, rows_b: list, included_roles: tuple[str, ...],
                     occupied_keys: set[str]) -> list[ComparisonFeatureView]:
    def group(rows):
        out = {}
        for row in rows:
            role = model.normalized_role(row)
            key = fm.candidate_key(row)
            if role not in included_roles or key in occupied_keys:
                continue
            content_key = (role, row["group_name"] or "", row["subgroup"] or "",
                           row["label"] or "")
            out.setdefault(content_key, []).append(row)
        return out

    ga, gb = group(rows_a), group(rows_b)
    views = []
    for key in sorted(set(ga) | set(gb), key=lambda value: tuple(map(str, value))):
        role, group_name, subgroup, label = key
        aa, bb = ga.get(key, []), gb.get(key, [])
        a, b = (aa[0] if aa else None), (bb[0] if bb else None)
        relation = AUXILIARY if role == AUX_METRIC else (
            COINCIDENCE if a and b else PRESENT_ONLY_TEXT1 if a else PRESENT_ONLY_TEXT2)
        fragments_a = [r["fragment"] for r in aa if r["fragment"]]
        fragments_b = [r["fragment"] for r in bb if r["fragment"]]
        source_kind = (model.get_field(a or b, "source_kind", "")
                       or model.SOURCE_ENGINEERING)
        views.append(ComparisonFeatureView(
            feature_id=fm.candidate_key(a or b), feature_name=label,
            method_group=group_name, method_subgroup=subgroup,
            individualization_level="AUX" if role == AUX_METRIC else "NOT_APPLICABLE",
            source_kind=source_kind, role=role,
            method_trace=_method_trace(None, a or b),
            method_informativeness=INFO_NOT_SPECIFIED,
            expert_identification_value=VALUE_NOT_SET,
            expert_status=NOT_REVIEWED, comparison_relation=relation,
            evidence_spans_text1=locate_evidence_spans(doc_a, text_a, fragments_a),
            evidence_spans_text2=locate_evidence_spans(doc_b, text_b, fragments_b),
            value_text1=" ; ".join(r["value"] for r in aa if r["value"]),
            value_text2=" ; ".join(r["value"] for r in bb if r["value"]),
            comparison_explanation=_position_explanation(relation),
            notes="",
        ))
    return views


def build_feature_views(pdb: "protocol_db.ProtocolDB", project_id: int,
                        doc_a: int, doc_b: int) -> list[ComparisonFeatureView]:
    del project_id  # reserved for future per-case policies; no computation here
    text_a = pdb.get_layer(doc_a, protocol_db.LAYER_ORIGINAL) or ""
    text_b = pdb.get_layer(doc_b, protocol_db.LAYER_ORIGINAL) or ""
    cand_map_a, rows_a = _candidate_maps(pdb, doc_a)
    cand_map_b, rows_b = _candidate_maps(pdb, doc_b)
    views = _comparison_views(pdb, doc_a, doc_b, text_a, text_b, cand_map_a, cand_map_b)
    occupied = {key for row in pdb.fetch_comparisons(doc_a, doc_b)
                for key in (row["feature_key_a"], row["feature_key_b"]) if key}
    views.extend(_candidate_views(
        pdb, doc_a, doc_b, text_a, text_b, rows_a, rows_b,
        (AUX_METRIC, EVIDENCE), occupied))
    return views


def filter_views(rows: Iterable[ComparisonFeatureView], *, role: str = "",
                 level: str = "", relation: str = "", status: str = "",
                 method_informativeness: str = "", expert_value: str = ""
                 ) -> list[ComparisonFeatureView]:
    return [row for row in rows
            if (not role or row.role == role)
            and (not level or row.individualization_level == level)
            and (not relation or row.comparison_relation == relation)
            and (not status or row.expert_status == status)
            and (not method_informativeness
                 or row.method_informativeness == method_informativeness)
            and (not expert_value or row.expert_identification_value == expert_value)]


def summarize(rows: Iterable[ComparisonFeatureView]) -> dict:
    rows = list(rows)
    methods = [row for row in rows if row.role == METHOD_FEATURE]
    return {
        "total_candidates": len(rows),
        "method": {status: sum(row.expert_status == status for row in methods)
                   for status in (ACCEPTED, REJECTED, NOT_REVIEWED)},
        "aux": sum(row.role == AUX_METRIC for row in rows),
        "relations": {relation: sum(row.comparison_relation == relation for row in rows)
                      for relation in (COINCIDENCE, DIFFERENCE,
                                       PRESENT_ONLY_TEXT1, PRESENT_ONLY_TEXT2)},
        "levels": {level: sum(row.individualization_level == level for row in methods)
                   for level in ("NN", "NS", "NSV")},
        "method_informativeness": {
            value: sum(row.method_informativeness == value for row in methods)
            for value in (INFO_HIGH, INFO_MEDIUM, INFO_LOW, INFO_NOT_SPECIFIED)},
        "expert_high": sum(row.expert_identification_value == VALUE_HIGH
                           for row in methods),
    }
