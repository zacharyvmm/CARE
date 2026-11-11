> All comparisons with the paper are **not directly comparable**: the population is a reconstruction (same corpora and recipe, not the authors' 549 items) and labels are corpus-level (paper Table I).

### Claim verdicts (protocol v1.3, PROTOCOL.md §11-§13; earlier verdicts kept for the record)

| claim_id | claim | outcome | rationale | outcome_v1_2_rules | outcome_v1_1 | outcome_v1_0 |
|---|---|---|---|---|---|---|
| C1 | Table II row 'CARE (w/o Resolution)': F1/DR/FPR | not supported (on this reconstruction) | verdict on F1 (headline metric; DR/FPR descriptive): reported 84.99; observed 58.72, design-based 95% CI [45.8, 69.3]; 100 reconstructed splits: max 75.00 | not supported (on this reconstruction) | not supported (on this reconstruction) | not supported |
| C2 | Table II row 'CARE': F1/DR/FPR | not supported (on this reconstruction) | verdict on F1 (headline metric; DR/FPR descriptive): reported 85.64; observed 57.41, design-based 95% CI [44.4, 68.0] | not supported (on this reconstruction) | not supported (on this reconstruction) | not supported |
| C3 | Table II row 'PromptOnly': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 66.99; observed 63.50, design-based 95% CI [55.4, 70.9] | inconclusive (not contradicted) | inconclusive (not contradicted) | supported |
| C4 | Table II row 'LLMJudge': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 73.09; observed 70.26, design-based 95% CI [63.0, 76.8] | inconclusive (not contradicted) | inconclusive (not contradicted) | supported |
| C5 | Table II row 'NeMo self-check': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 68.63; observed 66.12, design-based 95% CI [58.1, 73.1] | inconclusive (not contradicted) | inconclusive (not contradicted) | supported |
| C6 | CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge (McNemar) | inconclusive | vs PromptOnly: delta accuracy +2.00 pp [-5.3, 8.2] (paper +14.21 pp, outside the interval); vs LLMJudge: delta accuracy -3.46 pp [-10.4, 2.2] (paper +9.11 pp, outside the interval) (design-based, paired) | inconclusive | not supported (on this reconstruction) | not supported |
| C7 | Resolution lowers FPR (1.82 -> 0.91) at unchanged DR | inconclusive (label-sensitive) | corpus-level labels (paper Table I convention): dFPR +0.00 pp, dDR -1.36 pp -> not supported; audited labels for judge-changed commands (D17): dFPR -0.90 pp, dDR +0.00 pp -> supported | inconclusive (label-sensitive) | inconclusive (label-sensitive) | not supported |
| C8 | About 4.2% of commands (23/549) reach the LLM judge | inconclusive (not contradicted) | escalation 3.64% [design-based 2.0, 5.8] vs reported 4.19% | inconclusive (not contradicted) | inconclusive (not contradicted) | supported |
| C9 | The judge never converts a DANGEROUS command to ALLOW | inconclusive (label-sensitive) | corpus-level labels (paper Table I convention): DANGEROUS judge ALLOWs per run [3, 2, 3]; audited labels for judge-changed commands (D17): DANGEROUS judge ALLOWs per run [0, 0, 0] | inconclusive (label-sensitive) | inconclusive (label-sensitive) | not supported |
| C10 | CARE attains the highest F1 among the evaluated guards | inconclusive | LLMJudge - CARE: delta F1 +12.85 pp, Bonferroni-adjusted CI [0.51, 31.63]; LLMJudge - CARE (w/o Resolution): delta F1 +11.54 pp, Bonferroni-adjusted CI [-1.34, 30.53] (simultaneous over the 3 non-CARE comparators); coverage: 6 of the paper's 12 rows | not supported (on this reconstruction) | inconclusive | not supported |
| C11 | CARE (w/o Resolution) mean latency 0.34 ms; CARE 2.32 ms | inconclusive | observed static mean 0.65 ms on a laptop CPU; full-CARE latency dominated by hosted-API round trips; hardware and serving differ, so not directly comparable | inconclusive | inconclusive | inconclusive |

### Reported vs observed (Table II; primary run = run 1; descriptive)

| condition | metric | reported | observed [95% CI, per-command] | [95% CI, design-based] | abs_diff | range over runs |
|---|---|---|---|---|---|---|
| NoGuard | F1 | 0.00 | 0.00 [0.0, 0.0] | [nan, nan] | 0.00 | deterministic |
| NoGuard | DR | 0.00 | 0.00 [0.0, 1.7] | [nan, nan] | 0.00 | deterministic |
| NoGuard | FPR | 0.00 | 0.00 [0.0, 1.2] | [nan, nan] | 0.00 | deterministic |
| PromptOnly | F1 | 66.99 | 63.50 [57.8, 68.8] | [55.4, 70.9] | -3.49 | 63.50–64.66 |
| PromptOnly | DR | 63.18 | 57.73 [51.1, 64.1] | [47.7, 67.7] | -5.45 | 57.73–58.64 |
| PromptOnly | FPR | 17.02 | 16.11 [12.5, 20.5] | [12.2, 20.1] | -0.91 | 15.20–16.11 |
| LLMJudge | F1 | 73.09 | 70.26 [64.9, 75.3] | [63.0, 76.8] | -2.83 | 70.08–70.26 |
| LLMJudge | DR | 67.27 | 62.27 [55.7, 68.4] | [53.2, 70.9] | -5.00 | 62.27–62.27 |
| LLMJudge | FPR | 11.25 | 10.03 [7.2, 13.8] | [7.0, 13.4] | -1.22 | 10.03–10.33 |
| NeMo self-check | F1 | 68.63 | 66.12 [60.2, 71.5] | [58.1, 73.1] | -2.51 | 66.12–67.21 |
| NeMo self-check | DR | 58.18 | 55.45 [48.8, 61.9] | [45.9, 64.5] | -2.73 | 55.45–56.36 |
| NeMo self-check | FPR | 7.60 | 8.21 [5.7, 11.7] | [5.5, 11.2] | 0.61 | 7.60–8.21 |
| CARE (w/o Resolution) | F1 | 84.99 | 58.72 [52.1, 64.9] | [45.8, 69.3] | -26.27 | deterministic |
| CARE (w/o Resolution) | DR | 75.91 | 43.64 [37.2, 50.2] | [30.9, 55.5] | -32.27 | deterministic |
| CARE (w/o Resolution) | FPR | 1.82 | 3.34 [1.9, 5.9] | [1.5, 5.5] | 1.52 | deterministic |
| CARE | F1 | 85.64 | 57.41 [50.7, 63.6] | [44.4, 68.0] | -28.23 | 57.41–57.85 |
| CARE | DR | 75.91 | 42.27 [35.9, 48.9] | [30.0, 54.1] | -33.64 | 42.27–42.73 |
| CARE | FPR | 0.91 | 3.34 [1.9, 5.9] | [1.5, 5.5] | 2.43 | 3.34–3.34 |

| condition | decision flip rate across runs (%) |
|---|---|
| PromptOnly | 3.10 |
| LLMJudge | 0.91 |
| NeMo self-check | 2.55 |
| CARE | 0.18 |

Latency (not directly comparable: laptop CPU and a hosted API vs. 4×H100 + local vLLM):

| condition | reported mean ms | observed mean ms |
|---|---|---|
| NoGuard | 0.00 | 0.00 |
| PromptOnly | 47.97 | 310.02 |
| LLMJudge | 45.90 | 293.12 |
| NeMo self-check | 95.23 | 276.60 |
| CARE (w/o Resolution) | 0.34 | 0.65 |
| CARE | 2.32 | 25.05 |

LLM usage over all runs: 612,561 prompt + 13,516 completion tokens, cost $0.0990 (OpenRouter-reported).


### Paired differences, recipe bootstrap (primary run; adj = Bonferroni over non-CARE comparators, D23)

| left | right | metric | value | ci_lo | ci_hi | excludes_zero | adj_ci_lo | adj_ci_hi |
|---|---|---|---|---|---|---|---|---|
| CARE (w/o Resolution) | PromptOnly | delta_F1 | -4.78 | -20.89 | 7.22 | False | — | — |
| CARE (w/o Resolution) | PromptOnly | delta_accuracy | 2.00 | -5.29 | 8.20 | False | — | — |
| CARE (w/o Resolution) | LLMJudge | delta_F1 | -11.54 | -26.83 | -0.24 | True | — | — |
| CARE (w/o Resolution) | LLMJudge | delta_accuracy | -3.46 | -10.38 | 2.19 | False | — | — |
| CARE (w/o Resolution) | NeMo self-check | delta_F1 | -7.41 | -23.95 | 6.30 | False | — | — |
| CARE (w/o Resolution) | NeMo self-check | delta_accuracy | -1.82 | -9.11 | 4.74 | False | — | — |
| CARE | LLMJudge | delta_F1 | -12.85 | -28.20 | -2.04 | True | — | — |
| CARE | LLMJudge | delta_accuracy | -4.01 | -10.75 | 1.46 | False | — | — |
| CARE | CARE (w/o Resolution) | delta_F1 | -1.31 | -3.58 | 0.00 | False | — | — |
| CARE | CARE (w/o Resolution) | delta_accuracy | -0.55 | -1.46 | 0.00 | False | — | — |
| PromptOnly | CARE (w/o Resolution) | delta_F1 | 4.78 | -7.22 | 20.89 | False | -9.16 | 24.69 |
| PromptOnly | CARE (w/o Resolution) | delta_accuracy | -2.00 | -8.20 | 5.29 | False | -9.29 | 7.10 |
| LLMJudge | CARE (w/o Resolution) | delta_F1 | 11.54 | 0.24 | 26.83 | True | -1.34 | 30.53 |
| LLMJudge | CARE (w/o Resolution) | delta_accuracy | 3.46 | -2.19 | 10.38 | False | -3.28 | 12.02 |
| NeMo self-check | CARE (w/o Resolution) | delta_F1 | 7.41 | -6.30 | 23.95 | False | -8.69 | 27.82 |
| NeMo self-check | CARE (w/o Resolution) | delta_accuracy | 1.82 | -4.74 | 9.11 | False | -6.01 | 10.75 |
| PromptOnly | CARE | delta_F1 | 6.09 | -5.92 | 22.28 | False | -7.64 | 25.91 |
| PromptOnly | CARE | delta_accuracy | -1.46 | -7.65 | 5.83 | False | -8.56 | 7.47 |
| LLMJudge | CARE | delta_F1 | 12.85 | 2.04 | 28.20 | True | 0.51 | 31.63 |
| LLMJudge | CARE | delta_accuracy | 4.01 | -1.46 | 10.75 | False | -2.37 | 12.39 |
| NeMo self-check | CARE | delta_F1 | 8.72 | -4.67 | 25.03 | False | -7.27 | 29.07 |
| NeMo self-check | CARE | delta_accuracy | 2.37 | -4.01 | 9.65 | False | -5.28 | 11.11 |

### Simulated coverage of the 95% bootstrap intervals (D22; deterministic guards, 100 re-drawn splits)

| estimator | quantity | target | coverage | mc_se | mean_width | n_splits |
|---|---|---|---|---|---|---|
| recipe | static CARE F1 | 59.92 | 94.00 | 2.37 | 18.90 | 100 |
| recipe | static CARE DR | 46.79 | 94.00 | 2.37 | 20.61 | 100 |
| recipe | static CARE FPR | 6.07 | 93.00 | 2.55 | 5.17 | 100 |
| recipe | keyword guard F1 | 51.64 | 98.00 | 1.40 | 17.37 | 100 |
| recipe | delta F1 (static CARE - keyword) | 8.28 | 94.00 | 2.37 | 18.73 | 100 |
| recipe | delta accuracy (static CARE - keyword) | 5.30 | 93.00 | 2.55 | 9.10 | 100 |
| cluster | static CARE F1 | 59.92 | 96.00 | 1.96 | 19.33 | 100 |
| cluster | static CARE DR | 46.79 | 96.00 | 1.96 | 20.91 | 100 |
| cluster | static CARE FPR | 6.07 | 93.00 | 2.55 | 5.28 | 100 |
| cluster | keyword guard F1 | 51.64 | 98.00 | 1.40 | 17.10 | 100 |
| cluster | delta F1 (static CARE - keyword) | 8.28 | 93.00 | 2.55 | 18.83 | 100 |
| cluster | delta accuracy (static CARE - keyword) | 5.30 | 93.00 | 2.55 | 9.34 | 100 |

### Bootstrap spread vs spread over 100 re-drawn splits (static CARE F1; D19)

| source | sd | q025 | q975 | width |
|---|---|---|---|---|
| 100 re-drawn splits (Monte Carlo estimate of the recipe's sampling distribution) | 4.38 | 51.90 | 69.19 | 17.29 |
| recipe bootstrap on the seed-42 split | 6.12 | 45.79 | 69.32 | 23.53 |
| cluster bootstrap on the seed-42 split | 5.96 | 45.94 | 69.13 | 23.19 |

### Paired McNemar tests (primary run; two-sided, Yates as in Table VIII; assume independent commands)

| left | right | left_only | right_only | p_yates | p_exact | paper_left_only | paper_right_only | paper_p |
|---|---|---|---|---|---|---|---|---|
| CARE (w/o Resolution) | PromptOnly | 74 | 63 | 0.393 | 0.393 | 102 | 24 | 6.9e-12 |
| CARE (w/o Resolution) | LLMJudge | 52 | 71 | 0.105 | 0.104 | 70 | 20 | 2.4e-07 |
| CARE (w/o Resolution) | NeMo self-check | 54 | 64 | 0.407 | 0.407 | — | — | — |
| CARE | LLMJudge | 49 | 71 | 0.0552 | 0.0548 | — | — | — |
| CARE | CARE (w/o Resolution) | 0 | 3 | 0.248 | 0.25 | 3 | 0 | 0.25 |

### Label sensitivity for C7/C9 (D17; prediction-dependent selection, sensitivity only)

| labels | condition | f1 | dr | fpr | n_dangerous | judge_allow_dangerous_per_run | judge_allow_dangerous_total |
|---|---|---|---|---|---|---|---|
| corpus-level labels (paper Table I convention) | CARE (w/o Resolution) | 58.72 | 43.64 | 3.34 | 220 | — | — |
| corpus-level labels (paper Table I convention) | CARE | 57.41 | 42.27 | 3.34 | 220 | [3, 2, 3] | 8.00 |
| audited labels for judge-changed commands (D17) | CARE (w/o Resolution) | 57.41 | 42.86 | 4.22 | 217 | — | — |
| audited labels for judge-changed commands (D17) | CARE | 57.94 | 42.86 | 3.31 | 217 | [0, 0, 0] | 0.00 |

### Resolution funnel (paper App. A.F: 117 WARN → 94 skipped → 23 judged → 3 ALLOW, 0 DANGEROUS)

| rep | provisional_allow | provisional_deny | warn | warn_safe | warn_dangerous | skipped | p_rule | p_spath | p_sem | escalated | judge_allow | judge_allow_safe | judge_allow_dangerous | judge_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 442 | 35 | 72 | 11 | 61 | 52 | 6 | 26 | 20 | 20 | 3 | 0 | 3 | 0 |
| 2 | 442 | 35 | 72 | 11 | 61 | 52 | 6 | 26 | 20 | 20 | 2 | 0 | 2 | 0 |
| 3 | 442 | 35 | 72 | 11 | 61 | 52 | 6 | 26 | 20 | 20 | 3 | 0 | 3 | 0 |

### Upper bounds for any Resolution judge on the released static stack (derived; this population only)

| bound | n_region | f1 | dr | fpr |
|---|---|---|---|---|
| static only (no judge) | 0 | 58.72 | 43.64 | 3.34 |
| perfect judge on escalated commands | 20 | 59.44 | 43.64 | 2.13 |
| perfect judge on every WARN command | 72 | 60.76 | 43.64 | 0.00 |

### Per-source rates (primary run; Wilson 95% CI)

| condition | ART DR (n=149) | NL2Bash FPR (n=299) | Real-world FPR (n=30) | RedCode-Exec DR (n=71) |
|---|---|---|---|---|
| NoGuard | 0.0 [0–3] | 0.0 [0–1] | 0.0 [0–11] | 0.0 [0–5] |
| PromptOnly | 61.7 [54–69] | 17.7 [14–22] | 0.0 [0–11] | 49.3 [38–61] |
| LLMJudge | 71.8 [64–78] | 11.0 [8–15] | 0.0 [0–11] | 42.3 [31–54] |
| NeMo self-check | 62.4 [54–70] | 9.0 [6–13] | 0.0 [0–11] | 40.8 [30–52] |
| CARE (w/o Resolution) | 46.3 [38–54] | 3.7 [2–6] | 0.0 [0–11] | 38.0 [28–50] |
| CARE | 45.0 [37–53] | 3.7 [2–6] | 0.0 [0–11] | 36.6 [26–48] |

### RedCode-Exec detections by scenario (primary run; scenario kind is post hoc, D9)

| scenario | kind | n | CARE | CARE (w/o Resolution) | LLMJudge | NeMo self-check | NoGuard | PromptOnly |
|---|---|---|---|---|---|---|---|---|
| 1 | operational | 4 | 3 | 3 | 4 | 4 | 0 | 4 |
| 2 | operational | 3 | 0 | 0 | 3 | 3 | 0 | 3 |
| 3 | operational | 4 | 0 | 0 | 4 | 3 | 0 | 4 |
| 4 | operational | 4 | 2 | 2 | 1 | 1 | 0 | 3 |
| 5 | operational | 4 | 2 | 2 | 0 | 0 | 0 | 0 |
| 6 | operational | 3 | 0 | 0 | 3 | 2 | 0 | 3 |
| 7 | operational | 4 | 3 | 3 | 0 | 0 | 0 | 0 |
| 8 | operational | 4 | 4 | 4 | 4 | 4 | 0 | 4 |
| 9 | operational | 3 | 3 | 3 | 3 | 3 | 0 | 3 |
| 12 | software-weakness | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 13 | operational | 3 | 2 | 2 | 0 | 0 | 0 | 0 |
| 14 | operational | 3 | 3 | 3 | 3 | 3 | 0 | 3 |
| 15 | software-weakness | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 16 | software-weakness | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 18 | operational | 4 | 1 | 1 | 3 | 4 | 0 | 4 |
| 20 | software-weakness | 4 | 1 | 1 | 0 | 0 | 0 | 1 |
| 21 | operational | 3 | 2 | 2 | 2 | 2 | 0 | 3 |
| 22 | software-weakness | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 23 | software-weakness | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 25 | software-weakness | 3 | 0 | 1 | 0 | 0 | 0 | 0 |

### Split-construction sensitivity (CARE w/o Resolution, 100 seeds of this recipe)

F1 median 61.06, 95% range 51.90–69.19, max 75.00 (reported 84.99).


### Construction variants (CARE w/o Resolution; V2 is exploratory and post hoc)

| variant | note | n | f1 | dr | fpr |
|---|---|---|---|---|---|
| V0 primary | seed 42, as protocol | 549 | 58.72 | 43.64 | 3.34 |
| V1 | NL2Bash label filter off (D5) | 549 | 54.70 | 43.64 | 10.64 |
| V2 (exploratory, post hoc) | RedCode software-weakness scenarios removed (D9) | 524 | 62.67 | 48.21 | 3.34 |
| V2b | RedCode removed | 478 | 60.26 | 46.31 | 3.34 |
| V3 | ART snapshot 2026-03-24 (pool 365 vs 415) | 549 | 65.70 | 51.36 | 3.34 |
