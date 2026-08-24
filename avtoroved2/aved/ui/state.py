"""Состояние сессии экспертизы: объекты и результаты стадий."""
from __future__ import annotations

from aved.core import pipeline
from aved.core.models import FeatureValue, ObjectText, Role
from aved.core.pipeline import IdentificationResult
from aved.core.registry import Registry
from aved.stages import s3_comparison, s4_verdict


class Session:
    def __init__(self) -> None:
        self.registry = Registry.load()
        self.objects: list[ObjectText] = []
        self.docs: dict = {}
        self.suitability = None
        self.models: dict = {}
        self.disputed_model = None
        self.sample_model = None
        self.comparison = None
        self.verdict = None
        self.use_llm = False
        self.profiles: dict = {}   # сухие показатели и маркеры по объектам
        self._counter = 0

    def compute_profiles(self) -> dict:
        """Сухие верифицируемые данные по каждому объекту (без выводов)."""
        from aved import markers, metrics

        self.docs = pipeline.analyze_objects(self.objects)
        self.profiles = {}
        for o in self.objects:
            doc = self.docs[o.id]
            self.profiles[o.id] = {
                "title": o.title,
                "role": o.role.value,
                "word_count": doc.word_count(),
                "metrics": metrics.compute(doc),
                "markers": markers.scan(doc),
            }
        return self.profiles

    def add(self, title: str, text: str, role: Role) -> None:
        self._counter += 1
        prefix = "Q" if role is Role.DISPUTED else "S"
        self.objects.append(
            ObjectText(id=f"{prefix}{self._counter}", role=role, title=title, text=text)
        )

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.objects):
            self.objects.pop(index)

    def _assessor(self):
        if not self.use_llm:
            return None
        from aved.features.assessor import OllamaAssessor

        return OllamaAssessor()

    def run_suitability(self):
        self.docs = pipeline.analyze_objects(self.objects)
        self.suitability = pipeline.run_suitability(self.objects, self.docs)
        return self.suitability

    def run_analysis(self):
        # всегда заново разбираем тексты: набор объектов мог измениться между запусками
        self.run_suitability()
        self.models = pipeline.run_separate(
            self.objects, self.docs, self.registry, assessor=self._assessor()
        )
        return self.recompute()

    def recompute(self):
        """Пересобрать сравнение и вывод из текущих моделей (учитывая правки эксперта)."""
        disputed = [self.models[o.id] for o in self.objects
                    if o.role is Role.DISPUTED and o.id in self.models]
        samples = [self.models[o.id] for o in self.objects
                   if o.role is Role.SAMPLE and o.id in self.models]
        if not disputed or not samples:
            self.comparison = self.verdict = None
            return None
        self.disputed_model = s3_comparison.aggregate_samples(disputed)
        self.disputed_model.object_id = "disputed"
        self.sample_model = s3_comparison.aggregate_samples(samples)
        self.comparison = s3_comparison.compare(
            self.disputed_model, self.sample_model, self.registry
        )
        self.verdict = s4_verdict.decide(self.comparison)
        return self.verdict

    def set_present(self, object_id: str, feature_id: str, present: bool) -> None:
        """Экспертное переопределение наличия признака в объекте."""
        model = self.models.get(object_id)
        if model is None:
            return
        fv = model.values.get(feature_id)
        if fv is None:
            model.values[feature_id] = FeatureValue(
                feature_id=feature_id, present=present, source_kind="expert",
                stable=present, expert_confirmed=True,
                note="отмечено экспертом",
            )
        else:
            fv.present = present
            fv.stable = present if fv.source_kind == "expert" else fv.stable
            fv.expert_confirmed = True

    def object_text(self, object_id: str) -> str:
        for o in self.objects:
            if o.id == object_id:
                return o.text
        return ""

    def result(self) -> IdentificationResult:
        return IdentificationResult(self.suitability, self.models, self.comparison, self.verdict)

    def generate_report(self, path, meta=None):
        from aved.report import generate

        return generate(self.result(), self.objects, self.registry, path, meta)
