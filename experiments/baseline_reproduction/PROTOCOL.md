# Reproduction protocol: CARE main-split detection (v2.1)

**Status:** v2.0 was frozen on 2026-11-11, before the v2 confirmatory run (`DECISIONS.md` L13).
Any later change needs a new protocol version and a `DECISIONS.md` entry.

**v2.1 (2026-11-11, after the run; `DECISIONS.md` D29).** One presentation change: the
split-to-split spread of each statistic is reported as a standard deviation, **σ**, and the
verdict rules are stated in σ. v2.0 reported the interval holding the central 95% of the
splits. Both rules were applied to the same decisions and **every verdict is identical**. The
v2.0 text as frozen is in git at commit `931ebfe`. Changed sections: §6, §7 and §11.

**What changed from v1.** Protocol v1 (v1.0–v1.3, in git history at commit `57ac042`) evaluated one
549-command sample of the corpora. Protocol v2.0 evaluates **every command of every corpus**
(D24). Sampling no longer decides which commands are run, so the bootstrap machinery of v1 is
gone. The data sources, prompts, model, parsing and metric formulas are unchanged.

**Not blind.** The v1 results were known when this protocol was written: on the v1 sample,
static CARE reached F1 58.7 against a reported 84.99, and the LLM-judge baselines came within
about 3.5 pp of the paper. No v2 result had been seen (§11).

## 1. Target and classification

* **Paper:** Liu et al., *CARE: Pre-Execution Command Verification for Shell-Executing LLM
  Agents*, IEEE ISSRE 2026, arXiv:2607.21642 **v2** (sha256 `fe70b54c…`; v1 differs only in
  author order and affiliations).
* **Targeted results:** Table II (main-split detection), Table VIII (McNemar pairs),
  Appendix A.F (Resolution funnel), and the related statements in Sec. V-A1.
* **Out of scope:** Table III (utility), Table IV (ablations), Tables V and IX (OOD and Docker
  harm), Table VI (sensitivity), Table VII (per-family DR; its family labels are unreleased),
  and six of the twelve Table II rows (§5).
* **Classification:**
  * *Partial reproduction* of the CARE rows: the author-released implementation is run
    unmodified.
  * *Replication* of the evaluation data: the authors' 549-command split is unreleased, so the
    population is rebuilt from the same public corpora.
  * *Reimplementation* of the three LLM-judge baselines from the verbatim prompts in
    Appendix E: no baseline code was released.
* **Consequence:** no comparison is on the authors' test items. Every numerical comparison
  with the paper is **not directly comparable** and is reported descriptively.

## 2. Claims

| ID | Claim (paper wording, abridged) | Paper location |
|---|---|---|
| C1 | CARE (w/o Resolution): F1 84.99, DR 75.91, FPR 1.82 | Table II |
| C2 | CARE: F1 85.64, DR 75.91, FPR 0.91 | Table II |
| C3 | PromptOnly: F1 66.99, DR 63.18, FPR 17.02 | Table II |
| C4 | LLMJudge: F1 73.09, DR 67.27, FPR 11.25 | Table II |
| C5 | NeMo Guardrails: F1 68.63, DR 58.18, FPR 7.60 | Table II |
| C6 | CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge | Sec. V-A1, Table VIII |
| C7 | Resolution lowers FPR 1.82 → 0.91 at unchanged DR | Sec. V-A1 |
| C8 | Only about 4.2% (23/549) of commands reach the LLM | Abstract; App. A.F |
| C9 | No DANGEROUS command is converted to ALLOW by the judge | App. A.F |
| C10 | CARE has the highest F1 of the compared guards | Table II |
| C11 | Mean latency 0.34 ms (static) and 2.32 ms (full) | Table II |

## 3. Methodology matrix

Confidence: **E** = explicit in the paper or code; **I** = inferred; **U** = unknown, so we
chose and documented a value.

| Choice | Paper specification (location) | Original artifact | This reproduction | Conf. | Decision |
|---|---|---|---|---|---|
| Corpora | ART, RedCode-Exec (bash), NL2Bash, 12 canonical attacks, 30 real-world commands (Table I) | not released | ART `a0e3f9b`, RedCode `664e479`, NL2Bash `d6b9f5b` (`config.yaml`) | E (sources) / U (versions) | D12, variant V3 |
| Evaluated commands | 549 = 220 DANGEROUS + 329 SAFE, a 30% evaluation partition of a 1,862-record pool (Table I, Sec. IV-B) | not released | **every** unique command of the corpora: 11,665 (§4) | E (paper) / deviation | D1, D24 |
| Comparison with Table II | metrics of the 549-command split | — | the paper's composition re-drawn 10,000 times from the population; mean and σ (§6) | — | D25, D29 |
| Split composition | 137 ART + 12 canonical + 71 RedCode + 299 NL2Bash + 30 real-world (Table I) | not released | identical counts per paper-sized split | E | — |
| Template family | "ART YAML or NL2Bash template" (Sec. IV-B) | not released | ART = technique YAML; NL2Bash = lexical mask of strings, paths, globs and numbers | I | D11 |
| NL2Bash sampling | "head-stratified" (Table I); cap 12 per head stated for the RQ3 pool | not released | cap 12 per head in each paper-sized split | I | — |
| NL2Bash SAFE hygiene | not stated for the main split; the RQ3 pools filter dangerous tokens (Table I) | — | 284 commands with "unconditionally dangerous" operations are run but not counted as SAFE | U | D5, D27, variant V1 |
| Canonical attacks (12) | "released with the dataset" (Sec. IV-B); not found in the artifact | absent | slots filled from ART | U | D2 |
| Real-world SAFE (30) | build/lint/git/container commands (Table I) | absent | `data/manual/real_world_commands.txt` | U | D4 |
| RedCode unit | "bash subset" (Table I) | — | each script, stripped of shebang and comments, is one command; scenarios are strata | U | D3 |
| Labels | one class per corpus (Table I) | — | same (corpus-level) | E | D17 |
| CARE implementation | Sec. III, Alg. 1, App. A | release `81dd742` | unmodified (checked on every run) | E | D13 |
| Thresholds and weights | τ = 0.15/0.35; w = .3/.3/.3/.1; θ_rule = .8, θ_sem = .7 (App. A.E–F) | same in code | code defaults | E | — |
| Skip predicates | H_sem, p_rule, p_spath as in App. A.F | code differs from the paper | **released code** | E (conflict) | D14 |
| Judge model | Qwen3-Coder-30B-A3B-Instruct on vLLM (Sec. IV-D, App. E); reference [25] cites *Qwen3-4B-Instruct-2507* | env var `CARE_LLM_MODEL` | `qwen/qwen3-coder-30b-a3b-instruct` via OpenRouter, pinned to Amazon Bedrock | E (text) / conflict ([25]) | D6 |
| Precision / quantisation | not stated | — | provider-side, not exposed | U | D6 |
| Decoding | temperature 0; max_tokens 8 (CARE, PromptOnly, LLMJudge), 4 (NeMo); single-shot (App. E) | CARE code: same | same | E | — |
| Prompts | verbatim (App. E, Prompts 1–4) | CARE prompt in code (identical) | verbatim | E | — |
| Output parsing | App. E mappings | CARE code: 'DANGEROUS' or 'UNSAFE' in answer → DENY | CARE: code; baselines: App. E (NeMo: anything but "yes" → ALLOW) | E / I | — |
| Error policy | CARE fails closed (DENY); baselines: on_parse_error = ALLOW (App. E) | CARE code: DENY | same; 6 retries before the policy applies | E | — |
| NeMo Guardrails | NeMo v0.9 `self_check_input` rail (App. E) | not released | the prompt sent as one user message, without the framework | E (prompt) | D7 |
| Other baselines | Regex, ClawGuardSim, OpenClaw4Layer, Granite Guardian 2B, Llama Guard 3-8B, GPT-OSS-Safeguard-20B | not released / not served | not run | — | D8 |
| Metrics | DR, FPR, F1; latency = mean wall-clock (Sec. IV-E) | — | same formulas (`repro/stats.py`) | E | — |
| Statistics | McNemar two-sided with Yates (Table VIII) | — | the same test, applied to every paper-sized split | E | D25 |
| Hardware | 4×H100, local vLLM (Sec. IV-D) | — | laptop CPU and a hosted API | E | latency not comparable |

## 4. Population

Every unique command of the pinned corpora is evaluated (`data/population.parquet`, rebuilt
from the sources and checked on every run).

| Source | Class | Commands | Notes |
|---|---|---|---|
| Atomic Red Team | DANGEROUS | 415 | every Linux sh/bash atomic test (117 techniques) |
| RedCode-Exec (bash) | DANGEROUS | 598 | every bash script (20 risk scenarios) |
| NL2Bash | SAFE | 10,338 | |
| Real-world | SAFE | 30 | written for this reproduction (D4) |
| **Primary population** | | **11,381** | 1,013 DANGEROUS / 10,368 SAFE |
| NL2Bash, set aside | — | 284 | perform an operation the paper calls unconditionally dangerous (D5). Run, reported separately, in no metric (D27) |

* **Labels** are corpus-level, the paper's own convention (Table I). Metrics therefore measure
  agreement with that labelling scheme, not audited harmfulness.
* **Removed:** `hostname` and `history -c` occur in both ART and NL2Bash with conflicting
  labels (D10).

## 5. Conditions and execution

* **Conditions:** NoGuard, PromptOnly, LLMJudge, NeMo self-check, CARE (w/o Resolution) and
  CARE. The other six Table II rows are not run (D8).
* **Static conditions** (NoGuard, CARE w/o Resolution) are deterministic. They run once, and
  the notebook asserts determinism with a second pass.
* **LLM conditions** run **3** times on the full population. **Run 1 is the primary run**
  (fixed in advance); runs 2 and 3 measure the nondeterminism of hosted serving.
* **Run label:** `confirmatory-v2-r{1,2,3}`, with a fresh call cache: no v1 reply is reused.
* **Failures:** every call error is recorded. A failed call is never dropped: after 6 retries
  it falls to the method's error policy and counts toward the metrics.
* **Latency** is recorded but not comparable to the paper (hardware and serving differ).

## 6. Metrics and the comparison with the paper

**Metrics.** F1, DR and FPR in %, with DANGEROUS as the positive class and DENY as the
positive prediction (paper Sec. IV-E).

Results are reported in two views of the same decisions:

1. **Full corpora.** DR on all 1,013 DANGEROUS commands and FPR on all 10,368 SAFE commands,
   in total and per corpus. These are exact counts; nothing is sampled. F1 on the full corpora
   is reported too, but it is **not** comparable with the paper's F1: F1 depends on the class
   mix, which is 9% DANGEROUS here and 40% in the paper's split.

2. **Paper-sized splits.** Every number in the paper is a statistic of one 549-command split.
   To compare like with like, the paper's composition (Table I) is re-drawn from the
   population **10,000 times** (seeds 0–9,999) with the split recipe of v1 (`paper_sized_splits.SplitRecipe`):
   * ART: whole technique families in random order until 149 commands;
   * RedCode-Exec: round-robin over the 20 scenarios, random scripts within each, 71 commands;
   * NL2Bash: whole template families until 299 commands, at most 12 per command head;
   * Real-world: the 30 commands.

   Each statistic is computed on every split from the decisions already made. We report its
   **mean** (the value the paper's procedure yields on average on this population) and its
   standard deviation over the splits, **σ**.

**Reading σ.** σ is not a standard error and "mean, σ" is not a confidence interval. It says
how much a statistic varies between 549-command splits drawn this way from these corpora. A
value counts as *apart* from the mean when it is more than **1.96σ** away, the distance that
leaves out 5% of a normal distribution; over the 10,000 splits the statistics are close to
normal, with a slight lean to the left. A reported value that far from the mean is one that no
plausible split of this recipe produces on our population. It cannot say why: the authors'
pool may differ from ours (§10).

**Comparison with Table II** uses the paper-sized splits of the primary run, with the
full-corpora value alongside.

## 7. Verdict rules

Outcomes are *supported*, *not supported (on this reconstruction)* or *inconclusive*.

| Claims | Evidence | Rule |
|---|---|---|
| C1–C5 (F1), C8 (escalation rate) | paper-sized splits, primary run | *not supported* if the reported value is more than 1.96σ from the mean; otherwise *inconclusive (not contradicted)*. A value within 1.96σ is not evidence of equivalence. DR and FPR are reported descriptively |
| C6 | paired difference in accuracy, CARE (w/o Resolution) minus PromptOnly, and minus LLMJudge, on each paper-sized split | *supported* if the mean difference is more than 1.96σ above 0 for both pairs; *not supported* if it is more than 1.96σ below 0 for either; otherwise *inconclusive*. The paper's McNemar test is applied to every split and reported descriptively |
| C7 | full corpora, primary run | *supported* if FPR(CARE) < FPR(CARE w/o Resolution) at equal DR, otherwise *not supported*; evaluated under corpus-level and under audited labels (below); if the two disagree, *inconclusive (label-sensitive)* |
| C9 | full corpora, all runs | *supported* if the judge allows no DANGEROUS command, otherwise *not supported*; same two label sets as C7 |
| C10 | paired difference in F1, each CARE variant minus each of the 3 comparators, on each paper-sized split | the threshold is **2.39σ**, which holds for the three comparators at once (level 1 − 0.05/3), because the strongest comparator is known only after the results. *supported* if some CARE variant's mean difference is more than 2.39σ above 0 against every comparator; *not supported* if every CARE variant has a comparator against which it is more than 2.39σ below 0; otherwise *inconclusive* |
| C11 | — | always *inconclusive* |

**Audited labels (C7, C9 only).** These claims depend on the few DANGEROUS-labelled commands
that the judge allows. Those commands are re-labelled under the effect-based policy in
`data/label_audit.yaml` (unchanged since v1.1, D17). The selection depends on the predictions
and the auditor is the AI assistant that built the artifact, so this is a sensitivity
analysis only; it never replaces the primary labels (D28). A command that is not audited
keeps its corpus label.

## 8. Secondary analyses (none replaces a primary result)

* **Per source:** DR or FPR of every guard on every corpus; RedCode-Exec per risk scenario.
* **Resolution funnel:** WARN → skipped → escalated → judge ALLOW, per paper-sized split and
  on the full corpora, next to the paper's.
* **Oracle bounds:** the best F1 any Resolution judge could reach on top of the released
  static stack.
* **Construction variants**, each changing one decision (expected F1 on paper-sized splits):
  * V1: the 284 NL2Bash commands set aside by D5 are drawn and counted as SAFE;
  * V2: RedCode software-weakness scenarios are not drawn (*exploratory*, D9);
  * V2b: no RedCode;
  * V3: the ART snapshot of 2026-03-24 (static CARE only; the LLM conditions were not run on it).
* **Run-to-run stability** of the LLM conditions.
* **Consistency with v1:** on the 549 commands v1 evaluated, static decisions must be
  identical, and the agreement of the LLM conditions is reported. This was checked once
  (`DECISIONS.md` L14); the v1 files have since been removed from the artifact (L20).

## 9. Modes and resources

* **`REPRO_MODE=full`** (default): the protocol above.
  * With `OPENROUTER_API_KEY` set, the LLM conditions are queried live: about 106,000 calls,
    30–40 min with 16 workers, about US$2 (estimated from v1's US$0.099 for 5,001 calls).
  * Without a key, the committed `results/observations.parquet` is **reused** after checking
    that the static decisions and the LLM requests are identical to the executed ones. This
    takes a few minutes.
* **`REPRO_MODE=smoke`:** 40 commands, one run, 200 small splits, outputs in `results/smoke/`,
  every report prefixed "SMOKE MODE — NOT A REPRODUCTION".
* **Environment:** Python 3.12 (the lockfile requires it). Sources take about 15 MB as sparse
  clones.

## 10. Limits of what this protocol can show

* It describes **our reconstruction** of the population. The canonical attacks, the authors'
  RedCode filter and their ART snapshot are unknown.
* A reported value within 1.96σ of our mean does not show that the paper's result is
  reproduced, and a value beyond it does not show why it is not. In particular, we cannot separate "the authors'
  commands differ from ours" from "the rule bank was fitted to their pool".
* Labels are corpus-level and unaudited, except for the sensitivity analysis of C7 and C9.
* Hosted serving at unknown precision replaces local vLLM; NeMo is emulated; six baselines are
  not run.

## 11. Disclosure: what was known when v2.0 was frozen

* **Known:** all v1 results (in git history at commit `57ac042`), including three rounds of external
  review. The v2 verdict rules are the v1.3 rules with the spread over paper-sized splits in
  place of the bootstrap interval, and C7/C9 evaluated on the full corpora.
* **Not known:** any v2 result. Before the freeze, the pipeline was exercised only on 40
  commands with a stubbed LLM client (no real replies).
* **Decided after the run, and disclosed as such:**
  * the audited labels of the commands the judge allows (§7), which cannot be selected before
    the predictions exist;
  * v2.1: reporting the spread as σ and stating the rules in σ. This was chosen with the
    results known, to make the tables easier to read. All 15 Table II comparisons, the
    escalation rate and all 12 paired differences fall on the same side under both rules.

## 12. Using this baseline for a new method (matched protocol)

* Run the new method on **every** command in `data/population.parquet` (same `command_id`s).
  Only rows with `in_primary` count toward metrics.
* Report DR and FPR on the full corpora, and F1 on the paper-sized splits drawn with the same
  seeds:

  ```python
  from repro import stats
  from repro.paper_sized_splits import SplitRecipe, Splits

  recipe = SplitRecipe(population, configuration["paper_sized_splits"]["composition"], head_cap=12)
  splits = Splits(range(10_000), recipe.draw(range(10_000)))
  rates  = stats.rates(stats.split_counts(population.label_dangerous, your_deny_decisions, splits.rows))
  ```
* Compare against the *observed* rows in `results/observations.parquet`, paired on
  `command_id`, not against the paper's numbers. Comparing against several baselines needs
  the simultaneous threshold, as for C10.
* Any LLM component must use a pinned model and provider, at least 3 runs, and a primary run
  fixed in advance.
