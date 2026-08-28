# ThemeEngineV2 real development error analysis

> DEVELOPMENT METRICS — NOT SCIENTIFIC VALIDATION. Thresholds, weights,
> prototypes and fixtures were not tuned for this report.

## Model

```json
{
  "backend": "sentence-transformers",
  "model_name": "cointegrated/rubert-tiny2",
  "model_revision": "e8ed3b0c8bbf4fb6984c3de043bf7d2f4e5969ae",
  "tokenizer_revision": "e8ed3b0c8bbf4fb6984c3de043bf7d2f4e5969ae",
  "library_version": "5.7.0",
  "sentence_transformers_version": "5.7.0",
  "transformers_version": "5.16.1",
  "torch_version": "2.13.0",
  "device": "cpu",
  "normalization": "l2",
  "pooling": "cls",
  "inference_parameters": {
    "local_files_only": true,
    "show_progress_bar": false,
    "normalize_embeddings": true
  },
  "weights_sha256": null,
  "loaded": true,
  "error": null
}
```

## Aggregate metrics

| Engine | top-1 | micro P | micro R | micro F1 | macro F1 |
|---|---:|---:|---:|---:|---:|
| V1 | 0.720000 | 0.897436 | 0.583333 | 0.707071 | 0.696313 |
| REAL V2 | 0.960000 | 0.147059 | 1.000000 | 0.256410 | 0.255207 |

## REAL V2 per-theme metrics

| Theme | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `law` | 0.142857 | 1.000000 | 0.250000 | 6 |
| `medicine` | 0.159091 | 1.000000 | 0.274510 | 7 |
| `it` | 0.142857 | 1.000000 | 0.250000 | 5 |
| `economics` | 0.195122 | 1.000000 | 0.326531 | 8 |
| `military` | 0.100000 | 1.000000 | 0.181818 | 4 |
| `science` | 0.200000 | 1.000000 | 0.333333 | 8 |
| `religion` | 0.125000 | 1.000000 | 0.222222 | 5 |
| `politics` | 0.142857 | 1.000000 | 0.250000 | 6 |
| `sports` | 0.146341 | 1.000000 | 0.255319 | 6 |
| `everyday` | 0.116279 | 1.000000 | 0.208333 | 5 |

## Semantic-only / weak-lexical cases

Criterion: single expected theme and fewer than two unique lexical matches.

| Fixture | Expected | Lexical unique | V1 | REAL V2 | Expected-theme scores |
|---|---|---:|---|---|---|
| `medicine_vaccination` | `medicine` | 1 | dominant=none; top=[] | dominant=medicine; ranked=[medicine:0.5470, science:0.3811, everyday:0.3769] | semantic=0.6738; lexical=0.1667; coverage=1.0000 |
| `science_experiment` | `science` | 1 | dominant=none; top=[] | dominant=science; ranked=[science:0.5747, medicine:0.4936, military:0.4315] | semantic=0.7107; lexical=0.1667; coverage=1.0000 |
| `science_article` | `science` | 1 | dominant=none; top=[] | dominant=science; ranked=[science:0.5788, medicine:0.4656, it:0.4228] | semantic=0.7162; lexical=0.1667; coverage=1.0000 |
| `science_linguistics` | `science` | 1 | dominant=none; top=[] | dominant=science; ranked=[science:0.5010, it:0.4352, law:0.4119] | semantic=0.6125; lexical=0.1667; coverage=1.0000 |
| `religion_service` | `religion` | 1 | dominant=sports; top=[sports:0.0516] | dominant=religion; ranked=[religion:0.5882, everyday:0.3591, sports:0.3398] | semantic=0.7286; lexical=0.1667; coverage=1.0000 |
| `religion_pilgrimage` | `religion` | 1 | dominant=none; top=[] | dominant=religion; ranked=[religion:0.5787, everyday:0.3739, science:0.3621] | semantic=0.7160; lexical=0.1667; coverage=1.0000 |
| `religion_ethics` | `religion` | 1 | dominant=none; top=[] | dominant=religion; ranked=[religion:0.5092, law:0.4355, politics:0.4167] | semantic=0.6234; lexical=0.1667; coverage=1.0000 |
| `politics_diplomacy` | `politics` | 0 | dominant=law; top=[law:0.0531] | dominant=politics; ranked=[politics:0.5041, law:0.3844, everyday:0.3509] | semantic=0.6722; lexical=0.0000; coverage=1.0000 |
| `politics_protest` | `politics` | 1 | dominant=none; top=[] | dominant=politics; ranked=[politics:0.5255, law:0.4163, economics:0.3518] | semantic=0.6452; lexical=0.1667; coverage=1.0000 |
| `hard_single_keyword` | `everyday` | 1 | dominant=none; top=[] | dominant=everyday; ranked=[everyday:0.4306, law:0.3597, religion:0.3376] | semantic=0.5186; lexical=0.1667; coverage=1.0000 |
| `hard_very_short` | `sports` | 1 | dominant=sports; top=[sports:0.0516] | dominant=sports; ranked=[sports:0.5339, law:0.3764, military:0.3750] | semantic=0.6563; lexical=0.1667; coverage=1.0000 |
| `hard_semantic_without_direct_keyword` | `science` | 0 | dominant=none; top=[] | dominant=science; ranked=[science:0.4532, medicine:0.4231, it:0.4147] | semantic=0.6042; lexical=0.0000; coverage=1.0000 |
| `hard_metaphorical_attack` | `economics` | 1 | dominant=none; top=[] | dominant=military; ranked=[military:0.5076, economics:0.4811, sports:0.4589] | semantic=0.5859; lexical=0.1667; coverage=1.0000 |

## Mixed-theme cases

| Fixture | Expected | V1 | REAL V2 | Expected-theme coverage |
|---|---|---|---|---|
| `law_contract_dispute` | ['law', 'economics'] | dominant=law; top=[law:0.0763] | dominant=law; ranked=[law:0.6089, economics:0.4926, everyday:0.4118] | law=1.0000, economics=1.0000 |
| `medicine_trial` | ['medicine', 'science'] | dominant=economics; top=[economics:0.0570] | dominant=medicine; ranked=[medicine:0.5072, science:0.4525, economics:0.3809] | medicine=1.0000, science=1.0000 |
| `it_ml` | ['it', 'science'] | dominant=science; top=[science:0.0828] | dominant=science; ranked=[science:0.5951, it:0.5433, medicine:0.4052] | it=1.0000, science=1.0000 |
| `military_evacuation` | ['military', 'medicine'] | dominant=military; top=[military:0.0828] | dominant=military; ranked=[military:0.6452, sports:0.4507, medicine:0.4414] | military=1.0000, medicine=1.0000 |
| `politics_parliament` | ['politics', 'law'] | dominant=politics; top=[politics:0.0711] | dominant=politics; ranked=[politics:0.5594, law:0.3721, sports:0.3331] | politics=1.0000, law=1.0000 |
| `sports_injury` | ['sports', 'medicine'] | dominant=sports; top=[sports:0.0805] | dominant=sports; ranked=[sports:0.6150, medicine:0.4887, everyday:0.4145] | sports=1.0000, medicine=1.0000 |
| `hard_mixed_politics_economics` | ['politics', 'economics'] | dominant=economics; top=[economics:0.0930] | dominant=economics; ranked=[economics:0.6419, politics:0.4969, law:0.4066] | politics=1.0000, economics=1.0000 |
| `hard_law_politics_overlap` | ['law', 'politics'] | dominant=politics; top=[politics:0.0795] | dominant=politics; ranked=[politics:0.5778, law:0.5323, science:0.3446] | law=1.0000, politics=1.0000 |
| `hard_medicine_sports_overlap` | ['sports', 'medicine'] | dominant=medicine; top=[medicine:0.0903] | dominant=medicine; ranked=[medicine:0.6246, science:0.4781, sports:0.4624] | sports=1.0000, medicine=1.0000 |
| `hard_long_multisegment` | ['it', 'economics'] | dominant=economics; top=[economics:0.0664] | dominant=economics; ranked=[economics:0.4641, it:0.4590, military:0.4089] | it=1.0000, economics=1.0000 |
| `hard_religion_history` | ['religion', 'science'] | dominant=none; top=[] | dominant=religion; ranked=[religion:0.4912, science:0.4410, everyday:0.4078] | religion=1.0000, science=1.0000 |

## Error fixtures (49)

### `law_court_hearing`

- expected_themes: `['law']`
- V1 result: `dominant=law; top=[law:0.1224]`; predicted `['law']`
- V2 predicted: `['economics', 'everyday', 'law', 'medicine', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `law` | 0.712897 | 0.617196 | 1.000000 | 1.000000 | 1 |
| 2 | `sports` | 0.439149 | 0.474421 | 0.333333 | 1.000000 | 1 |
| 3 | `politics` | 0.395782 | 0.472153 | 0.166667 | 1.000000 | 1 |
| 4 | `science` | 0.357781 | 0.477041 | 0.000000 | 1.000000 | 1 |
| 5 | `religion` | 0.345266 | 0.404799 | 0.166667 | 0.000000 | 0 |
| 6 | `everyday` | 0.323409 | 0.431212 | 0.000000 | 1.000000 | 1 |
| 7 | `medicine` | 0.318230 | 0.424307 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.318169 | 0.424225 | 0.000000 | 1.000000 | 1 |
| 9 | `it` | 0.301130 | 0.401507 | 0.000000 | 0.000000 | 0 |
| 10 | `military` | 0.289346 | 0.385794 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `law` `segment-0001` [0:195], semantic=0.6172, lexical=7: Суд начал заседание с проверки явки сторон. Истец поддержал требования по договору, а адвокат ответчика попросил приобщить новые доказательства. После прений судья удалился для вынесения решения.
- `sports` `segment-0001` [0:195], semantic=0.4744, lexical=2: Суд начал заседание с проверки явки сторон. Истец поддержал требования по договору, а адвокат ответчика попросил приобщить новые доказательства. После прений судья удалился для вынесения решения.
- `politics` `segment-0001` [0:195], semantic=0.4722, lexical=1: Суд начал заседание с проверки явки сторон. Истец поддержал требования по договору, а адвокат ответчика попросил приобщить новые доказательства. После прений судья удалился для вынесения решения.

### `law_criminal_case`

- expected_themes: `['law']`
- V1 result: `dominant=law; top=[law:0.1360]`; predicted `['law']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `law` | 0.756680 | 0.675573 | 1.000000 | 1.000000 | 1 |
| 2 | `science` | 0.419215 | 0.503398 | 0.166667 | 1.000000 | 1 |
| 3 | `politics` | 0.397766 | 0.474799 | 0.166667 | 1.000000 | 1 |
| 4 | `sports` | 0.354007 | 0.472010 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.353128 | 0.470838 | 0.000000 | 1.000000 | 1 |
| 6 | `economics` | 0.337471 | 0.449962 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.327920 | 0.437227 | 0.000000 | 1.000000 | 1 |
| 8 | `military` | 0.318579 | 0.424772 | 0.000000 | 1.000000 | 1 |
| 9 | `everyday` | 0.317236 | 0.422981 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.317100 | 0.422800 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `law` `segment-0001` [0:186], semantic=0.6756, lexical=7: Следователь предъявил обвиняемому постановление и разъяснил право на защиту. Прокурор изучил материалы уголовного дела, после чего адвокат заявил ходатайство о дополнительной экспертизе.
- `science` `segment-0001` [0:186], semantic=0.5034, lexical=1: Следователь предъявил обвиняемому постановление и разъяснил право на защиту. Прокурор изучил материалы уголовного дела, после чего адвокат заявил ходатайство о дополнительной экспертизе.
- `politics` `segment-0001` [0:186], semantic=0.4748, lexical=1: Следователь предъявил обвиняемому постановление и разъяснил право на защиту. Прокурор изучил материалы уголовного дела, после чего адвокат заявил ходатайство о дополнительной экспертизе.

### `law_contract_dispute`

- expected_themes: `['economics', 'law']`
- V1 result: `dominant=law; top=[law:0.0763]`; predicted `['law']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `law` | 0.608932 | 0.589687 | 0.666667 | 1.000000 | 1 |
| 2 | `economics` | 0.492618 | 0.545713 | 0.333333 | 1.000000 | 1 |
| 3 | `everyday` | 0.411842 | 0.493567 | 0.166667 | 1.000000 | 1 |
| 4 | `religion` | 0.359475 | 0.423745 | 0.166667 | 1.000000 | 1 |
| 5 | `sports` | 0.348836 | 0.465114 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.326113 | 0.434817 | 0.000000 | 1.000000 | 1 |
| 7 | `medicine` | 0.325084 | 0.433445 | 0.000000 | 1.000000 | 1 |
| 8 | `science` | 0.323132 | 0.430842 | 0.000000 | 1.000000 | 1 |
| 9 | `it` | 0.322194 | 0.429592 | 0.000000 | 1.000000 | 1 |
| 10 | `military` | 0.315304 | 0.420406 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `law` `segment-0001` [0:185], semantic=0.5897, lexical=4: Компания не исполнила обязательство по поставке товара в установленный договором срок. Покупатель направил претензию и потребовал возместить убытки, а затем подал иск в арбитражный суд.
- `economics` `segment-0001` [0:185], semantic=0.5457, lexical=2: Компания не исполнила обязательство по поставке товара в установленный договором срок. Покупатель направил претензию и потребовал возместить убытки, а затем подал иск в арбитражный суд.
- `everyday` `segment-0001` [0:185], semantic=0.4936, lexical=1: Компания не исполнила обязательство по поставке товара в установленный договором срок. Покупатель направил претензию и потребовал возместить убытки, а затем подал иск в арбитражный суд.

### `law_appeal`

- expected_themes: `['law']`
- V1 result: `dominant=law; top=[law:0.1133]`; predicted `['law']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `law` | 0.700241 | 0.655877 | 0.833333 | 1.000000 | 1 |
| 2 | `sports` | 0.417894 | 0.501636 | 0.166667 | 1.000000 | 1 |
| 3 | `science` | 0.406504 | 0.542005 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.401629 | 0.479949 | 0.166667 | 1.000000 | 1 |
| 5 | `politics` | 0.385690 | 0.514253 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.337551 | 0.450068 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.323477 | 0.431303 | 0.000000 | 1.000000 | 1 |
| 8 | `religion` | 0.321994 | 0.429325 | 0.000000 | 1.000000 | 1 |
| 9 | `it` | 0.318045 | 0.424060 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.317365 | 0.423154 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `law` `segment-0001` [0:189], semantic=0.6559, lexical=5: Защитник обжаловал приговор, указав на нарушение процессуального порядка исследования показаний. Апелляционная инстанция проверила доводы жалобы и оставила часть выводов суда без изменения.
- `sports` `segment-0001` [0:189], semantic=0.5016, lexical=1: Защитник обжаловал приговор, указав на нарушение процессуального порядка исследования показаний. Апелляционная инстанция проверила доводы жалобы и оставила часть выводов суда без изменения.
- `science` `segment-0001` [0:189], semantic=0.5420, lexical=0: Защитник обжаловал приговор, указав на нарушение процессуального порядка исследования показаний. Апелляционная инстанция проверила доводы жалобы и оставила часть выводов суда без изменения.

### `medicine_diagnosis`

- expected_themes: `['medicine']`
- V1 result: `dominant=medicine; top=[medicine:0.0993]`; predicted `['medicine']`
- V2 predicted: `['economics', 'everyday', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `medicine` | 0.694795 | 0.648615 | 0.833333 | 1.000000 | 1 |
| 2 | `science` | 0.377459 | 0.503278 | 0.000000 | 1.000000 | 1 |
| 3 | `sports` | 0.358026 | 0.477368 | 0.000000 | 1.000000 | 1 |
| 4 | `everyday` | 0.357574 | 0.421210 | 0.166667 | 1.000000 | 1 |
| 5 | `religion` | 0.339660 | 0.452880 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.332865 | 0.443820 | 0.000000 | 1.000000 | 1 |
| 7 | `economics` | 0.326124 | 0.434832 | 0.000000 | 1.000000 | 1 |
| 8 | `military` | 0.320445 | 0.427260 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.316580 | 0.422106 | 0.000000 | 1.000000 | 1 |
| 10 | `it` | 0.299179 | 0.398906 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `medicine` `segment-0001` [0:179], semantic=0.6486, lexical=5: Пациент пожаловался врачу на кашель, слабость и повышенную температуру. После осмотра и анализа крови терапевт уточнил диагноз и назначил лечение противовоспалительным препаратом.
- `science` `segment-0001` [0:179], semantic=0.5033, lexical=0: Пациент пожаловался врачу на кашель, слабость и повышенную температуру. После осмотра и анализа крови терапевт уточнил диагноз и назначил лечение противовоспалительным препаратом.
- `sports` `segment-0001` [0:179], semantic=0.4774, lexical=0: Пациент пожаловался врачу на кашель, слабость и повышенную температуру. После осмотра и анализа крови терапевт уточнил диагноз и назначил лечение противовоспалительным препаратом.

### `medicine_surgery`

- expected_themes: `['medicine']`
- V1 result: `dominant=medicine; top=[medicine:0.0712]`; predicted `['medicine']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `medicine` | 0.690064 | 0.697863 | 0.666667 | 1.000000 | 1 |
| 2 | `sports` | 0.434645 | 0.523971 | 0.166667 | 1.000000 | 1 |
| 3 | `science` | 0.420960 | 0.505725 | 0.166667 | 1.000000 | 1 |
| 4 | `military` | 0.412718 | 0.494735 | 0.166667 | 1.000000 | 1 |
| 5 | `everyday` | 0.402448 | 0.481042 | 0.166667 | 1.000000 | 1 |
| 6 | `it` | 0.398043 | 0.475168 | 0.166667 | 1.000000 | 1 |
| 7 | `politics` | 0.386673 | 0.460008 | 0.166667 | 1.000000 | 1 |
| 8 | `religion` | 0.357434 | 0.476578 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.355538 | 0.474051 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.323597 | 0.431462 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `medicine` `segment-0001` [0:174], semantic=0.6979, lexical=4: Хирургическая операция прошла без осложнений. В послеоперационной палате медсестра контролировала давление и состояние пациента, а врач составил план дальнейшей реабилитации.
- `sports` `segment-0001` [0:174], semantic=0.5240, lexical=1: Хирургическая операция прошла без осложнений. В послеоперационной палате медсестра контролировала давление и состояние пациента, а врач составил план дальнейшей реабилитации.
- `science` `segment-0001` [0:174], semantic=0.5057, lexical=1: Хирургическая операция прошла без осложнений. В послеоперационной палате медсестра контролировала давление и состояние пациента, а врач составил план дальнейшей реабилитации.

### `medicine_vaccination`

- expected_themes: `['medicine']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `medicine` | 0.547023 | 0.673809 | 0.166667 | 1.000000 | 1 |
| 2 | `science` | 0.381065 | 0.508086 | 0.000000 | 1.000000 | 1 |
| 3 | `everyday` | 0.376856 | 0.446919 | 0.166667 | 1.000000 | 1 |
| 4 | `sports` | 0.366760 | 0.489013 | 0.000000 | 1.000000 | 1 |
| 5 | `military` | 0.358340 | 0.477787 | 0.000000 | 1.000000 | 1 |
| 6 | `it` | 0.349098 | 0.465464 | 0.000000 | 1.000000 | 1 |
| 7 | `religion` | 0.340960 | 0.454613 | 0.000000 | 1.000000 | 1 |
| 8 | `law` | 0.340519 | 0.454025 | 0.000000 | 1.000000 | 1 |
| 9 | `politics` | 0.330116 | 0.440154 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.328902 | 0.438536 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `medicine` `segment-0001` [0:192], semantic=0.6738, lexical=1: Перед сезонным ростом инфекции поликлиника организовала вакцинацию. Медицинские работники проверяли противопоказания, объясняли возможные побочные реакции и наблюдали пациентов после прививки.
- `science` `segment-0001` [0:192], semantic=0.5081, lexical=0: Перед сезонным ростом инфекции поликлиника организовала вакцинацию. Медицинские работники проверяли противопоказания, объясняли возможные побочные реакции и наблюдали пациентов после прививки.
- `everyday` `segment-0001` [0:192], semantic=0.4469, lexical=1: Перед сезонным ростом инфекции поликлиника организовала вакцинацию. Медицинские работники проверяли противопоказания, объясняли возможные побочные реакции и наблюдали пациентов после прививки.

### `medicine_trial`

- expected_themes: `['medicine', 'science']`
- V1 result: `dominant=economics; top=[economics:0.0570]`; predicted `['economics']`
- V2 predicted: `['economics', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `medicine` | 0.507187 | 0.676249 | 0.000000 | 1.000000 | 1 |
| 2 | `science` | 0.452478 | 0.603304 | 0.000000 | 1.000000 | 1 |
| 3 | `economics` | 0.380931 | 0.452353 | 0.166667 | 1.000000 | 1 |
| 4 | `it` | 0.373898 | 0.498531 | 0.000000 | 1.000000 | 1 |
| 5 | `law` | 0.363882 | 0.485176 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.355977 | 0.474636 | 0.000000 | 1.000000 | 1 |
| 7 | `sports` | 0.343026 | 0.457368 | 0.000000 | 1.000000 | 1 |
| 8 | `religion` | 0.338710 | 0.451613 | 0.000000 | 1.000000 | 1 |
| 9 | `politics` | 0.338641 | 0.451521 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.305652 | 0.407536 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `medicine` `segment-0001` [0:200], semantic=0.6762, lexical=0: В клиническом исследовании сравнивали две схемы терапии. Участникам регулярно проводили лабораторные обследования, а эффективность лекарства оценивали по заранее установленным медицинским показателям.
- `science` `segment-0001` [0:200], semantic=0.6033, lexical=0: В клиническом исследовании сравнивали две схемы терапии. Участникам регулярно проводили лабораторные обследования, а эффективность лекарства оценивали по заранее установленным медицинским показателям.
- `economics` `segment-0001` [0:200], semantic=0.4524, lexical=1: В клиническом исследовании сравнивали две схемы терапии. Участникам регулярно проводили лабораторные обследования, а эффективность лекарства оценивали по заранее установленным медицинским показателям.

### `it_server`

- expected_themes: `['it']`
- V1 result: `dominant=it; top=[it:0.0579]`; predicted `['it']`
- V2 predicted: `['economics', 'everyday', 'it', 'medicine', 'military', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `it` | 0.554195 | 0.627815 | 0.333333 | 1.000000 | 1 |
| 2 | `science` | 0.451586 | 0.491004 | 0.333333 | 1.000000 | 1 |
| 3 | `everyday` | 0.370424 | 0.438343 | 0.166667 | 1.000000 | 1 |
| 4 | `sports` | 0.345199 | 0.460265 | 0.000000 | 1.000000 | 1 |
| 5 | `religion` | 0.329933 | 0.439910 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.325454 | 0.433939 | 0.000000 | 1.000000 | 1 |
| 7 | `politics` | 0.323110 | 0.375258 | 0.166667 | 0.000000 | 0 |
| 8 | `economics` | 0.322715 | 0.430286 | 0.000000 | 1.000000 | 1 |
| 9 | `medicine` | 0.318194 | 0.424258 | 0.000000 | 1.000000 | 1 |
| 10 | `law` | 0.307239 | 0.409652 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `it` `segment-0001` [0:193], semantic=0.6278, lexical=2: После обновления сервер стал медленнее отвечать на сетевые запросы. Разработчик изучил журнал ошибок, нашел утечку памяти в коде сервиса и подготовил исправление для следующей версии программы.
- `science` `segment-0001` [0:193], semantic=0.4910, lexical=2: После обновления сервер стал медленнее отвечать на сетевые запросы. Разработчик изучил журнал ошибок, нашел утечку памяти в коде сервиса и подготовил исправление для следующей версии программы.
- `everyday` `segment-0001` [0:193], semantic=0.4383, lexical=1: После обновления сервер стал медленнее отвечать на сетевые запросы. Разработчик изучил журнал ошибок, нашел утечку памяти в коде сервиса и подготовил исправление для следующей версии программы.

### `it_database`

- expected_themes: `['it']`
- V1 result: `dominant=it; top=[it:0.0887]`; predicted `['it']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `it` | 0.600579 | 0.634105 | 0.500000 | 1.000000 | 1 |
| 2 | `economics` | 0.424567 | 0.510534 | 0.166667 | 1.000000 | 1 |
| 3 | `science` | 0.418757 | 0.558343 | 0.000000 | 1.000000 | 1 |
| 4 | `military` | 0.401003 | 0.534671 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.381436 | 0.508581 | 0.000000 | 1.000000 | 1 |
| 6 | `sports` | 0.381144 | 0.508192 | 0.000000 | 1.000000 | 1 |
| 7 | `law` | 0.373865 | 0.498487 | 0.000000 | 1.000000 | 1 |
| 8 | `everyday` | 0.369146 | 0.492195 | 0.000000 | 1.000000 | 1 |
| 9 | `politics` | 0.364126 | 0.485501 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.351247 | 0.468329 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `it` `segment-0001` [0:183], semantic=0.6341, lexical=3: Приложение хранит сведения о заказах в базе данных. Новый алгоритм группирует записи, а индекс ускоряет поиск и уменьшает нагрузку на процессор при одновременной работе пользователей.
- `economics` `segment-0001` [0:183], semantic=0.5105, lexical=1: Приложение хранит сведения о заказах в базе данных. Новый алгоритм группирует записи, а индекс ускоряет поиск и уменьшает нагрузку на процессор при одновременной работе пользователей.
- `science` `segment-0001` [0:183], semantic=0.5583, lexical=0: Приложение хранит сведения о заказах в базе данных. Новый алгоритм группирует записи, а индекс ускоряет поиск и уменьшает нагрузку на процессор при одновременной работе пользователей.

### `it_security`

- expected_themes: `['it']`
- V1 result: `dominant=it; top=[it:0.0707, science:0.0619]`; predicted `['it', 'science']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `it` | 0.668865 | 0.669598 | 0.666667 | 1.000000 | 1 |
| 2 | `science` | 0.521766 | 0.529021 | 0.500000 | 1.000000 | 1 |
| 3 | `law` | 0.419260 | 0.503457 | 0.166667 | 1.000000 | 1 |
| 4 | `sports` | 0.394860 | 0.470925 | 0.166667 | 1.000000 | 1 |
| 5 | `economics` | 0.391935 | 0.467024 | 0.166667 | 1.000000 | 1 |
| 6 | `everyday` | 0.381282 | 0.452820 | 0.166667 | 1.000000 | 1 |
| 7 | `politics` | 0.378356 | 0.448919 | 0.166667 | 1.000000 | 1 |
| 8 | `military` | 0.369090 | 0.492120 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.353952 | 0.471936 | 0.000000 | 1.000000 | 1 |
| 10 | `medicine` | 0.348925 | 0.465233 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `it` `segment-0001` [0:191], semantic=0.6696, lexical=4: Система проверяет учетные данные перед доступом к интерфейсу. Пароли сохраняются в зашифрованном виде, сетевой протокол использует защищенное соединение, а подозрительные запросы блокируются.
- `science` `segment-0001` [0:191], semantic=0.5290, lexical=3: Система проверяет учетные данные перед доступом к интерфейсу. Пароли сохраняются в зашифрованном виде, сетевой протокол использует защищенное соединение, а подозрительные запросы блокируются.
- `law` `segment-0001` [0:191], semantic=0.5035, lexical=1: Система проверяет учетные данные перед доступом к интерфейсу. Пароли сохраняются в зашифрованном виде, сетевой протокол использует защищенное соединение, а подозрительные запросы блокируются.

### `it_ml`

- expected_themes: `['it', 'science']`
- V1 result: `dominant=science; top=[science:0.0828]`; predicted `['science']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.595125 | 0.626834 | 0.500000 | 1.000000 | 1 |
| 2 | `it` | 0.543311 | 0.668859 | 0.166667 | 1.000000 | 1 |
| 3 | `medicine` | 0.405168 | 0.540224 | 0.000000 | 1.000000 | 1 |
| 4 | `economics` | 0.386629 | 0.515505 | 0.000000 | 1.000000 | 1 |
| 5 | `law` | 0.376103 | 0.501471 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.362540 | 0.483386 | 0.000000 | 1.000000 | 1 |
| 7 | `military` | 0.362291 | 0.483055 | 0.000000 | 1.000000 | 1 |
| 8 | `sports` | 0.354137 | 0.472183 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.334964 | 0.446618 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.317989 | 0.423986 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `science` `segment-0001` [0:190], semantic=0.6268, lexical=3: Исследователи подготовили набор цифровых данных и обучили модель распознавать изображения. Точность алгоритма проверили на отдельной выборке, после чего модель встроили в программный сервис.
- `it` `segment-0001` [0:190], semantic=0.6689, lexical=1: Исследователи подготовили набор цифровых данных и обучили модель распознавать изображения. Точность алгоритма проверили на отдельной выборке, после чего модель встроили в программный сервис.
- `medicine` `segment-0001` [0:190], semantic=0.5402, lexical=0: Исследователи подготовили набор цифровых данных и обучили модель распознавать изображения. Точность алгоритма проверили на отдельной выборке, после чего модель встроили в программный сервис.

### `economics_inflation`

- expected_themes: `['economics']`
- V1 result: `dominant=economics; top=[economics:0.0940]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.631961 | 0.675948 | 0.500000 | 1.000000 | 1 |
| 2 | `everyday` | 0.380526 | 0.451813 | 0.166667 | 1.000000 | 1 |
| 3 | `politics` | 0.370791 | 0.494388 | 0.000000 | 1.000000 | 1 |
| 4 | `military` | 0.343762 | 0.458349 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.340497 | 0.453996 | 0.000000 | 1.000000 | 1 |
| 6 | `sports` | 0.338247 | 0.450996 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.323993 | 0.431990 | 0.000000 | 1.000000 | 1 |
| 8 | `science` | 0.323492 | 0.431323 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.315590 | 0.420787 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.314945 | 0.419926 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `economics` `segment-0001` [0:181], semantic=0.6759, lexical=3: Рост цен ускорил инфляцию и сократил покупательную способность населения. Центральный банк повысил процентную ставку, чтобы ограничить кредитование и стабилизировать денежный рынок.
- `everyday` `segment-0001` [0:181], semantic=0.4518, lexical=1: Рост цен ускорил инфляцию и сократил покупательную способность населения. Центральный банк повысил процентную ставку, чтобы ограничить кредитование и стабилизировать денежный рынок.
- `politics` `segment-0001` [0:181], semantic=0.4944, lexical=0: Рост цен ускорил инфляцию и сократил покупательную способность населения. Центральный банк повысил процентную ставку, чтобы ограничить кредитование и стабилизировать денежный рынок.

### `economics_company`

- expected_themes: `['economics']`
- V1 result: `dominant=economics; top=[economics:0.0886]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.624951 | 0.666601 | 0.500000 | 1.000000 | 1 |
| 2 | `everyday` | 0.416100 | 0.499244 | 0.166667 | 1.000000 | 1 |
| 3 | `law` | 0.390771 | 0.465472 | 0.166667 | 1.000000 | 1 |
| 4 | `science` | 0.376640 | 0.502187 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.365945 | 0.487927 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.363952 | 0.485269 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.353575 | 0.471433 | 0.000000 | 1.000000 | 1 |
| 8 | `military` | 0.353321 | 0.471095 | 0.000000 | 1.000000 | 1 |
| 9 | `sports` | 0.338357 | 0.451142 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.322428 | 0.429904 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `economics` `segment-0001` [0:180], semantic=0.6666, lexical=3: Компания увеличила выручку от продажи продукции, но расходы на сырье тоже выросли. В финансовой отчетности прибыль оказалась ниже прогноза, поэтому руководство пересмотрело бюджет.
- `everyday` `segment-0001` [0:180], semantic=0.4992, lexical=1: Компания увеличила выручку от продажи продукции, но расходы на сырье тоже выросли. В финансовой отчетности прибыль оказалась ниже прогноза, поэтому руководство пересмотрело бюджет.
- `law` `segment-0001` [0:180], semantic=0.4655, lexical=1: Компания увеличила выручку от продажи продукции, но расходы на сырье тоже выросли. В финансовой отчетности прибыль оказалась ниже прогноза, поэтому руководство пересмотрело бюджет.

### `economics_investment`

- expected_themes: `['economics']`
- V1 result: `dominant=economics; top=[economics:0.1074]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.678553 | 0.682515 | 0.666667 | 1.000000 | 1 |
| 2 | `politics` | 0.395982 | 0.472420 | 0.166667 | 1.000000 | 1 |
| 3 | `medicine` | 0.383466 | 0.455732 | 0.166667 | 1.000000 | 1 |
| 4 | `law` | 0.378997 | 0.505329 | 0.000000 | 1.000000 | 1 |
| 5 | `it` | 0.364225 | 0.485633 | 0.000000 | 1.000000 | 1 |
| 6 | `science` | 0.359389 | 0.479185 | 0.000000 | 1.000000 | 1 |
| 7 | `military` | 0.358918 | 0.478558 | 0.000000 | 1.000000 | 1 |
| 8 | `everyday` | 0.351985 | 0.469313 | 0.000000 | 1.000000 | 1 |
| 9 | `sports` | 0.346867 | 0.462489 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.313596 | 0.418128 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `economics` `segment-0001` [0:147], semantic=0.6825, lexical=4: Инвестор распределил капитал между акциями и облигациями. Перед покупкой ценных бумаг он оценил доходность, биржевой курс и риск возможных убытков.
- `politics` `segment-0001` [0:147], semantic=0.4724, lexical=1: Инвестор распределил капитал между акциями и облигациями. Перед покупкой ценных бумаг он оценил доходность, биржевой курс и риск возможных убытков.
- `medicine` `segment-0001` [0:147], semantic=0.4557, lexical=1: Инвестор распределил капитал между акциями и облигациями. Перед покупкой ценных бумаг он оценил доходность, биржевой курс и риск возможных убытков.

### `economics_trade`

- expected_themes: `['economics']`
- V1 result: `dominant=economics; top=[economics:0.0698]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'medicine', 'military', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.610003 | 0.646671 | 0.500000 | 1.000000 | 1 |
| 2 | `everyday` | 0.404676 | 0.484013 | 0.166667 | 1.000000 | 1 |
| 3 | `politics` | 0.378685 | 0.449358 | 0.166667 | 1.000000 | 1 |
| 4 | `law` | 0.353151 | 0.415312 | 0.166667 | 0.000000 | 0 |
| 5 | `science` | 0.345031 | 0.460042 | 0.000000 | 1.000000 | 1 |
| 6 | `medicine` | 0.344351 | 0.459135 | 0.000000 | 1.000000 | 1 |
| 7 | `military` | 0.340792 | 0.454390 | 0.000000 | 1.000000 | 1 |
| 8 | `it` | 0.330245 | 0.440327 | 0.000000 | 1.000000 | 1 |
| 9 | `sports` | 0.326243 | 0.434991 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.281344 | 0.375125 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `economics` `segment-0001` [0:170], semantic=0.6467, lexical=3: Экспорт товаров вырос после изменения валютного курса. Производители расширили поставки на внешний рынок, тогда как стоимость импортного оборудования заметно увеличилась.
- `everyday` `segment-0001` [0:170], semantic=0.4840, lexical=1: Экспорт товаров вырос после изменения валютного курса. Производители расширили поставки на внешний рынок, тогда как стоимость импортного оборудования заметно увеличилась.
- `politics` `segment-0001` [0:170], semantic=0.4494, lexical=1: Экспорт товаров вырос после изменения валютного курса. Производители расширили поставки на внешний рынок, тогда как стоимость импортного оборудования заметно увеличилась.

### `military_defense`

- expected_themes: `['military']`
- V1 result: `dominant=military; top=[military:0.1019]`; predicted `['military']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `military` | 0.723353 | 0.686693 | 0.833333 | 1.000000 | 1 |
| 2 | `sports` | 0.456802 | 0.609069 | 0.000000 | 1.000000 | 1 |
| 3 | `law` | 0.408950 | 0.489711 | 0.166667 | 1.000000 | 1 |
| 4 | `medicine` | 0.382050 | 0.509400 | 0.000000 | 1.000000 | 1 |
| 5 | `politics` | 0.380650 | 0.507533 | 0.000000 | 1.000000 | 1 |
| 6 | `it` | 0.377325 | 0.503100 | 0.000000 | 1.000000 | 1 |
| 7 | `science` | 0.375202 | 0.500269 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.363726 | 0.429413 | 0.166667 | 1.000000 | 1 |
| 9 | `religion` | 0.347460 | 0.463280 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.336378 | 0.448504 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `military` `segment-0001` [0:180], semantic=0.6867, lexical=5: Подразделение заняло оборонительные позиции и оборудовало траншеи. Командир передал приказ усилить наблюдение, а расчет артиллерии подготовил боеприпасы на случай атаки противника.
- `sports` `segment-0001` [0:180], semantic=0.6091, lexical=0: Подразделение заняло оборонительные позиции и оборудовало траншеи. Командир передал приказ усилить наблюдение, а расчет артиллерии подготовил боеприпасы на случай атаки противника.
- `law` `segment-0001` [0:180], semantic=0.4897, lexical=1: Подразделение заняло оборонительные позиции и оборудовало траншеи. Командир передал приказ усилить наблюдение, а расчет артиллерии подготовил боеприпасы на случай атаки противника.

### `military_training`

- expected_themes: `['military']`
- V1 result: `dominant=military; top=[military:0.0682]`; predicted `['military']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `military` | 0.629738 | 0.672984 | 0.500000 | 1.000000 | 1 |
| 2 | `sports` | 0.525770 | 0.589916 | 0.333333 | 1.000000 | 1 |
| 3 | `it` | 0.383576 | 0.511434 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.380580 | 0.507440 | 0.000000 | 1.000000 | 1 |
| 5 | `science` | 0.376957 | 0.502609 | 0.000000 | 1.000000 | 1 |
| 6 | `law` | 0.367182 | 0.489576 | 0.000000 | 1.000000 | 1 |
| 7 | `politics` | 0.364247 | 0.485663 | 0.000000 | 1.000000 | 1 |
| 8 | `everyday` | 0.357132 | 0.476176 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.335609 | 0.447479 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.332616 | 0.443488 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `military` `segment-0001` [0:168], semantic=0.6730, lexical=3: На полигоне военнослужащие отрабатывали взаимодействие взвода с бронемашинами. После стрельбы офицер разобрал ошибки личного состава и уточнил задачи следующего учения.
- `sports` `segment-0001` [0:168], semantic=0.5899, lexical=2: На полигоне военнослужащие отрабатывали взаимодействие взвода с бронемашинами. После стрельбы офицер разобрал ошибки личного состава и уточнил задачи следующего учения.
- `it` `segment-0001` [0:168], semantic=0.5114, lexical=0: На полигоне военнослужащие отрабатывали взаимодействие взвода с бронемашинами. После стрельбы офицер разобрал ошибки личного состава и уточнил задачи следующего учения.

### `military_logistics`

- expected_themes: `['military']`
- V1 result: `dominant=military; top=[military:0.0682]`; predicted `['military']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `military` | 0.653288 | 0.704384 | 0.500000 | 1.000000 | 1 |
| 2 | `sports` | 0.437111 | 0.582814 | 0.000000 | 1.000000 | 1 |
| 3 | `medicine` | 0.423577 | 0.509214 | 0.166667 | 1.000000 | 1 |
| 4 | `politics` | 0.417556 | 0.501186 | 0.166667 | 1.000000 | 1 |
| 5 | `it` | 0.379173 | 0.505564 | 0.000000 | 1.000000 | 1 |
| 6 | `economics` | 0.368337 | 0.491116 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.353240 | 0.470987 | 0.000000 | 1.000000 | 1 |
| 8 | `science` | 0.349017 | 0.465356 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.341660 | 0.455547 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.331127 | 0.441503 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `military` `segment-0001` [0:178], semantic=0.7044, lexical=3: Штаб организовал снабжение частей топливом, продовольствием и боеприпасами. Колонна военной техники прибыла в район операции, после чего командование провело перегруппировку сил.
- `sports` `segment-0001` [0:178], semantic=0.5828, lexical=0: Штаб организовал снабжение частей топливом, продовольствием и боеприпасами. Колонна военной техники прибыла в район операции, после чего командование провело перегруппировку сил.
- `medicine` `segment-0001` [0:178], semantic=0.5092, lexical=1: Штаб организовал снабжение частей топливом, продовольствием и боеприпасами. Колонна военной техники прибыла в район операции, после чего командование провело перегруппировку сил.

### `military_evacuation`

- expected_themes: `['medicine', 'military']`
- V1 result: `dominant=military; top=[military:0.0828]`; predicted `['military']`
- V2 predicted: `['everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `military` | 0.645158 | 0.637989 | 0.666667 | 1.000000 | 1 |
| 2 | `sports` | 0.450667 | 0.545334 | 0.166667 | 1.000000 | 1 |
| 3 | `medicine` | 0.441361 | 0.588481 | 0.000000 | 1.000000 | 1 |
| 4 | `politics` | 0.380001 | 0.451112 | 0.166667 | 1.000000 | 1 |
| 5 | `religion` | 0.356634 | 0.475512 | 0.000000 | 1.000000 | 1 |
| 6 | `it` | 0.337736 | 0.450315 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.337458 | 0.449944 | 0.000000 | 1.000000 | 1 |
| 8 | `science` | 0.327434 | 0.436578 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.320950 | 0.427933 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.302805 | 0.403740 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `military` `segment-0001` [0:154], semantic=0.6380, lexical=4: После обстрела санитарная группа эвакуировала раненых с боевой позиции. Военные медики оказали первую помощь и доставили пострадавших в полевой госпиталь.
- `sports` `segment-0001` [0:154], semantic=0.5453, lexical=1: После обстрела санитарная группа эвакуировала раненых с боевой позиции. Военные медики оказали первую помощь и доставили пострадавших в полевой госпиталь.
- `medicine` `segment-0001` [0:154], semantic=0.5885, lexical=0: После обстрела санитарная группа эвакуировала раненых с боевой позиции. Военные медики оказали первую помощь и доставили пострадавших в полевой госпиталь.

### `science_experiment`

- expected_themes: `['science']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.574666 | 0.710666 | 0.166667 | 1.000000 | 1 |
| 2 | `medicine` | 0.493572 | 0.658096 | 0.000000 | 1.000000 | 1 |
| 3 | `military` | 0.431477 | 0.519747 | 0.166667 | 1.000000 | 1 |
| 4 | `it` | 0.429934 | 0.573245 | 0.000000 | 1.000000 | 1 |
| 5 | `sports` | 0.414319 | 0.496869 | 0.166667 | 1.000000 | 1 |
| 6 | `politics` | 0.384096 | 0.456573 | 0.166667 | 1.000000 | 1 |
| 7 | `law` | 0.381699 | 0.508932 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.344266 | 0.459022 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.325760 | 0.434347 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.295075 | 0.393434 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `science` `segment-0001` [0:173], semantic=0.7107, lexical=1: Исследователи сформулировали гипотезу и провели серию лабораторных экспериментов. Полученные измерения обработали статистически, а результаты сравнили с контрольной группой.
- `medicine` `segment-0001` [0:173], semantic=0.6581, lexical=0: Исследователи сформулировали гипотезу и провели серию лабораторных экспериментов. Полученные измерения обработали статистически, а результаты сравнили с контрольной группой.
- `military` `segment-0001` [0:173], semantic=0.5197, lexical=1: Исследователи сформулировали гипотезу и провели серию лабораторных экспериментов. Полученные измерения обработали статистически, а результаты сравнили с контрольной группой.

### `science_article`

- expected_themes: `['science']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.578822 | 0.716207 | 0.166667 | 1.000000 | 1 |
| 2 | `medicine` | 0.465647 | 0.565307 | 0.166667 | 1.000000 | 1 |
| 3 | `it` | 0.422766 | 0.563688 | 0.000000 | 1.000000 | 1 |
| 4 | `law` | 0.420633 | 0.560844 | 0.000000 | 1.000000 | 1 |
| 5 | `sports` | 0.389872 | 0.464273 | 0.166667 | 1.000000 | 1 |
| 6 | `military` | 0.375853 | 0.501137 | 0.000000 | 1.000000 | 1 |
| 7 | `politics` | 0.369451 | 0.492602 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.361139 | 0.481518 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.357231 | 0.476308 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.304120 | 0.405493 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `science` `segment-0001` [0:170], semantic=0.7162, lexical=1: В научной статье автор описал методику, состав выборки и ограничения исследования. Рецензенты попросили уточнить анализ данных и привести ссылки на предыдущие публикации.
- `medicine` `segment-0001` [0:170], semantic=0.5653, lexical=1: В научной статье автор описал методику, состав выборки и ограничения исследования. Рецензенты попросили уточнить анализ данных и привести ссылки на предыдущие публикации.
- `it` `segment-0001` [0:170], semantic=0.5637, lexical=0: В научной статье автор описал методику, состав выборки и ограничения исследования. Рецензенты попросили уточнить анализ данных и привести ссылки на предыдущие публикации.

### `science_biology`

- expected_themes: `['science']`
- V1 result: `dominant=science; top=[science:0.0531]`; predicted `['science']`
- V2 predicted: `['economics', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.595155 | 0.682429 | 0.333333 | 1.000000 | 1 |
| 2 | `medicine` | 0.472978 | 0.630637 | 0.000000 | 1.000000 | 1 |
| 3 | `it` | 0.401991 | 0.535988 | 0.000000 | 1.000000 | 1 |
| 4 | `sports` | 0.384354 | 0.456916 | 0.166667 | 1.000000 | 1 |
| 5 | `law` | 0.384012 | 0.456460 | 0.166667 | 1.000000 | 1 |
| 6 | `military` | 0.366611 | 0.488815 | 0.000000 | 1.000000 | 1 |
| 7 | `economics` | 0.349006 | 0.465342 | 0.000000 | 1.000000 | 1 |
| 8 | `politics` | 0.337592 | 0.450123 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.335956 | 0.447941 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.298550 | 0.398067 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `science` `segment-0001` [0:161], semantic=0.6824, lexical=2: В лаборатории наблюдали деление клеток под микроскопом. Биологи измеряли скорость реакции организмов на изменение среды и проверяли воспроизводимость результата.
- `medicine` `segment-0001` [0:161], semantic=0.6306, lexical=0: В лаборатории наблюдали деление клеток под микроскопом. Биологи измеряли скорость реакции организмов на изменение среды и проверяли воспроизводимость результата.
- `it` `segment-0001` [0:161], semantic=0.5360, lexical=0: В лаборатории наблюдали деление клеток под микроскопом. Биологи измеряли скорость реакции организмов на изменение среды и проверяли воспроизводимость результата.

### `science_linguistics`

- expected_themes: `['science']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.501007 | 0.612454 | 0.166667 | 1.000000 | 1 |
| 2 | `it` | 0.435224 | 0.524743 | 0.166667 | 1.000000 | 1 |
| 3 | `law` | 0.411908 | 0.493655 | 0.166667 | 1.000000 | 1 |
| 4 | `religion` | 0.373888 | 0.498517 | 0.000000 | 1.000000 | 1 |
| 5 | `sports` | 0.344706 | 0.459608 | 0.000000 | 1.000000 | 1 |
| 6 | `everyday` | 0.336920 | 0.449227 | 0.000000 | 1.000000 | 1 |
| 7 | `medicine` | 0.331946 | 0.442594 | 0.000000 | 1.000000 | 1 |
| 8 | `military` | 0.330373 | 0.440498 | 0.000000 | 1.000000 | 1 |
| 9 | `politics` | 0.328719 | 0.438292 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.325279 | 0.433705 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `science` `segment-0001` [0:163], semantic=0.6125, lexical=1: Лингвисты изучили употребление слов в большом корпусе текстов. Частоты сравнили между жанрами, после чего исследователи предложили модель изменения языковой нормы.
- `it` `segment-0001` [0:163], semantic=0.5247, lexical=1: Лингвисты изучили употребление слов в большом корпусе текстов. Частоты сравнили между жанрами, после чего исследователи предложили модель изменения языковой нормы.
- `law` `segment-0001` [0:163], semantic=0.4937, lexical=1: Лингвисты изучили употребление слов в большом корпусе текстов. Частоты сравнили между жанрами, после чего исследователи предложили модель изменения языковой нормы.

### `religion_service`

- expected_themes: `['religion']`
- V1 result: `dominant=sports; top=[sports:0.0516]`; predicted `['sports']`
- V2 predicted: `['everyday', 'medicine', 'religion', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `religion` | 0.588152 | 0.728647 | 0.166667 | 1.000000 | 1 |
| 2 | `everyday` | 0.359133 | 0.423288 | 0.166667 | 1.000000 | 1 |
| 3 | `sports` | 0.339841 | 0.342010 | 0.333333 | 1.000000 | 1 |
| 4 | `medicine` | 0.315351 | 0.420468 | 0.000000 | 1.000000 | 1 |
| 5 | `law` | 0.275980 | 0.367973 | 0.000000 | 0.000000 | 0 |
| 6 | `military` | 0.270877 | 0.361170 | 0.000000 | 0.000000 | 0 |
| 7 | `science` | 0.268253 | 0.357670 | 0.000000 | 0.000000 | 0 |
| 8 | `it` | 0.267551 | 0.356734 | 0.000000 | 0.000000 | 0 |
| 9 | `politics` | 0.263288 | 0.351050 | 0.000000 | 0.000000 | 0 |
| 10 | `economics` | 0.254354 | 0.339139 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `religion` `segment-0001` [0:164], semantic=0.7286, lexical=1: Во время богослужения священник прочитал молитву и обратился к прихожанам с проповедью. Верующие поставили свечи перед иконами и приняли участие в церковном обряде.
- `everyday` `segment-0001` [0:164], semantic=0.4233, lexical=1: Во время богослужения священник прочитал молитву и обратился к прихожанам с проповедью. Верующие поставили свечи перед иконами и приняли участие в церковном обряде.
- `sports` `segment-0001` [0:164], semantic=0.3420, lexical=2: Во время богослужения священник прочитал молитву и обратился к прихожанам с проповедью. Верующие поставили свечи перед иконами и приняли участие в церковном обряде.

### `religion_pilgrimage`

- expected_themes: `['religion']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['everyday', 'medicine', 'military', 'politics', 'religion', 'science']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `religion` | 0.578665 | 0.715997 | 0.166667 | 1.000000 | 1 |
| 2 | `everyday` | 0.373918 | 0.498558 | 0.000000 | 1.000000 | 1 |
| 3 | `science` | 0.362138 | 0.482850 | 0.000000 | 1.000000 | 1 |
| 4 | `politics` | 0.345752 | 0.461003 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.318795 | 0.425060 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.317057 | 0.422743 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.309458 | 0.412611 | 0.000000 | 0.000000 | 0 |
| 8 | `economics` | 0.307600 | 0.410133 | 0.000000 | 0.000000 | 0 |
| 9 | `law` | 0.300231 | 0.400308 | 0.000000 | 0.000000 | 0 |
| 10 | `sports` | 0.280222 | 0.373629 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `religion` `segment-0001` [0:143], semantic=0.7160, lexical=1: Паломники отправились к древнему монастырю, чтобы поклониться святыне. По дороге они обсуждали веру, духовную жизнь и историю церковной общины.
- `everyday` `segment-0001` [0:143], semantic=0.4986, lexical=0: Паломники отправились к древнему монастырю, чтобы поклониться святыне. По дороге они обсуждали веру, духовную жизнь и историю церковной общины.
- `science` `segment-0001` [0:143], semantic=0.4829, lexical=0: Паломники отправились к древнему монастырю, чтобы поклониться святыне. По дороге они обсуждали веру, духовную жизнь и историю церковной общины.

### `religion_ethics`

- expected_themes: `['religion']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `religion` | 0.509199 | 0.623377 | 0.166667 | 1.000000 | 1 |
| 2 | `law` | 0.435549 | 0.525176 | 0.166667 | 1.000000 | 1 |
| 3 | `politics` | 0.416690 | 0.555587 | 0.000000 | 1.000000 | 1 |
| 4 | `everyday` | 0.400582 | 0.534109 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.382283 | 0.509711 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.379478 | 0.505971 | 0.000000 | 1.000000 | 1 |
| 7 | `science` | 0.363386 | 0.484515 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.361063 | 0.481417 | 0.000000 | 1.000000 | 1 |
| 9 | `sports` | 0.360722 | 0.480962 | 0.000000 | 1.000000 | 1 |
| 10 | `it` | 0.340706 | 0.454275 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `religion` `segment-0001` [0:174], semantic=0.6234, lexical=1: На встрече говорили о заповедях, покаянии и нравственном выборе человека. Настоятель объяснил, почему помощь нуждающимся считается частью служения и духовной ответственности.
- `law` `segment-0001` [0:174], semantic=0.5252, lexical=1: На встрече говорили о заповедях, покаянии и нравственном выборе человека. Настоятель объяснил, почему помощь нуждающимся считается частью служения и духовной ответственности.
- `politics` `segment-0001` [0:174], semantic=0.5556, lexical=0: На встрече говорили о заповедях, покаянии и нравственном выборе человека. Настоятель объяснил, почему помощь нуждающимся считается частью служения и духовной ответственности.

### `religion_holiday`

- expected_themes: `['religion']`
- V1 result: `dominant=religion; top=[religion:0.0557]`; predicted `['religion']`
- V2 predicted: `['economics', 'everyday', 'medicine', 'military', 'politics', 'religion', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `religion` | 0.584993 | 0.668879 | 0.333333 | 1.000000 | 1 |
| 2 | `everyday` | 0.420391 | 0.504966 | 0.166667 | 1.000000 | 1 |
| 3 | `politics` | 0.344126 | 0.458835 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.334867 | 0.446489 | 0.000000 | 1.000000 | 1 |
| 5 | `economics` | 0.330130 | 0.440173 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.328342 | 0.437789 | 0.000000 | 1.000000 | 1 |
| 7 | `sports` | 0.326842 | 0.435789 | 0.000000 | 1.000000 | 1 |
| 8 | `it` | 0.305018 | 0.406691 | 0.000000 | 0.000000 | 0 |
| 9 | `science` | 0.296440 | 0.395254 | 0.000000 | 0.000000 | 0 |
| 10 | `law` | 0.289204 | 0.385606 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `religion` `segment-0001` [0:171], semantic=0.6689, lexical=2: Приход готовился к большому религиозному празднику. Семьи соблюдали пост, дети изучали церковные традиции, а волонтеры собирали пожертвования для благотворительной помощи.
- `everyday` `segment-0001` [0:171], semantic=0.5050, lexical=1: Приход готовился к большому религиозному празднику. Семьи соблюдали пост, дети изучали церковные традиции, а волонтеры собирали пожертвования для благотворительной помощи.
- `politics` `segment-0001` [0:171], semantic=0.4588, lexical=0: Приход готовился к большому религиозному празднику. Семьи соблюдали пост, дети изучали церковные традиции, а волонтеры собирали пожертвования для благотворительной помощи.

### `politics_election`

- expected_themes: `['politics']`
- V1 result: `dominant=politics; top=[politics:0.0711]`; predicted `['politics']`
- V2 predicted: `['economics', 'it', 'law', 'medicine', 'military', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `politics` | 0.599746 | 0.688550 | 0.333333 | 1.000000 | 1 |
| 2 | `science` | 0.405728 | 0.485415 | 0.166667 | 1.000000 | 1 |
| 3 | `sports` | 0.373022 | 0.497363 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.352129 | 0.469505 | 0.000000 | 1.000000 | 1 |
| 5 | `it` | 0.330622 | 0.440829 | 0.000000 | 1.000000 | 1 |
| 6 | `law` | 0.329770 | 0.439694 | 0.000000 | 1.000000 | 1 |
| 7 | `military` | 0.323110 | 0.430814 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.319205 | 0.425607 | 0.000000 | 1.000000 | 1 |
| 9 | `everyday` | 0.285796 | 0.381061 | 0.000000 | 0.000000 | 0 |
| 10 | `religion` | 0.282258 | 0.376344 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `politics` `segment-0001` [0:162], semantic=0.6885, lexical=2: Кандидаты начали предвыборную кампанию и представили программы избирателям. После голосования комиссия подсчитала бюллетени, а партия обсудила результаты выборов.
- `science` `segment-0001` [0:162], semantic=0.4854, lexical=1: Кандидаты начали предвыборную кампанию и представили программы избирателям. После голосования комиссия подсчитала бюллетени, а партия обсудила результаты выборов.
- `sports` `segment-0001` [0:162], semantic=0.4974, lexical=0: Кандидаты начали предвыборную кампанию и представили программы избирателям. После голосования комиссия подсчитала бюллетени, а партия обсудила результаты выборов.

### `politics_parliament`

- expected_themes: `['law', 'politics']`
- V1 result: `dominant=politics; top=[politics:0.0711]`; predicted `['politics']`
- V2 predicted: `['law', 'politics', 'science']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `politics` | 0.559392 | 0.634745 | 0.333333 | 1.000000 | 1 |
| 2 | `law` | 0.372118 | 0.496157 | 0.000000 | 1.000000 | 1 |
| 3 | `sports` | 0.333057 | 0.388520 | 0.166667 | 0.000000 | 0 |
| 4 | `science` | 0.322631 | 0.430175 | 0.000000 | 1.000000 | 1 |
| 5 | `everyday` | 0.306815 | 0.409087 | 0.000000 | 0.000000 | 0 |
| 6 | `economics` | 0.301891 | 0.402522 | 0.000000 | 0.000000 | 0 |
| 7 | `medicine` | 0.287725 | 0.383633 | 0.000000 | 0.000000 | 0 |
| 8 | `military` | 0.278948 | 0.371930 | 0.000000 | 0.000000 | 0 |
| 9 | `it` | 0.272846 | 0.363795 | 0.000000 | 0.000000 | 0 |
| 10 | `religion` | 0.267160 | 0.356213 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `politics` `segment-0001` [0:150], semantic=0.6347, lexical=2: Депутаты провели парламентские дебаты о государственной реформе. Министр ответил на вопросы оппозиции, после чего законопроект вынесли на голосование.
- `law` `segment-0001` [0:150], semantic=0.4962, lexical=0: Депутаты провели парламентские дебаты о государственной реформе. Министр ответил на вопросы оппозиции, после чего законопроект вынесли на голосование.
- `sports` `segment-0001` [0:150], semantic=0.3885, lexical=1: Депутаты провели парламентские дебаты о государственной реформе. Министр ответил на вопросы оппозиции, после чего законопроект вынесли на голосование.

### `politics_diplomacy`

- expected_themes: `['politics']`
- V1 result: `dominant=law; top=[law:0.0531]`; predicted `['law']`
- V2 predicted: `['economics', 'everyday', 'law', 'politics', 'religion']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `politics` | 0.504116 | 0.672155 | 0.000000 | 1.000000 | 1 |
| 2 | `law` | 0.384401 | 0.456979 | 0.166667 | 1.000000 | 1 |
| 3 | `everyday` | 0.350942 | 0.467922 | 0.000000 | 1.000000 | 1 |
| 4 | `economics` | 0.330238 | 0.440317 | 0.000000 | 1.000000 | 1 |
| 5 | `religion` | 0.328783 | 0.438377 | 0.000000 | 1.000000 | 1 |
| 6 | `science` | 0.308223 | 0.410964 | 0.000000 | 0.000000 | 0 |
| 7 | `military` | 0.300731 | 0.400975 | 0.000000 | 0.000000 | 0 |
| 8 | `it` | 0.300238 | 0.400317 | 0.000000 | 0.000000 | 0 |
| 9 | `sports` | 0.295513 | 0.394018 | 0.000000 | 0.000000 | 0 |
| 10 | `medicine` | 0.280041 | 0.373388 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `politics` `segment-0001` [0:156], semantic=0.6722, lexical=0: Президенты двух государств встретились для международных переговоров. Стороны обсудили внешнюю политику, дипломатические отношения и условия отмены санкций.
- `law` `segment-0001` [0:156], semantic=0.4570, lexical=1: Президенты двух государств встретились для международных переговоров. Стороны обсудили внешнюю политику, дипломатические отношения и условия отмены санкций.
- `everyday` `segment-0001` [0:156], semantic=0.4679, lexical=0: Президенты двух государств встретились для международных переговоров. Стороны обсудили внешнюю политику, дипломатические отношения и условия отмены санкций.

### `politics_protest`

- expected_themes: `['politics']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `politics` | 0.525539 | 0.645163 | 0.166667 | 1.000000 | 1 |
| 2 | `law` | 0.416349 | 0.499576 | 0.166667 | 1.000000 | 1 |
| 3 | `economics` | 0.351827 | 0.469103 | 0.000000 | 1.000000 | 1 |
| 4 | `military` | 0.342310 | 0.456414 | 0.000000 | 1.000000 | 1 |
| 5 | `sports` | 0.332579 | 0.443439 | 0.000000 | 1.000000 | 1 |
| 6 | `science` | 0.331173 | 0.441564 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.318731 | 0.424975 | 0.000000 | 1.000000 | 1 |
| 8 | `medicine` | 0.318451 | 0.424602 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.317617 | 0.423489 | 0.000000 | 1.000000 | 1 |
| 10 | `it` | 0.275992 | 0.367989 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `politics` `segment-0001` [0:181], semantic=0.6452, lexical=1: Участники общественного протеста потребовали от правительства изменить решение. Представители оппозиции выступили на площади и призвали граждан участвовать в политической дискуссии.
- `law` `segment-0001` [0:181], semantic=0.4996, lexical=1: Участники общественного протеста потребовали от правительства изменить решение. Представители оппозиции выступили на площади и призвали граждан участвовать в политической дискуссии.
- `economics` `segment-0001` [0:181], semantic=0.4691, lexical=0: Участники общественного протеста потребовали от правительства изменить решение. Представители оппозиции выступили на площади и призвали граждан участвовать в политической дискуссии.

### `sports_football`

- expected_themes: `['sports']`
- V1 result: `dominant=sports; top=[sports:0.1153]`; predicted `['sports']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `sports` | 0.736429 | 0.648572 | 1.000000 | 1.000000 | 1 |
| 2 | `military` | 0.452788 | 0.603717 | 0.000000 | 1.000000 | 1 |
| 3 | `everyday` | 0.385602 | 0.458581 | 0.166667 | 1.000000 | 1 |
| 4 | `economics` | 0.381440 | 0.453031 | 0.166667 | 1.000000 | 1 |
| 5 | `politics` | 0.353318 | 0.471090 | 0.000000 | 1.000000 | 1 |
| 6 | `medicine` | 0.353041 | 0.470721 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.335507 | 0.447343 | 0.000000 | 1.000000 | 1 |
| 8 | `law` | 0.330253 | 0.440337 | 0.000000 | 1.000000 | 1 |
| 9 | `science` | 0.318656 | 0.424875 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.318601 | 0.424801 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `sports` `segment-0001` [0:155], semantic=0.6486, lexical=6: Футбольная команда начала матч с активного нападения. Нападающий забил гол после передачи, а во втором тайме тренер усилил защиту и сохранил победный счет.
- `military` `segment-0001` [0:155], semantic=0.6037, lexical=0: Футбольная команда начала матч с активного нападения. Нападающий забил гол после передачи, а во втором тайме тренер усилил защиту и сохранил победный счет.
- `everyday` `segment-0001` [0:155], semantic=0.4586, lexical=1: Футбольная команда начала матч с активного нападения. Нападающий забил гол после передачи, а во втором тайме тренер усилил защиту и сохранил победный счет.

### `sports_training`

- expected_themes: `['sports']`
- V1 result: `dominant=sports; top=[sports:0.0956]`; predicted `['sports']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `sports` | 0.665166 | 0.664666 | 0.666667 | 1.000000 | 1 |
| 2 | `military` | 0.428933 | 0.571911 | 0.000000 | 1.000000 | 1 |
| 3 | `it` | 0.389246 | 0.463439 | 0.166667 | 1.000000 | 1 |
| 4 | `economics` | 0.388171 | 0.462006 | 0.166667 | 1.000000 | 1 |
| 5 | `law` | 0.377888 | 0.448295 | 0.166667 | 1.000000 | 1 |
| 6 | `medicine` | 0.377355 | 0.503140 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.369811 | 0.493081 | 0.000000 | 1.000000 | 1 |
| 8 | `science` | 0.355230 | 0.473640 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.339587 | 0.452783 | 0.000000 | 1.000000 | 1 |
| 10 | `politics` | 0.338966 | 0.451954 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `sports` `segment-0001` [0:172], semantic=0.6647, lexical=4: Спортсмен готовился к чемпионату и ежедневно увеличивал нагрузку. Тренер следил за выносливостью, корректировал технику и оставлял время на восстановление после тренировки.
- `military` `segment-0001` [0:172], semantic=0.5719, lexical=0: Спортсмен готовился к чемпионату и ежедневно увеличивал нагрузку. Тренер следил за выносливостью, корректировал технику и оставлял время на восстановление после тренировки.
- `it` `segment-0001` [0:172], semantic=0.4634, lexical=1: Спортсмен готовился к чемпионату и ежедневно увеличивал нагрузку. Тренер следил за выносливостью, корректировал технику и оставлял время на восстановление после тренировки.

### `sports_hockey`

- expected_themes: `['sports']`
- V1 result: `dominant=sports; top=[sports:0.1185]`; predicted `['sports']`
- V2 predicted: `['economics', 'everyday', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `sports` | 0.748907 | 0.665209 | 1.000000 | 1.000000 | 1 |
| 2 | `law` | 0.442504 | 0.478895 | 0.333333 | 1.000000 | 1 |
| 3 | `military` | 0.391261 | 0.521681 | 0.000000 | 1.000000 | 1 |
| 4 | `everyday` | 0.373403 | 0.497871 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.362808 | 0.428189 | 0.166667 | 1.000000 | 1 |
| 6 | `science` | 0.341312 | 0.455083 | 0.000000 | 1.000000 | 1 |
| 7 | `religion` | 0.335630 | 0.447506 | 0.000000 | 1.000000 | 1 |
| 8 | `politics` | 0.332543 | 0.443391 | 0.000000 | 1.000000 | 1 |
| 9 | `economics` | 0.328879 | 0.438505 | 0.000000 | 1.000000 | 1 |
| 10 | `it` | 0.301209 | 0.401612 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `sports` `segment-0001` [0:163], semantic=0.6652, lexical=6: Хоккейный клуб выиграл встречу на домашней арене. Вратарь отразил опасный бросок, судья удалил игрока за нарушение, а болельщики праздновали выход команды в финал.
- `law` `segment-0001` [0:163], semantic=0.4789, lexical=2: Хоккейный клуб выиграл встречу на домашней арене. Вратарь отразил опасный бросок, судья удалил игрока за нарушение, а болельщики праздновали выход команды в финал.
- `military` `segment-0001` [0:163], semantic=0.5217, lexical=0: Хоккейный клуб выиграл встречу на домашней арене. Вратарь отразил опасный бросок, судья удалил игрока за нарушение, а болельщики праздновали выход команды в финал.

### `sports_injury`

- expected_themes: `['medicine', 'sports']`
- V1 result: `dominant=sports; top=[sports:0.0805]`; predicted `['sports']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `sports` | 0.615015 | 0.653353 | 0.500000 | 1.000000 | 1 |
| 2 | `medicine` | 0.488695 | 0.596038 | 0.166667 | 1.000000 | 1 |
| 3 | `everyday` | 0.414484 | 0.497090 | 0.166667 | 1.000000 | 1 |
| 4 | `science` | 0.404398 | 0.483642 | 0.166667 | 1.000000 | 1 |
| 5 | `military` | 0.392982 | 0.523976 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.340798 | 0.454397 | 0.000000 | 1.000000 | 1 |
| 7 | `law` | 0.339020 | 0.452027 | 0.000000 | 1.000000 | 1 |
| 8 | `religion` | 0.334493 | 0.445991 | 0.000000 | 1.000000 | 1 |
| 9 | `it` | 0.332423 | 0.443230 | 0.000000 | 1.000000 | 1 |
| 10 | `economics` | 0.323620 | 0.431493 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `sports` `segment-0001` [0:153], semantic=0.6534, lexical=3: Бегун получил травму во время соревнования и не завершил дистанцию. Врач осмотрел спортсмена, после чего тренер изменил график подготовки и реабилитации.
- `medicine` `segment-0001` [0:153], semantic=0.5960, lexical=1: Бегун получил травму во время соревнования и не завершил дистанцию. Врач осмотрел спортсмена, после чего тренер изменил график подготовки и реабилитации.
- `everyday` `segment-0001` [0:153], semantic=0.4971, lexical=1: Бегун получил травму во время соревнования и не завершил дистанцию. Врач осмотрел спортсмена, после чего тренер изменил график подготовки и реабилитации.

### `everyday_shopping`

- expected_themes: `['everyday']`
- V1 result: `dominant=everyday; top=[everyday:0.0729]`; predicted `['everyday']`
- V2 predicted: `['economics', 'everyday', 'religion']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `everyday` | 0.592558 | 0.623411 | 0.500000 | 1.000000 | 1 |
| 2 | `religion` | 0.360269 | 0.480359 | 0.000000 | 1.000000 | 1 |
| 3 | `economics` | 0.341483 | 0.455311 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.313837 | 0.418449 | 0.000000 | 0.000000 | 0 |
| 5 | `sports` | 0.297644 | 0.396859 | 0.000000 | 0.000000 | 0 |
| 6 | `law` | 0.289988 | 0.386651 | 0.000000 | 0.000000 | 0 |
| 7 | `military` | 0.285106 | 0.380142 | 0.000000 | 0.000000 | 0 |
| 8 | `science` | 0.279121 | 0.372161 | 0.000000 | 0.000000 | 0 |
| 9 | `politics` | 0.275913 | 0.367884 | 0.000000 | 0.000000 | 0 |
| 10 | `it` | 0.275202 | 0.366936 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `everyday` `segment-0001` [0:115], semantic=0.6234, lexical=3: После работы семья зашла в магазин за продуктами. Дома приготовили ужин, убрали кухню и обсудили планы на выходные.
- `religion` `segment-0001` [0:115], semantic=0.4804, lexical=0: После работы семья зашла в магазин за продуктами. Дома приготовили ужин, убрали кухню и обсудили планы на выходные.
- `economics` `segment-0001` [0:115], semantic=0.4553, lexical=0: После работы семья зашла в магазин за продуктами. Дома приготовили ужин, убрали кухню и обсудили планы на выходные.

### `everyday_family`

- expected_themes: `['everyday']`
- V1 result: `dominant=everyday; top=[everyday:0.0842]`; predicted `['everyday']`
- V2 predicted: `['everyday', 'law', 'medicine', 'religion', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `everyday` | 0.628626 | 0.615946 | 0.666667 | 1.000000 | 1 |
| 2 | `religion` | 0.385697 | 0.514263 | 0.000000 | 1.000000 | 1 |
| 3 | `law` | 0.317978 | 0.423970 | 0.000000 | 1.000000 | 1 |
| 4 | `sports` | 0.316078 | 0.421438 | 0.000000 | 1.000000 | 1 |
| 5 | `medicine` | 0.315676 | 0.420901 | 0.000000 | 1.000000 | 1 |
| 6 | `economics` | 0.301395 | 0.401860 | 0.000000 | 0.000000 | 0 |
| 7 | `politics` | 0.285735 | 0.380980 | 0.000000 | 0.000000 | 0 |
| 8 | `military` | 0.275921 | 0.367894 | 0.000000 | 0.000000 | 0 |
| 9 | `it` | 0.264925 | 0.353234 | 0.000000 | 0.000000 | 0 |
| 10 | `science` | 0.252433 | 0.336577 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `everyday` `segment-0001` [0:134], semantic=0.6159, lexical=4: В субботу родственники собрались дома на день рождения. Дети играли в комнате, взрослые готовили еду и разговаривали о семейных делах.
- `religion` `segment-0001` [0:134], semantic=0.5143, lexical=0: В субботу родственники собрались дома на день рождения. Дети играли в комнате, взрослые готовили еду и разговаривали о семейных делах.
- `law` `segment-0001` [0:134], semantic=0.4240, lexical=0: В субботу родственники собрались дома на день рождения. Дети играли в комнате, взрослые готовили еду и разговаривали о семейных делах.

### `everyday_repair`

- expected_themes: `['everyday']`
- V1 result: `dominant=everyday; top=[everyday:0.0831]`; predicted `['everyday']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `everyday` | 0.678281 | 0.626597 | 0.833333 | 1.000000 | 1 |
| 2 | `sports` | 0.436528 | 0.470926 | 0.333333 | 1.000000 | 1 |
| 3 | `military` | 0.360821 | 0.481095 | 0.000000 | 1.000000 | 1 |
| 4 | `law` | 0.357440 | 0.476586 | 0.000000 | 1.000000 | 1 |
| 5 | `religion` | 0.354194 | 0.472259 | 0.000000 | 1.000000 | 1 |
| 6 | `economics` | 0.348492 | 0.464656 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.345118 | 0.460157 | 0.000000 | 1.000000 | 1 |
| 8 | `medicine` | 0.343077 | 0.457436 | 0.000000 | 1.000000 | 1 |
| 9 | `politics` | 0.330692 | 0.440923 | 0.000000 | 1.000000 | 1 |
| 10 | `science` | 0.313127 | 0.417503 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `everyday` `segment-0001` [0:137], semantic=0.6266, lexical=5: В квартире сломалась стиральная машина, и хозяин вызвал мастера. Пока шел ремонт, соседи помогли передвинуть мебель и убрать воду с пола.
- `sports` `segment-0001` [0:137], semantic=0.4709, lexical=2: В квартире сломалась стиральная машина, и хозяин вызвал мастера. Пока шел ремонт, соседи помогли передвинуть мебель и убрать воду с пола.
- `military` `segment-0001` [0:137], semantic=0.4811, lexical=0: В квартире сломалась стиральная машина, и хозяин вызвал мастера. Пока шел ремонт, соседи помогли передвинуть мебель и убрать воду с пола.

### `hard_neutral`

- expected_themes: `[]`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['everyday']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `everyday` | 0.423157 | 0.508654 | 0.166667 | 1.000000 | 1 |
| 2 | `religion` | 0.314213 | 0.418950 | 0.000000 | 0.000000 | 0 |
| 3 | `medicine` | 0.300275 | 0.400367 | 0.000000 | 0.000000 | 0 |
| 4 | `sports` | 0.296431 | 0.395242 | 0.000000 | 0.000000 | 0 |
| 5 | `military` | 0.295505 | 0.394006 | 0.000000 | 0.000000 | 0 |
| 6 | `science` | 0.290864 | 0.387819 | 0.000000 | 0.000000 | 0 |
| 7 | `law` | 0.285562 | 0.380750 | 0.000000 | 0.000000 | 0 |
| 8 | `it` | 0.285305 | 0.380406 | 0.000000 | 0.000000 | 0 |
| 9 | `politics` | 0.273325 | 0.364433 | 0.000000 | 0.000000 | 0 |
| 10 | `economics` | 0.254472 | 0.339296 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `everyday` `segment-0001` [0:89], semantic=0.5087, lexical=1: В комнате было тихо. За окном постепенно темнело, и никто не торопился начинать разговор.
- `religion` `segment-0001` [0:89], semantic=0.4189, lexical=0: В комнате было тихо. За окном постепенно темнело, и никто не торопился начинать разговор.
- `medicine` `segment-0001` [0:89], semantic=0.4004, lexical=0: В комнате было тихо. За окном постепенно темнело, и никто не торопился начинать разговор.

### `hard_mixed_politics_economics`

- expected_themes: `['economics', 'politics']`
- V1 result: `dominant=economics; top=[economics:0.0930]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.641910 | 0.633658 | 0.666667 | 1.000000 | 1 |
| 2 | `politics` | 0.496869 | 0.606936 | 0.166667 | 1.000000 | 1 |
| 3 | `law` | 0.406591 | 0.486566 | 0.166667 | 1.000000 | 1 |
| 4 | `science` | 0.357105 | 0.476140 | 0.000000 | 1.000000 | 1 |
| 5 | `everyday` | 0.354985 | 0.473313 | 0.000000 | 1.000000 | 1 |
| 6 | `medicine` | 0.344083 | 0.458778 | 0.000000 | 1.000000 | 1 |
| 7 | `religion` | 0.335274 | 0.447032 | 0.000000 | 1.000000 | 1 |
| 8 | `it` | 0.332041 | 0.442721 | 0.000000 | 1.000000 | 1 |
| 9 | `military` | 0.330836 | 0.441114 | 0.000000 | 1.000000 | 1 |
| 10 | `sports` | 0.327834 | 0.437112 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `economics` `segment-0001` [0:169], semantic=0.6337, lexical=4: Правительство представило бюджет и предложило повысить налог на прибыль. Депутаты спорили о влиянии решения на компании, инвестиции и предстоящую избирательную кампанию.
- `politics` `segment-0001` [0:169], semantic=0.6069, lexical=1: Правительство представило бюджет и предложило повысить налог на прибыль. Депутаты спорили о влиянии решения на компании, инвестиции и предстоящую избирательную кампанию.
- `law` `segment-0001` [0:169], semantic=0.4866, lexical=1: Правительство представило бюджет и предложило повысить налог на прибыль. Депутаты спорили о влиянии решения на компании, инвестиции и предстоящую избирательную кампанию.

### `hard_law_politics_overlap`

- expected_themes: `['law', 'politics']`
- V1 result: `dominant=politics; top=[politics:0.0795]`; predicted `['politics']`
- V2 predicted: `['law', 'politics']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `politics` | 0.577753 | 0.603670 | 0.500000 | 1.000000 | 1 |
| 2 | `law` | 0.532282 | 0.598598 | 0.333333 | 1.000000 | 1 |
| 3 | `science` | 0.344648 | 0.403975 | 0.166667 | 0.000000 | 0 |
| 4 | `sports` | 0.312454 | 0.416606 | 0.000000 | 0.000000 | 0 |
| 5 | `medicine` | 0.301261 | 0.401682 | 0.000000 | 0.000000 | 0 |
| 6 | `economics` | 0.293774 | 0.391698 | 0.000000 | 0.000000 | 0 |
| 7 | `it` | 0.293367 | 0.391156 | 0.000000 | 0.000000 | 0 |
| 8 | `military` | 0.291815 | 0.389087 | 0.000000 | 0.000000 | 0 |
| 9 | `everyday` | 0.287305 | 0.383073 | 0.000000 | 0.000000 | 0 |
| 10 | `religion` | 0.274815 | 0.366420 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `politics` `segment-0001` [0:138], semantic=0.6037, lexical=3: Парламент принял закон, регулирующий полномочия региональной власти. Оппозиция намерена обжаловать отдельные нормы в конституционном суде.
- `law` `segment-0001` [0:138], semantic=0.5986, lexical=2: Парламент принял закон, регулирующий полномочия региональной власти. Оппозиция намерена обжаловать отдельные нормы в конституционном суде.
- `science` `segment-0001` [0:138], semantic=0.4040, lexical=1: Парламент принял закон, регулирующий полномочия региональной власти. Оппозиция намерена обжаловать отдельные нормы в конституционном суде.

### `hard_single_keyword`

- expected_themes: `['everyday']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['everyday', 'law', 'medicine', 'religion']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `everyday` | 0.430648 | 0.518642 | 0.166667 | 1.000000 | 1 |
| 2 | `law` | 0.359736 | 0.424092 | 0.166667 | 1.000000 | 1 |
| 3 | `religion` | 0.337635 | 0.450180 | 0.000000 | 1.000000 | 1 |
| 4 | `medicine` | 0.316082 | 0.421443 | 0.000000 | 1.000000 | 1 |
| 5 | `it` | 0.314693 | 0.419590 | 0.000000 | 0.000000 | 0 |
| 6 | `sports` | 0.305131 | 0.406841 | 0.000000 | 0.000000 | 0 |
| 7 | `economics` | 0.304019 | 0.405359 | 0.000000 | 0.000000 | 0 |
| 8 | `military` | 0.293217 | 0.390956 | 0.000000 | 0.000000 | 0 |
| 9 | `science` | 0.290635 | 0.387513 | 0.000000 | 0.000000 | 0 |
| 10 | `politics` | 0.279991 | 0.373321 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `everyday` `segment-0001` [0:137], semantic=0.5186, lexical=1: На полке лежал старый кодекс, который использовали как подставку для чашки. Остальной вечер прошел за обычным разговором о ремонте кухни.
- `law` `segment-0001` [0:137], semantic=0.4241, lexical=1: На полке лежал старый кодекс, который использовали как подставку для чашки. Остальной вечер прошел за обычным разговором о ремонте кухни.
- `religion` `segment-0001` [0:137], semantic=0.4502, lexical=0: На полке лежал старый кодекс, который использовали как подставку для чашки. Остальной вечер прошел за обычным разговором о ремонте кухни.

### `hard_very_short`

- expected_themes: `['sports']`
- V1 result: `dominant=sports; top=[sports:0.0516]`; predicted `['sports']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `sports` | 0.533900 | 0.656311 | 0.166667 | 1.000000 | 1 |
| 2 | `law` | 0.376438 | 0.501917 | 0.000000 | 1.000000 | 1 |
| 3 | `military` | 0.375023 | 0.500031 | 0.000000 | 1.000000 | 1 |
| 4 | `everyday` | 0.370001 | 0.493335 | 0.000000 | 1.000000 | 1 |
| 5 | `it` | 0.352739 | 0.470318 | 0.000000 | 1.000000 | 1 |
| 6 | `science` | 0.345016 | 0.460021 | 0.000000 | 1.000000 | 1 |
| 7 | `politics` | 0.342638 | 0.456851 | 0.000000 | 1.000000 | 1 |
| 8 | `economics` | 0.341047 | 0.454729 | 0.000000 | 1.000000 | 1 |
| 9 | `religion` | 0.339802 | 0.453069 | 0.000000 | 1.000000 | 1 |
| 10 | `medicine` | 0.327510 | 0.436680 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `sports` `segment-0001` [0:16], semantic=0.6563, lexical=1: Матч закончился.
- `law` `segment-0001` [0:16], semantic=0.5019, lexical=0: Матч закончился.
- `military` `segment-0001` [0:16], semantic=0.5000, lexical=0: Матч закончился.

### `hard_semantic_without_direct_keyword`

- expected_themes: `['science']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `science` | 0.453174 | 0.604232 | 0.000000 | 1.000000 | 1 |
| 2 | `medicine` | 0.423140 | 0.564186 | 0.000000 | 1.000000 | 1 |
| 3 | `it` | 0.414708 | 0.552944 | 0.000000 | 1.000000 | 1 |
| 4 | `sports` | 0.406706 | 0.486719 | 0.166667 | 1.000000 | 1 |
| 5 | `everyday` | 0.377670 | 0.448004 | 0.166667 | 1.000000 | 1 |
| 6 | `military` | 0.371123 | 0.494831 | 0.000000 | 1.000000 | 1 |
| 7 | `law` | 0.364568 | 0.486090 | 0.000000 | 1.000000 | 1 |
| 8 | `religion` | 0.339777 | 0.453036 | 0.000000 | 1.000000 | 1 |
| 9 | `economics` | 0.330265 | 0.440354 | 0.000000 | 1.000000 | 1 |
| 10 | `politics` | 0.311481 | 0.415308 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `science` `segment-0001` [0:155], semantic=0.6042, lexical=0: Каждое утро она измеряла образцы одинаковым способом, записывала наблюдения и сопоставляла их с контрольной серией, чтобы другие могли повторить процедуру.
- `medicine` `segment-0001` [0:155], semantic=0.5642, lexical=0: Каждое утро она измеряла образцы одинаковым способом, записывала наблюдения и сопоставляла их с контрольной серией, чтобы другие могли повторить процедуру.
- `it` `segment-0001` [0:155], semantic=0.5529, lexical=0: Каждое утро она измеряла образцы одинаковым способом, записывала наблюдения и сопоставляла их с контрольной серией, чтобы другие могли повторить процедуру.

### `hard_medicine_sports_overlap`

- expected_themes: `['medicine', 'sports']`
- V1 result: `dominant=medicine; top=[medicine:0.0903]`; predicted `['medicine']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `medicine` | 0.624572 | 0.610540 | 0.666667 | 1.000000 | 1 |
| 2 | `science` | 0.478130 | 0.581951 | 0.166667 | 1.000000 | 1 |
| 3 | `sports` | 0.462424 | 0.616566 | 0.000000 | 1.000000 | 1 |
| 4 | `politics` | 0.424804 | 0.510849 | 0.166667 | 1.000000 | 1 |
| 5 | `law` | 0.393403 | 0.524537 | 0.000000 | 1.000000 | 1 |
| 6 | `military` | 0.392725 | 0.523633 | 0.000000 | 1.000000 | 1 |
| 7 | `it` | 0.376046 | 0.501394 | 0.000000 | 1.000000 | 1 |
| 8 | `religion` | 0.370893 | 0.494524 | 0.000000 | 1.000000 | 1 |
| 9 | `economics` | 0.369887 | 0.493183 | 0.000000 | 1.000000 | 1 |
| 10 | `everyday` | 0.362693 | 0.483591 | 0.000000 | 1.000000 | 1 |

Top supporting segments:

- `medicine` `segment-0001` [0:154], semantic=0.6105, lexical=4: После финиша участнику измерили пульс и давление. Специалист рекомендовал временно снизить нагрузку и пройти обследование перед следующими соревнованиями.
- `science` `segment-0001` [0:154], semantic=0.5820, lexical=1: После финиша участнику измерили пульс и давление. Специалист рекомендовал временно снизить нагрузку и пройти обследование перед следующими соревнованиями.
- `sports` `segment-0001` [0:154], semantic=0.6166, lexical=0: После финиша участнику измерили пульс и давление. Специалист рекомендовал временно снизить нагрузку и пройти обследование перед следующими соревнованиями.

### `hard_metaphorical_attack`

- expected_themes: `['economics']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `military` | 0.507551 | 0.565623 | 0.333333 | 1.000000 | 1 |
| 2 | `economics` | 0.481083 | 0.585889 | 0.166667 | 1.000000 | 1 |
| 3 | `sports` | 0.458859 | 0.556256 | 0.166667 | 1.000000 | 1 |
| 4 | `medicine` | 0.423276 | 0.508812 | 0.166667 | 1.000000 | 1 |
| 5 | `science` | 0.404555 | 0.539406 | 0.000000 | 1.000000 | 1 |
| 6 | `politics` | 0.389451 | 0.519268 | 0.000000 | 1.000000 | 1 |
| 7 | `everyday` | 0.372715 | 0.496954 | 0.000000 | 1.000000 | 1 |
| 8 | `it` | 0.367212 | 0.489616 | 0.000000 | 1.000000 | 1 |
| 9 | `law` | 0.356290 | 0.475054 | 0.000000 | 1.000000 | 1 |
| 10 | `religion` | 0.304729 | 0.406306 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `military` `segment-0001` [0:136], semantic=0.5656, lexical=2: Команда маркетологов начала наступление на новый рынок и атаковала конкурентов низкими ценами. Военной операции в тексте не описывается.
- `economics` `segment-0001` [0:136], semantic=0.5859, lexical=1: Команда маркетологов начала наступление на новый рынок и атаковала конкурентов низкими ценами. Военной операции в тексте не описывается.
- `sports` `segment-0001` [0:136], semantic=0.5563, lexical=1: Команда маркетологов начала наступление на новый рынок и атаковала конкурентов низкими ценами. Военной операции в тексте не описывается.

### `hard_long_multisegment`

- expected_themes: `['economics', 'it']`
- V1 result: `dominant=economics; top=[economics:0.0664]`; predicted `['economics']`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science', 'sports']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `economics` | 0.464130 | 0.544766 | 0.222222 | 1.000000 | 3 |
| 2 | `it` | 0.458976 | 0.593449 | 0.055556 | 1.000000 | 3 |
| 3 | `military` | 0.408945 | 0.545260 | 0.000000 | 1.000000 | 3 |
| 4 | `science` | 0.406096 | 0.504425 | 0.111111 | 1.000000 | 3 |
| 5 | `sports` | 0.404328 | 0.520585 | 0.055556 | 1.000000 | 3 |
| 6 | `everyday` | 0.392786 | 0.505196 | 0.055556 | 1.000000 | 3 |
| 7 | `medicine` | 0.390037 | 0.501531 | 0.055556 | 1.000000 | 3 |
| 8 | `politics` | 0.382664 | 0.473182 | 0.111111 | 0.666667 | 2 |
| 9 | `law` | 0.370107 | 0.474958 | 0.055556 | 1.000000 | 3 |
| 10 | `religion` | 0.344388 | 0.459185 | 0.000000 | 1.000000 | 3 |

Top supporting segments:

- `economics` `segment-0002` [156:326], semantic=0.6196, lexical=3: После обеда руководство компании обсудило стоимость простоя, потерянную выручку и бюджет на новое оборудование. Финансовый директор предложил застраховать инфраструктуру.
- `economics` `segment-0003` [328:436], semantic=0.5512, lexical=1: Вечером команда подготовила технический отчет и план обновления системы без остановки обслуживания клиентов.
- `it` `segment-0003` [328:436], semantic=0.6445, lexical=1: Вечером команда подготовила технический отчет и план обновления системы без остановки обслуживания клиентов.
- `it` `segment-0001` [0:154], semantic=0.6022, lexical=0: Утром разработчики обнаружили сбой сервера и восстановили базу данных из резервной копии. Они проверили сетевые журналы и выпустили исправление программы.
- `military` `segment-0003` [328:436], semantic=0.5977, lexical=0: Вечером команда подготовила технический отчет и план обновления системы без остановки обслуживания клиентов.
- `military` `segment-0002` [156:326], semantic=0.5265, lexical=0: После обеда руководство компании обсудило стоимость простоя, потерянную выручку и бюджет на новое оборудование. Финансовый директор предложил застраховать инфраструктуру.

### `hard_religion_history`

- expected_themes: `['religion', 'science']`
- V1 result: `dominant=none; top=[]`; predicted `[]`
- V2 predicted: `['economics', 'everyday', 'it', 'law', 'medicine', 'military', 'politics', 'religion', 'science']`

| Rank | Theme | Combined | Semantic | Lexical | Coverage | Supports |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `religion` | 0.491163 | 0.654884 | 0.000000 | 1.000000 | 1 |
| 2 | `science` | 0.441027 | 0.588036 | 0.000000 | 1.000000 | 1 |
| 3 | `everyday` | 0.407829 | 0.488216 | 0.166667 | 1.000000 | 1 |
| 4 | `it` | 0.354659 | 0.472879 | 0.000000 | 1.000000 | 1 |
| 5 | `military` | 0.351707 | 0.468942 | 0.000000 | 1.000000 | 1 |
| 6 | `economics` | 0.350570 | 0.467427 | 0.000000 | 1.000000 | 1 |
| 7 | `politics` | 0.342894 | 0.457192 | 0.000000 | 1.000000 | 1 |
| 8 | `law` | 0.336889 | 0.449186 | 0.000000 | 1.000000 | 1 |
| 9 | `medicine` | 0.322688 | 0.430250 | 0.000000 | 1.000000 | 1 |
| 10 | `sports` | 0.300514 | 0.400685 | 0.000000 | 0.000000 | 0 |

Top supporting segments:

- `religion` `segment-0001` [0:146], semantic=0.6549, lexical=0: Историк изучал письма монастырской общины и описывал, как менялись церковные обряды. Работа основана на архивных источниках и сравнении рукописей.
- `science` `segment-0001` [0:146], semantic=0.5880, lexical=0: Историк изучал письма монастырской общины и описывал, как менялись церковные обряды. Работа основана на архивных источниках и сравнении рукописей.
- `everyday` `segment-0001` [0:146], semantic=0.4882, lexical=1: Историк изучал письма монастырской общины и описывал, как менялись церковные обряды. Работа основана на архивных источниках и сравнении рукописей.

## Engineering benchmark

```json
{
  "status": "ok",
  "reason": null,
  "v1_total_seconds": 0.057902,
  "v2_process_cold_total_seconds": 9.611361,
  "v2_reloaded_instance_seconds": 2.227369,
  "v2_warm_total_seconds": 2.068498,
  "v2_warm_mean_ms_per_document": 41.37,
  "definition": "process_cold=first evaluation in process; reloaded_instance=new model instance after libraries are warm; warm=same model instance+prototype cache"
}
```

## Interpretation

REAL V2 has high dominant-theme accuracy and full recall on this small
development corpus, but very low multi-label precision because many themes
cross the unchanged support thresholds. This report records the baseline;
no threshold, weight, prototype or fixture was changed.
