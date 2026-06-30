"""Оценщик качественных признаков локальной LLM через Ollama (оффлайн).

По умолчанию использует модель из переменной AVED_LLM_MODEL (иначе qwen2.5:3b).
Признаки оцениваются пакетами (один запрос на несколько признаков) ради скорости.
При недоступности Ollama возвращает None — ядро продолжает работать без LLM.
"""
from __future__ import annotations

import json
import os
import re

from aved.core.models import Evidence, Feature, FeatureValue
from aved.features.assessor.prompts import build_batch_prompt
from aved.features.extractors.base import ExtractorContext

_DEFAULT_MODEL = os.environ.get("AVED_LLM_MODEL", "qwen2.5:3b")


class OllamaAssessor:
    def __init__(self, model: str = _DEFAULT_MODEL, max_chars: int = 2500, batch_size: int = 12) -> None:
        self.model = model
        self.max_chars = max_chars
        self.batch_size = batch_size

    def health(self) -> tuple[bool, str]:
        """Проверить, что модель реально загружается (быстрый запрос на 1 токен)."""
        try:
            import ollama

            ollama.generate(model=self.model, prompt="ок", options={"num_predict": 1})
            return True, f"модель {self.model} доступна"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)[:200]

    def assess(self, feature: Feature, ctx: ExtractorContext) -> FeatureValue | None:
        return self.assess_batch([feature], ctx).get(feature.id)

    def assess_batch(
        self, features: list[Feature], ctx: ExtractorContext
    ) -> dict[str, FeatureValue]:
        results: dict[str, FeatureValue] = {}
        excerpt = ctx.doc.text[: self.max_chars]
        for i in range(0, len(features), self.batch_size):
            chunk = features[i : i + self.batch_size]
            items = self._query(chunk, excerpt)
            # сопоставляем ПОЗИЦИОННО: модель часто придумывает свои id, но порядок
            # элементов соответствует порядку признаков в запросе
            for f, it in zip(chunk, items):
                if not isinstance(it, dict):
                    continue
                present = bool(it.get("present"))
                conf = float(it.get("confidence", 0.5) or 0.5)
                quote = str(it.get("evidence") or "").strip()
                ev = [Evidence(quote)] if quote else []
                results[f.id] = FeatureValue(
                    feature_id=f.id, present=present, confidence=conf,
                    evidence=ev, source_kind="llm",
                    note="оценка локальной LLM (требует подтверждения эксперта)",
                )
        return results

    def _query(self, features: list[Feature], excerpt: str) -> list[dict]:
        try:
            import ollama

            resp = ollama.generate(
                model=self.model,
                prompt=build_batch_prompt(features, excerpt),
                format="json",
                options={"temperature": 0},
            )
        except Exception:
            return []  # Ollama недоступна — деградируем к пустому результату
        return _parse_items(resp.get("response", ""))


def _parse_items(text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        items = data.get("items")
        return items if isinstance(items, list) else []
    return data if isinstance(data, list) else []
