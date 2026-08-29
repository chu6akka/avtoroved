# StyleEngineV2: DEVELOPMENT error analysis

> Baseline зафиксирован для commit `1909a4f48cda1bedc65423b5da8ea975dc1cf7c9`. Это инженерный development corpus, а не научная валидация.

## Baseline

35 fixtures; top-1 `0.800000`; micro P/R/F1 `0.882353/0.882353/0.882353`; macro F1 `0.870000`; abstentions `6`; mixed recall `0.750000`.

## Full fixture matrix

| Fixture | Expected | Selected | Leading | Ranked support | FP | FN |
|---|---|---|---|---|---|---|
| `official_order` | official_business | official_business | official_business | official_business=0.266667, scientific=0.133333, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `official_notice` | official_business | official_business | official_business | official_business=0.333333, conversational=0.066667, publicistic=0.066667, oratorical=0.000000, scientific=0.000000 | — | — |
| `official_procedure` | official_business | official_business | official_business | official_business=0.200000, scientific=0.133333, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `official_protocol` | official_business | official_business | official_business | official_business=0.266667, scientific=0.200000, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `official_application` | official_business | official_business | official_business | official_business=0.333333, scientific=0.133333, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `scientific_definition` | scientific | scientific | scientific | scientific=0.400000, official_business=0.133333, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `scientific_experiment` | scientific | scientific | scientific | scientific=0.333333, official_business=0.066667, publicistic=0.066667, conversational=0.000000, oratorical=0.000000 | — | — |
| `scientific_article` | scientific | scientific | scientific | scientific=0.333333, conversational=0.066667, official_business=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `scientific_results` | scientific | scientific | scientific | scientific=0.333333, official_business=0.133333, publicistic=0.066667, conversational=0.000000, oratorical=0.000000 | — | — |
| `scientific_model` | scientific | scientific | scientific | scientific=0.266667, official_business=0.133333, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `publicistic_city` | publicistic | publicistic | publicistic | publicistic=0.133333, official_business=0.066667, scientific=0.066667, conversational=0.000000, oratorical=0.000000 | — | — |
| `publicistic_education` | publicistic | — | conversational | conversational=0.133333, publicistic=0.133333, official_business=0.066667, scientific=0.066667, oratorical=0.000000 | — | publicistic |
| `publicistic_environment` | publicistic | — | official_business | official_business=0.066667, publicistic=0.066667, conversational=0.000000, oratorical=0.000000, scientific=0.000000 | — | publicistic |
| `publicistic_comment` | publicistic | conversational, publicistic | publicistic | publicistic=0.266667, conversational=0.200000, official_business=0.200000, scientific=0.200000, oratorical=0.066667 | conversational | — |
| `publicistic_culture` | publicistic | conversational, publicistic | publicistic | publicistic=0.466667, conversational=0.266667, official_business=0.000000, oratorical=0.000000, scientific=0.000000 | conversational | — |
| `oratorical_colleagues` | oratorical | oratorical | oratorical | oratorical=0.266667, conversational=0.066667, publicistic=0.066667, official_business=0.000000, scientific=0.000000 | — | — |
| `oratorical_friends` | oratorical | conversational, oratorical | oratorical | oratorical=0.200000, conversational=0.133333, official_business=0.133333, publicistic=0.000000, scientific=0.000000 | conversational | — |
| `oratorical_citizens` | oratorical | oratorical | oratorical | oratorical=0.200000, conversational=0.066667, official_business=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `oratorical_question_answer` | oratorical | oratorical | oratorical | oratorical=0.200000, conversational=0.000000, official_business=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `oratorical_memory` | oratorical | oratorical | oratorical | oratorical=0.200000, conversational=0.000000, official_business=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `conversational_weekend` | conversational | conversational | conversational | conversational=0.333333, official_business=0.000000, oratorical=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `conversational_trip` | conversational | conversational | conversational | conversational=0.400000, publicistic=0.200000, official_business=0.000000, oratorical=0.000000, scientific=0.000000 | — | — |
| `conversational_meeting` | conversational | conversational | conversational | conversational=0.333333, publicistic=0.200000, official_business=0.000000, oratorical=0.000000, scientific=0.000000 | — | — |
| `conversational_family` | conversational | conversational | conversational | conversational=0.200000, publicistic=0.133333, official_business=0.000000, oratorical=0.000000, scientific=0.000000 | — | — |
| `conversational_purchase` | conversational | conversational | conversational | conversational=0.400000, publicistic=0.200000, official_business=0.066667, oratorical=0.000000, scientific=0.000000 | — | — |
| `hard_scientific_question` | scientific | scientific | scientific | scientific=0.333333, official_business=0.200000, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `hard_official_terminology` | official_business | official_business | official_business | official_business=0.266667, scientific=0.066667, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `hard_publicistic_official_lexicon` | publicistic | — | official_business | official_business=0.200000, scientific=0.200000, conversational=0.066667, publicistic=0.066667, oratorical=0.000000 | — | publicistic |
| `hard_conversational_without_slang` | conversational | conversational | conversational | conversational=0.266667, official_business=0.000000, oratorical=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `hard_oratorical_no_questions` | oratorical | oratorical | oratorical | oratorical=0.200000, publicistic=0.133333, official_business=0.066667, scientific=0.066667, conversational=0.000000 | — | — |
| `hard_mixed_official_scientific` | official_business, scientific | official_business, scientific | scientific | scientific=0.266666, official_business=0.200000, conversational=0.000000, oratorical=0.000000, publicistic=0.000000 | — | — |
| `hard_mixed_publicistic_oratorical` | publicistic, oratorical | conversational, oratorical | conversational | conversational=0.133333, oratorical=0.133333, official_business=0.066667, publicistic=0.066667, scientific=0.000000 | conversational | publicistic |
| `hard_short_ambiguous` | — | — | conversational | conversational=0.066667, official_business=0.066667, scientific=0.066667, oratorical=0.000000, publicistic=0.000000 | — | — |
| `hard_list` | — | — | conversational | conversational=0.066667, official_business=0.000000, oratorical=0.000000, publicistic=0.000000, scientific=0.000000 | — | — |
| `hard_neutral_information` | — | — | conversational | conversational=0.066667, official_business=0.066667, scientific=0.066667, oratorical=0.000000, publicistic=0.000000 | — | — |

Полные пять family-level значений, feature IDs и evidence counts находятся в `docs/style_v2_score_analysis.csv`.

## Publicistic false negatives

### `publicistic_education`

Rank `2`; support `0.133333`; competing style `conversational` (`0.133333`); families `syntactic`.

Signals present: `v2.publicistic.parceling_candidate`. Potential existing detectors without evidence: `v2.publicistic.evaluative_lexicon, v2.publicistic.exclamation, v2.publicistic.quotation, v2.shared.lexical_repetition`. Diagnosis: **insufficient independent detector coverage**. The fixture is not relabelled and no missing detector is implemented in C.2.

### `publicistic_environment`

Rank `2`; support `0.066667`; competing style `official_business` (`0.066667`); families `punctuation`.

Signals present: `v2.publicistic.exclamation, v2.publicistic.quotation`. Potential existing detectors without evidence: `v2.publicistic.evaluative_lexicon, v2.publicistic.parceling_candidate, v2.shared.lexical_repetition`. Diagnosis: **insufficient independent detector coverage**. The fixture is not relabelled and no missing detector is implemented in C.2.

### `hard_publicistic_official_lexicon`

Rank `4`; support `0.066667`; competing style `official_business` (`0.200000`); families `punctuation`.

Signals present: `v2.publicistic.exclamation, v2.publicistic.quotation`. Potential existing detectors without evidence: `v2.publicistic.evaluative_lexicon, v2.publicistic.parceling_candidate, v2.shared.lexical_repetition`. Diagnosis: **insufficient independent detector coverage**. The fixture is not relabelled and no missing detector is implemented in C.2.

### `hard_mixed_publicistic_oratorical`

Rank `4`; support `0.066667`; competing style `conversational` (`0.133333`); families `punctuation`.

Signals present: `v2.publicistic.exclamation`. Potential existing detectors without evidence: `v2.publicistic.evaluative_lexicon, v2.publicistic.parceling_candidate, v2.publicistic.quotation, v2.shared.lexical_repetition`. Diagnosis: **insufficient independent detector coverage**. The fixture is not relabelled and no missing detector is implemented in C.2.

## Conversational false positives

- `publicistic_comment`: score `0.200000`, families `lexical, syntactic`, features `v2.conversational.stratified_lexicon, v2.conversational.incomplete_sentence`. The false positive is secondary or weak CANDIDATE_ONLY support, not a new independent conversational detector.
- `publicistic_culture`: score `0.266667`, families `lexical, syntactic`, features `v2.conversational.stratified_lexicon, v2.conversational.incomplete_sentence`. The false positive is secondary or weak CANDIDATE_ONLY support, not a new independent conversational detector.
- `oratorical_friends`: score `0.133333`, families `lexical, syntactic`, features `v2.conversational.stratified_lexicon, v2.conversational.incomplete_sentence`. The false positive is secondary or weak CANDIDATE_ONLY support, not a new independent conversational detector.
- `hard_mixed_publicistic_oratorical`: score `0.133333`, families `lexical, syntactic`, features `v2.conversational.stratified_lexicon, v2.conversational.incomplete_sentence`. The false positive is secondary or weak CANDIDATE_ONLY support, not a new independent conversational detector.

The recurring sources are the legacy stratified-lexicon signal and the incomplete-sentence proxy. General punctuation does not enter the score as an independent AUTO confirmation. Calibration therefore acts on selection gates rather than changing method significance or detector weights.

## Detector diagnostics

`docs/style_v2_detector_diagnostics.csv` contains firing counts, in-style and outside-style counts, rough signal precision and style distribution for all `27` non-EXPERT_ONLY runtime detectors. These figures are engineering diagnostics on a small corpus and are not feature validation.

## Family dominance

Support is the equal mean of five family maxima. A saturated single family therefore contributes at most `0.2`; it cannot pass selection without the independent-family gate. The error matrix confirms that publicistic misses with punctuation-only evidence must remain abstentions rather than being rescued by a lower score floor.

## Mixed cases

- `hard_mixed_official_scientific`: expected `official_business, scientific`; selected `official_business, scientific`; ranked `scientific=0.266666`, `official_business=0.200000`, `conversational=0.000000`, `oratorical=0.000000`, `publicistic=0.000000`.
- `hard_mixed_publicistic_oratorical`: expected `publicistic, oratorical`; selected `conversational, oratorical`; ranked `conversational=0.133333`, `oratorical=0.133333`, `official_business=0.066667`, `publicistic=0.066667`, `scientific=0.000000`.

## Abstention and short texts

Good abstentions (`3`): `hard_short_ambiguous, hard_list, hard_neutral_information`.

Bad abstentions (`3`): `publicistic_education, publicistic_environment, hard_publicistic_official_lexicon`.

Short ambiguous/list/neutral fixtures remain legitimate abstentions. A single marker is intentionally insufficient; no length correction is introduced.

## Conclusion

Publicistic recall is detector-coverage limited. Conversational precision can be improved by relative-to-best and weak-evidence abstention gates while preserving ranking, evidence, registry metadata and production behavior.
