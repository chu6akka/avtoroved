# StyleEngineV2 — shadow functional-style analysis

Status: Patch C, **shadow-only**. Production `StyleEngine.analyze()` still
returns the unchanged `StratificationEngine` V1 result. V2 is available only
through an explicit `StyleEngineV2().analyze(...)` or
`StyleEngine.analyze_shadow(...)` call.

## Scope

V2 models five functional-style layers and permits more than one layer:

- `official_business` — official-business;
- `scientific` — scientific;
- `publicistic` — publicistic;
- `oratorical` — oratorical;
- `conversational` — conversational.

It does not add artistic, epistolary, internet, legal, advertising or separate
journalistic styles. Internet markers remain EXPERIMENTAL evidence and do not
contribute to the conversational score.

## Evidence and automation

Every detector specification has one of three automation statuses:

- `AUTO`: reproducible formal detection, not expert acceptance;
- `CANDIDATE_ONLY`: a fragment is raised for human confirmation;
- `EXPERT_ONLY`: the phenomenon is documented but never asserted by code.

Metaphor and communicative tone are EXPERT_ONLY. Rhetorical question,
parceling, inversion/ellipsis proxies, terminology and contextual evaluative
lexicon are candidates. A question mark is only a question; it is not a
rhetorical question. No result populates `expert_identification_value`.

Aggregate counts are `AUX_METRIC`; source spans are `EVIDENCE`. The current
method registry contains no functional-style METHOD mappings, so Patch C does
not create an accepted METHOD_FEATURE. Any future mapping must still begin as
an unaccepted candidate and be confirmed by an expert.

## Scoring

Signals are normalized within five independent families:

1. lexical;
2. morphological;
3. syntactic;
4. discourse;
5. punctuation.

Repeated hits in one family cannot dominate: the family receives the maximum
normalized support of its features. Evidence with the same source coordinates
cannot be counted as independent support in multiple families. The document
`style_support_score` is the equal mean of the five family supports.

Selection requires `style_support_score >= 0.12` and at least two independent
families. Consequently, one abbreviation, term, question, imperative or
punctuation mark cannot select a style. The score is an engineering support
value, not probability, confidence or methodological informativeness.

## Segments and output

V2 reuses `theme_segmenter.segment_text`; it does not copy a second segmenter.
Each segment records source offsets, text, detected feature IDs and support for
all five styles. Document output contains ranked `styles`, multi-layer
`selected_styles`, debug-only `leading_style`, segment coverage, detected
features and exact evidence fragments. `selected_styles=[]` is valid for short,
neutral, list-like or otherwise insufficient material.

`parsed_tokens` can be supplied from the existing document analysis. V2 never
starts Stanza itself. In `analyze_shadow`, the already calculated V1 lexical
stratification is reused rather than run twice. The development evaluator had
no parsed document, so morphology/dependency features were deliberately
limited and `parsed_document_reused=false` was recorded.

## Development baseline

The 35-fixture development corpus contains 25 clear-style texts and 10
mixed/hard cases. It is constructed regression material, not independent
scientific validation.

| Metric | V1 | V2 |
|---|---:|---:|
| top-1 accuracy | 0.200000 | 0.800000 |
| micro precision | — | 0.882353 |
| micro recall | — | 0.882353 |
| micro F1 | — | 0.882353 |
| macro F1 | — | 0.870000 |
| average selected styles | — | 0.971429 |
| abstentions | — | 6 |
| mixed-case recall | — | 0.750000 |

V1 top-1 is intentionally not given invented multi-label metrics: V1 performs
lexical register stratification and only its conversational-reduced label maps
unambiguously to one of the five V2 classes.

## Limitations

- The corpus is small and authored for development tests.
- Publicistic recall and conversational precision require separate calibration.
- Regex morphology is limited without supplied Stanza tokens.
- RuSentiLex raises contextual candidates; it does not prove publicistic style.
- Lexical register, writing skill, theme and functional style remain separate.
- V2 must stay shadow-only until broader genre/topic-controlled validation.

Full metrics: `docs/style_v2_development_metrics.json`. Resolution of the 32
legacy indicators: `docs/style_feature_resolution.md`.
