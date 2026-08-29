# Style METHOD registry runtime coverage

> Patch C.1.1. Отчёт различает методическую допустимость автоматизации
> (`automation_status`) и фактическую реализацию в текущем StyleEngineV2
> (`implementation_status`).

`IMPLEMENTED` означает зарегистрированный detector, реально вызываемый маршрутом
`StyleEngineV2.analyze`. `PARTIAL` означает проверяемый legacy producer и явную
mapping-связь, но отсутствие полного canonical V2 detector. `NOT_IMPLEMENTED`
допускает формализуемость признака, но запрещает runtime detection.
`NOT_APPLICABLE` используется для сознательно экспертных явлений.

| method_feature_id | style | automation_status | implementation_status | detector | producer | evidence_type | runtime_reachable | notes |
|---|---|---|---|---|---|---|---|---|
| `nn.lang.style_colloquial` | `conversational` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.aggregate.functional_style.conversational` | `analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:selected_styles` | `aggregate_style_support_with_source_spans` | yes — StyleEngineV2 | Инженерная классификация функционального стиля является только кандидатом и требует экспертного подтверждения. |
| `nn.lang.style_official_business` | `official_business` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.aggregate.functional_style.official_business` | `analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:selected_styles` | `aggregate_style_support_with_source_spans` | yes — StyleEngineV2 | Инженерная классификация функционального стиля является только кандидатом и требует экспертного подтверждения. |
| `nn.lang.style_oratorical` | `oratorical` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.aggregate.functional_style.oratorical` | `analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:selected_styles` | `aggregate_style_support_with_source_spans` | yes — StyleEngineV2 | Инженерная классификация функционального стиля является только кандидатом и требует экспертного подтверждения. |
| `nn.lang.style_publicistic` | `publicistic` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.aggregate.functional_style.publicistic` | `analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:selected_styles` | `aggregate_style_support_with_source_spans` | yes — StyleEngineV2 | Инженерная классификация функционального стиля является только кандидатом и требует экспертного подтверждения. |
| `nn.lang.style_scientific` | `scientific` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.aggregate.functional_style.scientific` | `analyzer.semantic_layers.style_engine_v2.StyleEngineV2.analyze:selected_styles` | `aggregate_style_support_with_source_spans` | yes — StyleEngineV2 | Инженерная классификация функционального стиля является только кандидатом и требует экспертного подтверждения. |
| `ns.style.coll.clarifications` | `conversational` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.coll.conj_omission_inversion` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.ellipsis_action` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.ellipsis_addressee` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.ellipsis_noun` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.ellipsis_object` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.inversion_adv_adj` | `conversational` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.coll.inversion_genitive` | `conversational` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.coll.inversion_question` | `conversational` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.coll.main_clause_omission` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.prefixed_occasionalisms` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.coll.thematic_adjacency` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.ob.close_meaning_chains` | `official_business` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.ob.person_by_activity` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.ob.subordinate_chains` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.ob.substitutes_stamps` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `ns.style.ob.synonym_repeat_adv_adj` | `official_business` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `ns.style.ob.three_part_model` | `official_business` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.broad_meaning_words` | `conversational` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.coll.contextual_metaphors` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.expressive_adj_noun` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.expressive_adv_adj` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.lowering_metaphors` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.pronoun_metaphors` | `conversational` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.coll.u_genitive_possession` | `conversational` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.compound_words` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.conjunction_abbr` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.date_abbr` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.document_abbr` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.fronted_adverbials` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.initial_abbr` | `official_business` | `AUTO` | `IMPLEMENTED` | `v2.official.abbreviation` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |
| `nsv.style.ob.mixed_abbr` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.neg_verbal_nouns` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.rank_abbr` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.specific_adjectives` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.stamps` | `official_business` | `AUTO` | `IMPLEMENTED` | `v2.official.cliche` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |
| `nsv.style.ob.substitutes` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.sya_verbs` | `official_business` | `AUTO` | `IMPLEMENTED` | `v2.official.reflexive_verbs` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |
| `nsv.style.ob.syllabic_abbr` | `official_business` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.territorial_abbr` | `official_business` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.ob.verbal_nouns` | `official_business` | `AUTO` | `IMPLEMENTED` | `v2.shared.deverbal_nouns` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |
| `nsv.style.orat.causal_words` | `oratorical` | `AUTO` | `PARTIAL` | `metrics.conjunctions.02`<br>`metrics.conjunctions.04` | `analyzer.metrics.STYLE_MARKERS` | `legacy_exact_marker_count` | yes — legacy evidence only | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.orat.generic_synonym_repeat` | `oratorical` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.orat.logic_emphasis` | `oratorical` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.orat.pressure_words` | `oratorical` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.orat.style_assessment_words` | `oratorical` | `AUTO` | `PARTIAL` | `metrics.connectors.02` | `analyzer.metrics.STYLE_MARKERS` | `legacy_exact_marker_count` | yes — legacy evidence only | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.pub.linking_verbs` | `publicistic` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.pub.metaphor_stamps` | `publicistic` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.pub.metaphor_synrows` | `publicistic` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.pub.simile_metaphors` | `publicistic` | `EXPERT_ONLY` | `NOT_APPLICABLE` | — | — | — | no | Высокоуровневое явление не устанавливается StyleEngineV2 автоматически. |
| `nsv.style.sci.deadjective_genitive` | `scientific` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.sci.deverbal_genitive` | `scientific` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.sci.deverbal_nouns` | `scientific` | `AUTO` | `IMPLEMENTED` | `v2.shared.deverbal_nouns` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Общий detector отглагольных существительных не связывает признак с одним стилем без контекста; экспертное принятие обязательно. |
| `nsv.style.sci.genitive_chains` | `scientific` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.scientific.genitive_chain` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `parsed_token_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |
| `nsv.style.sci.identity_constructs` | `scientific` | `AUTO` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.sci.specific_adjectives` | `scientific` | `CANDIDATE_ONLY` | `NOT_IMPLEMENTED` | — | — | — | no | Подтверждённый методический признак пока не имеет активного detector-а в StyleEngineV2. |
| `nsv.style.sci.terms` | `scientific` | `CANDIDATE_ONLY` | `IMPLEMENTED` | `v2.scientific.terminology_candidate` | `analyzer.semantic_layers.style_detectors.detect_style_features` | `source_span` | yes — StyleEngineV2 | Формальное срабатывание detector-а создаёт только неподтверждённого кандидата; экспертное принятие обязательно. |

## Summary

- METHOD total: 62
- IMPLEMENTED: 12
- PARTIAL: 2
- NOT_IMPLEMENTED: 30
- NOT_APPLICABLE: 18

- AUTO total: 26
- AUTO implemented: 5
- AUTO partial: 2
- AUTO not implemented: 19

- CANDIDATE_ONLY total: 18
- CANDIDATE_ONLY implemented: 7
- CANDIDATE_ONLY partial: 0
- CANDIDATE_ONLY not implemented: 11

- EXPERT_ONLY total: 18
- EXPERT_ONLY not applicable: 18

Machine verification is implemented by
`analyzer.semantic_layers.style_runtime_integrity.assert_style_method_runtime_integrity`.
It executes the actual detector routing audit and rejects unreachable IMPLEMENTED
entries. Aggregate candidates map only to the five general `nn.lang.style_*`
features; they do not cascade into private style features.
