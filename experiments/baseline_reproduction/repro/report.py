"""Presentation: figures, notebook views and Markdown (`results/report.md`).

Nothing here computes a result.  Every function formats tables produced by `analysis` and
`claims`, so the notebook and report.md show the same numbers.
"""
from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

from . import HERE
from .analysis import CONDITIONS, CORPORA, FULL, NOT_COUNTED, SPLITS, STATIC

# ------------------------------------------------------------------ figures
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OURS, PAPER = "#2a78d6", "#eb6834"   # categorical slots 1 and 2 of the validated palette


def _style(ax, grid="x"):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def figures(comparison, split_f1, n_splits, outdir):
    """Write both figures; return {name: path}.  `split_f1` maps condition -> F1 of every paper-sized split."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(outdir, exist_ok=True)
    t = comparison[comparison.metric.isin(["F1", "DR", "FPR"]) & (comparison.condition != "NoGuard")]
    guards = [c for c in CONDITIONS if c in set(t.condition)]

    # 1. Table II, reported vs observed
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True, facecolor=SURFACE)
    rows = np.arange(len(guards))[::-1]
    for ax, (metric, title) in zip(axes, [("F1", "F1 % ↑"), ("DR", "Detection rate % ↑"), ("FPR", "False-positive rate % ↓")]):
        _style(ax)
        d = t[t.metric == metric].set_index("condition").loc[guards]
        ax.hlines(rows, d.range_lo, d.range_hi, color=OURS, lw=2)
        ax.plot(d.observed, rows, "o", ms=8, color=OURS, mec=SURFACE, mew=2, label="Observed: mean and range of the paper-sized splits")
        ax.plot(d.reported, rows, "D", ms=8, mfc="none", mec=PAPER, mew=2, label="Reported (Table II)")
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_yticks(rows, guards, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=2, frameon=False, labelcolor=INK, bbox_to_anchor=(0.01, 0.99))
    fig.savefig(os.path.join(outdir, "reported_vs_observed.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)

    # 2. F1 of every paper-sized split, one row per guard
    reported = t[t.metric == "F1"].set_index("condition").reported
    fig, axes = plt.subplots(len(guards), 1, figsize=(8, 1.15 * len(guards) + 1.0), sharex=True, facecolor=SURFACE)
    bins = np.arange(0, 101, 1)
    for ax, c in zip(np.atleast_1d(axes), guards):
        _style(ax)
        ax.hist(split_f1[c], bins=bins, color=OURS)
        ax.axvline(reported[c], color=PAPER, lw=2)
        ax.set_yticks([])
        ax.set_ylabel(c, rotation=0, ha="right", va="center", color=INK)
        ax.set_xlim(20, 100)
    top = np.atleast_1d(axes)[0]
    top.plot([], [], "s", color=OURS, label=f"Observed: F1 of each of the {n_splits:,} paper-sized splits")
    top.plot([], [], "-", color=PAPER, lw=2, label="Reported (Table II)")
    fig.legend(*top.get_legend_handles_labels(), loc="upper left", ncol=2, frameon=False, labelcolor=INK, bbox_to_anchor=(0.01, 0.995))
    np.atleast_1d(axes)[-1].set_xlabel("F1 %", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(outdir, "f1_over_splits.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return {f[:-4]: os.path.join(outdir, f) for f in sorted(os.listdir(outdir)) if f.endswith(".png")}


# ------------------------------------------------------------------ views (shared by the notebook and report.md)
def _in_order(df, column="condition"):
    order = {c: i for i, c in enumerate(CONDITIONS)}
    return df.sort_values(column, key=lambda s: s.map(order), kind="stable").reset_index(drop=True)


def headline(comparison):
    """Table II at a glance: per condition and metric, "reported → observed [range of splits]"."""
    t = comparison[comparison.metric.isin(["F1", "DR", "FPR"]) & (comparison.condition != "NoGuard")]
    cell = lambda r: (f"{r.reported:.2f} → **{r.observed:.2f}** [{r.range_lo:.1f}, {r.range_hi:.1f}] "  # noqa: E731
                      + ("∈" if r.inside_range else "∉"))
    wide = t.assign(cell=t.apply(cell, axis=1)).pivot(index="condition", columns="metric", values="cell")
    return _in_order(wide[["F1", "DR", "FPR"]].reset_index())


def corpora_view(metrics, run=1):
    """Every guard on every command: DR per DANGEROUS corpus, FPR per SAFE corpus, as % (k/n)."""
    m = metrics[(metrics.run == run) & (metrics.scope != SPLITS)]
    m = m[(m.condition != "NoGuard") & m.metric.isin(["DR", "FPR", "deny rate", "F1"])]
    cell = lambda r: f"{r.value:.2f}" if r.metric == "F1" else f"{r.value:.1f} ({int(r.k):,}/{int(r.n):,})"  # noqa: E731
    m = m.assign(cell=m.apply(cell, axis=1), col=m.metric + ": " + m.scope)
    wide = m.pivot(index="condition", columns="col", values="cell")
    columns = {f"DR: {CORPORA}": "DR, all DANGEROUS", "DR: ART": "DR, ART", "DR: RedCode-Exec": "DR, RedCode-Exec",
               f"FPR: {CORPORA}": "FPR, all SAFE", "FPR: NL2Bash": "FPR, NL2Bash", "FPR: Real-world": "FPR, Real-world",
               f"F1: {CORPORA}": "F1", f"deny rate: {NOT_COUNTED}": "denied, NL2Bash set aside (D5)"}
    return _in_order(wide[[c for c in columns if c in wide]].rename(columns=columns).reset_index())


def differences_view(differences):
    d = differences.copy()
    d["pair"] = d.left + " − " + d.right
    d["mean [range]"] = d.apply(lambda r: f"{r.value:+.2f} [{r.lo:.1f}, {r.hi:.1f}]", axis=1)
    d["simultaneous range"] = d.apply(lambda r: "—" if np.isnan(r.adj_lo) else f"[{r.adj_lo:.1f}, {r.adj_hi:.1f}]", axis=1)
    d["left better in"] = d.share_left_better.map(lambda v: f"{100 * v:.1f}% of splits")
    d["on the full corpora"] = d.full_corpora.map(lambda v: f"{v:+.2f}")
    d["metric"] = d.metric.str.replace("delta_", "")
    return d[["pair", "metric", "mean [range]", "simultaneous range", "left better in", "on the full corpora"]]


def mcnemar_view(differences):
    """The paper's Table VIII test applied to every paper-sized split."""
    d = differences[differences.metric == "delta_accuracy"]
    return pd.DataFrame(dict(
        pair=d.left + " vs " + d.right,
        discordant=d.apply(lambda r: f"{r.left_only:.1f} / {r.right_only:.1f}", axis=1),
        paper=d.apply(lambda r: "—" if pd.isna(r.paper_left_only) else
                      f"{int(r.paper_left_only)} / {int(r.paper_right_only)} (p = {r.paper_p:.2g})", axis=1),
        favours_left=d.mcnemar_favours_left.map(lambda v: f"{100 * v:.1f}% of splits"),
        favours_right=d.mcnemar_favours_right.map(lambda v: f"{100 * v:.1f}% of splits"))).rename(
            columns={"discordant": "left only / right only correct (mean per split)", "paper": "paper (Table VIII)",
                     "favours_left": "p < 0.05 favouring left", "favours_right": "p < 0.05 favouring right"})


def funnel_view(funnel):
    """The paper's funnel first, then ours per run: mean count per paper-sized split, and the full corpora."""
    number = lambda v: "—" if pd.isna(v) else f"{v:,.0f}" if float(v).is_integer() else f"{v:.1f}"  # noqa: E731
    f = funnel.copy()
    for c in ["run", "n", "warn", "skipped", "escalated", "judge_allow", "judge_allow_dangerous"]:
        f[c] = f[c].map(number)
    cols = ["scope", "run", "n", "warn", "skipped", "escalated", "escalated_pct", "judge_allow", "judge_allow_dangerous"]
    return f[cols].rename(columns={"n": "commands", "escalated_pct": "escalated %", "judge_allow": "judge ALLOW",
                                   "judge_allow_dangerous": "judge ALLOW, DANGEROUS-labelled"})


def oracle_view(oracle):
    o = oracle.assign(f1_range=oracle.apply(lambda r: f"[{r.f1_lo:.1f}, {r.f1_hi:.1f}]", axis=1))
    return o[["bound", "judged_per_split", "f1", "f1_range", "dr", "fpr"]].rename(columns={
        "judged_per_split": "commands judged per split", "f1": "F1", "f1_range": "F1 range", "dr": "DR", "fpr": "FPR"})


def label_view(label_sens):
    t = label_sens[["labels", "condition", "dr", "fpr", "judge_allow_dangerous_per_run"]]
    return t.rename(columns={"dr": "DR", "fpr": "FPR",
                             "judge_allow_dangerous_per_run": "DANGEROUS commands the judge allowed, per run"})


def stability_view(stability):
    return stability.rename(columns={"decisions_that_differ_pct": "decisions that differ between runs (%)"} | {
        c: c.replace("f1_run", "F1, run ") for c in stability.columns if c.startswith("f1_run")})


def v1_view(v1):
    return v1.rename(columns={"same_decision_pct": "same decision as v1 (%)", "f1_v1": "F1 in v1", "f1_now": "F1 now"})


def variants_view(variants):
    """Expected F1 on paper-sized splits per construction variant (rows) and guard (columns)."""
    wide = variants.pivot(index=["variant", "note"], columns="condition", values="f1")
    return wide[[c for c in CONDITIONS if c in wide]].reset_index()


def latency_view(comparison):
    return comparison[comparison.metric == "latency_mean"][["condition", "reported", "observed"]].rename(
        columns={"reported": "reported mean ms", "observed": "observed mean ms"})


def usage_line(metrics):
    cost = metrics[metrics.metric.isin(["prompt_tokens", "completion_tokens", "cost"])]
    if not len(cost):
        return ""
    c = cost.groupby("metric").value.sum()
    return (f"LLM usage over all runs: {int(c.get('prompt_tokens', 0)):,} prompt + "
            f"{int(c.get('completion_tokens', 0)):,} completion tokens, cost US${c.get('cost', 0):.2f} (as reported by OpenRouter).")


def judge_allowed_dangerous(obs, population, audit):
    """DANGEROUS-labelled commands that CARE's Resolution judge turned into ALLOW, with their audited label."""
    d = obs[(obs.condition == FULL) & obs.llm_called & obs.label_dangerous & (obs.decision == "ALLOW")]
    runs = d.groupby("command_id").run.agg(lambda r: ",".join(map(str, sorted(r)))).rename("allowed in runs")
    t = population.set_index("command_id").loc[runs.index, ["source", "family", "command"]].join(runs).reset_index()
    t["audited label"] = t.command_id.map(audit).fillna("not audited")
    t["command"] = t.command.str.replace(r"\s*\n\s*", " ⏎ ", regex=True).str[:140]
    return t[["command_id", "source", "family", "allowed in runs", "audited label", "command"]]


def static_false_positives(obs, population, limit=15):
    """A sample of the SAFE-labelled commands that CARE (w/o Resolution) denies, and how many there are."""
    denied = obs[(obs.condition == STATIC) & obs.in_primary & ~obs.label_dangerous & obs.prediction_dangerous]
    t = population.set_index("command_id").loc[denied.command_id, ["source", "command"]].reset_index(drop=True)
    return t.head(limit).assign(command=lambda d: d.command.str[:140]), len(t)


def observation_counts(obs):
    return _in_order(obs.pivot_table(index="condition", columns="run_id", values="command_id", aggfunc="size").reset_index())


def show(df, floatfmt=".2f"):
    """Display a DataFrame as a Markdown table (renders the same in Jupyter and on GitHub)."""
    from IPython.display import Markdown, display
    display(Markdown(md_table(df, floatfmt) if len(df) else "*(no rows)*"))


# ------------------------------------------------------------------ markdown
def md_table(df, floatfmt=".2f"):
    def f(v):
        if isinstance(v, (float, np.floating)):
            return "—" if np.isnan(v) else format(v, floatfmt)
        return "—" if v is None else str(v).replace("|", "\\|")
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def results_markdown(res, cfg, run):
    """All tables in one Markdown file (results/report.md).  `res` is a `pipeline.Results`."""
    n = res.n_splits
    L = ["# Results: CARE baseline reproduction (protocol v%s)\n" % cfg["protocol_version"]]
    if not run.full:
        L.append("> **SMOKE MODE — NOT A REPRODUCTION.** The numbers below come from a few commands.\n")
    L.append("> Every comparison with the paper is **not directly comparable**: the population is rebuilt from the "
             "public corpora (the authors' 549 commands are unreleased) and labels are corpus-level (paper Table I).\n")
    L += ["## Claim verdicts\n", md_table(res.claims[["claim_id", "claim", "outcome", "rationale"]])]
    L += [f"\n## Table II: reported → observed on {n:,} paper-sized splits (mean [range]; primary run)\n",
          "∈ / ∉: the reported value lies inside / outside the range.\n", md_table(headline(res.comparison))]
    L += ["\n## Full corpora: every guard on every command (primary run)\n", md_table(corpora_view(res.metrics))]
    L += ["\n## CARE vs each comparator on the paper-sized splits (left − right, percentage points)\n",
          md_table(differences_view(res.differences)),
          "\nThe paper's McNemar test (two-sided, Yates, α = 0.05) on every split:\n", md_table(mcnemar_view(res.differences))]
    L += ["\n## Resolution funnel\n", md_table(funnel_view(res.funnel))]
    L += ["\n## Upper bounds for any Resolution judge on the released static stack (paper-sized splits)\n",
          md_table(oracle_view(res.oracle))]
    L += ["\n## Label sensitivity of the Resolution claims (C7, C9; full corpora)\n", md_table(label_view(res.label_sensitivity))]
    L += ["\n## RedCode-Exec: commands denied per risk scenario (of n; primary run)\n", md_table(res.redcode, ".0f")]
    if res.variants is not None:
        L += ["\n## Construction variants: expected F1 on paper-sized splits\n", md_table(variants_view(res.variants))]
    if len(res.stability):
        L += ["\n## Run-to-run stability of the LLM conditions\n", md_table(stability_view(res.stability))]
    if res.v1 is not None:
        L += ["\n## Consistency with the archived v1 run (the 549 commands v1 evaluated)\n", md_table(v1_view(res.v1))]
    L += ["\n## Latency (not comparable: laptop CPU and hosted API vs 4×H100 and local vLLM)\n",
          md_table(latency_view(res.comparison))]
    if usage := usage_line(res.metrics):
        L.append(f"\n{usage}")
    return "\n".join(L) + "\n"



def protocol_sections(numbers, path=None):
    """The given top-level sections of PROTOCOL.md (e.g. [2, 3]), verbatim, as Markdown."""
    text = open(path or os.path.join(HERE, "PROTOCOL.md"), encoding="utf-8").read()
    parts = re.split(r"(?m)^(?=## \d+\. )", text)
    keep = [p for p in parts if (m := re.match(r"## (\d+)\. ", p)) and int(m.group(1)) in set(numbers)]
    return "\n".join("##" + p.rstrip() + "\n" for p in keep)
