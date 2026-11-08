# Decision and deviation log (append-only)

Entries are never edited or removed. A correction is a new entry that references
the old one. Two kinds of entry:

* **D-entries** are methodological decisions. Each gives the change, the
  rationale, the evidence, the expected impact, and the experiments it affects.
* **L-entries** are process events: runs, audits, and changes to the artifact.

All dates are 2026-11-07 (UTC) unless stated.

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
