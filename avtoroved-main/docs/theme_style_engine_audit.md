# Аудит Theme/Style Engine v1 перед переходом к v2

Статус: Patch A, фиксация поведения без изменения алгоритмов, порогов,
ролей данных и форматов результатов. Новые facade-классы делегируют legacy-коду;
JSON в `data/` является снимком существующих констант и словарей, но пока не
заменяет их как источник вычислений.

## ThemeEngineV2 pre-refactor baseline

Baseline зафиксирован на коммите `998cc0c5e2ba23818d3b6293afccf42f4202e879`.
Legacy producer — `analyzer/thematic_engine.py`, публичный API —
`ThematicEngine.analyze(lemmas)`. Он возвращает `ThematicResult` со всеми
`DomainScore`, максимум тремя `top_domains`, общим числом слов и числом
словарных совпадений. Dominant topic фактически является первым элементом
`top_domains` после сортировки по cosine.

V1 содержит десять неизменяемых ID: `law`, `medicine`, `it`, `economics`,
`military`, `science`, `religion`, `politics`, `sports`, `everyday`. Алгоритм
строит словарные TF-IDF-центроиды и использует порог
`max(0.05, best_cosine × 0.25)` с лимитом 3. `protocol/profile.py` дополнительно
не создаёт thematic candidate ниже `0.15`, а интервал `0.15–0.25` помечает как
слабую атрибуцию. Neural embeddings в V1 отсутствуют.

Consumers до Patch B: `protocol/profile.py`, `ui/main_window.py`,
`ui2/analysis.py`, thematic UI tabs, legacy export/diagnostic views и инструменты
словаря. Все production consumers проходят через `ThemeEngine.analyze()` и
получают исходный V1-формат. Patch B не меняет этот маршрут: V2 вызывается
только явно и не передаётся в `semantic_candidates`, comparison, SQLite или
логику заключения.

## Тематический блок

### Главный producer

| Поле | Текущее состояние |
|---|---|
| Файл и функция | `analyzer/thematic_engine.py`, `ThematicEngine.analyze(lemmas)` |
| Вход | список лемм всего текста в нижнем регистре |
| Выход | `ThematicResult(scores, top_domains, total_words, matched_words)`; элементы — `DomainScore` |
| Темы | 10 файлов `data/thematic/*.json`; метки и цвета — `DOMAIN_META` |
| Score | TF-IDF текста и косинусное сходство с нормированным словарным центроидом домена |
| Порог движка | `max(0.05, best_cosine × 0.25)`, максимум 3 top domain |
| Порог профиля | `semantic_candidates`: не создаёт запись ниже `0.15`; `0.15–0.25` — слабая атрибуция |
| Область текста | whole-text; segment-level анализа нет |
| Embedding | при анализе не используется |
| Модель | ML-модели нет; словарный TF-IDF |
| Fallback | отсутствующий словарь даёт пустой центроид; пустой вход — пустой результат; исключения orchestration подавляет и оставляет `None` |

`analyzer/rusvec_engine.py` не является альтернативным scoring pipeline. Это
ручная утилита расширения файлов словарей через Navec/RusVectores; после записи
слов движок v1 всё равно выполняет обычный TF-IDF. Пользовательские слова из
`corpus_manager.get_user_domain_words()` также добавляются при загрузке v1.

### Тематические классы и роли

| ID | Текущая метка | Статус | Результат `semantic_candidates` |
|---|---|---|---|
| `law` | Юридическая / правовая | AUXILIARY | `AUX_METRIC` |
| `medicine` | Медицинская / фармацевтика | AUXILIARY | `AUX_METRIC` |
| `it` | IT / цифровые технологии | AUXILIARY | `AUX_METRIC` |
| `economics` | Экономика / финансы | AUXILIARY | `AUX_METRIC` |
| `military` | Военная / силовые структуры | METHOD | кандидат `nn.smysl.military` |
| `science` | Научная / академическая | AUXILIARY | `AUX_METRIC` |
| `religion` | Религиозная / духовная | AUXILIARY | `AUX_METRIC` |
| `politics` | Политическая / государственная | METHOD | кандидат `nn.smysl.political` |
| `sports` | Спортивная / физкультура | AUXILIARY | `AUX_METRIC` |
| `everyday` | Бытовая / разговорная | METHOD | кандидат `nn.smysl.everyday` |

Ни один тематический producer не создаёт `EVIDENCE`. Автоматическая
идентификационная значимость не выставляется: `expert_identification_value`
остаётся `NULL`. METHOD-статус следует только из
`protocol/method_features.json`; неизвестная тема не повышается до признака.

`theme_ontology.json` содержит все 4244 существующих ключевых слова, метки,
цвета и текущие пороги. У v1 нет topic descriptions/reference phrases как
отдельных прототипов, поэтому `theme_prototypes.json` содержит десять пустых
массивов — новые тексты не придуманы.

### Consumers

- `protocol/profile.py`: `build_document_profile` запускает анализ,
  `semantic_candidates` формирует METHOD_FEATURE либо AUX_METRIC;
- `ui/main_window.py` и `ui2/analysis.py`: запускают анализ и сохраняют
  совместимый `ThematicResult`;
- `ui/tabs/thematic_tab.py` и `ui2/stages.py`: визуализация;
- `analyzer/diagnostic_engine.py`: legacy-диагностика пола/возраста, исключённая
  из активного протокольного вывода;
- `analyzer/export.py` и `ui/tabs/report_tab.py`: старые/архивные пути экспорта;
- `_smoke_test.py` и `_semantic_poc.py`: ручные инструменты разработки.

Новый `ThemeEngine` подключён в двух UI orchestrators и в `profile.py`.
`analyze()` возвращает исходный `ThematicResult` без адаптации. Новый контракт
доступен только через дополнительный `analyze_structured()` и не используется
текущими consumers.

## Стилистический блок

Единого legacy StyleEngine до Patch A не существовало. Обнаружены три
независимых producer, которые нельзя методически объединять без валидации.

### 1. Лексическая стратификация

| Поле | Текущее состояние |
|---|---|
| Файл и функция | `analyzer/stratification_engine.py`, `StratificationEngine.analyze(text)` |
| Распознаваемое | 11 регистровых слоёв: obscene, criminal/drug/youth/general jargon, vernacular, colloquial_reduced, literary_standard, archaic, dialectal, euphemistic |
| Indicators | точные слова/фразы из `lexicon_stratified.json`, морфологическая нормализация, приоритет `LAYER_META`, whitelist/false-positive rules из `strat_filter.py` |
| Тип | rule-based + lexical + morphological |
| Выход | `StratResult`: токены, counts, words, total, marked ratio |
| Consumers | обе UI orchestration, вкладка стратификации, `profile.py`, `comparison_engine`, export, token card |
| Роли | агрегаты слоёв — `AUX_METRIC`; конкретные маркированные токены — `EVIDENCE`; obscene/euphemistic дополнительно представлены как psycho `EVIDENCE` |
| Registry | прямой связи с `method_features.json` нет |

### 2. Маркеры служебных слов и дискурсивных связок

| Поле | Текущее состояние |
|---|---|
| Файл и функция | `analyzer/metrics.py`: `STYLE_MARKERS`, подсчёт внутри `calculate_metrics` |
| Indicators | 8 частиц, 5 связок, 5 союзов — всего 18 точных слов/фраз |
| Тип | rule-based lexical regex, ненормированный count |
| Consumers | `protocol.profile.stylistic_candidates`, статистические представления |
| Роль | только `AUX_METRIC` |
| Registry | отсутствует |

Название `STYLE_MARKERS` историческое: эти 18 элементов не классифицируют
официально-деловой, научный, публицистический, ораторский или разговорный стиль.
Поэтому все они записаны в `style_features.json` как `style=unresolved`.

### 3. Эвристика ведущего регистрового/функционального стиля

| Поле | Текущее состояние |
|---|---|
| Файл и функция | `analyzer/comparison_engine.py`, `_leading_style(metrics, strat_result)` |
| Outputs | `разговорно-сниженный`, `книжно-письменный`, `нейтральный / смешанный` |
| Indicators | marked ratio `>=0.04` и минимум 2 сниженных единицы; иначе средняя длина предложения `>=18`; иначе default |
| Тип | rule-based lexical + statistical/syntactic proxy |
| Consumers | legacy `comparison_engine.compare`, `ui2/stages.py` |
| Роль | legacy comparison feature уровня НН; не METHOD_FEATURE строгого протокола |
| Registry | отсутствует |

Только `разговорно-сниженный` уверенно сопоставлен с будущим классом
`conversational`. `книжно-письменный` нельзя без нового основания разложить на
official_business/scientific/publicistic/oratorical, поэтому он и default
помечены `unresolved`.

### Прочие близкие, но не функционально-стилевые данные

- `errors.py`/LanguageTool создают категорию «Стилистическая ошибка» и степень
  стилистического навыка, но не определяют функциональный стиль;
- интернет-маркеры в `profile.py` описывают цифровую коммуникацию;
- POS, синтаксические длины и морфологические индексы сейчас являются
  самостоятельными метриками и не входят в классификатор пяти стилей.

Новый `StyleEngine` не объединяет эти ветви. `analyze()` делегирует
стратификации, `service_word_markers()` возвращает готовый legacy dict,
`leading_style()` вызывает существующую эвристику. В активной orchestration
подключён только совместимый `analyze()`.

## Наличие дублирующей или конфликтующей логики

Главный и `ui2` интерфейсы запускают одни и те же singleton producers, поэтому
конфликтующего тематического алгоритма нет. Стилевой блок фрагментирован, но
ветви решают разные задачи; Patch A их не смешивает. Представление одного
`StratResult` несколькими candidates в `profile.py` является дублированием
представления, а не вторым детектором.

## Candidate for future cleanup

- после валидации v2 сделать новые JSON единственным источником метаданных и
  убрать дублирование `DOMAIN_META`, `STYLE_MARKERS`, `LAYER_META`;
- дать публичное имя legacy `_leading_style`, если он сохранится;
- отделить регистровую стратификацию от классификации пяти функциональных стилей;
- переименовать исторический `STYLE_MARKERS` во избежание ложной интерпретации;
- проверить и удалить только действительно архивные consumers старых форматов;
- унифицировать resource-path после проверки PyInstaller-сборки;
- решать судьбу RusVec/Navec расширения отдельно: оно мутирует словари и не
  является runtime embedding-анализом.

До Patch D ничего из перечисленного не удаляется.
