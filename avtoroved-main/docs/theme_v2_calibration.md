# ThemeEngineV2 multi-label development calibration

> This is development calibration on a small synthetic corpus, not an
> independent scientific validation.

## Split discipline

The corpus was frozen first with seed `20260828`: 35 calibration and 15 untouched holdout fixtures. The tuning function accepts only calibration fixtures and their V2 ranking results; holdout labels/results are evaluated only after the parameters are fixed.

## Why baseline over-selected

Baseline treated every theme with at least one permissive segment-support hit as positive. Rubert similarities put many unrelated themes above the absolute semantic-only support threshold, so recall reached 1.0 while precision collapsed. Coverage is often 1.0 because most fixtures form a single segment: coverage then becomes binary, and one permissive hit means full coverage. Ranking still separates the correct top theme well.

For the 98% single-segment documents, the chosen document-level relative margin is equivalent to a within-segment relative comparison. The raw segment-support threshold was retained to preserve the recorded baseline; retuning it after holdout disclosure would invalidate this calibration cycle. Multi-segment coverage requires a later dedicated corpus.

## Score distributions

```json
{
  "expected": {
    "count": 60,
    "min": 0.372118,
    "p25": 0.504116,
    "median": 0.588152,
    "p75": 0.64191,
    "max": 0.75668,
    "mean": 0.5791124166666666
  },
  "non_expected": {
    "count": 440,
    "min": 0.252433,
    "p25": 0.318795,
    "median": 0.345031,
    "p75": 0.378356,
    "max": 0.52577,
    "mean": 0.35049637727272726
  },
  "supported_row_fraction": 0.816,
  "coverage_one_among_supported": 0.9975490196078431,
  "single_segment_document_fraction": 0.98
}
```

Full row-level scores are in `docs/theme_v2_score_analysis.csv`.

## Strategies evaluated on calibration only

| Strategy | Best parameters | Calibration metrics |
|---|---|---|
| `absolute` | `{"absolute_floor": 0.48, "minimum_coverage": 0.0, "minimum_supported_segments": 1, "relative_margin": null, "relative_ratio": null, "safety_max_labels": 4, "strategy": "absolute", "top_k": null}` | top1=0.942857; P=0.923077; R=0.857143; micro F1=0.888889; macro F1=0.891227; avg labels=1.114286 |
| `hybrid` | `{"absolute_floor": 0.44, "minimum_coverage": 0.0, "minimum_supported_segments": 1, "relative_margin": 0.08, "relative_ratio": null, "safety_max_labels": 4, "strategy": "hybrid", "top_k": null}` | top1=0.942857; P=0.948718; R=0.880952; micro F1=0.913580; macro F1=0.911941; avg labels=1.114286 |
| `relative_margin` | `{"absolute_floor": 0.0, "minimum_coverage": 0.0, "minimum_supported_segments": 1, "relative_margin": 0.06, "relative_ratio": null, "safety_max_labels": 4, "strategy": "relative_margin", "top_k": null}` | top1=0.942857; P=0.883721; R=0.904762; micro F1=0.894118; macro F1=0.896709; avg labels=1.228571 |
| `relative_ratio` | `{"absolute_floor": 0.0, "minimum_coverage": 0.0, "minimum_supported_segments": 1, "relative_margin": null, "relative_ratio": 0.9, "safety_max_labels": 4, "strategy": "relative_ratio", "top_k": null}` | top1=0.942857; P=0.923077; R=0.857143; micro F1=0.888889; macro F1=0.895115; avg labels=1.114286 |
| `top_k_support` | `{"absolute_floor": 0.0, "minimum_coverage": 0.0, "minimum_supported_segments": 1, "relative_margin": null, "relative_ratio": null, "safety_max_labels": 4, "strategy": "top_k_support", "top_k": 2}` | top1=0.942857; P=0.602941; R=0.976190; micro F1=0.745455; macro F1=0.774473; avg labels=1.942857 |

## Chosen calibration layer

```json
{
  "strategy": "hybrid",
  "absolute_floor": 0.44,
  "relative_margin": 0.08,
  "relative_ratio": null,
  "minimum_coverage": 0.0,
  "minimum_supported_segments": 1,
  "top_k": null,
  "safety_max_labels": 4
}
```

The layer applies after ranking and does not alter embeddings, prototypes,
semantic/lexical weights or `dominant_theme`. Empty selection is allowed.

## Metrics

| Set | Top-1 | Micro P | Micro R | Micro F1 | Macro F1 | Avg labels/doc |
|---|---:|---:|---:|---:|---:|---:|
| Baseline V2 (all 50) | 0.960000 | 0.147059 | 1.000000 | 0.256410 | 0.255207 | 8.160000 |
| Calibrated V2 — calibration | 0.942857 | 0.948718 | 0.880952 | 0.913580 | 0.911941 | 1.114286 |
| Calibrated V2 — untouched holdout | 1.000000 | 1.000000 | 0.888889 | 0.941176 | 0.933333 | 1.066667 |

## Holdout per-theme F1

Small support makes every per-theme value unstable.

| Theme | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `law` | 1.000000 | 0.500000 | 0.666667 | 2 |
| `medicine` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `it` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `economics` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `military` | 1.000000 | 1.000000 | 1.000000 | 1 |
| `science` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `religion` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `politics` | 1.000000 | 1.000000 | 1.000000 | 2 |
| `sports` | 1.000000 | 0.500000 | 0.666667 | 2 |
| `everyday` | 1.000000 | 1.000000 | 1.000000 | 1 |

## Mixed-theme cases

| Fixture | Expected | Ranked themes | Selected | Expected coverage/delta |
|---|---|---|---|---|
| `law_contract_dispute` | `['law', 'economics']` | `['law', 'economics', 'everyday', 'religion', 'sports', 'politics', 'medicine', 'science', 'it', 'military']` | `['law']` | law: coverage=1.000, delta=0.000; economics: coverage=1.000, delta=0.116 |
| `medicine_trial` | `['medicine', 'science']` | `['medicine', 'science', 'economics', 'it', 'law', 'military', 'sports', 'religion', 'politics', 'everyday']` | `['medicine', 'science']` | medicine: coverage=1.000, delta=0.000; science: coverage=1.000, delta=0.055 |
| `it_ml` | `['it', 'science']` | `['science', 'it', 'medicine', 'economics', 'law', 'politics', 'military', 'sports', 'religion', 'everyday']` | `['science', 'it']` | it: coverage=1.000, delta=0.052; science: coverage=1.000, delta=0.000 |
| `military_evacuation` | `['military', 'medicine']` | `['military', 'sports', 'medicine', 'politics', 'religion', 'it', 'everyday', 'science', 'law', 'economics']` | `['military']` | military: coverage=1.000, delta=0.000; medicine: coverage=1.000, delta=0.204 |
| `politics_parliament` | `['politics', 'law']` | `['politics', 'law', 'sports', 'science', 'everyday', 'economics', 'medicine', 'military', 'it', 'religion']` | `['politics']` | politics: coverage=1.000, delta=0.000; law: coverage=1.000, delta=0.187 |
| `sports_injury` | `['sports', 'medicine']` | `['sports', 'medicine', 'everyday', 'science', 'military', 'politics', 'law', 'religion', 'it', 'economics']` | `['sports']` | sports: coverage=1.000, delta=0.000; medicine: coverage=1.000, delta=0.126 |
| `hard_mixed_politics_economics` | `['politics', 'economics']` | `['economics', 'politics', 'law', 'science', 'everyday', 'medicine', 'religion', 'it', 'military', 'sports']` | `['economics']` | politics: coverage=1.000, delta=0.145; economics: coverage=1.000, delta=0.000 |
| `hard_law_politics_overlap` | `['law', 'politics']` | `['politics', 'law', 'science', 'sports', 'medicine', 'economics', 'it', 'military', 'everyday', 'religion']` | `['politics', 'law']` | law: coverage=1.000, delta=0.045; politics: coverage=1.000, delta=0.000 |
| `hard_medicine_sports_overlap` | `['sports', 'medicine']` | `['medicine', 'science', 'sports', 'politics', 'law', 'military', 'it', 'religion', 'economics', 'everyday']` | `['medicine']` | sports: coverage=1.000, delta=0.162; medicine: coverage=1.000, delta=0.000 |
| `hard_long_multisegment` | `['it', 'economics']` | `['economics', 'it', 'military', 'science', 'sports', 'everyday', 'medicine', 'politics', 'law', 'religion']` | `['economics', 'it']` | it: coverage=1.000, delta=0.005; economics: coverage=1.000, delta=0.000 |
| `hard_religion_history` | `['religion', 'science']` | `['religion', 'science', 'everyday', 'it', 'military', 'economics', 'politics', 'law', 'medicine', 'sports']` | `['religion', 'science']` | religion: coverage=1.000, delta=0.000; science: coverage=1.000, delta=0.050 |

## Protected semantic-only/weak-lexical cases

| Fixture | Expected | Ranked themes | Selected | Expected coverage/delta |
|---|---|---|---|---|
| `medicine_vaccination` | `['medicine']` | `['medicine', 'science', 'everyday', 'sports', 'military', 'it', 'religion', 'law', 'politics', 'economics']` | `['medicine']` | medicine: coverage=1.000, delta=0.000 |
| `science_experiment` | `['science']` | `['science', 'medicine', 'military', 'it', 'sports', 'politics', 'law', 'economics', 'religion', 'everyday']` | `['science']` | science: coverage=1.000, delta=0.000 |
| `science_article` | `['science']` | `['science', 'medicine', 'it', 'law', 'sports', 'military', 'politics', 'economics', 'religion', 'everyday']` | `['science']` | science: coverage=1.000, delta=0.000 |
| `religion_service` | `['religion']` | `['religion', 'everyday', 'sports', 'medicine', 'law', 'military', 'science', 'it', 'politics', 'economics']` | `['religion']` | religion: coverage=1.000, delta=0.000 |
| `politics_diplomacy` | `['politics']` | `['politics', 'law', 'everyday', 'economics', 'religion', 'science', 'military', 'it', 'sports', 'medicine']` | `['politics']` | politics: coverage=1.000, delta=0.000 |
| `hard_semantic_without_direct_keyword` | `['science']` | `['science', 'medicine', 'it', 'sports', 'everyday', 'military', 'law', 'religion', 'economics', 'politics']` | `['science']` | science: coverage=1.000, delta=0.000 |

## Interpretation

The holdout is internal to the same constructed development corpus. These
numbers justify keeping V2 in shadow mode and proceeding to broader corpus
validation; they do not establish forensic validity.
