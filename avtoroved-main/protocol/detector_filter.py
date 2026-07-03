"""
protocol/detector_filter.py — слой фильтрации поверх детектора ошибок.

Задача: снизить ложные срабатывания старого детектора (собственные regex-правила
punct_checker + LanguageTool), НЕ переписывая сами правила. Управление — только
через конфиг protocol/detector_filter.json (единственная точка, без правки кода):

  • disabled_rules        — правило отключено, срабатывания подавляются;
  • low_confidence_rules  — срабатывания сохраняются с надёжностью «низкая»
                            (в UI по умолчанию скрыты за переключателем);
  • exception_dictionary  — слова-исключения (имена, термины): срабатывания,
                            чей фрагмент содержит такое слово, подавляются;
  • category_defaults     — дефолтная надёжность по категории ошибки.

Каждое подавленное срабатывание не исчезает бесследно: apply_filter возвращает
счётчики подавленных по правилам, вызывающая сторона пишет их в audit_log.
Хэш конфига (sha256 файла) фиксируется для воспроизводимости.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "detector_filter.json")

# Уровни надёжности кандидата.
RELIABILITY_LOW = "низкая"
RELIABILITY_MEDIUM = "средняя"
RELIABILITY_HIGH = "высокая"

_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass
class FilterResult:
    """Итог фильтрации: оставленные срабатывания и статистика подавленных."""
    kept: list = field(default_factory=list)            # [(TextError, reliability)]
    suppressed: Counter = field(default_factory=Counter)  # rule_id -> число подавленных
    total_in: int = 0

    @property
    def total_suppressed(self) -> int:
        return sum(self.suppressed.values())


def rule_id_of(error: Any) -> str:
    """Единый идентификатор правила для ошибки детектора."""
    rid = getattr(error, "rule_ref", "") or ""
    if rid:
        return rid
    return f"{getattr(error, 'source', '?')}:{getattr(error, 'subtype', '?')}"


def load_config(path: Optional[str] = None) -> tuple[dict, str]:
    """
    Загрузить конфиг фильтра. Возвращает (config, sha256-хэш файла, 12 знаков).
    Если файла нет — пустой конфиг (фильтр ничего не делает), хэш 'нет-конфига'.
    """
    p = path or DEFAULT_CONFIG_PATH
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except OSError:
        return {}, "нет-конфига"
    cfg = json.loads(raw.decode("utf-8"))
    return cfg, hashlib.sha256(raw).hexdigest()[:12]


def _fragment_words(error: Any) -> set[str]:
    frag = (getattr(error, "fragment", "") or "").lower()
    return set(_WORD_RE.findall(frag))


def reliability_for(error: Any, config: dict) -> str:
    """Надёжность срабатывания по конфигу: правило → категория → 'средняя'."""
    if rule_id_of(error) in set(config.get("low_confidence_rules", [])):
        return RELIABILITY_LOW
    defaults = config.get("category_defaults", {})
    return defaults.get(getattr(error, "error_type", ""), RELIABILITY_MEDIUM)


def apply_filter(errors: list, config: dict) -> FilterResult:
    """
    Применить фильтр к списку ошибок детектора (единственная точка применения —
    между детектором и записью в feature_candidates).
    """
    result = FilterResult(total_in=len(errors or []))
    disabled = set(config.get("disabled_rules", []))
    exceptions = {w.lower() for w in config.get("exception_dictionary", [])}

    for err in errors or []:
        rid = rule_id_of(err)
        if rid in disabled:
            result.suppressed[rid] += 1
            continue
        if exceptions and (_fragment_words(err) & exceptions):
            result.suppressed[f"{rid} (исключение-словарь)"] += 1
            continue
        result.kept.append((err, reliability_for(err, config)))
    return result
