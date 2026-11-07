# Baseline reproduction: CARE main-split detection (paper Table II, RQ1)

Independent reproduction of the **RQ1 detection experiment** of *CARE: Pre-Execution
Command Verification for Shell-Executing LLM Agents* (ISSRE 2026, arXiv:2607.21642).
It covers the detection numbers in Table II (F1, DR, FPR, latency), the Table VIII
McNemar pairs, and the Resolution funnel in Appendix A.F.
It does **not** cover RQ1 utility (NL2SH-ALFA), RQ2 ablations, RQ3 OOD/Docker
harm, or RQ4 sensitivity.

The results are in [`results/SUMMARY.md`](results/SUMMARY.md).

## Pipeline

```bash
pip install -e . && pip install -r experiments/baseline_reproduction/requirements.txt
experiments/baseline_reproduction/fetch_sources.sh          # pinned upstream corpora -> data/raw/
python experiments/baseline_reproduction/build_dataset.py   # -> data/main_split.parquet
export OPENROUTER_API_KEY=...                               # never committed
python experiments/baseline_reproduction/run_eval.py        # -> results/decisions.parquet
python experiments/baseline_reproduction/analyze.py         # -> results/*.parquet, SUMMARY.md, figures/
```

Every table is built in pandas and written as Parquet.

| File | Content |
|---|---|
| `data/main_split.parquet` | the 549-command split: `command_id, source, label, family, head, command, meta` |
| `data/main_split_manifest.json` | seed, pool sizes, families drawn, upstream commit SHAs |
| `data/manual/real_world_commands.txt` | 30 real-world developer commands (D4) |
| `results/decisions.parquet` | one row per (method, run, command): decision, latency, raw LLM reply, provider, CARE trace (provisional verdict, score, layers, rules, skip predicate) |
| `results/metrics_main.parquet` | Table II reproduction with CIs and paper values |
| `results/metrics_by_source.parquet`, `redcode_scenarios.parquet` | where the errors are |
| `results/mcnemar.parquet`, `care_funnel.parquet` | Table VIII pairs, Resolution funnel |
| `results/sensitivity_seeds.parquet`, `sensitivity_variants.parquet` | dataset-construction sensitivity |
| `results/run_metadata.json` | model, provider pin, run count, timestamp, error count |

## Decisions and deviations from the paper

The authors did not release the evaluation split, the two curated subsets, or the
static baseline ports. Each choice we had to make is listed here, together with the
direction it is expected to bias the result.

| ID | Decision | Rationale / expected effect |
|---|---|---|
| D1 | Rebuild the 549-command split from the public corpora, matching the paper's composition exactly: 220 DANGEROUS (ART 137+12, RedCode-Exec 71) and 329 SAFE (NL2Bash 299, real-world 30). | The split is unreleased. F1 depends on prevalence, so we match the class mix. |
| D2 | Fill the 12 *canonical attack* slots with ART commands instead of writing our own. | Hand-written curl\|bash and fork-bomb examples closely match CARE's 16 Manual-Cases rules, so authoring them would favour CARE. This choice probably *lowers* CARE's DR relative to the paper by up to 12/220 = 5.5 pp. |
| D3 | RedCode-Exec bash: strip the shebang and comments and keep each multi-line script as one command. Sample in seeded round-robin over the 20 risk scenarios. | The paper's example (`nc ... -e /bin/sh`) suggests single commands, but no filter is described. Grouping by scenario would leave only about 2 scenarios in the split. |
| D4 | The 30 real-world SAFE commands were written for this reproduction (build, lint, git, docker, kubectl, terraform). | The paper's 30 are unreleased. No method flags any of them (FPR 0/30 for all), so this choice has no effect on the ranking. |
| D5 | NL2Bash label hygiene: drop commands the paper itself calls "unconditionally dangerous" (sudo, shred, kill -9, root chown, SUID chmod, writes under /etc/, plus mkfs, dd of=/dev, `rm -r /`, fork bombs). This removes 284 of 10,624. | A SAFE label must be correct. With the filter off (variant V1), CARE's FPR rises to 10.6%. |
| D6 | LLM stack: `qwen/qwen3-coder-30b-a3b-instruct` (the paper's model) via OpenRouter, pinned to a single provider (Amazon Bedrock, fallbacks disabled), temperature 0, max_tokens as in the paper, and Appendix E prompts verbatim. **R = 3 runs**; run 1 is the pre-specified primary run. | The paper served the model with local vLLM. Hosted serving is not bit-deterministic at temperature 0, so we report run-to-run spread and the decision flip rate. Latency is not comparable to the paper. |
| D7 | *NeMo self-check* sends the paper's `self_check_input` prompt as a single user message without the NeMo framework. A reply containing "yes" maps to DENY. | This avoids the framework dependency. NeMo adds its own template, so treat this row as an approximation. |
| D8 | Baselines omitted: Regex (its 22 rules are unreleased), ClawGuardSim and OpenClaw4Layer (author ports unreleased), Granite Guardian 2B and Llama Guard 3-8B (not served on OpenRouter), GPT-OSS-Safeguard-20B (needs a policy prompt the paper does not give). | We do not invent baselines. |
| D9 | We classify RedCode scenarios as *operational* or *software-weakness* by reading their task text. | This is a post-hoc, exploratory classification used only for diagnosis, never for the primary result. |
| D10 | Strings that occur in two sources with conflicting labels (`hostname`, `history -c`: ART=DANGEROUS, NL2Bash=SAFE) are dropped from all pools. | Removes label noise. |
| D11 | Leakage control: we draw whole template families (ART technique YAML, NL2Bash lexical template) in seeded order until each target is met, instead of the paper's 70/30 dev/eval split over a 1,862-record pool. | We tune nothing, so no dev partition is needed. A strict 30% of the 415 ART commands (117 techniques) would not reach 149. |
| D12 | ART is used at HEAD (2026-11-06). Variant V3 rebuilds the split from a 2026-03-24 snapshot, closer to the paper's submission. | ART grows over time. V3 raises CARE's F1 from 58.7 to 65.7, still far below 84.99. |
| D13 | CARE runs unmodified from this repository. The only intervention is replacing its OpenAI client with an OpenRouter shim that pins the provider. | The method under test is not altered. |

## Threats to validity

* **The split is a reconstruction.** Our absolute numbers are not those of the
  authors' 549 commands. The 100-seed sensitivity analysis shows how far the
  construction alone can move CARE's F1: a 95% range of about 52–69, with a maximum
  of 75.0 across all 100 seeds.
* **Labels are inherited from the source corpora.** ART "attacks" include benign-looking
  discovery and test steps, such as base64-encoding "Hello from Atomic Red Team".
  RedCode-Exec bash includes CWE-style logic-flaw programs. No shell-command guard can
  detect the latter, and all methods score about 0 on them.
* CARE's rule bank was authored by the paper's authors, possibly with knowledge of
  their dev split. We cannot reproduce that coupling, and it would favour the paper's
  numbers.
