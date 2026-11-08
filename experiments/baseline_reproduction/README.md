# Baseline reproduction: CARE main-split detection (Table II)

**Status: PARTIAL / provisional.**
* **Execution.** The protocol was executed in full: one live confirmatory run and a clean-clone re-execution of
  the notebook.
* **Protocol history.** The protocol was amended to v1.1 after an external review (DECISIONS L8). The amendment
  changes how uncertainty is computed and how verdicts are worded, not data, runs or metric formulas.
* **Scope.** Every result is on a **reconstructed** population, and every numerical comparison with the paper is
  **not directly comparable**.

**Entry point:** [`baseline_reproduction.ipynb`](baseline_reproduction.ipynb). Restart & Run All.
Each stage is one call into [`repro/pipeline.py`](repro/pipeline.py), which reads top to bottom in
the same order.
* §1 is the contract and protocol.
* §2–§6 run the pipeline.
* §7 gives the results, §8 the diagnostics and §9 the limitations.

| | |
|---|---|
| Paper | Liu et al., *CARE: Pre-Execution Command Verification for Shell-Executing LLM Agents*, IEEE ISSRE 2026, [arXiv:2607.21642v2](https://arxiv.org/abs/2607.21642v2) |
| Targets | Table II (6 of 12 rows), Table VIII (McNemar), App. A.F (Resolution funnel), Sec. V-A1. Claims C1–C11 |
| Classification | *Partial reproduction* for CARE (author code, run unmodified). *Replication* for the data: the split is reconstructed because the authors' split is unreleased. *Reimplementation* for the LLM-judge baselines (verbatim App. E prompts) |
| Protocol | [`PROTOCOL.md`](PROTOCOL.md). v1.0 was frozen in commit `de2bc54` before the confirmatory run; the v1.1 amendment (§11) was written after the results and an external review. **Not blind:** a pilot came first |
| Decisions | [`DECISIONS.md`](DECISIONS.md), append-only: D1–D18, L1–L8 |

## Results (primary run = run 1 of 3; descriptive comparison)

* **Population.** The same corpora and recipe as the paper, but not the authors' 549 items.
* **Labels.** Corpus-level, the paper's Table I convention.
* **CIs.** All intervals are **design-based** 95% CIs: families are resampled within each source, and RedCode
  commands within each scenario (D15).
* **Symbols.** ∈ / ∉ say whether the reported value falls inside that interval. Inclusion is not evidence of
  equivalence.

| Condition | F1 reported → observed [95% CI] | DR reported → observed | FPR reported → observed | Verdict (v1.1) |
|---|---|---|---|---|
| PromptOnly | 66.99 → 63.50 [53.9, 71.6] ∈ | 63.18 → 57.73 | 17.02 → 16.11 | C3 inconclusive (not contradicted) |
| LLMJudge | 73.09 → 70.26 [61.6, 77.5] ∈ | 67.27 → 62.27 | 11.25 → 10.03 | C4 inconclusive (not contradicted) |
| NeMo self-check (emulated) | 68.63 → 66.12 [57.1, 73.7] ∈ | 58.18 → 55.45 | 7.60 → 8.21 | C5 inconclusive (not contradicted) |
| CARE (w/o Resolution) | 84.99 → **58.72** [45.9, 69.1] ∉ | 75.91 → 43.64 | 1.82 → 3.34 | C1 **not supported** (on this reconstruction) |
| CARE | 85.64 → **57.41** [44.6, 68.0] ∉ | 75.91 → 42.27 | 0.91 → 3.34 | C2 **not supported** (on this reconstruction) |

The other claims:

* **C6 not supported (on this reconstruction).** The paired difference in accuracy, CARE (w/o R) minus the
  baseline, with design-based CIs:
  * vs PromptOnly: +2.0 pp [−6.4, 8.5];
  * vs LLMJudge: −3.5 pp [−11.6, 2.7].
  Both intervals exclude the paper's effects of +14.2 and +9.1 pp from Table VIII.
* **C7 and C9 inconclusive (label-sensitive).** Under corpus-level labels, Resolution allows 3 / 2 / 3
  DANGEROUS-labelled commands per run and lowers DR by 1.4 pp. Those three commands are benign in content: two ART
  base64 "Hello" round-trips and one RedCode in-memory lookup. When they are audited as SAFE (D17), Resolution
  lowers FPR by 0.9 pp at unchanged DR, and allows no dangerous command.
* **C8 inconclusive (not contradicted).** The escalation rate is 3.64% [1.9, 5.7], against 4.19% reported.
* **C10 inconclusive.** LLMJudge has the highest F1 of the 6 evaluated conditions. LLMJudge minus CARE is
  +12.8 pp [1.5, 28.4], but LLMJudge minus CARE (w/o R) is +11.5 pp [−0.2, 27.3].
* **C11 inconclusive.** Hardware differs, so latency is not comparable.

The v1.0 verdicts (per-command CIs, with CI inclusion counted as "supported") are kept in `results/claims.parquet`
(`outcome_v1_0`). Full tables are in `results/report.md` and the executed notebook.

## Methods (adaptable for a paper)

> We attempted to reproduce the main detection experiment of CARE (Liu et al., ISSRE 2026;
> arXiv:2607.21642v2, Table II). The authors' 549-command evaluation split is not released, so we rebuilt a split
> with the published composition (220 DANGEROUS / 329 SAFE) from the same public corpora.
>
> * **DANGEROUS (220):** Atomic Red Team Linux sh/bash tests (149, including 12 slots for the unreleased canonical
>   attacks) and RedCode-Exec bash scripts (71, stratified over its 20 risk scenarios).
> * **SAFE (329):** NL2Bash (299, head-stratified with at most 12 per head, after removing operations the paper
>   deems unconditionally dangerous) and 30 real-world developer commands.
>
> Labels are corpus-level, as in the paper's Table I. Sampling is seeded (seed 42) and draws whole template
> families, with all sources pinned to commits.
>
> We evaluated the released CARE implementation without modification, in its static configuration and with its
> Resolution judge. We also evaluated three LLM-judge baselines with the paper's verbatim prompts: PromptOnly,
> LLMJudge, and a framework-free emulation of the NeMo Guardrails self-check rail. All LLM calls used
> Qwen3-Coder-30B-A3B-Instruct, the paper's backbone, through OpenRouter pinned to a single provider, with
> temperature 0 and the paper's max_tokens. Each LLM condition was run three times, and run 1 was fixed in advance
> as the primary run.
>
> We report F1, detection rate and false-positive rate. The 95% CIs come from a paired, design-based bootstrap
> (10,000 resamples) that mirrors the sampling design: families are resampled within each source, and RedCode
> scripts within each scenario. We also give the paper's per-command McNemar tests for fidelity.
>
> Because the population differs, comparisons with the reported values are descriptive. A claim was judged not
> supported on our reconstruction only when the reported value lay outside our interval. The confirmatory run made
> 5,001 calls with no errors and cost US$0.099.

## Reproducibility assessment

* **What the evidence shows on this reconstruction.**
  * Released CARE reaches a static F1 of 58.7 [45.9, 69.1], against 84.99 reported.
  * None of 100 splits drawn with this recipe exceeds 75.0.
  * On this population, even a *perfect* Resolution judge on every WARN command would raise F1 only to 60.8.
  * The misses are static ALLOWs on ART (46% DR) and RedCode (38% DR).
  * The LLM-judge baselines' reported values lie inside our intervals, but their F1 point estimates are
    2.5–3.5 pp lower (63.50 vs 66.99, 70.26 vs 73.09, 66.12 vs 68.63).
* **What it does not show.**
  * Why the paper's numbers differ: our seeds vary only *our* recipe.
  * The canonical attacks, the authors' RedCode filter and their ART snapshot are unknown. V3, an older ART
    snapshot, already moves static F1 from 58.7 to 65.7.
  * That the LLM-judge rows are not contradicted does not establish that our population is equally hard.
* **Unresolved.** We cannot separate (a) differences between the authors' items and ours from (b) a rule bank fitted
  to their pool. Releasing the authors' split would resolve this.
* **Risks.**
  * Labels are corpus-level, and a full independent label audit was not done.
  * The NeMo row is emulated.
  * Six baselines are not run.
  * Hosted serving has unknown precision.
  * The protocol is not blind: a pilot came first, and v1.1 was written after the results.
* **Next validation steps.**
  * Obtain the authors' split and curated subsets.
  * Run an independent two-annotator label audit.
  * Run Llama Guard 3 and Granite Guardian on local vLLM.
  * Run NeMo with the actual framework.
  * Repeat on local vLLM to compare latency.

## Using this as a baseline for a new method

* Evaluate the new method on `data/main_split.parquet`, using the same `command_id`s and corpus-level labels.
* Compare against the observed rows here (`results/observations.parquet`), not the paper's numbers. Use paired,
  design-based differences: `repro/stats.py: cluster_bootstrap_weights` and `weighted_rates`, as in
  `report.design_bootstrap`.
* See PROTOCOL §10 and §11.

## Artifact inventory

| Path | Content |
|---|---|
| `baseline_reproduction.ipynb` | executable narrative, executed in reuse mode. The live LLM execution is `results/executed/confirmatory_live_run.ipynb` |
| `PROTOCOL.md`, `DECISIONS.md`, `config.yaml` | protocol (v1.0 plus the v1.1 amendment), append-only log, configuration (pins, fingerprints, reported values) |
| `repro/` | `pipeline` (one function per notebook stage, in execution order; start here), `sources` (pinned sparse fetch, fingerprints), `dataset` (split reconstruction), `guards` (CARE + baselines, provider-pinned client, fingerprinted cache), `stats` (metric formulas, design-based bootstrap), `report` (tables, claims, figures, views) |
| `tests/test_repro.py` | 57 unit tests: metrics vs statsmodels, design-based bootstrap, parsing, cache identity and reply freshness, CARE fail-closed path, sampling, end-to-end split, settings (the API key never appears in output). The notebook also runs the repo's 10 CARE tests |
| `environment/requirements.lock.txt` | exact package versions |
| `data/main_split.parquet`, `data/NOTICE.md` | the 549-command split and the corpus licenses (ART MIT, RedCode CC BY 4.0, NL2Bash MIT) |
| `data/label_audit.yaml` | effect-based re-labelling of the 3 judge-changed commands (sensitivity analysis only, D17) |
| `results/observations.parquet` | 7,686 rows (method × run × command). Each holds the decision, latency, raw LLM reply, provider, generation id, UTC timestamp, tokens, cost, and the CARE trace |
| `results/metrics.parquet`, `comparison.parquet`, `claims.parquet` | long-format metrics with per-command CIs; reported vs observed (descriptive, with design-based CIs); claim verdicts (v1.1 and v1.0) |
| `results/design_intervals.parquet`, `design_differences.parquet`, `label_sensitivity.parquet` | design-based CIs, paired differences, and C7/C9 label sensitivity |
| `results/{mcnemar,resolution_funnel,oracle_bounds,by_source,redcode_scenarios,sensitivity_seeds,sensitivity_variants}.parquet` | secondary and diagnostic tables |
| `results/provenance.json`, `validation.json`, `report.md`, `figures/` | provenance (sources, fingerprints, env, LLM usage, output checksums), validation summary, rendered tables, figures |
| `results/executed/` | the live confirmatory run as executed (notebook, provenance, validation) and the clean-clone validation record |
| `results/pilot/` | pilot runs A and B (pre-protocol), kept for transparency; not used for any claim |

The PR carries the `experiment` label. A `baseline-reproduction` label does not exist in the repository and was not created (it needs the owner's go-ahead).
