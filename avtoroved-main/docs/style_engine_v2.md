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

Aggregate counts are `AUX_METRIC`; source spans are `EVIDENCE`. Patch C.1 adds
a separate canonical registry of 62 source-traceable style METHOD_FEATURE
definitions. Detector signals are projected to `method_feature_candidates`
only after scoring and every projected row has `accepted=false` and
`expert_identification_value=None`. This projection cannot affect style score,
selection or methodological counts.

The layers are deliberately distinct:

1. **LEGACY FEATURE** — one of the preserved 32 historical metrics;
2. **DETECTOR SIGNAL** — a reproducible V2 engineering hit;
3. **EVIDENCE** — a source span supporting review;
4. **CANONICAL METHOD FEATURE** — a source-traceable registry definition;
5. **EXPERT ACCEPTED FEATURE** — a separately qualified case feature after
   rationale, evidence linking, stability and comparability assessment.

`AUTO` describes formal detection only. `CANDIDATE_ONLY` requires context
review. `EXPERT_ONLY` entries are never emitted as detected candidates.
Independently, `implementation_status` records whether the current program has
an `IMPLEMENTED`, `PARTIAL`, `NOT_IMPLEMENTED` or `NOT_APPLICABLE` route.
`AUTO` therefore does not imply `IMPLEMENTED`.

Runtime projection accepts only `IMPLEMENTED`/`PARTIAL` definitions with a real
producer and evidence type. Every `IMPLEMENTED` detector is checked by executing
the actual `detect_style_features` route; aggregate detector IDs are generated
by the same function used in candidate projection. Merely writing a detector
name in JSON cannot make it runtime-reachable.

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

Patch C.2 separates ranking from selection. Selection requires
`style_support_score >= 0.12`, distance from the leading score no greater than
`0.08`, and at least two independent families. A style supported exclusively
by weak `CANDIDATE_ONLY` evidence additionally requires score `>= 0.14`.
Consequently, one abbreviation, term, question, imperative or punctuation mark
cannot select a style. The score is an engineering support value, not
probability, confidence or methodological informativeness. Every style row has
a debug-only `selection_reason` with the gates, strongest evidence and failure
reasons; it is explicitly not an expert justification.

## Segments and output

V2 reuses `theme_segmenter.segment_text`; it does not copy a second segmenter.
Each segment records source offsets, text, detected feature IDs and support for
all five styles. Document output contains ranked `styles`, multi-layer
`selected_styles`, debug-only `leading_style`, segment coverage, detected
features, exact evidence fragments and an independent tuple of unaccepted
`method_feature_candidates`. `selected_styles=[]` is valid for short, neutral,
list-like or otherwise insufficient material.

The five aggregate style results project only to the corresponding general
`nn.lang.style_*` candidate. Selection of `scientific`, for example, does not
assert terminology, genitive chains, deverbal nouns or any other private
feature without that feature's own detector evidence.

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

The frozen Patch C baseline above remains reproducible through
`LEGACY_STYLE_SELECTION_PARAMETERS`. After DEVELOPMENT CALIBRATION on 24
fixtures, the four global parameters were frozen and evaluated once on an
11-fixture INTERNAL HOLDOUT. Holdout micro F1 changed from `0.818182` to
`0.857143`; full-corpus shadow micro F1 is `0.923077` (precision `0.967742`,
recall `0.882353`). These are internal engineering figures, not scientific
validation. Details: `docs/style_v2_calibration.md`.

V1 top-1 is intentionally not given invented multi-label metrics: V1 performs
lexical register stratification and only its conversational-reduced label maps
unambiguously to one of the five V2 classes.

## Limitations

- The corpus is small and authored for development tests.
- Publicistic recall remains limited by independent detector coverage.
- Regex morphology is limited without supplied Stanza tokens.
- RuSentiLex raises contextual candidates; it does not prove publicistic style.
- Lexical register, writing skill, theme and functional style remain separate.
- V2 must stay shadow-only until broader genre/topic-controlled validation.

Full metrics: `docs/style_v2_development_metrics.json`. Resolution of the 32
legacy indicators: `docs/style_feature_resolution.md`. Canonical definitions
and complete traceability: `docs/style_method_feature_registry.md`. Runtime
coverage: `docs/style_method_runtime_coverage.md`.
