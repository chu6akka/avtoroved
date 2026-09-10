from pathlib import Path

import pytest

from authoroved_core.core.feature_models import AutomationMode
from authoroved_core.core.feature_registry import FeatureRegistry, FeatureRegistryError


EXPECTED_IDS = {
    "LEX_001", "LEX_002", "LEX_005", "MOR_001", "MOR_003",
    "MOR_004", "SYN_001", "PUN_001", "PUN_002", "GRA_001",
}


def test_default_registry_contains_only_first_ten_auto_features():
    registry = FeatureRegistry.load()

    assert registry.version == "0.1.0"
    assert registry.identification_thresholds is None
    assert registry.default_suitability_minimum_words is None
    assert {item.id for item in registry.features} == EXPECTED_IDS
    assert all(item.automation_mode is AutomationMode.AUTO for item in registry.features)
    assert all(item.sources and all(source.locator for source in item.sources)
               for item in registry.features)
    assert all(item.dependency_group for item in registry.features)
    assert "внутренней операционализацией" in registry.notice


def test_registry_rejects_authorship_thresholds(tmp_path):
    source = Path("authoroved_core/methodology/feature_registry.yaml").read_text(encoding="utf-8")
    path = tmp_path / "registry.yaml"
    path.write_text(source.replace("identification_thresholds: null", "identification_thresholds: 0.8"),
                    encoding="utf-8")

    with pytest.raises(FeatureRegistryError, match="пороги авторства"):
        FeatureRegistry.load(path)


def test_registry_rejects_missing_source_locator(tmp_path):
    source = Path("authoroved_core/methodology/feature_registry.yaml").read_text(encoding="utf-8")
    path = tmp_path / "registry.yaml"
    path.write_text(source.replace('locator: "с. 13"', 'locator: ""', 1), encoding="utf-8")

    with pytest.raises(FeatureRegistryError, match="locator|локатор|источник"):
        FeatureRegistry.load(path)
