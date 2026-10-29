# run-debugger eval report

Generated from `cache/` by `python -m harness.report`. All cases are **synthetic** (see `data/README.md`).

- Skill: `duvoai/skills` run-debugger `SKILL.md` @ `04dc340`, used verbatim as the system prompt
- Prompt version (skill + harness suffix): `db8ed4679cbd79c1`
- Models (as reported by the API): `claude-haiku-5-5`, `claude-opus-5-5`, `claude-sonnet-5-5`
- Backend: claude-cli; cost = list-price USD as reported per call
- Cases: 40

## 1. Headline

| Model | Replies | Accuracy (95% CI) | Strict | Fix target | Evidence grounded | Stable across repeats | Format OK | Cost / diagnosis | p50 / p95 latency |
|---|---|---|---|---|---|---|---|---|---|
| haiku | 200 (5×) | **97.0%** (93.0%–99.5%) | 93.5% | 94.0% | 97.0% | 85.0% | 98.0% | $0.0009 | 8.7s / 12.2s |
| sonnet | 200 (5×) | **97.0%** (91.0%–100.0%) | 85.5% | 94.0% | 96.0% | 92.5% | 100.0% | $0.0111 | 8.0s / 14.5s |
| opus | 80 (2×) | **100.0%** (100.0%–100.0%) | 95.0% | 100.0% | 100.0% | 100.0% | 100.0% | $0.0312 | 10.3s / 15.4s |

Sensitivity: accepting the disputed alternate label (C03 → missing_data) gives haiku 97.0%, sonnet 99.5%, opus 100.0%.

*Accuracy*: failure mode in the case's acceptable set; CI is a case-level bootstrap. *Strict*: exact primary label. *Evidence grounded*: every quoted span in the Evidence section appears verbatim in the input. *Stable*: share of cases where all repeats gave the same failure mode. *Latency*: API time per call.

## 2. Accuracy by slice

| | n | haiku | sonnet | opus |
|---|---|---|---|---|
| ambiguity | 5 | 100.0% | 100.0% | 100.0% |
| clean | 24 | 95.0% | 95.0% | 100.0% |
| discriminator | 3 | 100.0% | 100.0% | 100.0% |
| not_a_failure | 2 | 100.0% | 100.0% | 100.0% |
| trap | 6 | 100.0% | 100.0% | 100.0% |

## 3. Accuracy by ground-truth failure mode

| | n | haiku | sonnet | opus |
|---|---|---|---|---|
| aop_ambiguity | 6 | 100.0% | 100.0% | 100.0% |
| batch_leak | 5 | 96.0% | 100.0% | 100.0% |
| connection_failure | 8 | 100.0% | 87.5% | 100.0% |
| missing_data | 5 | 100.0% | 96.0% | 100.0% |
| missing_hitl | 3 | 100.0% | 100.0% | 100.0% |
| missing_terminal_closure | 3 | 100.0% | 100.0% | 100.0% |
| named_pattern | 1 | 100.0% | 100.0% | 100.0% |
| not_a_failure | 2 | 100.0% | 100.0% | 100.0% |
| platform_infra | 4 | 100.0% | 100.0% | 100.0% |
| wrong_decomposition | 3 | 66.7% | 100.0% | 100.0% |

## 4. Routing: when is the cheap model good enough?

Policies replayed offline over the cached replies (5 repeats per case, averaged). Δ and savings are relative to Sonnet-only, with case-level bootstrap 95% CIs. Held-out rows choose the policy on one half of the cases and score it on the other half (and swap), with the rule: cheapest policy within 2 pp of Sonnet on the training half.

| Policy | Rows | Accuracy | Δ vs Sonnet (95% CI) | Cost / diagnosis | Savings vs Sonnet (95% CI) | Escalated | p50 / p95 |
|---|---|---|---|---|---|---|---|
| haiku only | in-sample | 97.0% | +0.0 pp (-5.5…+7.0) | $0.0009 | 91.8% (91.2%…92.4%) | 0.0% | 8.7s / 12.2s |
| sonnet only | in-sample | 97.0% | +0.0 pp (+0.0…+0.0) | $0.0111 | 0.0% (0.0%…0.0%) | 0.0% | 8.0s / 14.5s |
| opus only | in-sample | 100.0% | +3.0 pp (+0.0…+9.0) | $0.0312 | -180.2% (-230.9%…-140.2%) | 0.0% | 10.3s / 15.4s |
| haiku → sonnet if confidence < 0.60 | in-sample | 97.0% | +0.0 pp (-5.5…+7.0) | $0.0009 | 91.8% (91.2%…92.4%) | 0.0% | 8.7s / 12.2s |
| haiku → sonnet if confidence < 0.70 | in-sample | 97.5% | +0.5 pp (-4.0…+7.5) | $0.0014 | 87.7% (82.7%…91.3%) | 3.0% | 8.7s / 13.2s |
| haiku → sonnet if confidence < 0.80 | in-sample | 99.0% | +2.0 pp (-2.0…+8.0) | $0.0032 | 71.7% (59.7%…83.2%) | 16.0% | 8.8s / 24.2s |
| haiku → sonnet if confidence < 0.85 | in-sample | 99.5% | +2.5 pp (+0.0…+7.5) | $0.0045 | 59.6% (45.5%…74.4%) | 26.0% | 8.9s / 25.8s |
| haiku → sonnet if confidence < 0.90 | in-sample | 97.0% | +0.0 pp (+0.0…+0.0) | $0.0087 | 22.1% (11.2%…35.0%) | 64.5% | 16.0s / 26.4s |
| haiku → sonnet if confidence < 0.95 | in-sample | 97.0% | +0.0 pp (+0.0…+0.0) | $0.0119 | -6.8% (-8.5%…-4.3%) | 98.0% | 16.9s / 26.6s |
| 2× haiku, → sonnet on disagreement | in-sample | 99.5% | +2.5 pp (-1.0…+8.5) | $0.0029 | 73.7% (66.1%…80.5%) | 7.0% | 9.1s / 23.8s |
| cross-fitted pick (held-out) | held-out | 97.0% | +0.0 pp (-5.5…+7.0) | $0.0009 | 91.8% (91.2%…92.4%) | 0.0% | 8.7s / 12.2s |
| category gate, weak set fitted per fold (held-out) | held-out | 97.0% | +0.0 pp (-5.5…+7.0) | $0.0016 | 85.6% (77.4%…91.6%) | 5.0% | 8.7s / 16.5s |

Held-out choices per fold: haiku → sonnet if confidence < 0.60; haiku → sonnet if confidence < 0.60. Category-gate weak sets per fold: haiku → sonnet if predicted ∈ {aop_ambiguity, named_pattern}; haiku → sonnet if predicted ∈ {missing_terminal_closure}.

## 5. Most common mistakes

- **haiku**: wrong_decomposition → connection_failure ×3, batch_leak → named_pattern ×1, wrong_decomposition → missing_terminal_closure ×1, wrong_decomposition → aop_ambiguity ×1
- **sonnet**: connection_failure → missing_data ×5, missing_data → aop_ambiguity ×1
- **opus**: none

## 6. Is self-reported confidence usable?

| Model | Confidence | Replies | Accuracy |
|---|---|---|---|
| haiku | 0.6–0.8 | 32 | 87.5% |
| haiku | 0.8–0.9 | 97 | 97.9% |
| haiku | ≥0.9 | 71 | 100.0% |
| sonnet | 0.6–0.8 | 31 | 96.8% |
| sonnet | 0.8–0.9 | 60 | 91.7% |
| sonnet | ≥0.9 | 109 | 100.0% |
| opus | 0.6–0.8 | 10 | 100.0% |
| opus | 0.8–0.9 | 28 | 100.0% |
| opus | ≥0.9 | 42 | 100.0% |

## 7. Does the harness's JSON line change the diagnosis?

Same cases, one reply each: with the JSON suffix (main run, repeat 0) vs. without it (label parsed from the prose *Failure mode* section).

| Model | n | With JSON line | Without | JSON label = prose label |
|---|---|---|---|---|
| haiku | 40 | 97.5% | 90.0% | 100.0% |
| sonnet | 40 | 97.5% | 97.5% | 100.0% |

## 8. Spend

| Model | Calls | List-price cost | Cache-write tokens | Cache-read tokens | Output tokens |
|---|---|---|---|---|---|
| haiku | 240 | $0.23 | 102,897 | 1,886,107 | 374,474 |
| opus | 80 | $2.50 | 92,303 | 570,925 | 82,265 |
| sonnet | 240 | $2.85 | 115,163 | 1,868,801 | 220,370 |
| **total** | | **$5.58** | | | |

