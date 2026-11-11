"""Presentation: the tables and figures shown in the notebook, and `results/report.md`.

    report = Report(analysis)
    show(report.table_ii())                        # a table
    show(report.reported_vs_observed_figure())     # a figure

Nothing here computes a result: every method formats a table of the analysis.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import stats
from .corpora import FULL_CORPORA, SET_ASIDE
from .guards import FULL_CARE, PAPER_ORDER, STATIC_CARE
from .paper_sized_splits import PAPER_SIZED_SPLITS

SURFACE, INK, MUTED_INK, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OBSERVED_COLOUR, REPORTED_COLOUR = "#2a78d6", "#eb6834"   # categorical slots 1 and 2 of the validated palette


def show(thing, float_format=".2f"):
    """Display a table (as Markdown), a figure (a .png path) or a line of text in the notebook."""
    from IPython.display import display
    if isinstance(thing, pd.DataFrame):
        display({"text/markdown": markdown_table(thing, float_format) if len(thing) else "*(no rows)*"}, raw=True)
    elif str(thing).endswith(".png"):
        display({"image/png": open(thing, "rb").read()}, raw=True)
    else:
        display({"text/markdown": str(thing)}, raw=True)


def markdown_table(table, float_format=".2f"):
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return "—" if np.isnan(value) else format(value, float_format)
        return "—" if value is None else str(value).replace("|", "\\|")

    lines = ["| " + " | ".join(table.columns) + " |", "|" + "---|" * len(table.columns)]
    for row in table.itertuples(index=False):
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


class Report:
    """The analysis, formatted for reading."""

    def __init__(self, analysis):
        self.analysis = analysis
        self.figures_directory = os.path.join(analysis.configuration.output_directory, "figures")

    # -------------------------------------------------------------- results
    def full_corpora(self):
        """Every guard on every command: DR per DANGEROUS corpus, FPR per SAFE corpus, as % (denied / commands)."""
        metrics = self.analysis.metrics
        shown = metrics[(metrics.run == self.analysis.primary_run) & (metrics.scope != PAPER_SIZED_SPLITS)
                        & (metrics.condition != "NoGuard") & metrics.metric.isin(["DR", "FPR", "deny rate", "F1"])]
        cells = [f"{row.value:.2f}" if row.metric == "F1" else f"{row.value:.1f} ({int(row.k):,}/{int(row.n):,})"
                 for row in shown.itertuples()]
        wide = shown.assign(cell=cells, column=shown.metric + ": " + shown.scope)
        wide = wide.pivot(index="condition", columns="column", values="cell")
        names = {f"DR: {FULL_CORPORA}": "DR, all DANGEROUS", "DR: ART": "DR, ART",
                 "DR: RedCode-Exec": "DR, RedCode-Exec", f"FPR: {FULL_CORPORA}": "FPR, all SAFE",
                 "FPR: NL2Bash": "FPR, NL2Bash", "FPR: Real-world": "FPR, Real-world", f"F1: {FULL_CORPORA}": "F1",
                 f"deny rate: {SET_ASIDE}": "denied, NL2Bash set aside (D5)"}
        present = [column for column in names if column in wide]
        return _in_paper_order(wide[present].rename(columns=names).reset_index())

    def table_ii(self):
        """Table II at a glance: per guard and metric, "reported → observed mean (σ over the splits)"."""
        comparison = self.analysis.comparison
        rates = comparison[comparison.metric.isin(["F1", "DR", "FPR"]) & (comparison.condition != "NoGuard")]
        cells = [f"{row.reported:.2f} → **{row.observed:.2f}** (σ = {row.sigma:.2f})" for row in rates.itertuples()]
        wide = rates.assign(cell=cells).pivot(index="condition", columns="metric", values="cell")
        return _in_paper_order(wide[["F1", "DR", "FPR"]].reset_index())

    def verdicts(self):
        verdicts = self.analysis.verdicts[["claim_id", "claim", "outcome", "rationale"]]
        return verdicts.rename(columns={"claim_id": "id", "outcome": "verdict", "rationale": "evidence"})

    def reported_vs_observed_figure(self):
        """Table II as a figure: the reported value against the mean ± 1.96σ of the paper-sized splits."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        comparison = self.analysis.comparison
        threshold = comparison.threshold.dropna().iloc[0]
        guards = [guard for guard in PAPER_ORDER if guard in self.analysis.evaluated_guards]
        heights = np.arange(len(guards))[::-1]
        figure, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True, facecolor=SURFACE)
        panels = [("F1", "F1 % ↑"), ("DR", "Detection rate % ↑"), ("FPR", "False-positive rate % ↓")]
        for axis, (metric, title) in zip(axes, panels):
            _style(axis)
            rows = comparison[comparison.metric == metric].set_index("condition").loc[guards]
            axis.hlines(heights, rows.observed - threshold * rows.sigma, rows.observed + threshold * rows.sigma,
                        color=OBSERVED_COLOUR, lw=2)
            axis.plot(rows.observed, heights, "o", ms=8, color=OBSERVED_COLOUR, mec=SURFACE, mew=2,
                      label=f"Observed: mean ± {threshold:.2f}σ over the paper-sized splits")
            axis.plot(rows.reported, heights, "D", ms=8, mfc="none", mec=REPORTED_COLOUR, mew=2,
                      label="Reported (Table II)")
            axis.set_title(title, color=INK, fontsize=11, loc="left")
            axis.set_yticks(heights, guards, color=INK)
        figure.tight_layout(rect=(0, 0, 1, 0.86))
        figure.legend(*axes[0].get_legend_handles_labels(), loc="upper left", ncol=2, frameon=False,
                      labelcolor=INK, bbox_to_anchor=(0.01, 0.99))
        return self._save(figure, "reported_vs_observed.png")

    def f1_of_every_split_figure(self):
        """The F1 of every paper-sized split, one row per guard, next to the reported value."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        comparison = self.analysis.comparison
        reported = comparison[comparison.metric == "F1"].set_index("condition").reported
        guards = [guard for guard in PAPER_ORDER if guard in self.analysis.evaluated_guards]
        figure, axes = plt.subplots(len(guards), 1, figsize=(8, 1.15 * len(guards) + 1.0), sharex=True,
                                    facecolor=SURFACE)
        axes = np.atleast_1d(axes)
        for axis, guard in zip(axes, guards):
            _style(axis)
            axis.hist(self.analysis.f1_of_every_split[guard], bins=np.arange(0, 101, 1), color=OBSERVED_COLOUR)
            axis.axvline(reported[guard], color=REPORTED_COLOUR, lw=2)
            axis.set_yticks([])
            axis.set_ylabel(guard, rotation=0, ha="right", va="center", color=INK)
            axis.set_xlim(20, 100)
        axes[0].plot([], [], "s", color=OBSERVED_COLOUR,
                     label=f"Observed: F1 of each of the {len(self.analysis.splits):,} paper-sized splits")
        axes[0].plot([], [], "-", color=REPORTED_COLOUR, lw=2, label="Reported (Table II)")
        figure.legend(*axes[0].get_legend_handles_labels(), loc="upper left", ncol=2, frameon=False,
                      labelcolor=INK, bbox_to_anchor=(0.01, 0.995))
        axes[-1].set_xlabel("F1 %", color=INK)
        figure.tight_layout(rect=(0, 0, 1, 0.93))
        return self._save(figure, "f1_over_splits.png")

    def _save(self, figure, file_name):
        import matplotlib.pyplot as plt
        os.makedirs(self.figures_directory, exist_ok=True)
        path = os.path.join(self.figures_directory, file_name)
        figure.savefig(path, dpi=160, facecolor=SURFACE)
        plt.close(figure)
        return path

    # -------------------------------------------------------------- CARE against the LLM judges
    def head_to_head(self):
        """One row per pair: the mean difference in F1 and in accuracy (σ over the splits), and the paper's test."""
        differences = self.analysis.paired_differences
        f1 = differences[differences.metric == "delta_F1"].set_index(["left", "right"])
        accuracy = differences[differences.metric == "delta_accuracy"].set_index(["left", "right"])
        rows = []
        for (left, right), by_accuracy in accuracy.iterrows():
            by_f1 = f1.loc[(left, right)]
            rows.append({
                "pair": f"{left} − {right}",
                "F1 difference": f"{by_f1.value:+.2f} (σ = {by_f1.sigma:.2f})",
                "accuracy difference": f"{by_accuracy.value:+.2f} (σ = {by_accuracy.sigma:.2f})",
                "paper's McNemar test favours left": f"{100 * by_accuracy.mcnemar_favours_left:.0f}% of splits",
                "favours right": f"{100 * by_accuracy.mcnemar_favours_right:.0f}% of splits"})
        return pd.DataFrame(rows)

    def paired_differences(self):
        """Every pair and metric, with the distance of the mean difference from 0 in σ."""
        differences = self.analysis.paired_differences
        return pd.DataFrame({
            "pair": differences.left + " − " + differences.right,
            "metric": differences.metric.str.replace("delta_", ""),
            "mean difference": [f"{row.value:+.2f} (σ = {row.sigma:.2f})" for row in differences.itertuples()],
            "distance from 0": differences.sigmas_from_zero.map(stats.in_sigmas),
            "left better in": differences.share_left_better.map(_share_of_splits),
            "on the full corpora": [f"{value:+.2f}" for value in differences.full_corpora]})

    def mcnemar(self):
        """The paper's Table VIII test applied to every paper-sized split."""
        accuracy = self.analysis.paired_differences
        accuracy = accuracy[accuracy.metric == "delta_accuracy"]
        paper = ["—" if pd.isna(row.paper_left_only) else
                 f"{int(row.paper_left_only)} / {int(row.paper_right_only)} (p = {row.paper_p:.2g})"
                 for row in accuracy.itertuples()]
        return pd.DataFrame({
            "pair": accuracy.left + " vs " + accuracy.right,
            "left only / right only correct (mean per split)":
                [f"{row.left_only:.1f} / {row.right_only:.1f}" for row in accuracy.itertuples()],
            "paper (Table VIII)": paper,
            "p < 0.05 favouring left": accuracy.mcnemar_favours_left.map(_share_of_splits),
            "p < 0.05 favouring right": accuracy.mcnemar_favours_right.map(_share_of_splits)})

    # -------------------------------------------------------------- Resolution
    def resolution_funnel(self, every_run=False):
        """The paper's funnel, then ours: the mean count per paper-sized split, and the full corpora."""
        funnel = self.analysis.resolution_funnel
        if not every_run:
            funnel = funnel[funnel.run.isna() | (funnel.run == self.analysis.primary_run)]
        shown = funnel.copy()
        for column in ["run", "n", "warn", "skipped", "escalated", "judge_allow", "judge_allow_dangerous"]:
            shown[column] = shown[column].map(_count)
        columns = ["scope", "run", "n", "warn", "skipped", "escalated", "escalated_pct", "judge_allow",
                   "judge_allow_dangerous"]
        return shown[columns].rename(columns={
            "n": "commands", "escalated_pct": "escalated %", "judge_allow": "judge ALLOW",
            "judge_allow_dangerous": "judge ALLOW, DANGEROUS-labelled"})

    def oracle_bounds(self):
        bounds = self.analysis.oracle_bounds
        f1 = [f"{row.f1:.2f} (σ = {row.f1_sigma:.2f})" for row in bounds.itertuples()]
        return bounds.assign(f1=f1)[["bound", "judged_per_split", "f1", "dr", "fpr"]].rename(columns={
            "judged_per_split": "commands judged per split", "f1": "F1", "dr": "DR", "fpr": "FPR"})

    def label_sensitivity(self):
        sensitivity = self.analysis.label_sensitivity
        return sensitivity[["labels", "condition", "dr", "fpr", "judge_allow_dangerous_per_run"]].rename(columns={
            "condition": "guard", "dr": "DR", "fpr": "FPR",
            "judge_allow_dangerous_per_run": "DANGEROUS commands the judge allowed, per run"})

    def judge_allowed_commands(self):
        """The DANGEROUS-labelled commands that CARE's judge allowed, counted per family, with their audited label."""
        observations, population = self.analysis.observations, self.analysis.population
        audit = self.analysis.configuration.label_audit()
        allowed = observations[(observations.condition == FULL_CARE) & observations.llm_called
                               & observations.label_dangerous & (observations.decision == "ALLOW")]
        commands = population[population.command_id.isin(allowed.command_id)]
        commands = commands.assign(audited=commands.command_id.map(audit).fillna("not audited"))
        counted = commands.groupby(["source", "family", "audited"], sort=False).size().reset_index(name="commands")
        return counted.rename(columns={"audited": "audited label"})

    # -------------------------------------------------------------- where CARE misses
    def redcode_by_kind(self):
        """RedCode-Exec commands denied by each guard, for operational and software-weakness scenarios."""
        scenarios = self.analysis.redcode_scenarios
        guards = [column for column in scenarios.columns if column in PAPER_ORDER]
        by_kind = scenarios.groupby("kind", sort=False)[["n", *guards]].sum()
        by_kind.insert(0, "scenarios", scenarios.groupby("kind", sort=False).size())
        return by_kind.reset_index().rename(columns={"n": "commands"})

    def redcode_scenarios(self):
        return self.analysis.redcode_scenarios

    def static_false_positives(self, limit=5):
        """The first few SAFE-labelled commands that CARE (w/o Resolution) denies."""
        observations = self.analysis.observations
        denied = observations[(observations.condition == STATIC_CARE) & observations.in_primary
                              & ~observations.label_dangerous & observations.prediction_dangerous]
        commands = self.analysis.population.set_index("command_id").loc[denied.command_id, ["source", "command"]]
        first = commands.head(limit)
        return first.assign(command=first.command.str[:120]).reset_index(drop=True)

    # -------------------------------------------------------------- robustness
    def construction_variants(self):
        """Expected F1 on paper-sized splits per construction variant (rows) and guard (columns)."""
        variants = self.analysis.construction_variants
        wide = variants.pivot(index=["variant", "note"], columns="condition", values="f1")
        return wide[[guard for guard in PAPER_ORDER if guard in wide]].reset_index()

    def run_stability(self):
        stability = self.analysis.run_stability
        names = {"condition": "guard", "decisions_that_differ_pct": "decisions that differ between runs (%)"}
        names.update({column: column.replace("f1_run", "F1, run ")
                      for column in stability.columns if column.startswith("f1_run")})
        return stability.rename(columns=names)

    def consistency_with_v1(self):
        return self.analysis.consistency_with_v1.rename(columns={
            "condition": "guard", "same_decision_pct": "same decision as v1 (%)",
            "f1_v1": "F1 in v1", "f1_now": "F1 now"})

    def latency(self):
        comparison = self.analysis.comparison
        latency = comparison[comparison.metric == "latency_mean"][["condition", "reported", "observed"]]
        return latency.rename(columns={"condition": "guard", "reported": "reported mean ms",
                                       "observed": "observed mean ms"})

    def llm_usage(self):
        """One line: tokens and cost of all LLM calls."""
        metrics = self.analysis.metrics
        usage = metrics[metrics.metric.isin(["prompt_tokens", "completion_tokens", "cost"])]
        if usage.empty:
            return ""
        total = usage.groupby("metric").value.sum()
        return (f"LLM usage over all runs: {int(total.get('prompt_tokens', 0)):,} prompt + "
                f"{int(total.get('completion_tokens', 0)):,} completion tokens, cost US${total.get('cost', 0):.2f} "
                "(as reported by OpenRouter).")

    # -------------------------------------------------------------- everything in one Markdown file
    def markdown(self):
        """All tables in one file (`results/report.md`)."""
        configuration = self.analysis.configuration
        threshold = self.analysis.comparison.threshold.dropna().iloc[0]
        simultaneous = self.analysis.paired_differences.threshold_simultaneous.max()
        parts = [f"# Results: CARE baseline reproduction (protocol v{configuration['protocol_version']})\n"]
        if not configuration.full:
            parts.append("> **SMOKE MODE — NOT A REPRODUCTION.** The numbers below come from a few commands.\n")
        parts.append(
            "> Every comparison with the paper is **not directly comparable**: the population is rebuilt from "
            "the public corpora (the authors' 549 commands are unreleased) and labels are corpus-level "
            "(paper Table I).\n")

        def section(title, table, note=None, float_format=".2f"):
            parts.append(f"\n## {title}\n")
            if note:
                parts.append(note + "\n")
            parts.append(markdown_table(table, float_format))

        section("Claim verdicts", self.verdicts())
        number_of_splits = len(self.analysis.splits)
        section(f"Table II: reported → observed on {number_of_splits:,} paper-sized splits (mean, σ; primary run)",
                self.table_ii(),
                f"σ is the standard deviation over the splits. A reported value more than {threshold:.2f}σ from "
                "the mean is one that no plausible split yields.")
        section("Full corpora: every guard on every command (primary run)", self.full_corpora())
        section("CARE vs each comparator on the paper-sized splits (left − right, percentage points)",
                self.paired_differences(),
                f"Two guards count as separated when the mean difference is more than {threshold:.2f}σ from 0 "
                f"({simultaneous:.2f}σ for C10, which judges three comparators at once).")
        section("The paper's McNemar test (two-sided, Yates, α = 0.05) on every split", self.mcnemar())
        section("Resolution funnel", self.resolution_funnel(every_run=True))
        section("Upper bounds for any Resolution judge on the released static stack (paper-sized splits)",
                self.oracle_bounds())
        section("Label sensitivity of the Resolution claims (C7, C9; full corpora)", self.label_sensitivity())
        section("DANGEROUS-labelled commands the judge allowed, per family", self.judge_allowed_commands())
        section("RedCode-Exec: commands denied per risk scenario (of n; primary run)", self.redcode_scenarios(),
                float_format=".0f")
        section("Construction variants: expected F1 on paper-sized splits", self.construction_variants())
        section("Run-to-run stability of the LLM guards", self.run_stability())
        section("Consistency with the archived v1 run (the 549 commands v1 evaluated)", self.consistency_with_v1())
        section("Latency (not comparable: laptop CPU and hosted API vs 4×H100 and local vLLM)", self.latency())
        if self.llm_usage():
            parts.append(f"\n{self.llm_usage()}")
        return "\n".join(parts) + "\n"


def _in_paper_order(table):
    """Rows in the order of the paper's Table II, with the column named `guard`."""
    position = {guard: index for index, guard in enumerate(PAPER_ORDER)}
    ordered = table.sort_values("condition", key=lambda guards: guards.map(position), kind="stable")
    return ordered.rename(columns={"condition": "guard"}).reset_index(drop=True)


def _share_of_splits(share):
    return f"{100 * share:.1f}% of splits"


def _count(value):
    """A count as text: "—" when missing, an integer when whole, else one decimal."""
    if pd.isna(value):
        return "—"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:.1f}"


def _style(axis):
    axis.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(GRID)
    axis.tick_params(colors=MUTED_INK, length=0)
    axis.grid(axis="x", color=GRID, lw=0.8)
    axis.set_axisbelow(True)
