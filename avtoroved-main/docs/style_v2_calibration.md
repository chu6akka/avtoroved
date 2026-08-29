# StyleEngineV2: DEVELOPMENT calibration

> This is DEVELOPMENT CALIBRATION with one INTERNAL HOLDOUT evaluation. It is not scientific validation and support scores are not probabilities.

## 1. Baseline

top1 `0.800000`, micro P/R/F1 `0.882353/0.882353/0.882353`, macro F1 `0.870000`, avg styles `0.971429`, abstentions `6`, mixed recall `0.750000`

## 2. Error analysis

The frozen matrix is in `style_v2_score_analysis.csv`; the detailed analysis is in `style_v2_error_analysis.md`.

## 3. Publicistic false negatives

The missed publicistic fixtures typically expose only punctuation or one candidate family. Lowering the floor would simulate missing independent evidence, so C.2 does not attempt to force recall to 1.0.

## 4. Conversational false positives

False positives are mainly secondary weak-only combinations of the legacy stratified lexicon and incomplete-sentence proxy. They motivate global weak-evidence abstention and relative-to-best gates; detector weights are unchanged.

## 5. Detector diagnostics

See `style_v2_detector_diagnostics.csv`. Rough precision is descriptive only; no detector was removed or promoted from this small corpus.

## 6. Score distributions

The full per-fixture and per-family distributions are in `style_v2_score_analysis.csv`. One-family publicistic scores cluster below the independent-family gate; false conversational labels are weak-only or far below the leading style.

## 7. Calibration strategy

Split: seed `20260829`; DEVELOPMENT CALIBRATION `24` fixtures; INTERNAL HOLDOUT `11` fixtures. The optimizer accepts only records marked `CALIBRATION` and rejects holdout records before reading them.

Tested A–F: current threshold only; absolute floor; relative margin; floor + margin; floor + independent families; and the four-parameter hybrid.

Frozen F_HYBRID parameters: `absolute_floor=0.12`, `relative_margin=0.08`, `minimum_family_support=2`, `weak_style_abstention_threshold=0.14`.

| Strategy | Parameters | micro F1 | macro F1 | mixed recall | FP |
|---|---|---:|---:|---:|---:|
| F_HYBRID | `{"absolute_floor": 0.1, "minimum_family_support": 2, "relative_margin": 0.08, "weak_style_abstention_threshold": 0.14}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.1, "minimum_family_support": 2, "relative_margin": 0.08, "weak_style_abstention_threshold": 0.16}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.1, "minimum_family_support": 2, "relative_margin": 0.1, "weak_style_abstention_threshold": 0.14}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.1, "minimum_family_support": 2, "relative_margin": 0.1, "weak_style_abstention_threshold": 0.16}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| **F_HYBRID (frozen winner)** | `{"absolute_floor": 0.12, "minimum_family_support": 2, "relative_margin": 0.08, "weak_style_abstention_threshold": 0.14}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.12, "minimum_family_support": 2, "relative_margin": 0.08, "weak_style_abstention_threshold": 0.16}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.12, "minimum_family_support": 2, "relative_margin": 0.1, "weak_style_abstention_threshold": 0.14}` | 0.954545 | 0.933333 | 1.000000 | 0 |
| F_HYBRID | `{"absolute_floor": 0.12, "minimum_family_support": 2, "relative_margin": 0.1, "weak_style_abstention_threshold": 0.16}` | 0.954545 | 0.933333 | 1.000000 | 0 |

## 8. DEVELOPMENT CALIBRATION metrics

Baseline: top1 `0.833333`, micro P/R/F1 `0.913043/0.913043/0.913043`, macro F1 `0.893333`, avg styles `0.958333`, abstentions `4`, mixed recall `1.000000`.

Frozen strategy: top1 `0.833333`, micro P/R/F1 `1.000000/0.913043/0.954545`, macro F1 `0.933333`, avg styles `0.875000`, abstentions `4`, mixed recall `1.000000`.

## 9. INTERNAL HOLDOUT metrics

Baseline: top1 `0.727273`, micro P/R/F1 `0.818182/0.818182/0.818182`, macro F1 `0.833333`, avg styles `1.000000`, abstentions `2`, mixed recall `0.500000`.

One frozen-parameter run: top1 `0.727273`, micro P/R/F1 `0.900000/0.818182/0.857143`, macro F1 `0.860000`, avg styles `0.909091`, abstentions `2`, mixed recall `0.500000`; mixed exact-set accuracy `0.000000`.

| Style | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| official_business | 1.000000 | 1.000000 | 1.000000 | 2 |
| scientific | 1.000000 | 1.000000 | 1.000000 | 2 |
| publicistic | 1.000000 | 0.333333 | 0.500000 | 3 |
| oratorical | 1.000000 | 1.000000 | 1.000000 | 2 |
| conversational | 0.666667 | 1.000000 | 0.800000 | 2 |

## 10. Mixed cases

- `hard_mixed_publicistic_oratorical`: expected `publicistic, oratorical`; selected `oratorical`; `conversational=0.133333` families=2, `oratorical=0.133333` families=2, `official_business=0.066667` families=1, `publicistic=0.066667` families=1, `scientific=0.000000` families=0.

## 11. Abstention analysis

INTERNAL HOLDOUT: good abstentions `1`, bad abstentions `1`. Weak ambiguous evidence can still produce a leading rank while `selected_styles` remains empty.

## 12. Limitations

The corpus has only 35 authored fixtures. The split is internal, small and not independent external validation. Scores depend on existing heuristic detectors and optional legacy stratification/sentiment resources. No forensic or expert significance is assigned automatically.

## 13. Future detector coverage

Broader corpus validation is required before any production switch. Publicistic recall should next be studied through independently justified METHOD detector coverage, not further threshold relaxation. No missing detector is implemented in Patch C.2.

## Full-corpus calibrated shadow result

top1 `0.800000`, micro P/R/F1 `0.967742/0.882353/0.923077`, macro F1 `0.904615`, avg styles `0.885714`, abstentions `6`, mixed recall `0.750000`

## Engineering performance

Warm development-corpus timing: V1 `0.002717` s; V2 `0.021716` s; mean V2
`0.620` ms/document. Timing is an engineering benchmark, not a scientific
metric; the selection gates use constant-time comparisons per style.
