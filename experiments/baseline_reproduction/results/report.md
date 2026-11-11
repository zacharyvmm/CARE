# Results: CARE baseline reproduction (protocol v2.1)

> Every comparison with the paper is **not directly comparable**: the population is rebuilt from the public corpora (the authors' 549 commands are unreleased) and labels are corpus-level (paper Table I).


## Claim verdicts

| id | claim | verdict | evidence |
|---|---|---|---|
| C1 | Table II row 'CARE (w/o Resolution)': F1 84.99 | not supported (on this reconstruction) | reported F1 84.99; paper-sized splits: mean 60.15, σ = 4.25, so the reported value is +5.8σ from the mean; best split 75.27; full corpora 49.46 |
| C2 | Table II row 'CARE': F1 85.64 | not supported (on this reconstruction) | reported F1 85.64; paper-sized splits: mean 59.21, σ = 4.30, so the reported value is +6.2σ from the mean; best split 74.46; full corpora 48.59 |
| C3 | Table II row 'PromptOnly': F1 66.99 | inconclusive (not contradicted) | reported F1 66.99; paper-sized splits: mean 61.06, σ = 3.17, so the reported value is +1.9σ from the mean; best split 72.06; full corpora 24.20 |
| C4 | Table II row 'LLMJudge': F1 73.09 | not supported (on this reconstruction) | reported F1 73.09; paper-sized splits: mean 66.15, σ = 3.07, so the reported value is +2.3σ from the mean; best split 76.62; full corpora 30.68 |
| C5 | Table II row 'NeMo self-check': F1 68.63 | inconclusive (not contradicted) | reported F1 68.63; paper-sized splits: mean 63.94, σ = 3.54, so the reported value is +1.3σ from the mean; best split 76.32; full corpora 33.61 |
| C6 | CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge | inconclusive | vs PromptOnly: accuracy +3.24 pp, σ = 2.73 (+1.2σ from 0; paper +14.21 pp); the paper's McNemar test favours CARE in 35% of splits and PromptOnly in 0%; vs LLMJudge: accuracy -0.84 pp, σ = 2.58 (-0.3σ from 0; paper +9.11 pp); the paper's McNemar test favours CARE in 2% of splits and LLMJudge in 10% |
| C7 | Resolution lowers FPR (1.82 -> 0.91) at unchanged DR | inconclusive (label-sensitive) | full corpora, primary run; corpus-level labels (paper Table I): FPR -0.38 pp, DR -2.27 pp; audited labels for the judge-allowed commands: FPR -0.60 pp, DR +0.00 pp |
| C8 | About 4.2% of commands (23/549) reach the LLM judge | inconclusive (not contradicted) | reported 4.19%; paper-sized splits: mean 4.21%, σ = 1.01 (+0.0σ from the mean); full corpora 1.93% |
| C9 | The judge never converts a DANGEROUS command to ALLOW | inconclusive (label-sensitive) | full corpora, all runs; corpus-level labels (paper Table I): DANGEROUS commands the judge allowed, per run [23, 23, 22]; audited labels for the judge-allowed commands: DANGEROUS commands the judge allowed, per run [0, 0, 0] (23 of 23 such commands audited) |
| C10 | CARE attains the highest F1 among the evaluated guards | inconclusive | CARE - LLMJudge: F1 -6.94 pp, σ = 4.96 (-1.4σ from 0); CARE (w/o Resolution) - LLMJudge: F1 -6.00 pp, σ = 4.96 (-1.2σ from 0); separated only beyond 2.39σ; coverage: 6 of the paper's 12 rows |
| C11 | Mean latency 0.34 ms (CARE w/o Resolution) and 2.32 ms (CARE) | inconclusive | observed mean 0.45 ms (static) and 13.04 ms (with Resolution) on a laptop CPU with a hosted API; the paper used 4xH100 with local vLLM, so the values are not comparable |

## Table II: reported → observed on 10,000 paper-sized splits (mean, σ; primary run)

σ is the standard deviation over the splits. A reported value more than 1.96σ from the mean is one that no plausible split yields.

| guard | F1 | DR | FPR |
|---|---|---|---|
| PromptOnly | 66.99 → **61.06** (σ = 3.17) | 63.18 → **55.08** (σ = 3.89) | 17.02 → **16.86** (σ = 2.13) |
| LLMJudge | 73.09 → **66.15** (σ = 3.07) | 67.27 → **58.69** (σ = 3.81) | 11.25 → **12.46** (σ = 1.88) |
| NeMo self-check | 68.63 → **63.94** (σ = 3.54) | 58.18 → **51.99** (σ = 4.10) | 7.60 → **6.98** (σ = 1.41) |
| CARE (w/o Resolution) | 84.99 → **60.15** (σ = 4.25) | 75.91 → **47.04** (σ = 4.64) | 1.82 → **6.07** (σ = 1.35) |
| CARE | 85.64 → **59.21** (σ = 4.30) | 75.91 → **45.58** (σ = 4.60) | 0.91 → **5.39** (σ = 1.27) |

## Full corpora: every guard on every command (primary run)

| guard | DR, all DANGEROUS | DR, ART | DR, RedCode-Exec | FPR, all SAFE | FPR, NL2Bash | FPR, Real-world | F1 | denied, NL2Bash set aside (D5) |
|---|---|---|---|---|---|---|---|---|
| PromptOnly | 52.1 (528/1,013) | 58.6 (243/415) | 47.7 (285/598) | 27.2 (2,822/10,368) | 27.3 (2,822/10,338) | 0.0 (0/30) | 24.20 | 47.9 (136/284) |
| LLMJudge | 52.4 (531/1,013) | 66.3 (275/415) | 42.8 (256/598) | 18.5 (1,918/10,368) | 18.6 (1,918/10,338) | 0.0 (0/30) | 30.68 | 56.7 (161/284) |
| NeMo self-check | 46.4 (470/1,013) | 58.8 (244/415) | 37.8 (226/598) | 12.7 (1,314/10,368) | 12.7 (1,314/10,338) | 0.0 (0/30) | 33.61 | 51.4 (146/284) |
| CARE (w/o Resolution) | 44.8 (454/1,013) | 49.6 (206/415) | 41.5 (248/598) | 3.6 (369/10,368) | 3.6 (369/10,338) | 0.0 (0/30) | 49.46 | 91.5 (260/284) |
| CARE | 42.5 (431/1,013) | 49.2 (204/415) | 38.0 (227/598) | 3.2 (330/10,368) | 3.2 (330/10,338) | 0.0 (0/30) | 48.59 | 91.5 (260/284) |

## CARE vs each comparator on the paper-sized splits (left − right, percentage points)

Two guards count as separated when the mean difference is more than 1.96σ from 0 (2.39σ for C10, which judges three comparators at once).

| pair | metric | mean difference | distance from 0 | left better in | on the full corpora |
|---|---|---|---|---|---|
| CARE (w/o Resolution) − PromptOnly | F1 | -0.91 (σ = 5.15) | -0.2σ | 45.8% of splits | +25.25 |
| CARE (w/o Resolution) − PromptOnly | accuracy | +3.24 (σ = 2.73) | +1.2σ | 86.9% of splits | +20.90 |
| CARE (w/o Resolution) − LLMJudge | F1 | -6.00 (σ = 4.96) | -1.2σ | 10.9% of splits | +18.78 |
| CARE (w/o Resolution) − LLMJudge | accuracy | -0.84 (σ = 2.58) | -0.3σ | 37.4% of splits | +12.93 |
| CARE (w/o Resolution) − NeMo self-check | F1 | -3.79 (σ = 5.45) | -0.7σ | 25.2% of splits | +15.85 |
| CARE (w/o Resolution) − NeMo self-check | accuracy | -1.44 (σ = 2.67) | -0.5σ | 29.3% of splits | +8.16 |
| CARE − PromptOnly | F1 | -1.85 (σ = 5.17) | -0.4σ | 38.8% of splits | +24.39 |
| CARE − PromptOnly | accuracy | +3.06 (σ = 2.69) | +1.1σ | 85.5% of splits | +21.04 |
| CARE − LLMJudge | F1 | -6.94 (σ = 4.96) | -1.4σ | 7.1% of splits | +17.91 |
| CARE − LLMJudge | accuracy | -1.02 (σ = 2.54) | -0.4σ | 34.5% of splits | +13.07 |
| CARE − NeMo self-check | F1 | -4.73 (σ = 5.46) | -0.9σ | 19.9% of splits | +14.98 |
| CARE − NeMo self-check | accuracy | -1.62 (σ = 2.62) | -0.6σ | 26.6% of splits | +8.30 |
| CARE − CARE (w/o Resolution) | F1 | -0.94 (σ = 0.72) | -1.3σ | 8.9% of splits | -0.86 |
| CARE − CARE (w/o Resolution) | accuracy | -0.18 (σ = 0.40) | -0.4σ | 24.4% of splits | +0.14 |

## The paper's McNemar test (two-sided, Yates, α = 0.05) on every split

| pair | left only / right only correct (mean per split) | paper (Table VIII) | p < 0.05 favouring left | p < 0.05 favouring right |
|---|---|---|---|---|
| CARE (w/o Resolution) vs PromptOnly | 80.8 / 63.0 | 102 / 24 (p = 6.9e-12) | 34.6% of splits | 0.2% of splits |
| CARE (w/o Resolution) vs LLMJudge | 60.8 / 65.5 | 70 / 20 (p = 2.4e-07) | 2.2% of splits | 9.8% of splits |
| CARE (w/o Resolution) vs NeMo self-check | 53.2 / 61.1 | — | 1.7% of splits | 17.3% of splits |
| CARE vs PromptOnly | 77.5 / 60.7 | — | 33.2% of splits | 0.2% of splits |
| CARE vs LLMJudge | 57.8 / 63.4 | — | 1.8% of splits | 11.3% of splits |
| CARE vs NeMo self-check | 50.0 / 58.9 | — | 1.4% of splits | 19.6% of splits |
| CARE vs CARE (w/o Resolution) | 2.2 / 3.2 | 3 / 0 (p = 0.25) | 0.1% of splits | 1.2% of splits |

## Resolution funnel

| scope | run | commands | warn | skipped | escalated | escalated % | judge ALLOW | judge ALLOW, DANGEROUS-labelled |
|---|---|---|---|---|---|---|---|---|
| paper (Appendix A.F) | — | 549 | 117 | 94 | 23 | 4.19 | 3 | 0 |
| paper-sized splits (mean) | 1 | 549 | 88.0 | 64.9 | 23.1 | 4.21 | 5.5 | 3.2 |
| paper-sized splits (mean) | 2 | 549 | 88.0 | 64.9 | 23.1 | 4.21 | 5.5 | 3.2 |
| paper-sized splits (mean) | 3 | 549 | 88.0 | 64.9 | 23.1 | 4.21 | 5.2 | 2.9 |
| full corpora | 1 | 11,381 | 672 | 452 | 220 | 1.93 | 62 | 23 |
| full corpora | 2 | 11,381 | 672 | 452 | 220 | 1.93 | 62 | 23 |
| full corpora | 3 | 11,381 | 672 | 452 | 220 | 1.93 | 61 | 22 |

## Upper bounds for any Resolution judge on the released static stack (paper-sized splits)

| bound | commands judged per split | F1 | DR | FPR |
|---|---|---|---|---|
| static only (no judge) | 0.00 | 60.15 (σ = 4.25) | 47.04 | 6.07 |
| perfect judge on the escalated commands | 23.13 | 61.36 (σ = 4.28) | 47.04 | 4.00 |
| perfect judge on every WARN command | 88.00 | 63.43 (σ = 4.32) | 47.04 | 0.66 |

## Label sensitivity of the Resolution claims (C7, C9; full corpora)

| labels | guard | DR | FPR | DANGEROUS commands the judge allowed, per run |
|---|---|---|---|---|
| corpus-level labels (paper Table I) | CARE (w/o Resolution) | 44.82 | 3.56 | — |
| corpus-level labels (paper Table I) | CARE | 42.55 | 3.18 | [23, 23, 22] |
| audited labels for the judge-allowed commands | CARE (w/o Resolution) | 43.54 | 3.77 | — |
| audited labels for the judge-allowed commands | CARE | 43.54 | 3.18 | [0, 0, 0] |

## DANGEROUS-labelled commands the judge allowed, per family

| source | family | audited label | commands |
|---|---|---|---|
| ART | T1140 | SAFE | 2 |
| RedCode-Exec | RC-12 | SAFE | 12 |
| RedCode-Exec | RC-16 | SAFE | 5 |
| RedCode-Exec | RC-20 | SAFE | 1 |
| RedCode-Exec | RC-22 | SAFE | 1 |
| RedCode-Exec | RC-25 | SAFE | 2 |

## RedCode-Exec: commands denied per risk scenario (of n; primary run)

| scenario | kind | n | PromptOnly | LLMJudge | NeMo self-check | CARE (w/o Resolution) | CARE |
|---|---|---|---|---|---|---|---|
| 1 | operational | 30 | 30 | 30 | 30 | 22 | 22 |
| 2 | operational | 30 | 30 | 30 | 29 | 0 | 0 |
| 3 | operational | 30 | 24 | 29 | 10 | 0 | 0 |
| 4 | operational | 28 | 21 | 7 | 4 | 20 | 20 |
| 5 | operational | 30 | 0 | 0 | 0 | 14 | 14 |
| 6 | operational | 30 | 30 | 16 | 13 | 1 | 1 |
| 7 | operational | 30 | 2 | 2 | 2 | 22 | 22 |
| 8 | operational | 30 | 23 | 23 | 20 | 30 | 30 |
| 9 | operational | 30 | 30 | 30 | 30 | 30 | 30 |
| 12 | software-weakness | 30 | 0 | 0 | 0 | 12 | 0 |
| 13 | operational | 30 | 2 | 3 | 0 | 27 | 27 |
| 14 | operational | 30 | 30 | 30 | 29 | 27 | 27 |
| 15 | software-weakness | 30 | 0 | 0 | 0 | 0 | 0 |
| 16 | software-weakness | 30 | 1 | 1 | 1 | 5 | 0 |
| 18 | operational | 30 | 28 | 26 | 30 | 9 | 9 |
| 20 | software-weakness | 30 | 4 | 1 | 3 | 3 | 2 |
| 21 | operational | 30 | 30 | 28 | 23 | 21 | 21 |
| 22 | software-weakness | 30 | 0 | 0 | 0 | 1 | 0 |
| 23 | software-weakness | 30 | 0 | 0 | 2 | 2 | 2 |
| 25 | software-weakness | 30 | 0 | 0 | 0 | 2 | 0 |

## Construction variants: expected F1 on paper-sized splits

| variant | note | PromptOnly | LLMJudge | NeMo self-check | CARE (w/o Resolution) | CARE |
|---|---|---|---|---|---|---|
| V0 | the protocol | 61.06 | 66.15 | 63.94 | 60.15 | 59.21 |
| V1 | NL2Bash: D5 filter off | 60.39 | 65.10 | 62.83 | 57.84 | 56.89 |
| V2 | RedCode: software-weakness scenarios not drawn (exploratory) | 66.89 | 71.43 | 68.85 | 64.65 | 64.77 |
| V2b | RedCode: not drawn | 59.76 | 68.35 | 67.38 | 60.71 | 60.84 |
| V3 | ART snapshot of 2026-03-24 (365 commands, now 415) | — | — | — | 61.89 | — |

## Run-to-run stability of the LLM guards

| guard | runs | decisions that differ between runs (%) | F1, run 1 | F1, run 2 | F1, run 3 |
|---|---|---|---|---|---|
| PromptOnly | 3 | 3.32 | 61.06 | 61.15 | 61.61 |
| LLMJudge | 3 | 1.78 | 66.15 | 66.32 | 66.39 |
| NeMo self-check | 3 | 1.85 | 63.94 | 63.37 | 65.01 |
| CARE | 3 | 0.10 | 59.21 | 59.22 | 59.38 |

## Latency (not comparable: laptop CPU and hosted API vs 4×H100 and local vLLM)

| guard | reported mean ms | observed mean ms |
|---|---|---|
| NoGuard | 0.00 | 0.00 |
| PromptOnly | 47.97 | 322.23 |
| LLMJudge | 45.90 | 329.26 |
| NeMo self-check | 95.23 | 324.44 |
| CARE (w/o Resolution) | 0.34 | 0.45 |
| CARE | 2.32 | 13.04 |

LLM usage over all runs: 11,352,714 prompt + 275,254 completion tokens, cost US$1.85 (as reported by OpenRouter).
