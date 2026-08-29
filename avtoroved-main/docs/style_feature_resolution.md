# Resolution of the 32 legacy style features

> DEVELOPMENT configuration for StyleEngineV2 shadow mode. This table does not
> create or accept forensic METHOD_FEATURE records.

The 32 rows remain a legacy engineering registry: `method_feature_id` stays
`null` for every row and none is promoted directly to METHOD. Of the 24
previously unresolved style mappings, 13 received conservative AUXILIARY style
routing and 11 remain UNRESOLVED. Patch C.1 adds only evidence links from a
legacy signal to 0..N canonical method features in the separate file
`data/style_legacy_method_mappings.json`. A link is not expert acceptance.

| feature | old status | new status | style | method mapping | automation status | reason | source/provenance | limitations |
|---|---|---|---|---|---|---|---|---|
| `metrics.particles.01` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `AUTO` | Прямая привязка к пяти функциональным стилям не подтверждена. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.02` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `AUTO` | Прямая привязка к пяти функциональным стилям не подтверждена. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.03` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.04` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.05` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.06` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `AUTO` | Прямая привязка к пяти функциональным стилям не подтверждена. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.07` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `AUTO` | Прямая привязка к пяти функциональным стилям не подтверждена. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.particles.08` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `AUTO` | Прямая привязка к пяти функциональным стилям не подтверждена. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.connectors.01` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.connectors.02` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.connectors.03` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.connectors.04` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.connectors.05` | `UNRESOLVED` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Формальный разговорный маркер; самостоятельной методической силы не имеет. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.conjunctions.01` | `UNRESOLVED` | `AUXILIARY` | `scientific, conversational` | `null` | `AUTO` | Общий дискурсивный маркер нескольких стилей; алгоритм не дублируется. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.conjunctions.02` | `UNRESOLVED` | `AUXILIARY` | `scientific` | `null` | `AUTO` | Инженерный сигнал логической связи; не METHOD_FEATURE. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.conjunctions.03` | `UNRESOLVED` | `AUXILIARY` | `scientific, publicistic` | `null` | `AUTO` | Общий дискурсивный маркер нескольких стилей; алгоритм не дублируется. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.conjunctions.04` | `UNRESOLVED` | `AUXILIARY` | `scientific, publicistic` | `null` | `AUTO` | Общий дискурсивный маркер нескольких стилей; алгоритм не дублируется. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `metrics.conjunctions.05` | `UNRESOLVED` | `AUXILIARY` | `scientific` | `null` | `AUTO` | Инженерный сигнал логической связи; не METHOD_FEATURE. | `analyzer.metrics.STYLE_MARKERS` | Контекст и функция маркера не устанавливаются простым regex. |
| `strat.layer.obscene` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.criminal_jargon` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.drug_jargon` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.youth_jargon` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.general_jargon` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.vernacular` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.colloquial_reduced` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Существующий стратификационный слой используется как вспомогательное evidence. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.literary_standard` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `CANDIDATE_ONLY` | Лексикон поднимает фрагмент, но функционально-стилевую роль подтверждает эксперт. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.archaic` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `CANDIDATE_ONLY` | Лексикон поднимает фрагмент, но функционально-стилевую роль подтверждает эксперт. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.dialectal` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `CANDIDATE_ONLY` | Лексикон поднимает фрагмент, но функционально-стилевую роль подтверждает эксперт. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `strat.layer.euphemistic` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `CANDIDATE_ONLY` | Лексикон поднимает фрагмент, но функционально-стилевую роль подтверждает эксперт. | `analyzer.stratification_engine.LAYER_META` | Словарный слой не равен функциональному стилю. |
| `comparison.leading_style.conversational_reduced` | `AUXILIARY` | `AUXILIARY` | `conversational` | `null` | `AUTO` | Legacy comparison rule сохранено только как вспомогательная совместимость. | `analyzer.comparison_engine._leading_style` | Legacy rule не является классификатором пяти функциональных стилей. |
| `comparison.leading_style.book_written` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `EXPERT_ONLY` | Legacy label нельзя надёжно разложить на пять стилей автоматически. | `analyzer.comparison_engine._leading_style` | Legacy rule не является классификатором пяти функциональных стилей. |
| `comparison.leading_style.neutral_mixed` | `UNRESOLVED` | `UNRESOLVED` | `unresolved` | `null` | `EXPERT_ONLY` | Legacy label нельзя надёжно разложить на пять стилей автоматически. | `analyzer.comparison_engine._leading_style` | Legacy rule не является классификатором пяти функциональных стилей. |

Automation totals: AUTO 26; CANDIDATE_ONLY 4; EXPERT_ONLY 2.
Method totals: METHOD 0; AUXILIARY 21; EXPERIMENTAL 0; UNRESOLVED 11.

## Non-empty legacy → canonical evidence links

The complete 32-row mapping, including empty lists, is machine-readable in
`data/style_legacy_method_mappings.json`. Non-empty links are intentionally
limited to signals that can support review without proving the target feature:

- conversational particles/connectors and reduced lexical layers may support
  `nn.lang.style_colloquial`;
- `короче` may additionally support
  `nsv.style.orat.style_assessment_words`;
- `так как` and `поэтому` may support `nsv.style.orat.causal_words`.

Raw particle/question counts remain AUX_METRIC. In particular, a question mark
does not map to a rhetorical-question METHOD feature, and a vernacular token
does not by itself establish conversational style.
