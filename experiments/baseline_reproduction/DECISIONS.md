# Decision and deviation log (append-only)

Entries are never edited or removed. A correction is a new entry that references
the old one. Two kinds of entry:

* **D-entries** are methodological decisions. Each gives the change, the
  rationale, the evidence, the expected impact, and the experiments it affects.
* **L-entries** are process events: runs, audits, and changes to the artifact.

All dates are 2026-11-07 (UTC) unless stated.

## Where things stand (index, not an entry)

The current protocol is **v2.1** (`PROTOCOL.md`): every guard is run on every command of the
corpora, and the spread over paper-sized splits is reported as σ. Entries D1–D23 and L1–L11 were written for protocol v1, which evaluated one
549-command sample (`archive/v1/`). This table says which of them still apply.

| Entries | Topic | Status under v2.0 |
|---|---|---|
| D1–D4 | population rebuilt from public corpora; canonical slots; RedCode unit; real-world commands | in force |
| D5 | NL2Bash label hygiene | in force; the commands it sets aside are now run and reported separately (D27) |
| D6–D8 | LLM serving; NeMo emulation; baselines not run | in force |
| D9, D10 | RedCode scenario kinds (diagnostic); conflicting labels removed | in force |
| D11 | whole template families, no dev partition | in force for the paper-sized splits; what is *run* is now everything (D24) |
| D12–D14 | ART snapshot; CARE unmodified; paper/code conflict | in force |
| D15, D19, D22 | cluster bootstrap, recipe bootstrap, coverage simulation | **superseded by D25** (paper-sized splits) |
| D16, D21, D23 | descriptive comparisons; direction-only verdicts; simultaneous comparators | in force, restated in D26 |
| D17 | corpus-level labels; label audit for C7 and C9 | in force; extended by D28 |
| D18, D20 | LLM cache identity; reuse gated on request identity | in force |
| D24–D28 | full corpora; paper-sized splits; verdict rules v2.0; set-aside commands; label audit | protocol v2.0 |
| L1–L11 | pilot, v1 confirmatory run, reviews and refactors | v1 history |
| D29 | spread reported as σ; verdict rules stated in σ | protocol v2.1; replaces the percentile range of D25 and D26, verdicts unchanged |
| L12– | v2 restructure, freeze, confirmatory run, clean clone | protocol v2.0–v2.1 |

---

### D1: Rebuild the main split from public corpora
* **Change:** we rebuilt the 549-command split rather than using the authors' split.
* **Rationale:** the split, the 1,862-record pool and the curated subsets are not
  in the artifact. Sec. IV-B says the curated subsets "are released with the
  dataset", but no such dataset is linked from the repo or the project page.
* **Evidence:** repo tree at `9d6852e`; `docs/index.html`; README ("ships only the
  CARE method — no baselines and no experiment harness").
* **Expected impact:** different items, same class mix, so absolute numbers can
  differ in either direction.
* **Affects:** all experiments.

### D2: Canonical-attack slots (12) filled from ART
* **Change:** the 12 slots are filled with 12 extra ART commands; we do not
  write our own canonical attacks.
* **Rationale:** the paper's examples (curl|bash, fork bomb, `chmod 777
  /etc/sudoers`) are exactly the patterns targeted by CARE's 16 Manual-Cases
  rules (App. A.D). Writing them ourselves would hand-pick items that CARE
  detects by construction.
* **Expected impact:** CARE's DR is lowered relative to the paper by at most
  12/220 = 5.5 pp, if all 12 canonical attacks were detected. The pilot gap is
  32 pp, so D2 cannot explain it alone.
* **Affects:** C1, C2, C6, C10.

### D3: RedCode-Exec unit of analysis
* **Change:**
  * each script, with shebang, comment-only and blank lines stripped, is one
    command;
  * the 20 risk scenarios are used as strata, not grouping units;
  * sampling is a seeded round-robin across scenarios (3–4 items each).
* **Rationale:** the paper does not describe its RedCode filter. Grouping by
  scenario would place only about 2 of the 20 scenarios in a 71-item sample.
* **Expected impact:** includes CWE-style "software-weakness" scenarios that no
  shell guard can flag (see D9).
* **Affects:** C1–C10.

### D4: Real-world SAFE commands (30)
* **Change:** we use the 30 commands in `data/manual/real_world_commands.txt`.
* **Provenance:** the file already existed (untracked) in the workspace when this
  reproduction session started. Its header says it was written for this
  reproduction. Its author is not recorded, and it may have been produced with
  AI assistance.
* **Expected impact:** small. In the pilot every method had FPR 0/30 on these.
* **Affects:** FPR for all conditions.

### D5: NL2Bash label hygiene
* **Change:** we drop NL2Bash commands matching the operations the paper itself
  calls "unconditionally dangerous", which are sudo, shred, kill -9, root chown,
  SUID chmod and writes under /etc/ (Table I, adversarial-benign row). We also
  drop mkfs/fdisk, `dd of=/dev`, `rm -r /` and fork bombs. This removes 284 of
  10,624 unique commands.
* **Rationale:** a SAFE label must be correct. NL2Bash is a translation corpus,
  not a safety corpus.
* **Expected impact:** lowers FPR for every method. Variant V1 (filter off) is
  reported.
* **Affects:** FPR, F1.

### D6: LLM serving
* **Change:** `qwen/qwen3-coder-30b-a3b-instruct` via OpenRouter, pinned to
  `Amazon Bedrock` with `allow_fallbacks=false`, temperature 0, and max_tokens
  as in App. E. The paper served the model on local vLLM.
* **Paper inconsistency:** Sec. IV-D and App. E name Qwen3-Coder-30B-A3B-Instruct,
  but reference [25] cites "Qwen3-4B-Instruct-2507". We follow the text, since it
  is stated four times and matches the code default.
* **Unknowns:** Bedrock's precision and quantisation are not exposed. Hosted
  serving is not deterministic at temperature 0, so we use R = 3 runs.
* **Affects:** C2–C9.

### D7: NeMo Guardrails emulation
* **Change:** the App. E `self_check_input` prompt is sent as a single user
  message without the NeMo framework. "yes" maps to DENY and anything else to
  ALLOW.
* **Expected impact:** NeMo wraps the prompt in its own template. Treat this row
  as an approximation of the paper's NeMo row.
* **Affects:** C5.

### D8: Baselines not run
* Regex (its 22 rules are unreleased).
* ClawGuardSim and OpenClaw4Layer (author ports unreleased).
* Granite Guardian 2B and Llama Guard 3-8B (not served on OpenRouter; checked
  2026-11-06).
* GPT-OSS-Safeguard-20B: served, but it needs a policy prompt and the paper
  states only "vendor-supplied prompts", which do not exist for this task.
* **Affects:** C10 coverage (6 of 12 rows).

### D9: RedCode scenario kinds (exploratory)
* **Change:** we label scenarios {12, 15, 16, 20, 22, 23, 25} *software-weakness*
  and the others *operational*. We made this call ourselves from each
  scenario's task text, after seeing the pilot. It is used only in diagnostic
  tables and variant V2.
* **Affects:** diagnostics only.

### D10: Cross-source conflicting labels removed
* **Change:** `hostname` and `history -c` occur in both ART (DANGEROUS) and
  NL2Bash (SAFE), so both are dropped from every pool.
* **Trigger:** found by a duplicate-command assertion while building
  alternative-seed splits after pilot run A (L1). Not a score-driven change.
* **Side effect:** the seed-42 draw changed (190 `command_id`s differ from pilot
  run A's split). We re-ran on the new split (L2).
* **Affects:** all experiments.

### D11: Leakage control without a dev partition
* **Change:** we draw whole template families in seeded order until each target
  is reached. We do not reconstruct the 70/30 dev:eval partition.
* **Rationale:** we tune nothing, so no dev partition is used. A strict 30 % of
  the 415 ART commands (117 techniques) gives about 125, short of 149.
* **Expected impact:** sibling commands are never split across a sampled and an
  unsampled family.
* **Affects:** split composition.

### D12: ART snapshot date
* **Change:** we use ART HEAD of 2026-11-06. ART adds tests over time, and the
  paper's snapshot is unknown.
* **Expected impact:** possibly more recent techniques than the paper's pool.
  Variant V3 rebuilds the split with the 2026-03-24 snapshot.
* **Affects:** C1, C2.

### D13: CARE run unmodified
* **Change:** we only replace CARE's lazily created OpenAI client with
  `PinnedClient`, which adds provider pinning and records metadata. No `.patch`
  is applied. `care/` is byte-identical to release commit `81dd742`, verified
  with `git diff 81dd742 9d6852e -- care/`.
* **Affects:** none methodologically.

### D14: Skip-predicate conflict, paper vs code
* **Conflict:** App. A.F defines H_sem, p_rule and p_spath differently from
  `care/resolution.py` (see PROTOCOL §3).
* **Change:** the primary target is the released code, as the author artifact.
* **Impact bound:** the predicates only decide which WARN commands reach the
  judge. The oracle analysis shows how much any judge could change F1, which
  bounds the effect of this conflict.
* **Affects:** C2, C7–C9.

---

### L1: Pilot run A (first pass, before any protocol)
* **Run:** 2026-11-07, about 05:00 UTC. Static methods and R = 3 LLM runs on the
  first seed-42 split, 5,007 calls with 0 errors.
* **Observed:** we saw the static CARE result (F1 57.8) *before* the LLM runs,
  and briefly checked the harness. Unit tests passed, the `workspace` argument
  was confirmed unused, and multi-line handling was checked. No CARE settings
  were changed.
* **Archive:** `results/pilot/pilot_llm_calls.parquet` (rows with
  `in_final_pilot_split == False` are calls exclusive to run A).

### L2: Pilot run B (after D10)
* **Run:** same code on the D10 split, reusing cached calls for unchanged
  commands; 0 errors.
* **Reported:** in the first draft PR.
* **Archive:** `results/pilot/pilot_observations.parquet`, `pilot_SUMMARY.md`,
  `pilot_run_metadata.json` and `figures/`. The pilot recorded no token usage,
  cost or request timestamps.

### L3: Self-audit against the baseline-reproduction checklist
Findings about the first pass:

1. No notebook entry point.
2. No protocol was frozen before execution; the success criterion was chosen
   after the static result was seen.
3. No token, cost or timestamp records.
4. No data checksums or environment lock.
5. No unit tests for the metrics or parsing.
6. The D14 paper/code conflict and the [25] model-reference conflict were not
   documented.
7. The paper version was not recorded.
8. The PR used ✅/❌ verdicts without the population caveat.
9. The provenance of the real-world file was not disclosed (now D4).
10. No RedCode CC BY 4.0 attribution.
11. The pilot call cache was not preserved in the repo.

Remedies: the protocol v1.0, the notebook, the `repro/` package with tests,
fingerprints, the lockfile, the archived pilot, and the confirmatory run (L4).
The first-pass scripts (`build_dataset.py`, `run_eval.py`, `analyze.py`,
`figures.py`, `fetch_sources.sh`) are replaced by `repro/` and the notebook. They
remain in git history at commit `c7cad18`. The refactored builder regenerates
the pilot-B split byte-for-byte.

### L4: Confirmatory run (protocol v1.0)
* **Run:** 2026-11-07 06:50:35–06:52:03 UTC, through the notebook in `REPRO_MODE=full`
  with a live LLM. The protocol had been frozen at `de2bc54` and pushed before
  the run.
* **Volume and quality:** 5,001 calls. 0 errors, 0 retries, every call served
  by `Amazon Bedrock`. 612,561 prompt and 13,516 completion tokens, US$0.0990.
* **Checks:** the static decisions equal those of pilot B, and the confirmatory
  LLM conclusions match the pilot.
* **Archive:** `results/executed/confirmatory_live_run.{ipynb,provenance.json,validation.json}`.

### L5: Notebook code change after the confirmatory run (non-methodological)
* **Change:** after L4, the notebook's *reuse-mode* branch was changed so that it
  no longer rewrites `observations.parquet` and keeps the live run's LLM
  provenance. One validation key was renamed from `llm_executed` to
  `llm_executed_in_this_session`. No data, prompt, model, parsing or metric
  code changed.
* **Re-execution:** the committed notebook was then re-executed in reuse mode.
  The static guards were re-run and the LLM observations reused. All 11 output
  tables were identical (`DataFrame.equals`) to the confirmatory outputs. The
  live-run notebook is preserved as executed.

### L6: Clean-clone validation
* **Setup:** a fresh `git clone` of `experiment/baseline-reproduction` at
  `45c49c1` from GitHub, a fresh Python 3.12 venv built from
  `environment/requirements.lock.txt` (no lockfile mismatches), and the notebook
  executed top to bottom.
* **Full mode, no API key (reuse):** 25 s. Sources were re-fetched and verified,
  the split was rebuilt identically, 56 tests passed, and the static guards were
  re-executed and matched the committed observations. **Every Parquet output,
  `report.md` and both figures regenerated byte-identical.** Only the timestamps
  and timings in `provenance.json` and `validation.json` differ.
* **Smoke mode, live API:** passed, with 0 errors.
* **Record:** `results/executed/clean_clone_validation.json`.
* **Provenance note:** the committed `results/provenance.json` records
  `repo_head = de2bc54`. That execution (L5) ran on a working tree in which the
  notebook and a display-only label change in `repro/report.py` ("single run"
  vs "deterministic" for single-run LLM rows, made before L4) were not yet
  committed. The clean-clone record confirms the committed state at `45c49c1`
  reproduces the same outputs.

### L7: Notebook readability refactor (non-methodological)
* **Date:** 2026-11-07, after L6.
* **Change:**
  * The orchestration code moved out of the notebook into `repro/pipeline.py`, one function per stage,
    in execution order. Each stage takes its inputs as arguments and returns its outputs.
  * Each notebook section is now a question, one short code cell, and the table that answers it.
  * Results (§6) come before the diagnostics (§7), and each diagnostic asks one question.
  * The verbatim protocol, environment JSON and inventory moved to appendices.
  * Display views (`headline`, `by_source_view`, `redcode_view`, and others) moved into `repro/report.py`.
    `results_markdown` now builds `report.md` from the same views.
  * Three tests were added: the API key is never shown, the reuse-mode switch, and the headline view.
* **Unchanged:** data, prompts, model, parsing, metric code, claim rules and every analysis call.
* **Verification:** the notebook was re-executed in reuse mode. All 11 Parquet tables, `observations.parquet`,
  `report.md` and both figures are **byte-identical** to those of L5/L6. In `provenance.json`, only the timestamps,
  stage timings, the test summary and `repo_head` differ.

---

Entries below follow the external review in L8. They are post-confirmatory. None
changes data, prompts, model, runs or metric formulas.

### D15: Design-based uncertainty (protocol v1.1 §11.1)
* **Change:** inferential 95% CIs for F1, DR, FPR, paired differences and the
  escalation rate now come from a bootstrap that mirrors how the split was
  drawn:
  * whole families are resampled within ART, NL2Bash and Real-world;
  * commands are resampled within each RedCode scenario.
* **Kept for paper fidelity:** the per-command Wilson, bootstrap and McNemar
  results.
* **Rationale:** the 149 ART commands come from 41 families, one of which has 21
  commands. Per-command CIs assume independence and are too narrow. For
  example, static CARE's F1 CI is [52.1, 64.9] per-command but [45.9, 69.1]
  design-based.
* **Evidence:** reviewer finding R2. `results/design_intervals.parquet` and
  `design_differences.parquet`.
* **Expected impact:** wider intervals, and paired differences that no longer
  reach significance (C6, C10).
* **Affects:** all verdicts (v1.1).

### D16: Comparisons are descriptive; verdicts no longer treat CI inclusion as reproduction (protocol v1.1 §11.2, §11.4)
* **Change:**
  * every Table II comparison is marked *not directly comparable*;
  * the `status` wording is now "reported inside/outside observed 95% CI";
  * new verdict rules (§11.4). Numeric claims can only be *not supported (on
    this reconstruction)* or *inconclusive (not contradicted)*.
* **Rationale:** when an interval fails to exclude a value, that does not show
  equivalence; the population, serving and NeMo framework all differ. This
  is reviewer finding R3.
* **Expected impact:** C3, C4, C5 and C8 change from *supported* to
  *inconclusive*. C1 and C2 stay *not supported*. The v1.0 verdicts are kept in
  `claims.parquet`.
* **Affects:** C1–C11.

### D17: Labels are corpus-level; label sensitivity for C7 and C9 (protocol v1.1 §11.3)
* **Change:**
  * Metrics are stated to measure agreement with corpus-level labels, the paper's
    Table I convention.
  * The commands on which CARE and CARE (w/o Resolution) disagree are
    re-labelled under an explicit effect-based policy (`data/label_audit.yaml`):
    3 commands, all judged SAFE.
  * C7 and C9 are evaluated under both label sets.
* **Rationale:** under corpus-level labels these 3 items alone make Resolution
  "lose recall" (C7) and "allow dangerous commands" (C9), but their content is
  benign:
  * a base64 greeting round-trip (2 ART T1140 tests);
  * an in-memory array lookup (RedCode 25_10).
  This is reviewer finding R1.
* **Limits:**
  * The selection depends on the predictions.
  * The auditor is the AI assistant that built the artifact, so the audit is not
    blind and not independent.
  * It is used only for a sensitivity analysis; it never replaces the primary
    labels. A full independent audit of all 549 labels was **not** done.
* **Expected impact:** C7 and C9 change from *not supported* to *inconclusive
  (label-sensitive)*. Under the audited labels, CARE F1 is 57.94 and CARE (w/o R)
  F1 is 57.41.
* **Affects:** C7, C9.

### D18: LLM cache identity and reuse provenance
* **Change:**
  * Cached replies are keyed by a request fingerprint: model, endpoint, provider
    pin, fallbacks, temperature, max_tokens, and the prompt template (for CARE,
    the SHA-256 of `care/`).
  * Every row now records the `model` and `request_fingerprint` that were sent,
    and whether the reply came from the cache (`from_cache`).
  * A live run reports `cached_rows`.
  * Reuse mode asserts that every committed reply was requested inside the live
    run's time window and has a unique generation id.
* **Rationale:** a cache keyed only by (condition, run, command) could attribute
  old replies to a new model. This is reviewer finding R5.
* **Committed run:** this does **not** affect the committed run. Its 5,001 replies
  all fall within 06:50:35–06:52:03 UTC on 2026-11-07, with unique generation
  ids; this is now checked on every reuse.
* **Affects:** provenance only.

### L8: External review, round 1 (Codex, gpt-6.1-sol, high effort)
* **Review:** an independent review of PR #1 at `7ecde67` against the
  baseline-reproduction rubric. Verdict: **REVISE**.
* **Findings:**
  * R1 (BLOCKER): source-derived labels drive C7 and C9 → D17.
  * R2 (MAJOR): uncertainty ignores family clustering → D15.
  * R3 (MAJOR): CI inclusion was used as "supported" across non-comparable
    protocols → D16.
  * R4 (MAJOR): the discrepancy analysis overreached ("split construction is
    not the cause"; "not uniformly harder") → wording in §11.5, the notebook,
    the README and the PR, now scoped to this population and recipe.
  * R5 (MAJOR): cache identity → D18.
  * R6 (MINOR): smoke mode without a key failed. It now reuses the smoke subset
    of the committed full run.
  * R7 (MINOR): the contract and protocol appeared after the results in the
    notebook. They are now §2, before execution.
* **What the reviewer verified:** 59 tests pass; byte-identical regeneration at
  `7ecde67`; the paper's SHA-256 matches.

### D19: Recipe bootstrap replaces the v1.1 cluster bootstrap for inference (protocol v1.2 §12.1)
* **Change:** inferential CIs now re-run the split recipe on the sample:
  * ART and NL2Bash: families are drawn until each source quota is reached; the
    last family is truncated; NL2Bash applies the head cap;
  * RedCode-Exec: commands are drawn within each scenario;
  * Real-world: the fixed subset is kept as is.
  The v1.1 cluster bootstrap is still reported (`estimator = cluster`).
* **Rationale:** reviewer finding F1 (L9). The v1.1 bootstrap let the source
  totals vary: ART ranged from 67 to 268 commands across resamples, and class
  prevalence from 29.6% to 50.7%. It also broke the NL2Bash head cap and
  resampled the deterministic real-world subset.
* **Evidence:**
  * The recipe bootstrap keeps every source total fixed and the head cap
    respected (unit-tested).
  * Calibration against the recipe's true sampling distribution for static CARE
    (100 re-drawn splits): the SD is 4.38 pp for the true distribution, against
    6.15 pp for the recipe bootstrap and 5.96 pp for the v1.1 cluster
    bootstrap. Both bootstraps are therefore conservative; the main reason is
    that they ignore the finite-population correction.
* **Impact:**
  * C10's interval for LLMJudge − CARE (w/o R) moves from [−0.19, 27.30] (v1.1)
    to [0.34, 26.75].
  * C10 becomes *not supported (on this reconstruction)*. It is flagged
    BORDERLINE: the lower bound is within 0.5 pp of 0, so the verdict depends on
    the estimator.
* **Affects:** all design-based CIs, C6, C8, C10.

### D20: Reuse is gated on request identity
* **Change:**
  * Added `results/llm_request_identity.json`.
  * Reuse now asserts:
    * the current request fingerprints equal the executed ones;
    * the requested configuration equals the executed configuration;
    * the observations record the executed model, served only by pinned
      providers.
  * Provenance stores `requested_config` and `executed_request_identity`
    separately; previously only the requested configuration was written.
  * Live runs write the identity file at execution.
* **Legacy run:** for the committed confirmatory run, the identity was
  *reconstructed* after the run. The executed configuration was copied from
  `results/executed/confirmatory_live_run.provenance.json`. The fingerprints were
  recomputed with the D18 recipe from the prompt builders and `care/` sources at
  `de2bc54`, the commit the live run executed, extracted with
  `git archive de2bc54 care experiments/baseline_reproduction/repro`. They equal
  the fingerprints of the current code (`care/` and the prompt constants are
  unchanged since `de2bc54`). The file records this as `how_established`. The
  observations keep their legacy schema, without per-row fingerprints.
* **Rationale:** reviewer finding F3 (L9). Reuse could accept a different
  configured model and write it into provenance.
* **Affects:** provenance only.

### D21: Directional claims are judged on direction only (protocol v1.2 §12.2)
* **Change:** C6 is *inconclusive* unless the interval of the paired accuracy
  difference excludes 0. Whether the paper's effect size lies inside the
  interval is now reported descriptively and no longer drives the verdict.
* **Rationale:** reviewer finding F2 (L9). The v1.1 rule rejected a directional
  claim because a magnitude was excluded, while it accepted any positive
  difference as support.
* **Impact:** C6 changes from *not supported* (v1.1) to *inconclusive*. Both
  intervals contain 0:
  * vs PromptOnly: +2.0 pp [−5.3, 8.2];
  * vs LLMJudge: −3.5 pp [−10.4, 2.2].
  Both exclude the paper's effects (+14.2 and +9.1 pp).
* **Affects:** C6 and C10 (C10 already used the direction-only rule).

### L9: External review, round 2 (Codex, gpt-6.1-sol, high effort)
* **Review:** of `e365f10`. Verdict: **REVISE**, with no blocker.
* **Round-1 status:**
  * R1, R3, R4, R6 and R7 resolved;
  * R2 and R5 partially resolved.
* **New findings:**
  * F1 (MAJOR): the bootstrap did not match the sampling design → D19.
  * F2 (MAJOR): the C6 rule mixed direction and magnitude → D21.
  * F3 (MAJOR): reuse did not check request identity → D20.
  * F4 (MINOR): the main figure showed per-command CIs while the PR said every
    interval was design-based. The figure now draws the recipe-bootstrap CIs.
  * F5 (MINOR): the stated Python requirement was ≥3.10 but the lockfile needs
    ≥3.12 → PROTOCOL §12.4; the notebook, README and PR now say 3.12.
  * F6 (MINOR): the PR described the old notebook layout → PR updated.
* **What the reviewer verified:**
  * 67 tests pass;
  * byte-identical regeneration;
  * the v1.0 verdicts equal those at `7ecde67`;
  * the post-hoc amendment and the scope of the label audit are adequately
    disclosed.

### D22: Recipe bootstrap completed and its coverage checked by simulation (protocol v1.3 §13.1–13.2)
* **Change:**
  * Family truncation now follows corpus order, using `dataset.corpus_order`.
  * The RedCode remainder allocation is random in each resample.
  * Interval coverage is checked by simulation:
    `results/bootstrap_coverage.parquet`, deterministic guards, 100 evaluated
    splits, and a target taken from 200 independent splits.
  * The claim that the intervals are "conservative" is withdrawn.
* **Rationale:** reviewer findings G1 and G2 (L10):
  * the bootstrap truncated in `command_id` order, which differs from corpus
    order in 19 of 41 ART families;
  * it fixed the seed-42 RedCode allocation;
  * an SD comparison does not establish coverage.
* **Evidence:** nominal 95% coverage (Monte Carlo SE about 2.4 pp):

  | Quantity | Recipe bootstrap | v1.1 cluster bootstrap |
  |---|---|---|
  | Static CARE F1, DR, FPR | 94%, 94%, 93% | 96%, 96%, 93% |
  | Keyword-guard F1 | 98% | 98% |
  | Paired ΔF1 | 94% | 93% |
  | Paired Δaccuracy | 93% | 93% |

  The recipe bootstrap's coverage is consistent with the nominal 95%. LLM
  conditions cannot be simulated without new calls; their coverage is assumed
  by analogy.
* **Impact:** the intervals move by at most about 0.4 pp; for example static
  CARE F1 is now [45.8, 69.3]. No verdict changes because of D22 alone.
* **Affects:** all design-based CIs.

### D23: C10 inference is simultaneous over comparators (protocol v1.3 §13.3)
* **Change:** C10 now uses Bonferroni-adjusted intervals over the 3 non-CARE
  comparators, instead of an unadjusted interval against the comparator chosen
  as the best observed F1. The BORDERLINE flag of v1.2 is removed.
* **Rationale:** reviewer finding G3 (L10). Choosing the comparator after
  observing F1 needs a selection adjustment.
* **Impact:**
  * C10 changes from *not supported* (v1.2 rules) to *inconclusive*.
  * LLMJudge − CARE (w/o R): +11.5 pp, adjusted [−1.34, 30.53].
  * LLMJudge − CARE: +12.8 pp, adjusted [0.51, 31.63].
  * The observed ranking, with LLMJudge highest, is reported descriptively.
* **Record:** the v1.2 C10 verdict as recorded at `1f32fd6` is in that commit's
  `results/claims.parquet`. The `outcome_v1_2_rules` column applies the v1.2
  rules with the D22 estimator.
* **Affects:** C10.

### L10: External review, round 3 (Codex, gpt-6.1-sol, high effort)
* **Review:** of `1f32fd6`. Verdict: **REVISE**, with no blocker.
* **Round-2 status:** F2, F3, F4, F5 and F6 resolved; F1 partially resolved. The
  reviewer independently reconstructed all four legacy request fingerprints
  from `de2bc54`, and they matched.
* **New findings:**
  * G1 (MAJOR): truncation order and RedCode remainder → D22.
  * G2 (MAJOR): calibration does not establish coverage → D22.
  * G3 (MAJOR): C10 comparator selection → D23.
  * G4 (MINOR): stale baseline-use instructions and summaries → the README,
    notebook and PR were corrected.
* **Convergence note:** two consecutive rounds found issues in the same area,
  inferential uncertainty. Following the review-loop guard, the estimator was
  completed against the recipe and validated by simulation, rather than patched
  case by case.

### L11: Code-structure refactor for readability (non-methodological)
* **Date:** 2026-11-08, after L10.
* **Change:**
  * `repro/report.py` (767 lines) held six jobs. It is split by responsibility: `analysis.py` (observations →
    metrics, design-based CIs, diagnostics), `sensitivity.py` (static CARE on re-drawn splits, CI coverage),
    `claims.py` (verdicts) and `report.py` (figures, views and `report.md` only).
  * `claims.py`: each claim is one function that returns (outcome, rationale). The v1.3 rules read straight
    through. Each superseded rule set is written as "v1.3 except these claims" (v1.2: C10; v1.1: cluster
    bootstrap, C6 and C10), replacing the `version` branches inside one 11-argument function.
  * `design_bootstrap` (weights built inside, a 3-tuple returned) is replaced by `recipe_weights` /
    `cluster_weights` and `design_intervals`, `paired_differences` and `escalation_rate`, which take the weight
    matrix explicitly. They are bundled per estimator as an `analysis.Design`.
  * `dataset.py` no longer caches pools in a module global (`_POOLS`): `load_pools` then `build_split(pools, …)`.
    The CARE memo for the sensitivity studies is a small class (`StaticCARE`) rather than a dict with a `"_guard"` key.
  * `pipeline.run_llm_guards` is split into `query_llm_guards` (live) and `reuse_llm_observations` (verified
    reuse); the notebook shows the branch. `pipeline.analyse` reads as six numbered steps.
* **Unchanged:** data, prompts, model, parsing, metric formulas, bootstrap code (`stats.py`), claim rules,
  rationale strings and every output.
* **Verification:** the notebook was re-executed in reuse mode, before and after the change. All 16 Parquet
  tables (including `observations.parquet` and `claims.parquet`), `report.md`, `llm_request_identity.json` and
  both figures are **byte-identical** to the committed ones, and so are the output checksums in
  `provenance.json`. Smoke mode passed, and the live path was exercised with a stubbed LLM client. All 61 tests and
  CARE's 10 pass; two tests were updated for the new `build_split` signature.

---

Entries below belong to **protocol v2.0** (2026-11-11). They were written with all v1 results
known and before any v2 result existed.

### D24: Evaluate the full corpora, not a 549-command sample (protocol v2.0 §4)
* **Change:** every guard is run on every unique command of the pinned corpora: 415 ART,
  598 RedCode-Exec, 10,338 NL2Bash and 30 real-world commands (11,381), plus the 284 NL2Bash
  commands set aside by D5 (D27). v1 ran one 549-command draw (seed 42) of these corpora.
* **Rationale:** requested by the maintainer of this reproduction ("instead of using samples
  from the datasets, run the whole thing"). A single draw made every v1 number depend on which
  commands happened to be drawn, and most of v1's complexity (two bootstraps, a coverage
  simulation, a seed sweep) existed only to quantify that.
* **Expected impact:** DR and FPR per corpus become exact counts. The LLM conditions cost about
  20 times more calls (about 106,000). No change to sources, prompts, model, parsing or metric
  formulas.
* **Deviation from the paper:** the paper evaluates 549 commands. The comparison with the paper
  is therefore made on paper-sized splits (D25).
* **Affects:** all experiments. Supersedes the sampling part of D11 for *what is run*; the
  family recipe of D11 is kept for the paper-sized splits.

### D25: Compare with the paper on paper-sized splits (protocol v2.0 §6)
* **Change:** the paper's Table I composition is re-drawn from the population 10,000 times
  (seeds 0–9,999) with the v1 recipe, and every statistic of the paper (F1, DR, FPR, the paired
  differences, McNemar's test, the escalation rate) is computed on each split from the stored
  decisions. We report the mean and the central 95% range.
* **Rationale:** F1 depends on the class mix (9% DANGEROUS on the full corpora, 40% in the
  paper's split), and NL2Bash is 57% `find` commands while the paper's split is head-stratified.
  A like-for-like comparison needs the paper's composition. With decisions for every command,
  the distribution of the paper's statistics over splits is computed directly, for every
  condition, instead of being approximated by a bootstrap on one draw.
* **Continuity:** the recipe is unchanged. Seed 42 regenerates the archived v1 split exactly
  (unit-tested against `archive/v1/main_split.parquet`).
* **Supersedes:** the design-based intervals of D15, D19 and D22 (cluster bootstrap, recipe
  bootstrap, coverage simulation) and the 100-seed sweep, which covered static CARE only.
* **Affects:** every comparison with the paper; C1–C6, C8, C10.

### D26: Verdict rules v2.0 (protocol v2.0 §7)
* **Change:** the v1.3 rules are kept, with the range over paper-sized splits in place of the
  bootstrap interval:
  * numeric claims (C1–C5, C8): *not supported (on this reconstruction)* if the reported value
    lies outside the range, else *inconclusive (not contradicted)* (as D16);
  * C6 and C10: direction only (as D21), C10 with ranges simultaneous over the three
    comparators (as D23);
  * C7 and C9: evaluated on the full corpora, under corpus-level and audited labels (as D17).
* **Rationale:** the rules were settled over three review rounds (L8–L10); only the source of
  variability changes. The range is a description of split-to-split variation, not a
  confidence interval, and the protocol says so.
* **Affects:** C1–C11.

### D27: The NL2Bash commands set aside by D5 are run and reported separately
* **Change:** the 284 NL2Bash commands that D5 does not count as SAFE are evaluated by every
  condition. They enter no metric; their deny rate is reported, and variant V1 counts them as
  SAFE. In v1 they were never run, and V1 existed for static CARE only.
* **Rationale:** "run the whole thing" (D24), and it makes the effect of D5 visible for every
  guard.
* **Affects:** variant V1; no primary metric.

### D28: Label audit on the full-corpus run
* **Change:** the selection rule and the effect-based policy of D17 are unchanged. The audited
  set is every DANGEROUS-labelled command that the judge allows in any v2 run, which can only
  be listed after the run. The three v1 items stay in `data/label_audit.yaml`.
* **Limits:** as D17. The auditor is the AI assistant that built the artifact; the audit is
  neither blind nor independent, and it is used only for the sensitivity analysis of C7 and C9.
* **Affects:** C7, C9.

### L12: Restructure for protocol v2.0
* **Date:** 2026-11-11.
* **Archive:** the v1 protocol, the seed-42 split, every v1 result, the executed v1 notebooks
  and the pilot moved to `archive/v1/` unchanged. The v1 code is in git history at `9fb29f7`.
* **Code:**
  * `dataset.py` loads the population and holds the split recipe (`SplitRecipe`);
  * `stats.py` holds the formulas, on one set of commands or on many splits at once;
  * `analysis.py`, `claims.py` and `report.py` are rewritten for the two views (full corpora,
    paper-sized splits);
  * `sensitivity.py` and both bootstraps are removed (D25).
* **Documents:** `PROTOCOL.md` is a new, self-contained v2.0. This log stays append-only; the
  status table at its top is an index, not an entry.

### L13: Protocol v2.0 frozen
* **Date:** 2026-11-11, before the v2 confirmatory run and before any guard had been run on
  the full corpora. The pipeline had been exercised only on 40 commands with a stubbed LLM
  client.
* **Record:** the SHA-256 of `PROTOCOL.md` and of `config.yaml` at the time of the run are
  written to `results/provenance.json` by the run itself.

### L14: Confirmatory run of protocol v2.0
* **Run:** 2026-11-11 18:19:53–18:53:33 UTC, through the notebook in `REPRO_MODE=full` with a
  live LLM, on all 11,665 commands with three runs per LLM condition.
* **Frozen inputs:** `PROTOCOL.md` sha256 `c4dde019…` and `config.yaml` sha256 `25bc802f…`, as
  frozen in L13 and recorded by the run in its provenance. Neither file has changed since.
* **Working tree:** the v2 code was not yet committed when the run executed. The provenance
  records `repo_head = 9fb29f7` with `uncommitted_changes = true`.
* **Volume and quality:** 105,651 calls. 0 errors, 0 retries, 0 replies taken from a cache,
  every call served by `Amazon Bedrock`. 11,352,714 prompt and 275,254 completion tokens,
  US$1.85.
* **Consistency with v1:** on the 549 commands v1 evaluated, the static decisions are
  identical, and the LLM conditions give the same decision on 98.0–99.3% of the commands.
* **Archive:** `results/executed/confirmatory_live_run.{ipynb,provenance.json,validation.json}`.

### L15: Label audit and final execution
* **Label audit (D28):** the judge allowed 23 DANGEROUS-labelled commands in at least one run
  (2 ART base64 round-trips and 21 RedCode-Exec scripts from the scenarios we call
  software-weakness). All 23 only compute and print a value, and are audited SAFE under the
  effect-based policy (`data/label_audit.yaml`). Twelve of them implement biased scoring rules;
  the policy judges what running a command does, and says so.
* **Effect on verdicts:** the live notebook (L14) was executed with only the three v1 audit
  items and printed C7 and C9 as *not supported*. With the 23 items they are *inconclusive
  (label-sensitive)*, as the rule in protocol §7 prescribes. No other verdict depends on the
  audit.
* **Code changes after the live run (no effect on any verdict):**
  * display only: column names in three report views, and a message for empty tables;
  * CARE's call rate on the full corpora now uses the primary population as its denominator
    (220 / 11,381 = 1.93%). The live run divided by all evaluated commands, including the 284
    set aside (222 / 11,665 = 1.90%). The value is descriptive.
* **Final execution:** the notebook was re-executed without a key (reuse mode).
  `observations.parquet` is byte-identical to the live run's, and so are the comparison,
  paired-difference, funnel, oracle, RedCode, stability, variant and v1-consistency tables.
  `metrics`, `claims` and `label_sensitivity` differ only for the reasons above. Two consecutive
  re-executions produced byte-identical tables, report and figures.
* **Not done:** a clean-clone validation (the changes are not committed yet) and an external
  review of protocol v2.0.

### L16: Commit, and clean-clone validation of protocol v2.0
* **Commits:** `d78d0d6` moves v1 to `archive/v1/` (pure renames); `931ebfe` adds protocol v2.0,
  its code and its results.
* **Clean clone:** a fresh `git clone` of `experiment/baseline-reproduction` at `931ebfe` from
  GitHub, a fresh Python 3.12 venv built from `environment/requirements.lock.txt` (no lockfile
  mismatches), and the notebook executed top to bottom without an API key (1 min 56 s).
  * The sources were re-fetched and verified, the population was rebuilt identically, 72 tests
    passed, and the static guards were re-executed and matched the committed observations.
  * **All 13 Parquet tables, `report.md` and both figures regenerated byte-identical.** Only
    the timestamps, timings and `repo_head` in `provenance.json` and `validation.json` differ.
* **Not covered by the clean clone:** smoke mode and the live LLM path (the live run is L14).
* **Record:** `results/executed/clean_clone_validation.json`. This closes the first open item
  of L15; an external review of protocol v2.0 is still open.

### L17: Correction to L16
* L16 and the message of commit `299d2bd` say "13 Parquet tables". The correct count is **12**
  Parquet tables (including `observations.parquet`), plus `report.md` and both figures: 15
  files, all byte-identical in the clean clone. The record
  `results/executed/clean_clone_validation.json` lists them and was correct.

### D29: The spread over paper-sized splits is reported as σ (protocol v2.1)
* **Change:** for every statistic on the paper-sized splits we report the mean and the standard
  deviation over the 10,000 splits, written "σ = X". The verdict rules use distances in σ:
  * numeric claims (C1–C5, C8): *not supported* if the reported value is more than 1.96σ from
    the mean;
  * C6: the mean paired difference must be more than 1.96σ from 0;
  * C10: 2.39σ, the Bonferroni threshold for three comparators (level 1 − 0.05/3).
  Protocol v2.0 used the interval holding the central 95% of the splits (98.3% for C10).
* **Rationale:** requested by the maintainer, for readability: "mean, σ" is more familiar than a
  percentile range, and the distance of a reported value can be stated directly (CARE's
  reported F1 is 5.8σ above the mean).
* **Post hoc:** the change was made after the v2 results were known. Both rules were applied to
  the same decisions: all 15 Table II comparisons, the escalation rate and all 12 paired
  differences fall on the same side, and **all 11 verdicts are identical**.
* **What it assumes:** 1.96σ matches the 95% interval only for a normal distribution. The
  statistics are close to normal over the splits, with a slight lean to the left, so mean ±
  1.96σ sits a little higher than the percentile interval (for static CARE's F1, [51.8, 68.5]
  against [51.4, 67.9]). The case nearest the threshold is C3: PromptOnly's reported F1 is
  1.87σ above the mean; under v2.0 it was inside the interval by 0.01.
* **Unchanged:** the population, the runs, the observations, the split recipe and seeds, and
  every metric formula. `metrics.parquet` keeps the minimum and maximum over the splits.
* **Affects:** the wording and the columns of `comparison`, `paired_differences`,
  `oracle_bounds` and `claims`; `PROTOCOL.md` §6, §7 and §11; the first figure.

### L18: Execution of protocol v2.1
* **Date:** 2026-11-11, after D29.
* **Run:** the notebook was re-executed without a key (reuse mode); no LLM call was made.
  `observations.parquet` is byte-identical to the live run's (L14).
* **Verdicts:** all 11 are identical to those of v2.0 (compared programmatically against the
  v2.0 `claims.parquet` at `fb05b60`); only the rationale strings now quote σ.
* **Tables:** `comparison`, `paired_differences`, `oracle_bounds`, `metrics` and `claims` have
  σ columns in place of range bounds; the other tables are unchanged. The first figure draws
  mean ± 1.96σ.
* **Tests:** 62 reproduction tests and CARE's 10 pass.
* **Not repeated:** the clean-clone validation of L16 was for `931ebfe`; it has not been re-run
  on this change.

### L19: The notebook is the pipeline (readability refactor, non-methodological)
* **Date:** 2026-11-11, after L18. Requested by the maintainer: full names instead of aliases,
  less line noise in the code and in the notebook outputs, the pipeline in the notebook, and
  objects instead of variables passed along at every step.
* **Notebook:**
  * It now calls each step directly; `repro/pipeline.py`, which only forwarded those calls, is
    removed. Imports use full module names (no `as D`, `as P`, `as R`).
  * Four objects carry what used to be passed around: `Configuration` (config.yaml and the run
    mode), `Analysis` (the observations aligned with the population; every table is an
    attribute computed on first use), `Report` (the tables and figures shown) and `RunRecord`
    (the checks before the run and the files written after it).
  * Outputs are compact. Removed: the verbatim protocol sections (the notebook links to
    `PROTOCOL.md`), the environment dump and the file inventory (both are in
    `provenance.json`), and the per-stage timers. Shortened: the head-to-head table (one row per
    pair), the funnel (primary run), the judge-allowed commands (counted per family) and the
    RedCode table (by scenario kind). The full versions are in `results/report.md`.
* **Code:** `dataset.py` is split into `corpora.py` (the population) and
  `paper_sized_splits.py` (the recipe); `evaluation.py` runs the guards and holds the reuse
  checks; names are spelled out and long one-liners unfolded.
* **Smoke mode** keeps evenly spaced commands per corpus and uses 3 commands per source in its
  small splits, so that it now exercises every analysis, including the construction variants.
  Smoke outputs are not results.
* **Unchanged:** data, prompts, model, parsing, formulas, the split recipe, the verdict rules
  and the request fingerprints (the committed replies are still accepted for reuse).
* **Verification:** before and after the change, the 11 analysis tables are equal
  cell for cell (`pandas.testing.assert_frame_equal`, exact), and `observations.parquet` is
  untouched. `provenance.json` and `validation.json` have a simpler layout (no stage timings,
  no preflight entry; the live path now probes the LLM before it starts). 62 reproduction
  tests and CARE's 10 pass; smoke mode passes without a key.
* **Protocol:** `PROTOCOL.md` changes only the module names in its usage example (§6, §12).
