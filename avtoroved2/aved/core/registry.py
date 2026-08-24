"""Загрузчик реестра признаков (`data/features/registry.yaml`).

Реестр — декларативное ядро программы: каждая запись описывает признак методики
(уровень, категория, значимость, способ установления, источник). Экстракторы и
оценщики опираются на реестр, а не наоборот.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from aved.core.models import Category, Feature, Level, Method, Significance


def find_data_dir() -> Path:
    """Каталог данных проекта. Переопределяется переменной AVED_DATA_DIR."""
    env = os.environ.get("AVED_DATA_DIR")
    if env:
        return Path(env)
    # aved/core/registry.py -> aved/core -> aved -> <project_root>
    return Path(__file__).resolve().parents[2] / "data"


def default_registry_path() -> Path:
    """Каталог с файлами реестра (по одному на уровень: registry_*.yaml)."""
    return find_data_dir() / "features"


def _enum(enum_cls, value, field_name, fid):
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise ValueError(
            f"признак {fid!r}: недопустимое {field_name}={value!r} (допустимо: {allowed})"
        ) from None


class Registry:
    """Загруженный набор признаков с индексами для выборок."""

    def __init__(self, features: list[Feature]) -> None:
        self._by_id: dict[str, Feature] = {}
        for f in features:
            if f.id in self._by_id:
                raise ValueError(f"дублирующийся id признака: {f.id!r}")
            self._by_id[f.id] = f

    # ------- загрузка ------- #
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Registry":
        """Загрузить реестр из файла или из каталога (все ``registry*.yaml``)."""
        path = Path(path) if path else default_registry_path()
        if path.is_dir():
            files = sorted(path.glob("registry*.yaml"))
            if not files:
                raise FileNotFoundError(f"в каталоге нет registry*.yaml: {path}")
        else:
            files = [path]

        features: list[Feature] = []
        for fp in files:
            with open(fp, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or []
            if not isinstance(raw, list):
                raise ValueError(f"{fp.name}: ожидается список признаков")
            features.extend(cls._parse(item) for item in raw)
        return cls(features)

    @staticmethod
    def _parse(item: dict) -> Feature:
        fid = item.get("id")
        if not fid:
            raise ValueError(f"запись без id: {item!r}")
        return Feature(
            id=fid,
            level=_enum(Level, item["level"], "level", fid),
            category=_enum(Category, item["category"], "category", fid),
            name=item["name"],
            significance=_enum(Significance, item["significance"], "significance", fid),
            method=_enum(Method, item["method"], "method", fid),
            source=item.get("source", ""),
            extractor=item.get("extractor"),
            lexicon=item.get("lexicon"),
            subcategory=item.get("subcategory"),
            note=item.get("note"),
        )

    # ------- выборки ------- #
    def all(self) -> list[Feature]:
        return list(self._by_id.values())

    def get(self, fid: str) -> Feature:
        return self._by_id[fid]

    def by_level(self, level: Level) -> list[Feature]:
        return [f for f in self._by_id.values() if f.level is level]

    def by_method(self, method: Method) -> list[Feature]:
        return [f for f in self._by_id.values() if f.method is method]

    def by_category(self, category: Category) -> list[Feature]:
        return [f for f in self._by_id.values() if f.category is category]

    def high_info(self) -> list[Feature]:
        return [f for f in self._by_id.values() if f.high_info]

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self):
        return iter(self._by_id.values())
