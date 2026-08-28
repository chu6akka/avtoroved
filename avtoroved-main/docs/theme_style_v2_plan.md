# Roadmap Theme/Style Engine v2

Patch A только фиксирует legacy-поведение, выносит снимок конфигурации и вводит
стабильные facade/contract. Следующие работы выполняются отдельными патчами
после согласования и валидации.

## Patch B — ThemeEngineV2

Статус: **implemented in shadow mode**. Production остаётся на ThemeEngine V1;
V2 доступен через `ThemeEngineV2().analyze(text)` или явный
`ThemeEngine.analyze_shadow(text, lemmas)`.

- сегментный анализ вместо только whole-text;
- multi-label результат;
- несколько прототипов на тему;
- явные lexical evidence и фрагменты;
- подключаемый embedding backend;
- оценка покрытия текста;
- параллельное сравнение результатов v2 с legacy v1;
- корпусная валидация до включения результата в методический контур.

Реализованы 200 инженерных прототипов, 40 development fixtures и 10 hard
cases. Это regression/development material, а не научная валидация. Реальный
embedding backend optional, lazy и offline-only; его отсутствие не ломает V1.

Patch B не должен автоматически переносить embedding score в экспертную
идентификационную значимость.

## Patch C — StyleEngineV2

- отдельные банки правил для официально-делового, научного,
  публицистического, ораторского и разговорного стилей;
- документированная методическая опора каждого правила;
- детекторы на существующей Stanza-разметке;
- evidence-фрагменты для каждого срабатывания;
- multi-style output;
- coverage и нормированные counts;
- раздельная валидация относительно регистра, жанра и темы.

Регистровая стратификация, ошибки навыков и функциональный стиль не должны
сливаться в один показатель.

## Patch D — cleanup

Только после сравнительной и корпусной валидации:

- удалить подтверждённый dead legacy code;
- убрать дублированные dictionaries и constants;
- удалить неиспользуемые thresholds;
- при необходимости убрать fallback v1;
- обновить packaged resources и документацию публичных interfaces.
