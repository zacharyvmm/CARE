# Baseline reproduction: CARE main-split detection (Table II)

**Status: PARTIAL / provisional.** The protocol was executed in full: one
confirmatory live run, plus a clean-clone re-execution of the notebook. Scope
and population limits are stated below.

**Entry point:** [`baseline_reproduction.ipynb`](baseline_reproduction.ipynb). Restart & Run All.
Each stage is one call into [`repro/pipeline.py`](repro/pipeline.py), which reads top to bottom in
the same order. Results (§6) and diagnostics (§7) follow the pipeline; the full protocol and the
environment details are in the appendices.

| | |
|---|---|
| Paper | Liu et al., *CARE: Pre-Execution Command Verification for Shell-Executing LLM Agents*, IEEE ISSRE 2026, [arXiv:2607.21642v2](https://arxiv.org/abs/2607.21642v2) |
| Targets | Table II (6 of 12 rows), Table VIII (McNemar), App. A.F (Resolution funnel), Sec. V-A1. Claims C1–C11 |
| Classification | *Partial reproduction* for CARE (author code, run unmodified). *Replication* for the data: the split is reconstructed because the authors' split is unreleased. *Reimplementation* for the LLM-judge baselines (verbatim App. E prompts) |
| Protocol | [`PROTOCOL.md`](PROTOCOL.md) v1.0, frozen in commit `de2bc54` before the confirmatory run. **Not blind:** a pilot came first |
| Decisions | [`DECISIONS.md`](DECISIONS.md), append-only: D1–D14, L1–L6 |

## Results (observed; primary run = run 1 of 3)

All comparisons are on a **reconstructed population**: the same corpora and
recipe, but not the authors' 549 items. Each reported value is *consistent*
when it lies inside our 95% CI.

| Condition | F1 reported → observed [95% CI] | DR reported → observed | FPR reported → observed | Verdict |
|---|---|---|---|---|
| PromptOnly | 66.99 → 63.50 [57.8, 68.8] | 63.18 → 57.73 | 17.02 → 16.11 | C3 **supported** |
| LLMJudge | 73.09 → 70.26 [64.9, 75.3] | 67.27 → 62.27 | 11.25 → 10.03 | C4 **supported** |
| NeMo self-check (emulated) | 68.63 → 66.12 [60.2, 71.5] | 58.18 → 55.45 | 7.60 → 8.21 | C5 **supported** |
| CARE (w/o Resolution) | 84.99 → **58.72** [52.1, 64.9] | 75.91 → 43.64 | 1.82 → 3.34 | C1 **not supported** |
| CARE | 85.64 → **57.41** [50.7, 63.6] | 75.91 → 42.27 | 0.91 → 3.34 | C2 **not supported** |

The other claims:

* **C6 not supported.** CARE (w/o R) vs LLMJudge: 52 vs 71 discordant pairs,
  p = 0.105. The paper reports 70 vs 20, p = 2.4e-7.
* **C7 not supported.** Resolution leaves FPR unchanged and lowers DR by 1.4 pp.
* **C8 supported.** 20/549 = 3.6% of commands are escalated, against 4.2%
  reported.
* **C9 not supported.** The judge allowed 2–3 DANGEROUS-labelled commands per
  run. Their labels are questionable: two are ART base64 "Hello" round-trips
  and one is a RedCode key lookup.
* **C10 not supported.** LLMJudge has the highest F1 among the 6 evaluated
  conditions.
* **C11 inconclusive.** Hardware differs, so latency is not comparable.

Full tables are in `results/report.md` and in the executed notebook.

## Methods (adaptable for a paper)

> We reproduced the main detection experiment of CARE (Liu et al., ISSRE 2026;
> arXiv:2607.21642v2, Table II). Because the authors' 549-command evaluation
> split is not released, we rebuilt a split with the published composition
> (220 DANGEROUS / 329 SAFE) from the same public corpora.
>
> * **DANGEROUS (220):** Atomic Red Team Linux sh/bash tests (149, including 12
>   slots for the unreleased canonical attacks) and RedCode-Exec bash scripts
>   (71, stratified over its 20 risk scenarios).
> * **SAFE (329):** NL2Bash (299, head-stratified with at most 12 per head, after
>   removing operations the paper deems unconditionally dangerous) and 30
>   real-world developer commands.
>
> Sampling is seeded (seed 42) and draws whole template families, with all
> sources pinned to commits. We evaluated the released CARE implementation
> without modification, in its static configuration and with its Resolution
> judge. We also evaluated three LLM-judge baselines (PromptOnly, LLMJudge, and a
> framework-free emulation of the NeMo Guardrails self-check rail) using the
> paper's verbatim prompts.
>
> All LLM calls used Qwen3-Coder-30B-A3B-Instruct, the paper's backbone, through
> OpenRouter pinned to a single provider, with temperature 0 and the paper's
> max_tokens. Each LLM condition was run three times; run 1 was fixed in advance
> as the primary run. We report F1, detection rate and false-positive rate with
> Wilson (DR, FPR) and paired-bootstrap (F1) 95% CIs, and paired McNemar tests
> with Yates' correction.
>
> The confirmatory run made 5,001 calls with no errors and cost US$0.099.
> Latency is reported but is not comparable to the paper, which used local
> serving on 4×H100.

## Reproducibility assessment

* **What supports the paper.**
  * The three LLM-judge baselines match Table II within our 95% CIs on all
    three metrics. Our point estimates are 2.5–3.5 pp lower in F1.
  * The escalation rate (3.6% vs 4.2%) matches.
  * The three "CARE vs CARE w/o R" disagreements reproduce in count (3 vs 0,
    p = 0.25), though here they cost recall rather than removing false positives.
* **What contradicts it.**
  * Static CARE detects 43.6% of attacks, against 75.9% reported, so F1 is 58.7
    vs 85.0.
  * This is not an artifact of our seed. Across 100 reconstructed splits the
    static F1 never exceeds 75.0, and its 95% range is 51.9–69.2.
  * It is not the Resolution stage. A *perfect* judge on every WARN command
    would raise F1 only to 60.8, so neither judge quality nor the paper/code
    skip-predicate conflict (D14) can close the gap.
  * The misses are static ALLOWs on ART (46% DR) and RedCode (38% DR).
* **Unresolved.** We cannot distinguish (a) differences between the authors'
  items and ours from (b) a rule bank fitted to their pool. Examples of (a) are
  the 12 canonical attacks, their RedCode filter and their ART snapshot. An ART
  snapshot closer to submission (V3) raises F1 to 65.7, which is still far
  below. Releasing the authors' split would resolve this.
* **Risks.**
  * The labels come from the corpora: every ART and RedCode item is DANGEROUS.
  * The NeMo row is emulated.
  * Six baselines are not run.
  * Hosted serving has unknown precision.
  * The protocol was frozen after a pilot, but no element affecting the primary
    numbers changed afterwards.
* **Next validation steps.**
  * Obtain the authors' split and curated subsets.
  * Run Llama Guard 3 and Granite Guardian on local vLLM.
  * Run NeMo with the actual framework.
  * Repeat on local vLLM to compare latency.

## Using this as a baseline for a new method

Evaluate the new method on `data/main_split.parquet` (same `command_id`s) with
`repro/stats.py`. Compare against the observed rows in `results/metrics.parquet`
using paired McNemar tests on `results/observations.parquet`. Do not compare
against the paper's numbers (PROTOCOL §10).

## Artifact inventory

| Path | Content |
|---|---|
| `baseline_reproduction.ipynb` | executable narrative, executed in reuse mode. The live LLM execution is `results/executed/confirmatory_live_run.ipynb` |
| `PROTOCOL.md`, `DECISIONS.md`, `config.yaml` | frozen protocol, append-only log, configuration (pins, fingerprints, reported values) |
| `repro/` | `pipeline` (one function per notebook stage, in execution order; start here), `sources` (pinned sparse fetch, fingerprints), `dataset` (split reconstruction), `guards` (CARE + baselines, provider-pinned client), `stats` (metric formulas), `report` (tables, claims, figures, views) |
| `tests/test_repro.py` | 49 unit tests: metrics vs statsmodels, parsing, CARE fail-closed path, sampling, end-to-end split, settings (the API key never appears in output). The notebook also runs the repo's 10 CARE tests |
| `environment/requirements.lock.txt` | exact package versions |
| `data/main_split.parquet`, `data/NOTICE.md` | the 549-command split and the corpus licenses (ART MIT, RedCode CC BY 4.0, NL2Bash MIT) |
| `results/observations.parquet` | 7,686 rows (method × run × command). Each holds the decision, latency, raw LLM reply, provider, generation id, UTC timestamp, tokens, cost, and the CARE trace |
| `results/metrics.parquet`, `comparison.parquet`, `claims.parquet` | long-format metrics with CIs; reported vs observed; claim verdicts |
| `results/{mcnemar,resolution_funnel,oracle_bounds,by_source,redcode_scenarios,sensitivity_seeds,sensitivity_variants}.parquet` | secondary and diagnostic tables |
| `results/provenance.json`, `validation.json`, `report.md`, `figures/` | provenance (sources, fingerprints, env, LLM usage, output checksums), validation summary, rendered tables, figures |
| `results/executed/` | the live confirmatory run as executed (notebook, provenance, validation) and the clean-clone validation record |
| `results/pilot/` | pilot runs A and B (pre-protocol), kept for transparency; not used for any claim |

The PR carries the `experiment` label. A `baseline-reproduction` label does not exist in the repository and was not created (it needs the owner's go-ahead).
