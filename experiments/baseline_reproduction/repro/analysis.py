"""Every analysis table, computed from the decisions of every guard.

    analysis = Analysis(observations, population, splits, older_art, configuration)

The same decisions are read in two ways (PROTOCOL.md §6):

    full corpora         every command of every corpus: exact rates, nothing sampled
    paper-sized splits   the paper's 549-command composition, re-drawn many times: the mean of
                         each of the paper's statistics, and its standard deviation (sigma)

Each table is an attribute, computed the first time it is used:

    analysis.metrics                 every guard and run, on the full corpora and on the splits
    analysis.comparison              Table II, reported vs observed
    analysis.paired_differences      CARE vs each comparator (Table VIII, C6, C10)
    analysis.verdicts                claims C1-C11
    analysis.resolution_funnel, .oracle_bounds, .label_sensitivity, .redcode_scenarios,
    analysis.construction_variants, .run_stability                            diagnostics
"""
from __future__ import annotations

from functools import cached_property

import numpy as np
import pandas as pd

from . import claims, corpora, stats
from .corpora import FULL_CORPORA, SET_ASIDE
from .guards import CARE_VARIANTS, COMPARATORS, FULL_CARE, PAPER_ORDER, STATIC_CARE
from .paper_sized_splits import PAPER_SIZED_SPLITS, SplitRecipe, Splits

PAIRS = [(variant, comparator) for variant in CARE_VARIANTS for comparator in COMPARATORS]   # CARE vs each comparator
PAIRS.append((FULL_CARE, STATIC_CARE))                                                       # and with vs without Resolution
RATES = [("f1", "F1"), ("dr", "DR"), ("fpr", "FPR"), ("acc", "accuracy")]
NOT_COMPARABLE = ("not directly comparable: reconstructed population (D1-D5, D12, D24), hosted serving (D6), "
                  "NeMo emulation (D7); differences are descriptive")


class Analysis:
    """The decisions of every guard, aligned row by row with the population, and the tables built on them."""

    def __init__(self, observations, population, splits, older_art, configuration):
        self.observations = observations
        self.population = population.reset_index(drop=True)
        self.splits = splits
        self.older_art = older_art          # the 2026-03-24 ART snapshot with static CARE's decisions, or None
        self.configuration = configuration
        self.primary_run = configuration["analysis"]["primary_run"]

        self.dangerous = self.population.label_dangerous.to_numpy(bool)   # the corpus-level label of each command
        self.primary = self.population.in_primary.to_numpy(bool)          # does the command count toward metrics?
        self._of = {key: rows.set_index("command_id").loc[self.population.command_id]
                    for key, rows in observations.groupby(["condition", "run"])}
        self.guards = [guard for guard in PAPER_ORDER if (guard, 1) in self._of]
        self.evaluated_guards = [guard for guard in self.guards if guard != "NoGuard"]

    # -------------------------------------------------------------- the decisions
    def runs(self, guard):
        return sorted(int(run) for name, run in self._of if name == guard)

    def of(self, guard, run=None):
        """The observations of one guard and run, one row per command.  A static guard has run 1 only."""
        run = self.primary_run if run is None else run
        return self._of.get((guard, run), self._of[(guard, 1)])

    def denied(self, guard, run=None):
        """Did the guard deny each command?"""
        return self.of(guard, run).prediction_dangerous.to_numpy(bool)

    def rates_over_splits(self, guard, run=None):
        """F1, DR, FPR and accuracy (fractions) of one guard on every paper-sized split."""
        return stats.rates(stats.split_counts(self.dangerous, self.denied(guard, run), self.splits.rows))

    @cached_property
    def f1_of_every_split(self):
        """F1 (%) of every paper-sized split, per guard: the distribution behind the mean and sigma."""
        return {guard: 100 * self.rates_over_splits(guard)["f1"] for guard in self.evaluated_guards}

    # -------------------------------------------------------------- what each guard decided
    @cached_property
    def metrics(self):
        """Every guard and run: on the full corpora, per source, and over the paper-sized splits."""
        rows = []
        for guard in self.guards:
            for run in self.runs(guard):
                rows += self._metrics_on_full_corpora(guard, run)
        for guard in self.guards:
            for run in self.runs(guard):
                rows += self._metrics_over_splits(guard, run)
        return pd.DataFrame(rows)

    def _metrics_on_full_corpora(self, guard, run):
        observed, denied = self.of(guard, run), self.denied(guard, run)
        this = dict(condition=guard, run_id=observed.run_id.iloc[0], run=run)
        counted = stats.point_metrics(self.dangerous[self.primary], denied[self.primary])
        rows = [dict(this, scope=FULL_CORPORA, metric="F1", value=100 * counted["f1"], unit="%"),
                _rate(this, FULL_CORPORA, "DR", counted["tp"], counted["tp"] + counted["fn"]),
                _rate(this, FULL_CORPORA, "FPR", counted["fp"], counted["fp"] + counted["tn"])]
        for count in ("tp", "fp", "fn", "tn"):
            rows.append(dict(this, scope=FULL_CORPORA, metric=count.upper(), value=counted[count], unit="count"))

        for source, of_source in self._commands_by_source():
            if of_source.any():
                metric = "deny rate" if source == SET_ASIDE else "DR" if self.dangerous[of_source].all() else "FPR"
                rows.append(_rate(this, source, metric, int(denied[of_source].sum()), int(of_source.sum())))

        latency = observed.latency_ms.astype(float)
        for metric, value in [("latency_mean", latency.mean()), ("latency_median", latency.median()),
                              ("latency_p95", latency.quantile(.95))]:
            rows.append(dict(this, scope=FULL_CORPORA, metric=metric, value=value, unit="ms"))
        llm_calls = int(observed.llm_called.to_numpy(bool)[self.primary].sum())
        llm_errors = int(observed.error.notna().sum())
        rows.append(_rate(this, FULL_CORPORA, "llm_call_rate", llm_calls, int(self.primary.sum())))
        rows.append(dict(this, scope=FULL_CORPORA, metric="llm_errors", value=llm_errors, unit="count"))
        if observed.prompt_tokens.notna().any():
            for metric, value, unit in [("prompt_tokens", observed.prompt_tokens.sum(), "tokens"),
                                        ("completion_tokens", observed.completion_tokens.sum(), "tokens"),
                                        ("cost", observed.cost_usd.fillna(0).sum(), "USD")]:
                rows.append(dict(this, scope=FULL_CORPORA, metric=metric, value=float(value), unit=unit))
        return rows

    def _commands_by_source(self):
        """(name, which commands) for each source, then for the NL2Bash commands set aside by D5."""
        source = self.population.source.to_numpy()
        return [(name, (source == name) & self.primary) for name in corpora.SOURCES] + [(SET_ASIDE, ~self.primary)]

    def _metrics_over_splits(self, guard, run):
        """`value` is the mean over the splits and `sd` their standard deviation."""
        this = dict(condition=guard, run_id=self.of(guard, run).run_id.iloc[0], run=run, scope=PAPER_SIZED_SPLITS)
        over_splits = self.rates_over_splits(guard, run)
        rows = [_mean_and_spread(this, name, 100 * over_splits[key]) for key, name in RATES]
        if guard == FULL_CARE:
            escalated = self.of(guard, run).llm_called.to_numpy(bool)[self.splits.rows].mean(1)
            rows.append(_mean_and_spread(this, "llm_call_rate", 100 * escalated))
        return rows

    # -------------------------------------------------------------- reported vs observed
    @cached_property
    def comparison(self):
        """Table II, reported vs observed, per guard and metric.

        `observed` is the mean over the paper-sized splits (primary run) and `sigma` their standard
        deviation; `full_corpora` is the same metric on every command.  `sigmas_from_mean` is the
        distance of the reported value from the mean, and `within_threshold` says whether that
        distance is at most `threshold` (1.96).  The comparison is descriptive: the populations
        differ, so every row is marked not directly comparable.
        """
        reported = self.configuration["reported"]["table_ii"]
        threshold = stats.sigma_threshold(self.configuration["paper_sized_splits"]["level"])
        metrics = self.metrics.set_index(["scope", "condition", "run", "metric"]).sort_index()
        rows = []
        for guard, reported_values in reported["rows"].items():
            if (PAPER_SIZED_SPLITS, guard) not in metrics.index:
                continue
            run = self.primary_run if (PAPER_SIZED_SPLITS, guard, self.primary_run) in metrics.index else 1
            for key, metric in RATES[:3]:
                observed = metrics.loc[(PAPER_SIZED_SPLITS, guard, run, metric)]
                value = reported_values[key]
                across_runs = metrics.loc[(PAPER_SIZED_SPLITS, guard)].xs(metric, level="metric").value
                distance = stats.sigmas_between(value, observed.value, observed.sd)
                within = bool(abs(distance) <= threshold)
                rows.append(dict(
                    source=reported["cite"], condition=guard, metric=metric, unit="%", reported=value,
                    observed=observed.value, sigma=observed.sd, sigmas_from_mean=distance, threshold=threshold,
                    within_threshold=within, split_min=observed["min"], split_max=observed["max"],
                    abs_diff=observed.value - value, rel_diff=(observed.value - value) / value if value else np.nan,
                    run_min=across_runs.min(), run_max=across_runs.max(),
                    full_corpora=metrics.loc[(FULL_CORPORA, guard, run, metric)].value,
                    status=f"reported {'within' if within else 'beyond'} {threshold:.2f} sigma of the mean "
                           "of the paper-sized splits",
                    comparability=NOT_COMPARABLE))
            rows.append(dict(
                source=reported["cite"], condition=guard, metric="latency_mean", unit="ms",
                reported=reported_values["latency_ms"],
                observed=metrics.loc[(FULL_CORPORA, guard, run, "latency_mean")].value,
                status="not comparable (different hardware and LLM serving)", comparability=NOT_COMPARABLE))
        return pd.DataFrame(rows)

    @cached_property
    def paired_differences(self):
        """CARE vs each comparator on the paper-sized splits: left - right, in percentage points.

        Per pair and metric (F1, accuracy): the mean and standard deviation over the splits, and
        `sigmas_from_zero`, the mean in units of that standard deviation.  Two guards count as
        separated beyond `threshold` (1.96), or `threshold_simultaneous` (2.39) when all three
        comparators are judged at once (C10).  Accuracy rows also apply the paper's own test
        (McNemar with Yates, alpha = 0.05; Table VIII) to every split.
        """
        level = self.configuration["paper_sized_splits"]["level"]
        threshold = stats.sigma_threshold(level)
        simultaneous = stats.sigma_threshold(level, comparisons=len(COMPARATORS))
        reported = self.configuration["reported"]
        paper_pairs = {(pair["left"], pair["right"]): pair for pair in reported["table_viii"]["rows"]}
        paper_split_size = reported["resolution_funnel"]["n"]

        over_splits = {guard: self.rates_over_splits(guard) for guard in self.evaluated_guards}
        on_corpora = {guard: stats.point_metrics(self.dangerous[self.primary], self.denied(guard)[self.primary])
                      for guard in self.evaluated_guards}
        rows = []
        for left, right in PAIRS:
            if left not in over_splits or right not in over_splits:
                continue
            left_correct = self.denied(left) == self.dangerous
            right_correct = self.denied(right) == self.dangerous
            left_only = (left_correct & ~right_correct)[self.splits.rows].sum(1)
            right_only = (~left_correct & right_correct)[self.splits.rows].sum(1)
            significant = stats.mcnemar_p_yates(left_only, right_only) < 0.05
            paper = paper_pairs.get((left, right), {})

            corpora_difference = {"f1": on_corpora[left]["f1"] - on_corpora[right]["f1"],
                                  "acc": _accuracy(on_corpora[left]) - _accuracy(on_corpora[right])}
            for key, metric in [("f1", "F1"), ("acc", "accuracy")]:
                difference = 100 * (over_splits[left][key] - over_splits[right][key])
                mean, sigma = float(difference.mean()), float(difference.std())
                row = dict(left=left, right=right, metric=f"delta_{metric}", value=mean, sigma=sigma,
                           sigmas_from_zero=stats.sigmas_between(mean, 0.0, sigma), threshold=threshold,
                           threshold_simultaneous=simultaneous if right in COMPARATORS else np.nan,
                           share_left_better=float((difference > 0).mean()),
                           full_corpora=100 * corpora_difference[key])
                if key == "acc":
                    row.update(
                        left_only=float(left_only.mean()), right_only=float(right_only.mean()),
                        mcnemar_favours_left=float((significant & (left_only > right_only)).mean()),
                        mcnemar_favours_right=float((significant & (right_only > left_only)).mean()),
                        paper_left_only=paper.get("left_only"), paper_right_only=paper.get("right_only"),
                        paper_p=paper.get("p"),
                        paper_delta=(100 * (paper["left_only"] - paper["right_only"]) / paper_split_size
                                     if paper else np.nan))
                rows.append(row)
        return pd.DataFrame(rows)

    @cached_property
    def verdicts(self):
        """Claims C1-C11: outcome and rationale (the rules are in claims.py)."""
        return claims.verdicts(self.comparison, self.paired_differences, self.label_sensitivity,
                               self.metrics, self.configuration)

    # -------------------------------------------------------------- diagnostics: Resolution
    def _static_warnings(self):
        """(WARN, escalated by the code) per command, from CARE's deterministic static stack."""
        static = self.of(STATIC_CARE)
        warn = static.provisional.eq("WARN").to_numpy()
        return warn, warn & static.skip_predicate.isna().to_numpy()

    @cached_property
    def resolution_funnel(self):
        """Static WARN -> skipped by a predicate -> escalated -> judge ALLOW, in the paper's terms (App. A.F).

        One row for the paper, then per run: the mean count in a paper-sized split, and the count
        on the full corpora.
        """
        warn, _ = self._static_warnings()
        paper = self.configuration["reported"]["resolution_funnel"]
        stages = ["warn", "skipped", "escalated", "judge_allow", "judge_allow_dangerous"]
        rows = [dict(scope=f"paper ({paper['cite']})", run=np.nan, n=paper["n"],
                     **{stage: paper[stage] for stage in stages}, judge_errors=np.nan)]
        for run in self.runs(FULL_CARE):
            judged = self.of(FULL_CARE, run)
            escalated = judged.llm_called.to_numpy(bool)
            allowed = escalated & judged.decision.eq("ALLOW").to_numpy()
            commands = dict(warn=warn, skipped=warn & ~escalated, escalated=escalated, judge_allow=allowed,
                            judge_allow_dangerous=allowed & self.dangerous)
            per_split = {stage: float(which[self.splits.rows].sum(1).mean()) for stage, which in commands.items()}
            on_corpora = {stage: int((which & self.primary).sum()) for stage, which in commands.items()}
            rows.append(dict(scope=f"{PAPER_SIZED_SPLITS} (mean)", run=run, n=self.splits.rows.shape[1],
                             **per_split, judge_errors=np.nan))
            rows.append(dict(scope=FULL_CORPORA, run=run, n=int(self.primary.sum()),
                             **on_corpora, judge_errors=int(judged.error.notna().sum())))
        funnel = pd.DataFrame(rows)
        funnel = funnel.assign(escalated_pct=100 * funnel.escalated / funnel.n)
        paper_first = funnel.scope.map(
            lambda scope: 0 if scope.startswith("paper (") else 1 if scope.startswith(PAPER_SIZED_SPLITS) else 2)
        return funnel.iloc[np.argsort(paper_first, kind="stable")].reset_index(drop=True)

    @cached_property
    def oracle_bounds(self):
        """Upper bounds on CARE's F1 for ANY Resolution judge, given the released static stack.

        The judge's decisions are replaced by the label: on the commands the code escalates, then
        on every WARN command (ignoring the skip predicates).  Derived from the observations.
        """
        static_denied = self.denied(STATIC_CARE)
        warn, escalated = self._static_warnings()
        rows = []
        for bound, judged in [("static only (no judge)", np.zeros_like(warn)),
                              ("perfect judge on the escalated commands", escalated),
                              ("perfect judge on every WARN command", warn)]:
            with_perfect_judge = np.where(judged, self.dangerous, static_denied)
            over_splits = stats.rates(stats.split_counts(self.dangerous, with_perfect_judge, self.splits.rows))
            rows.append(dict(bound=bound, judged_per_split=float(judged[self.splits.rows].sum(1).mean()),
                             f1=100 * over_splits["f1"].mean(), f1_sigma=100 * over_splits["f1"].std(),
                             dr=100 * over_splits["dr"].mean(), fpr=100 * over_splits["fpr"].mean()))
        return pd.DataFrame(rows)

    @cached_property
    def label_sensitivity(self):
        """CARE with and without Resolution under corpus-level labels and under audited labels (D17, D28).

        The audit covers the DANGEROUS-labelled commands that the judge allowed in any run: the
        only labels that can move C7 and C9.  The selection depends on the predictions, so this
        is a sensitivity analysis, never a replacement for the primary labels.
        """
        audit = self.configuration.label_audit()
        population = self.population
        audited_label = [audit.get(command, label) for command, label in zip(population.command_id, population.label)]
        audited_dangerous = np.array(audited_label) == "DANGEROUS"
        judge_allowed = {}
        for run in self.runs(FULL_CARE):
            judged = self.of(FULL_CARE, run)
            judge_allowed[run] = (judged.llm_called & judged.decision.eq("ALLOW")).to_numpy(bool)
        in_question = np.any(list(judge_allowed.values()), axis=0) & self.dangerous & self.primary

        rows = []
        for labels, dangerous in [("corpus-level labels (paper Table I)", self.dangerous),
                                  ("audited labels for the judge-allowed commands", audited_dangerous)]:
            for guard in CARE_VARIANTS:
                counted = stats.point_metrics(dangerous[self.primary], self.denied(guard)[self.primary])
                rows.append(dict(labels=labels, condition=guard, dr=100 * counted["dr"], fpr=100 * counted["fpr"],
                                 n_dangerous=int(dangerous[self.primary].sum())))
            per_run = [int((allowed & dangerous & self.primary).sum()) for allowed in judge_allowed.values()]
            rows[-1].update(judge_allow_dangerous_per_run=str(per_run), judge_allow_dangerous_total=sum(per_run),
                            commands_in_question=int(in_question.sum()),
                            commands_audited=int(population.command_id[in_question].isin(audit).sum()))
        return pd.DataFrame(rows)

    # -------------------------------------------------------------- diagnostics: where and why
    @cached_property
    def redcode_scenarios(self):
        """Commands denied per RedCode-Exec risk scenario and guard (scenario kind: D9)."""
        scenario = corpora.redcode_scenario(self.population)
        rows = []
        for number in sorted(scenario.dropna().unique()):
            of_scenario = (scenario == number).to_numpy()
            is_weakness = int(number) in corpora.REDCODE_WEAKNESS_SCENARIOS
            denied = {guard: int(self.denied(guard)[of_scenario].sum()) for guard in self.evaluated_guards}
            rows.append(dict(scenario=int(number), kind="software-weakness" if is_weakness else "operational",
                             n=int(of_scenario.sum()), **denied))
        return pd.DataFrame(rows)

    @cached_property
    def construction_variants(self):
        """Expected F1/DR/FPR on paper-sized splits when one construction decision is changed.

            V0   the protocol
            V1   NL2Bash commands set aside by D5 are drawn too, and count as SAFE
            V2   RedCode software-weakness scenarios are not drawn (exploratory, D9)
            V2b  no RedCode at all (149 DANGEROUS / 329 SAFE)
            V3   ART as of 2026-03-24 (D12): CARE (w/o Resolution) only, the one guard run on it
        """
        recipe = self.configuration["paper_sized_splits"]
        if not self.configuration.full:
            recipe = {**recipe, **self.configuration["smoke"]}
        seeds, drawn = self.splits.seeds, self.splits.by_source

        def redrawn(source, eligible):
            """The protocol's splits with one source re-drawn from the `eligible` commands."""
            other_recipe = SplitRecipe(self.population, recipe["composition"], recipe["nl2bash_head_cap"], eligible)
            return Splits(seeds, {**drawn, **other_recipe.draw(seeds, [source])})

        everything = np.ones(len(self.population), bool)
        weakness = corpora.redcode_scenario(self.population).isin(corpora.REDCODE_WEAKNESS_SCENARIOS).to_numpy()
        without_redcode = {source: rows for source, rows in drawn.items() if source != "RedCode-Exec"}
        variants = [
            ("V0", "the protocol", self.splits),
            ("V1", "NL2Bash: D5 filter off", redrawn("NL2Bash", everything)),
            ("V2", "RedCode: software-weakness scenarios not drawn (exploratory)",
             redrawn("RedCode-Exec", self.primary & ~weakness)),
            ("V2b", "RedCode: not drawn", Splits(seeds, without_redcode)),
        ]
        rows = []
        for variant, note, splits in variants:
            for guard in self.evaluated_guards:
                counts = stats.split_counts(self.dangerous, self.denied(guard), splits.rows)
                rows.append(dict(variant=variant, note=note, condition=guard, **_expected_rates(counts)))

        if self.older_art is not None:
            older = self.older_art
            art_quota = {"ART": recipe["composition"]["ART"]}
            older_art_rows = SplitRecipe(older, art_quota, None).draw(seeds, ["ART"])["ART"]
            without_art = Splits(seeds, {source: rows_ for source, rows_ in drawn.items() if source != "ART"})
            counts = (stats.split_counts(older.label_dangerous, older.deny, older_art_rows)
                      + stats.split_counts(self.dangerous, self.denied(STATIC_CARE), without_art.rows))
            now = int((self.population.source == "ART").sum())
            rows.append(dict(variant="V3", note=f"ART snapshot of 2026-03-24 ({len(older)} commands, now {now})",
                             condition=STATIC_CARE, **_expected_rates(counts)))
        return pd.DataFrame(rows)

    @cached_property
    def run_stability(self):
        """Per LLM guard: share of commands whose decision differs between runs, and the F1 of each run."""
        metrics = self.metrics
        f1 = metrics[(metrics.scope == PAPER_SIZED_SPLITS) & (metrics.metric == "F1")]
        f1 = f1.set_index(["condition", "run"]).value
        rows = []
        for guard in self.evaluated_guards:
            runs = self.runs(guard)
            if len(runs) > 1:
                denied = np.stack([self.denied(guard, run) for run in runs])
                differs = denied.min(0) != denied.max(0)
                f1_per_run = {f"f1_run{run}": f1[(guard, run)] for run in runs}
                rows.append(dict(condition=guard, runs=len(runs),
                                 decisions_that_differ_pct=100 * float(differs.mean()), **f1_per_run))
        return pd.DataFrame(rows)

    # -------------------------------------------------------------- everything, for export
    def tables(self):
        """Every analysis table, by the name of its Parquet file."""
        return dict(
            metrics=self.metrics, comparison=self.comparison, paired_differences=self.paired_differences,
            claims=self.verdicts, resolution_funnel=self.resolution_funnel, oracle_bounds=self.oracle_bounds,
            label_sensitivity=self.label_sensitivity, redcode_scenarios=self.redcode_scenarios,
            run_stability=self.run_stability, construction_variants=self.construction_variants)


def _rate(this, scope, metric, count, total):
    return dict(this, scope=scope, metric=metric, value=100 * count / total if total else np.nan, unit="%",
                k=count, n=total)


def _mean_and_spread(this, metric, values, unit="%"):
    return dict(this, metric=metric, value=float(np.nanmean(values)), unit=unit, sd=float(np.nanstd(values)),
                min=float(np.nanmin(values)), max=float(np.nanmax(values)), n=len(values))


def _accuracy(counted):
    return (counted["tp"] + counted["tn"]) / (counted["tp"] + counted["fp"] + counted["fn"] + counted["tn"])


def _expected_rates(counts):
    over_splits = stats.rates(counts)
    return dict(f1=100 * over_splits["f1"].mean(), dr=100 * np.nanmean(over_splits["dr"]),
                fpr=100 * np.nanmean(over_splits["fpr"]))
