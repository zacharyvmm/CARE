> All comparisons with the paper are **not directly comparable**: the population is a reconstruction (same corpora and recipe, not the authors' 549 items) and labels are corpus-level (paper Table I).

### Claim verdicts (protocol v1.1, PROTOCOL.md §11; v1.0 verdicts kept for the record)

| claim_id | claim | outcome | rationale | outcome_v1_0 |
|---|---|---|---|---|
| C1 | Table II row 'CARE (w/o Resolution)': F1/DR/FPR | not supported (on this reconstruction) | verdict on F1 (headline metric; DR/FPR descriptive): reported 84.99; observed 58.72, design-based 95% CI [45.9, 69.1]; 100 reconstructed splits: max 75.00 | not supported |
| C2 | Table II row 'CARE': F1/DR/FPR | not supported (on this reconstruction) | verdict on F1 (headline metric; DR/FPR descriptive): reported 85.64; observed 57.41, design-based 95% CI [44.6, 68.0] | not supported |
| C3 | Table II row 'PromptOnly': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 66.99; observed 63.50, design-based 95% CI [53.9, 71.6] | supported |
| C4 | Table II row 'LLMJudge': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 73.09; observed 70.26, design-based 95% CI [61.6, 77.5] | supported |
| C5 | Table II row 'NeMo self-check': F1/DR/FPR | inconclusive (not contradicted) | verdict on F1 (headline metric; DR/FPR descriptive): reported 68.63; observed 66.12, design-based 95% CI [57.1, 73.7] | supported |
| C6 | CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge (McNemar) | not supported (on this reconstruction) | vs PromptOnly: delta accuracy +2.00 pp [-6.4, 8.5], paper +14.21 pp; vs LLMJudge: delta accuracy -3.46 pp [-11.6, 2.7], paper +9.11 pp (design-based, paired) | not supported |
| C7 | Resolution lowers FPR (1.82 -> 0.91) at unchanged DR | inconclusive (label-sensitive) | corpus-level labels (paper Table I convention): dFPR +0.00 pp, dDR -1.36 pp -> not supported; audited labels for judge-changed commands (D17): dFPR -0.90 pp, dDR +0.00 pp -> supported | not supported |
| C8 | About 4.2% of commands (23/549) reach the LLM judge | inconclusive (not contradicted) | escalation 3.64% [design-based 1.9, 5.7] vs reported 4.19% | supported |
| C9 | The judge never converts a DANGEROUS command to ALLOW | inconclusive (label-sensitive) | corpus-level labels (paper Table I convention): DANGEROUS judge ALLOWs per run [3, 2, 3]; audited labels for judge-changed commands (D17): DANGEROUS judge ALLOWs per run [0, 0, 0] | not supported |
| C10 | CARE attains the highest F1 among the evaluated guards | inconclusive | LLMJudge - CARE (w/o Resolution): delta F1 +11.54 pp [-0.2, 27.3]; LLMJudge - CARE: delta F1 +12.85 pp [1.5, 28.4]; coverage: 6 of the paper's 12 rows | not supported |
| C11 | CARE (w/o Resolution) mean latency 0.34 ms; CARE 2.32 ms | inconclusive | observed static mean 0.65 ms on a laptop CPU; full-CARE latency dominated by hosted-API round trips; hardware and serving differ, so not directly comparable | inconclusive |

### Reported vs observed (Table II; primary run = run 1; descriptive)

| condition | metric | reported | observed [95% CI, per-command] | [95% CI, design-based] | abs_diff | range over runs |
|---|---|---|---|---|---|---|
| NoGuard | F1 | 0.00 | 0.00 [0.0, 0.0] | [nan, nan] | 0.00 | deterministic |
| NoGuard | DR | 0.00 | 0.00 [0.0, 1.7] | [nan, nan] | 0.00 | deterministic |
| NoGuard | FPR | 0.00 | 0.00 [0.0, 1.2] | [nan, nan] | 0.00 | deterministic |
| PromptOnly | F1 | 66.99 | 63.50 [57.8, 68.8] | [53.9, 71.6] | -3.49 | 63.50–64.66 |
| PromptOnly | DR | 63.18 | 57.73 [51.1, 64.1] | [47.1, 67.6] | -5.45 | 57.73–58.64 |
| PromptOnly | FPR | 17.02 | 16.11 [12.5, 20.5] | [12.2, 20.1] | -0.91 | 15.20–16.11 |
| LLMJudge | F1 | 73.09 | 70.26 [64.9, 75.3] | [61.6, 77.5] | -2.83 | 70.08–70.26 |
| LLMJudge | DR | 67.27 | 62.27 [55.7, 68.4] | [52.0, 71.2] | -5.00 | 62.27–62.27 |
| LLMJudge | FPR | 11.25 | 10.03 [7.2, 13.8] | [6.9, 13.3] | -1.22 | 10.03–10.33 |
| NeMo self-check | F1 | 68.63 | 66.12 [60.2, 71.5] | [57.1, 73.7] | -2.51 | 66.12–67.21 |
| NeMo self-check | DR | 58.18 | 55.45 [48.8, 61.9] | [45.5, 64.5] | -2.73 | 55.45–56.36 |
| NeMo self-check | FPR | 7.60 | 8.21 [5.7, 11.7] | [5.2, 11.4] | 0.61 | 7.60–8.21 |
| CARE (w/o Resolution) | F1 | 84.99 | 58.72 [52.1, 64.9] | [45.9, 69.1] | -26.27 | deterministic |
| CARE (w/o Resolution) | DR | 75.91 | 43.64 [37.2, 50.2] | [31.2, 55.4] | -32.27 | deterministic |
| CARE (w/o Resolution) | FPR | 1.82 | 3.34 [1.9, 5.9] | [1.5, 5.5] | 1.52 | deterministic |
| CARE | F1 | 85.64 | 57.41 [50.7, 63.6] | [44.6, 68.0] | -28.23 | 57.41–57.85 |
| CARE | DR | 75.91 | 42.27 [35.9, 48.9] | [30.1, 54.1] | -33.64 | 42.27–42.73 |
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


### Paired differences, design-based bootstrap (primary run; D15)

| left | right | metric | value | ci_lo | ci_hi | excludes_zero |
|---|---|---|---|---|---|---|
| CARE (w/o Resolution) | PromptOnly | delta_F1 | -4.78 | -21.21 | 7.70 | False |
| CARE (w/o Resolution) | PromptOnly | delta_accuracy | 2.00 | -6.36 | 8.54 | False |
| CARE (w/o Resolution) | LLMJudge | delta_F1 | -11.54 | -27.30 | 0.19 | False |
| CARE (w/o Resolution) | LLMJudge | delta_accuracy | -3.46 | -11.56 | 2.71 | False |
| CARE (w/o Resolution) | NeMo self-check | delta_F1 | -7.41 | -24.29 | 6.57 | False |
| CARE (w/o Resolution) | NeMo self-check | delta_accuracy | -1.82 | -10.02 | 4.88 | False |
| CARE | LLMJudge | delta_F1 | -12.85 | -28.41 | -1.47 | True |
| CARE | LLMJudge | delta_accuracy | -4.01 | -12.09 | 2.00 | False |
| CARE | CARE (w/o Resolution) | delta_F1 | -1.31 | -3.43 | 0.00 | False |
| CARE | CARE (w/o Resolution) | delta_accuracy | -0.55 | -1.43 | 0.00 | False |
| LLMJudge | CARE (w/o Resolution) | delta_F1 | 11.54 | -0.19 | 27.30 | False |
| LLMJudge | CARE (w/o Resolution) | delta_accuracy | 3.46 | -2.71 | 11.56 | False |
| LLMJudge | CARE | delta_F1 | 12.85 | 1.47 | 28.41 | True |
| LLMJudge | CARE | delta_accuracy | 4.01 | -2.00 | 12.09 | False |

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
