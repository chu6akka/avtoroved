"""ThemeEngineV2: segment-level multi-label analyzer, shadow mode only."""
from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from statistics import fmean
from typing import Any

from analyzer.semantic_layers import config_loader
from analyzer.semantic_layers.contracts import (
    PrototypeSimilarity,
    ThemeAnalysisResultV2,
    ThemeSegmentEvidence,
    ThemeV2Score,
)
from analyzer.semantic_layers.embedding_backend import (
    EmbeddingBackend,
    EmbeddingUnavailableError,
    SentenceTransformerEmbeddingBackend,
)
from analyzer.semantic_layers.lexical_theme_evidence import (
    LexicalThemeEvidenceExtractor,
)
from analyzer.semantic_layers.theme_scoring import (
    ENGINEERING_EVIDENCE_SIMILARITY_THRESHOLD,
    combined_theme_score,
    engineering_parameters,
    lexical_score,
    segment_supports_theme,
    summarise_prototypes,
)
from analyzer.semantic_layers.theme_segmenter import (
    SegmentationParameters,
    segment_text,
)


THEME_ENGINE_V2_VERSION = "v2-shadow"

_PROTOTYPE_CACHE: dict[tuple[str, str, str], tuple[tuple[float, ...], ...]] = {}
_PROTOTYPE_CACHE_LOCK = threading.Lock()


def clear_prototype_embedding_cache() -> None:
    with _PROTOTYPE_CACHE_LOCK:
        _PROTOTYPE_CACHE.clear()


def _prototype_hash(prototypes: list[str]) -> str:
    payload = json.dumps(prototypes, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cached_prototype_vectors(backend: EmbeddingBackend, theme_id: str,
                              prototypes: list[str]
                              ) -> tuple[tuple[float, ...], ...]:
    key = (backend.cache_key, theme_id, _prototype_hash(prototypes))
    with _PROTOTYPE_CACHE_LOCK:
        cached = _PROTOTYPE_CACHE.get(key)
    if cached is not None:
        return cached
    vectors = tuple(backend.encode(prototypes))
    with _PROTOTYPE_CACHE_LOCK:
        return _PROTOTYPE_CACHE.setdefault(key, vectors)


class ThemeEngineV2:
    """Явно вызываемый экспериментальный движок; production его не запускает."""

    version = THEME_ENGINE_V2_VERSION

    def __init__(
        self,
        embedding_backend: EmbeddingBackend | None = None,
        ontology: dict[str, dict] | None = None,
        prototype_config: dict[str, dict] | None = None,
        segmentation_parameters: SegmentationParameters | None = None,
        lemmatizer=None,
    ):
        self.embedding_backend = (
            embedding_backend or SentenceTransformerEmbeddingBackend())
        self.ontology = ontology or config_loader.load_theme_ontology()
        self.prototype_config = (
            prototype_config or config_loader.load_theme_prototypes())
        self.segmentation_parameters = (
            segmentation_parameters or SegmentationParameters())
        self.lexical_extractor = LexicalThemeEvidenceExtractor(
            self.ontology, lemmatizer=lemmatizer)
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        active_ids = {
            theme_id for theme_id, row in self.ontology.items()
            if row.get("active", False)
        }
        missing = active_ids - set(self.prototype_config)
        if missing:
            raise config_loader.SemanticConfigError(
                "Для активных тем отсутствуют prototypes: " + ", ".join(sorted(missing)))
        empty = {
            theme_id for theme_id in active_ids
            if not self.prototype_config[theme_id].get("prototypes")
        }
        if empty:
            raise config_loader.SemanticConfigError(
                "Для активных тем пусты prototypes: " + ", ".join(sorted(empty)))

    def _parameters(self) -> dict[str, Any]:
        return {
            **engineering_parameters(),
            "segmentation": {
                "min_tokens": self.segmentation_parameters.min_tokens,
                "target_tokens": self.segmentation_parameters.target_tokens,
                "max_tokens": self.segmentation_parameters.max_tokens,
                "overlap": 0,
                "threshold_kind": "ENGINEERING",
            },
            "prototype_cache": "theme_id+prototype_hash+model_revision",
        }

    def _controlled_result(self, *, status: str, reason: str | None,
                           segment_count: int = 0) -> ThemeAnalysisResultV2:
        return ThemeAnalysisResultV2(
            themes=(),
            dominant_theme=None,
            segment_count=segment_count,
            engine_version=self.version,
            model_info=dict(self.embedding_backend.model_info),
            parameters=self._parameters(),
            status=status,
            reason=reason,
        )

    def analyze(self, text: str) -> ThemeAnalysisResultV2:
        if not text or not text.strip():
            return self._controlled_result(status="empty", reason="empty text")

        segments = segment_text(text, self.segmentation_parameters)
        if not segments:
            return self._controlled_result(
                status="empty", reason="no valid text segments")

        active = {
            theme_id: row for theme_id, row in self.ontology.items()
            if row.get("active", False)
        }
        try:
            segment_vectors = self.embedding_backend.encode(
                [segment.text for segment in segments])
            prototype_vectors = {
                theme_id: _cached_prototype_vectors(
                    self.embedding_backend,
                    theme_id,
                    list(self.prototype_config[theme_id]["prototypes"]),
                )
                for theme_id in active
            }
        except EmbeddingUnavailableError as exc:
            return self._controlled_result(
                status="unavailable", reason=str(exc), segment_count=len(segments))

        semantic_values: dict[str, list[float]] = defaultdict(list)
        lexical_values: dict[str, list[float]] = defaultdict(list)
        combined_values: dict[str, list[float]] = defaultdict(list)
        support_counts: dict[str, int] = defaultdict(int)
        evidence: dict[str, list[ThemeSegmentEvidence]] = defaultdict(list)

        for segment, segment_vector in zip(segments, segment_vectors):
            for theme_id in active:
                prototypes = list(
                    self.prototype_config[theme_id]["prototypes"])
                summary = summarise_prototypes(
                    segment_vector, prototype_vectors[theme_id])
                semantic = summary.prototype_top3_mean
                lexical = self.lexical_extractor.analyze(
                    theme_id, segment.text, base_offset=segment.start)
                lexical_value = lexical_score(lexical.unique_match_count)
                combined = combined_theme_score(semantic, lexical_value)
                supports = segment_supports_theme(
                    combined, semantic, lexical.unique_match_count)

                semantic_values[theme_id].append(semantic)
                lexical_values[theme_id].append(lexical_value)
                combined_values[theme_id].append(combined)
                if supports:
                    support_counts[theme_id] += 1

                if (supports or lexical.fragments
                        or semantic >= ENGINEERING_EVIDENCE_SIMILARITY_THRESHOLD):
                    prototype_matches = tuple(
                        PrototypeSimilarity(prototypes[index], score)
                        for index, score in summary.ranked[:5]
                    )
                    evidence[theme_id].append(ThemeSegmentEvidence(
                        segment_id=segment.segment_id,
                        start=segment.start,
                        end=segment.end,
                        fragment=segment.text,
                        semantic_score=semantic,
                        prototype_max=summary.prototype_max,
                        prototype_top3_mean=summary.prototype_top3_mean,
                        prototype_top5_mean=summary.prototype_top5_mean,
                        lexical_match_count=lexical.match_count,
                        lexical_unique_match_count=lexical.unique_match_count,
                        lexical_coverage=lexical.coverage,
                        lexical_matches=lexical.matched_lemmas,
                        matched_phrases=lexical.matched_phrases,
                        prototype_matches=prototype_matches,
                    ))

        theme_scores: list[ThemeV2Score] = []
        segment_count = len(segments)
        for theme_id, row in active.items():
            semantic = fmean(semantic_values[theme_id])
            lexical = fmean(lexical_values[theme_id])
            combined = fmean(combined_values[theme_id])
            support_count = support_counts[theme_id]
            theme_scores.append(ThemeV2Score(
                theme_id=theme_id,
                label=row["label"],
                semantic_score=round(semantic, 6),
                lexical_score=round(lexical, 6),
                combined_score=round(combined, 6),
                coverage=round(support_count / segment_count, 6),
                segment_support_count=support_count,
                segment_count=segment_count,
                evidence=tuple(evidence[theme_id]),
                method_status=row["method_status"],
                method_feature_id=row.get("method_feature_id"),
                expert_identification_value=None,
            ))

        theme_scores.sort(
            key=lambda score: (
                -score.combined_score,
                -score.coverage,
                score.theme_id,
            ))
        dominant = next(
            (score for score in theme_scores if score.segment_support_count > 0),
            None,
        )
        return ThemeAnalysisResultV2(
            themes=tuple(theme_scores),
            dominant_theme=dominant,
            segment_count=segment_count,
            engine_version=self.version,
            model_info=dict(self.embedding_backend.model_info),
            parameters=self._parameters(),
            status="ok",
            reason=None,
        )


def compare_v1_v2(v1_result, v2_result: ThemeAnalysisResultV2) -> dict[str, Any]:
    """Сравнить ранги без утверждения о превосходстве одной версии."""
    v1_scores = [
        {"theme_id": row.key, "score": row.cosine}
        for row in getattr(v1_result, "scores", ())
    ]
    v1_dominant = (
        v1_result.top_domains[0].key
        if getattr(v1_result, "top_domains", ()) else None
    )
    v2_ranked = [
        {
            "theme_id": row.theme_id,
            "combined_score": row.combined_score,
            "semantic_similarity_score": row.semantic_score,
            "lexical_score": row.lexical_score,
            "coverage": row.coverage,
        }
        for row in v2_result.themes
    ]
    v2_dominant = (
        v2_result.dominant_theme.theme_id if v2_result.dominant_theme else None)
    v2_ids = [row["theme_id"] for row in v2_ranked]
    rank_shift = (
        v2_ids.index(v1_dominant) if v1_dominant in v2_ids else None)
    notes: list[str] = [
        "Shadow comparison; neither engine is declared superior.",
        "V2 scores are engineering similarity/ranking values, not probabilities.",
    ]
    if v2_result.status != "ok":
        notes.append(f"V2 {v2_result.status}: {v2_result.reason}")
    return {
        "v1_dominant": v1_dominant,
        "v1_scores": v1_scores,
        "v2_dominant": v2_dominant,
        "v2_ranked_themes": v2_ranked,
        "agreement": (
            v1_dominant == v2_dominant
            if v1_dominant is not None and v2_dominant is not None else False
        ),
        "rank_shift": rank_shift,
        "notes": notes,
    }
