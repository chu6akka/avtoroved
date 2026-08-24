"""Таблица истинности правила вывода (методика, с. 85–86).

Синтетические модели навыка прогоняются через S3 (сравнение) и S4 (вывод);
проверяются все исходы и порог ≥20 высокоинформативных признаков.
"""
import pytest

from aved.core.models import FeatureValue, Level, NavykModel, VerdictType
from aved.core.registry import Registry
from aved.stages.s3_comparison import compare
from aved.stages.s4_verdict import decide

reg = Registry.load()
NSV = [f.id for f in reg.by_level(Level.NSV)]
NS = [f.id for f in reg.by_level(Level.NS)]
STYLE_OB = "nn.lang.style_official_business"
STYLE_COLL = "nn.lang.style_colloquial"


def model(obj_id: str, present: dict[str, float]) -> NavykModel:
    # признаки считаем устойчиво установленными (stable=True)
    m = NavykModel(object_id=obj_id)
    for fid, val in present.items():
        m.values[fid] = FeatureValue(feature_id=fid, present=True, value=val, stable=True)
    return m


def verdict_for(disputed: NavykModel, sample: NavykModel) -> VerdictType:
    return decide(compare(disputed, sample, reg)).type


def test_categorical_positive():
    shared = {STYLE_OB: 10.0}
    shared.update({fid: 1.0 for fid in NSV[:22]})   # ≥20 высокоинформативных совпадений
    shared.update({fid: 1.0 for fid in NS[:6]})
    d = model("disputed", shared)
    s = model("samples", dict(shared))
    assert verdict_for(d, s) is VerdictType.CATEGORICAL_POSITIVE


def test_below_threshold_is_probable_positive():
    shared = {STYLE_OB: 10.0}
    shared.update({fid: 1.0 for fid in NSV[:19]})   # 19 < 20 — порог не достигнут
    shared.update({fid: 1.0 for fid in NS[:6]})
    d = model("disputed", shared)
    s = model("samples", dict(shared))
    assert verdict_for(d, s) is VerdictType.PROBABLE_POSITIVE


def test_categorical_negative_on_nn_style_conflict():
    d = model("disputed", {STYLE_OB: 10.0, **{fid: 1.0 for fid in NSV[:22]}})
    s = model("samples", {STYLE_COLL: 10.0, **{fid: 1.0 for fid in NSV[:22]}})
    # различие наборов норм на НН — категорический отрицательный, несмотря на совпадения НСВ
    assert verdict_for(d, s) is VerdictType.CATEGORICAL_NEGATIVE


def test_probable_negative_on_ns_and_nsv_differences():
    d = model("disputed", {STYLE_OB: 10.0, **{fid: 1.0 for fid in NSV[:5] + NS[:3]}})
    s = model("samples", {STYLE_OB: 10.0, **{fid: 1.0 for fid in NSV[5:10] + NS[3:6]}})
    assert verdict_for(d, s) is VerdictType.PROBABLE_NEGATIVE


def test_probable_positive_weak_nsv():
    shared = {STYLE_OB: 10.0}
    shared.update({fid: 1.0 for fid in NS[:5]})
    shared.update({fid: 1.0 for fid in NSV[:3]})    # НСВ почти не проявляется
    d = model("disputed", shared)
    s = model("samples", dict(shared))
    assert verdict_for(d, s) is VerdictType.PROBABLE_POSITIVE


def test_inconclusive_on_sparse_overlap():
    d = model("disputed", {fid: 1.0 for fid in NSV[:2]})
    s = model("samples", {fid: 1.0 for fid in NSV[:2]})
    # совпадения только на НСВ, нет совпадений на НН/НС, нет различий
    assert verdict_for(d, s) is VerdictType.INCONCLUSIVE
