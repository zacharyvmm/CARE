# Archive: protocol v1 (one 549-command sample)

This folder holds the first version of the reproduction, unchanged. It is **superseded** by
protocol v2.0, which evaluates every command of the corpora instead of one sample
(`../../PROTOCOL.md`, `../../DECISIONS.md` D24). Nothing here is used for a current claim,
except that the v2 notebook checks its static decisions against `results/observations.parquet`.

| Path | Content |
|---|---|
| `PROTOCOL.md` | protocol v1.0, frozen before the v1 confirmatory run, with the amendments v1.1–v1.3 written after three rounds of external review |
| `main_split.parquet` | the 549 commands v1 evaluated: the seed-42 draw of the split recipe. The v2 recipe regenerates it exactly (unit-tested) |
| `results/` | every v1 output: observations, metrics, comparison, claims, bootstrap tables, figures, `report.md`, provenance |
| `results/executed/` | the v1 confirmatory notebook as executed live, and the clean-clone validation record |
| `results/pilot/` | the two pilot runs that preceded protocol v1.0 |

**Code.** The code that produced these files is in git history at commit `9fb29f7`
(`experiments/baseline_reproduction/repro/`). It is not kept here.

**History.** `../../DECISIONS.md` entries D1–D23 and L1–L11 record every v1 decision and event.

**v1 headline** (primary run, seed-42 sample, 95% recipe-bootstrap interval):

| Condition | F1 reported | F1 observed |
|---|---|---|
| PromptOnly | 66.99 | 63.50 [55.4, 70.9] |
| LLMJudge | 73.09 | 70.26 [63.0, 76.8] |
| NeMo self-check (emulated) | 68.63 | 66.12 [58.1, 73.1] |
| CARE (w/o Resolution) | 84.99 | 58.72 [45.8, 69.3] |
| CARE | 85.64 | 57.41 [44.4, 68.0] |
