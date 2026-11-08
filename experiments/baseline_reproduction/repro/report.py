"""Presentation: figures, notebook views and Markdown (`results/report.md`).

Nothing here computes a result; every function formats tables produced by `analysis`,
`sensitivity` and `claims`, so the notebook and report.md show the same numbers.
"""
from __future__ import annotations

import os
import re

import numpy as np

from . import HERE
from .analysis import CONDITIONS, preds


# ------------------------------------------------------------------ figures
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OURS, PAPER = "#2a78d6", "#eb6834"  # validated categorical slots 1 and 2


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def figures(cmp, seeds, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    os.makedirs(outdir, exist_ok=True)
    t = cmp[cmp.metric.isin(["F1", "DR", "FPR"]) & (cmp.condition != "NoGuard")]
    conds = [c for c in CONDITIONS if c in set(t.condition)][::-1]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True, facecolor=SURFACE)
    for ax, (m, title) in zip(axes, [("F1", "F1 % ↑"), ("DR", "Detection rate % ↑"), ("FPR", "False-positive rate % ↓")]):
        _style(ax)
        d = t[t.metric == m].set_index("condition").loc[conds]
        yy = np.arange(len(conds))
        ax.hlines(yy, d.design_ci_lo, d.design_ci_hi, color=OURS, lw=2)
        ax.plot(d.observed, yy, "o", ms=8, color=OURS, mec=SURFACE, mew=2, label="Observed, run 1 (95% CI)")
        ax.plot(d.reported, yy, "D", ms=8, mfc="none", mec=PAPER, mew=2, label="Reported (Table II)")
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_yticks(yy, conds, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=2, frameon=False, labelcolor=INK, bbox_to_anchor=(0.01, 0.99))
    fig.text(0.99, 0.955, "CIs: design-based (recipe bootstrap, D19)", ha="right", va="center", color=INK2, fontsize=9)
    fig.savefig(os.path.join(outdir, "reported_vs_observed.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)

    if seeds is not None:
        fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=SURFACE)
        _style(ax)
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.hist(seeds.f1, bins=20, color=OURS, edgecolor=SURFACE, linewidth=2)
        ax.axvline(84.99, color=PAPER, lw=2, ls="--")
        ax.text(84.99, ax.get_ylim()[1] * 0.95, "reported 84.99 ", color=INK, va="top", ha="right")
        s42 = seeds.loc[seeds.seed == 42, "f1"].iloc[0]
        ax.axvline(s42, color=INK2, lw=1)
        ax.text(s42, ax.get_ylim()[1] * 0.80, " seed 42 (primary)", color=INK2, va="top")
        ax.set_xlabel(f"CARE (w/o Resolution) F1 %, {len(seeds)} reconstructed splits", color=INK)
        ax.set_ylabel("splits", color=INK)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "split_seed_sensitivity.png"), dpi=160, facecolor=SURFACE)
        plt.close(fig)
    return {f[:-4]: os.path.join(outdir, f) for f in sorted(os.listdir(outdir)) if f.endswith(".png")}


# ------------------------------------------------------------------ views (shared by the notebook and report.md)
def headline(cmp):
    """Table II at a glance: one row per condition, "reported → observed [95% CI]" per metric."""
    t = cmp[cmp.metric.isin(["F1", "DR", "FPR"])]
    cell = lambda r: (f"{r.reported:.2f} → **{r.observed:.2f}** [{r.design_ci_lo:.1f}, {r.design_ci_hi:.1f}] "  # noqa: E731
                      + ("∈" if r.inside_design_ci else "∉"))
    wide = t.assign(cell=t.apply(cell, axis=1)).pivot(index="condition", columns="metric", values="cell")
    order = [c for c in CONDITIONS if c in wide.index and c != "NoGuard"]
    return wide.loc[order, ["F1", "DR", "FPR"]].reset_index()


def table_ii_view(cmp):
    t = cmp[cmp.metric.isin(["F1", "DR", "FPR"])].copy()
    t["observed [95% CI, per-command]"] = t.apply(lambda r: f"{r.observed:.2f} [{r.ci_lo:.1f}, {r.ci_hi:.1f}]", axis=1)
    t["[95% CI, design-based]"] = t.apply(lambda r: f"[{r.design_ci_lo:.1f}, {r.design_ci_hi:.1f}]", axis=1)
    static = {"NoGuard", "CARE (w/o Resolution)"}
    t["range over runs"] = t.apply(lambda r: ("deterministic" if r.condition in static else "single run")
                                   if np.isnan(r.run_min) else f"{r.run_min:.2f}–{r.run_max:.2f}", axis=1)
    return t[["condition", "metric", "reported", "observed [95% CI, per-command]", "[95% CI, design-based]",
              "abs_diff", "range over runs"]]


def flip_rates(metrics):
    return metrics[metrics.metric == "decision_flip_rate"][["condition", "value"]].rename(
        columns={"value": "decision flip rate across runs (%)"})


def latency_view(cmp):
    return cmp[cmp.metric == "latency_mean"][["condition", "reported", "observed"]].rename(
        columns={"reported": "reported mean ms", "observed": "observed mean ms"})


def usage_line(metrics):
    cost = metrics[metrics.metric.isin(["prompt_tokens", "completion_tokens", "cost"])]
    if not len(cost):
        return ""
    c = cost.groupby("metric").value.sum()
    return (f"LLM usage over all runs: {int(c.get('prompt_tokens', 0)):,} prompt + "
            f"{int(c.get('completion_tokens', 0)):,} completion tokens, cost ${c.get('cost', 0):.4f} (OpenRouter-reported).")


def by_source_view(src):
    s = src.assign(cell=src.apply(lambda r: f"{r.value:.1f} [{r.ci_lo:.0f}–{r.ci_hi:.0f}]", axis=1),
                   col=src.apply(lambda r: f"{r.source} {r.metric} (n={r.n})", axis=1))
    wide = s.pivot(index="condition", columns="col", values="cell")
    return wide.loc[[c for c in CONDITIONS if c in set(s.condition)]].reset_index()


def redcode_view(rc):
    return rc.pivot_table(index=["scenario", "kind", "n"], columns="condition", values="detected").reset_index()


def seed_summary(seeds):
    q = seeds.f1.quantile([.025, .5, .975])
    return f"F1 median {q[.5]:.2f}, 95% range {q[.025]:.2f}–{q[.975]:.2f}, max {seeds.f1.max():.2f} (reported 84.99)."


def static_false_positives(obs, split, rep=1):
    """SAFE-labelled commands that CARE (w/o Resolution) denies."""
    p, _ = preds(obs, split.command_id.to_numpy(), "CARE (w/o Resolution)", rep)
    return split[(~split.label_dangerous) & p][["source", "command"]].reset_index(drop=True)


def judge_allowed_dangerous(obs, split):
    """DANGEROUS-labelled commands that CARE's Resolution judge turned into ALLOW (C9)."""
    d = obs[(obs.condition == "CARE") & obs.llm_called & obs.label_dangerous & (obs.decision == "ALLOW")]
    d = d.merge(split[["command_id", "command"]], on="command_id")[["run_id", "source", "command", "raw_response"]]
    return d.assign(command=d.command.str.replace(r"\s*\n\s*", " ⏎ ", regex=True).str[:160])


def observation_counts(obs):
    return obs.pivot_table(index="condition", columns="run_id", values="command_id", aggfunc="size").reset_index()


def show(df, floatfmt=".2f"):
    """Display a DataFrame as a Markdown table (renders the same in Jupyter and on GitHub)."""
    from IPython.display import Markdown, display
    display(Markdown(md_table(df, floatfmt)))


# ------------------------------------------------------------------ markdown
def md_table(df, floatfmt=".2f"):
    def f(v):
        if isinstance(v, (float, np.floating)):
            return "—" if np.isnan(v) else format(v, floatfmt)
        return str(v).replace("|", "\\|")
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def results_markdown(res, cfg, mode):
    """All tables in one Markdown file (results/report.md). `res` is a `pipeline.Results`."""
    p = cfg["analysis"]["primary_run"]
    L = []
    if mode != "full":
        L.append(f"> **{mode.upper()} MODE — NOT A REPRODUCTION.** Numbers below come from a reduced run.\n")
    L.append("> All comparisons with the paper are **not directly comparable**: the population is a reconstruction "
             "(same corpora and recipe, not the authors' 549 items) and labels are corpus-level (paper Table I).\n")
    L.append("### Claim verdicts (protocol v1.3, PROTOCOL.md §11-§13; earlier verdicts kept for the record)\n")
    L.append(md_table(res.claims[["claim_id", "claim", "outcome", "rationale", "outcome_v1_2_rules", "outcome_v1_1",
                                  "outcome_v1_0"]]))
    L.append("\n### Reported vs observed (Table II; primary run = run %d; descriptive)\n" % p)
    L.append(md_table(table_ii_view(res.comparison)))
    flips = flip_rates(res.metrics)
    if len(flips):
        L.append("\n" + md_table(flips))
    L.append("\nLatency (not directly comparable: laptop CPU and a hosted API vs. 4×H100 + local vLLM):\n")
    L.append(md_table(latency_view(res.comparison)))
    if usage := usage_line(res.metrics):
        L.append(f"\n{usage}\n")
    L.append("\n### Paired differences, recipe bootstrap (primary run; adj = Bonferroni over non-CARE comparators, D23)\n")
    L.append(md_table(res.design.differences.drop(columns=["ci_method", "estimator"])))
    if res.coverage is not None:
        L.append("\n### Simulated coverage of the 95% bootstrap intervals (D22; deterministic guards, 100 re-drawn splits)\n")
        L.append(md_table(res.coverage))
    if res.calibration is not None:
        L.append("\n### Bootstrap spread vs spread over 100 re-drawn splits (static CARE F1; D19)\n")
        L.append(md_table(res.calibration))
    L.append("\n### Paired McNemar tests (primary run; two-sided, Yates as in Table VIII; assume independent commands)\n")
    L.append(md_table(res.mcnemar, ".3g"))
    L.append("\n### Label sensitivity for C7/C9 (D17; prediction-dependent selection, sensitivity only)\n")
    L.append(md_table(res.label_sensitivity))
    L.append("\n### Resolution funnel (paper App. A.F: 117 WARN → 94 skipped → 23 judged → 3 ALLOW, 0 DANGEROUS)\n")
    L.append(md_table(res.funnel.drop(columns=["run_id"])))
    L.append("\n### Upper bounds for any Resolution judge on the released static stack (derived; this population only)\n")
    L.append(md_table(res.oracle))
    L.append("\n### Per-source rates (primary run; Wilson 95% CI)\n")
    L.append(md_table(by_source_view(res.by_source)))
    L.append("\n### RedCode-Exec detections by scenario (primary run; scenario kind is post hoc, D9)\n")
    L.append(md_table(redcode_view(res.redcode), ".0f"))
    if res.seeds is not None:
        L.append(f"\n### Split-construction sensitivity (CARE w/o Resolution, {len(res.seeds)} seeds of this recipe)\n")
        L.append(seed_summary(res.seeds) + "\n")
    if res.variants is not None:
        L.append("\n### Construction variants (CARE w/o Resolution; V2 is exploratory and post hoc)\n")
        L.append(md_table(res.variants))
    return "\n".join(L) + "\n"


def protocol_sections(numbers, path=None):
    """The given top-level sections of PROTOCOL.md (e.g. [1, 2, 3]), verbatim, as Markdown."""
    text = open(path or os.path.join(HERE, "PROTOCOL.md"), encoding="utf-8").read()
    parts = re.split(r"(?m)^(?=## \d+\. )", text)
    keep = [p for p in parts if (m := re.match(r"## (\d+)\. ", p)) and int(m.group(1)) in set(numbers)]
    return "\n".join(p.rstrip() + "\n" for p in keep)
