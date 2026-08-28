# ThemeEngineV2 — shadow thematic analysis

## Статус и границы

ThemeEngineV2 реализован в Patch B только как экспериментальный shadow engine.
Production `ThemeEngine.analyze(lemmas)` по-прежнему возвращает legacy
`ThematicResult` V1. Новый результат не поступает в `protocol/profile.py`,
comparison, methodological checks, SQLite и проект экспертного заключения.

Вызов V2 всегда явный:

```python
from analyzer.semantic_layers.theme_engine_v2 import ThemeEngineV2

result = ThemeEngineV2().analyze(text)
```

Для сопоставления версий без переключения поведения:

```python
shadow = theme_engine.analyze_shadow(text, lemmas)
```

Сбой V2 не ломает V1. Отсутствие optional dependency или локальных весов даёт
контролируемые `status="unavailable"` и `reason`, а не ImportError приложения.

## Segmentation

`theme_segmenter.py` сначала выделяет непустые абзацы, объединяет очень короткие
соседние блоки и делит длинные абзацы на неперекрывающиеся окна по предложениям.
Аномально длинное предложение делится по границам слов. Для каждого сегмента
сохраняются `segment_id`, исходный фрагмент, `start`, `end`, число предложений и
слов.

Engineering defaults:

- `MIN_SEGMENT_TOKENS = 8`;
- `TARGET_SEGMENT_TOKENS = 100`;
- `MAX_SEGMENT_TOKENS = 180`;
- overlap отсутствует.

Это параметры вычислительной реализации, а не методические нормативы.

## Ontology и prototypes

`data/theme_ontology.json` сохраняет десять legacy ID и их статусы. METHOD
остаются только `military`, `politics`, `everyday`, уже связанные с registry;
остальные темы имеют статус AUXILIARY. V2 не повышает статус по score.

`data/theme_prototypes.json` содержит по 20 естественных коротких описаний для
каждой темы. Все 200 записей помечены
`provenance="engineered_for_v2"`: это инженерное представление темы, а не
цитаты и не положения экспертной методики.

## Lexical evidence

`lexical_theme_evidence.py` лениво использует `pymorphy3` из существующего NLP
stack и сопоставляет леммы/фразы с ontology keywords. Результат содержит:

- совпавшие леммы и фразы;
- общее и уникальное число совпадений;
- lexical coverage;
- фрагменты и точные offsets.

Один keyword не считается достаточным segment support сам по себе. Лексический
сигнал является только одним компонентом V2.

## Semantic scoring

`embedding_backend.py` предоставляет pluggable API. Реальный backend использует
`cointegrated/rubert-tiny2` через `sentence-transformers`, но импортирует пакет
и открывает модель только при явном V2-вызове. Установлена политика
`local_files_only=True`: runtime не скачивает модель. Новая обязательная
dependency в Patch B не добавлена.

Для regression-тестов существует `DeterministicEmbeddingBackend`. Это
test-only hashing representation, не semantic model и не основание оценки
качества V2.

Для каждого сегмента вычисляются cosine similarity со всеми прототипами темы:

- `prototype_max`;
- `prototype_top3_mean`;
- `prototype_top5_mean`.

Основной semantic similarity score — top-3 mean. Prototype embeddings
кэшируются в памяти по `(model revision, theme ID, prototype hash)`.

## Multi-label output и coverage

`ThemeAnalysisResultV2.themes` содержит все активные темы. Для каждой доступны:

- `semantic_score`;
- `lexical_score`;
- инженерный `combined_score`;
- число поддерживающих сегментов;
- coverage как доля поддерживающих сегментов;
- segment evidence, prototype similarities и lexical matches;
- method status и registry ID, если он существовал до V2.

`dominant_theme` — лишь первая поддержанная тема в инженерном ранжировании. Он
не заменяет multi-label профиль.

## Similarity не является probability

Raw cosine называется `semantic_similarity_score`. `combined_score` —
прозрачный engineering ranking:

```text
0.75 × clipped semantic similarity + 0.25 × lexical support
```

Значение не калибровано, поэтому его нельзя называть вероятностью, процентом
уверенности или индивидуализирующей значимостью.

Engineering thresholds Patch B:

- lexical saturation: 6 уникальных совпадений;
- minimum lexical support: 2 уникальных совпадения;
- segment support combined score: 0.25;
- semantic-only support: 0.42;
- включение слабого semantic evidence для просмотра: 0.20;
- prototype top-k: 3.

Эти числа требуют отдельной корпусной проверки на устойчивость к теме, жанру,
длине, метафорам и смешанным текстам.

## Method safety

V2 никогда не назначает `expert_identification_value`: поле всегда `None`.
Даже METHOD theme остаётся машинным candidate evidence до экспертной проверки.
AUXILIARY/EXPERIMENTAL/UNRESOLVED темы не становятся METHOD_FEATURE и не
участвуют в порогах Моисеевой/Огорелкова, уровнях Рубцовой и формах вывода.

## Development evaluation

Локальный корпус содержит 40 тематических fixtures и 10 hard cases. Он нужен
для разработки и регрессии, но не доказывает научную валидность.

Реальный offline backend:

```powershell
.venv\Scripts\python.exe scripts\evaluate_theme_engines.py
```

Если модель недоступна, отчёт честно выводит `REAL V2 EVALUATION NOT RUN`.
Test-only технический проход:

```powershell
.venv\Scripts\python.exe scripts\evaluate_theme_engines.py --deterministic
```

Скрипт считает top-1 accuracy, micro precision/recall/F1 и macro F1 для V1 и
доступного V2 backend. Все показатели подписаны `DEVELOPMENT METRICS — NOT
SCIENTIFIC VALIDATION`.

## Что требует научной валидации

- качество и полнота engineered prototypes;
- переносимость embedding similarities между жанрами и длинами;
- инженерные thresholds и веса combined score;
- устойчивость к метафорам, цитатам, компиляции и тематическому смешению;
- калибровка coverage и правила выбора dominant theme;
- воспроизводимость конкретной локальной ревизии neural model;
- превосходство или непревосходство V2 над V1 на независимом корпусе.
