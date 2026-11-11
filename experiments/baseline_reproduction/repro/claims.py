"""Claim verdicts C1-C11 (PROTOCOL.md §7).

Every claim is one function that returns (outcome, rationale).  Distances are measured in sigma,
the standard deviation of a statistic over the paper-sized splits.  The rules:

  * numeric claims (C1-C5 on F1, C8): *not supported (on this reconstruction)* if the reported value
    is more than 1.96 sigma from the mean, else *inconclusive (not contradicted)*: a value within
    that distance is not evidence of equivalence, and the populations differ;
  * directional claims (C6, C10): judged only on whether the mean paired difference is more than
    1.96 sigma from 0; C10 uses 2.39 sigma, which holds for the three comparators at once;
  * Resolution claims (C7, C9): judged on the full corpora, under corpus-level and under audited
    labels; *inconclusive (label-sensitive)* when the two disagree.
"""
from __future__ import annotations

import pandas as pd

from . import stats
from .corpora import FULL_CORPORA
from .guards import CARE_VARIANTS, COMPARATORS, FULL_CARE, STATIC_CARE
from .paper_sized_splits import PAPER_SIZED_SPLITS

SUPPORTED, INCONCLUSIVE = "supported", "inconclusive"
NOT_SUPPORTED = "not supported (on this reconstruction)"
NOT_CONTRADICTED = "inconclusive (not contradicted)"
LABEL_SENSITIVE = "inconclusive (label-sensitive)"

CLAIMS = {   # id: (claim, where the paper makes it)
    "C1": ("Table II row 'CARE (w/o Resolution)': F1 84.99", "Table II"),
    "C2": ("Table II row 'CARE': F1 85.64", "Table II"),
    "C3": ("Table II row 'PromptOnly': F1 66.99", "Table II"),
    "C4": ("Table II row 'LLMJudge': F1 73.09", "Table II"),
    "C5": ("Table II row 'NeMo self-check': F1 68.63", "Table II"),
    "C6": ("CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge", "Sec. V-A1, Table VIII"),
    "C7": ("Resolution lowers FPR (1.82 -> 0.91) at unchanged DR", "Sec. V-A1"),
    "C8": ("About 4.2% of commands (23/549) reach the LLM judge", "Abstract; App. A.F"),
    "C9": ("The judge never converts a DANGEROUS command to ALLOW", "App. A.F"),
    "C10": ("CARE attains the highest F1 among the evaluated guards", "Table II"),
    "C11": ("Mean latency 0.34 ms (CARE w/o Resolution) and 2.32 ms (CARE)", "Table II"),
}
TABLE_II_GUARD = {"C1": STATIC_CARE, "C2": FULL_CARE, "C3": "PromptOnly", "C4": "LLMJudge", "C5": "NeMo self-check"}


def verdicts(comparison, paired_differences, label_sensitivity, metrics, configuration):
    """One row per claim: outcome and rationale."""
    verdict = {claim: table_ii_f1(guard, comparison) for claim, guard in TABLE_II_GUARD.items()}
    verdict["C6"] = beats_llm_judges(paired_differences)
    verdict["C7"] = resolution_lowers_fpr(label_sensitivity)
    verdict["C8"] = escalation_rate_matches(metrics, configuration)
    verdict["C9"] = judge_never_allows_dangerous(label_sensitivity)
    verdict["C10"] = highest_f1(paired_differences)
    verdict["C11"] = latency(comparison)
    rows = []
    for claim, (statement, where) in CLAIMS.items():
        outcome, rationale = verdict[claim]
        rows.append(dict(claim_id=claim, claim=statement, paper_source=where, outcome=outcome, rationale=rationale))
    return pd.DataFrame(rows)


def table_ii_f1(guard, comparison):
    """C1-C5: is the reported F1 more than 1.96 sigma from the mean of the paper-sized splits?"""
    f1 = comparison.set_index(["condition", "metric"]).loc[(guard, "F1")]
    rationale = (
        f"reported F1 {f1.reported:.2f}; paper-sized splits: mean {f1.observed:.2f}, σ = {f1.sigma:.2f}, so the "
        f"reported value is {stats.in_sigmas(f1.sigmas_from_mean)} from the mean; best split {f1.split_max:.2f}; "
        f"full corpora {f1.full_corpora:.2f}")
    return (NOT_CONTRADICTED if f1.within_threshold else NOT_SUPPORTED), rationale


def beats_llm_judges(paired_differences):
    """C6: does CARE (w/o Resolution) beat PromptOnly and LLMJudge in accuracy on the paper-sized splits?"""
    differences = paired_differences.set_index(["left", "right", "metric"])
    outcomes, evidence = [], []
    for judge in ("PromptOnly", "LLMJudge"):
        accuracy = differences.loc[(STATIC_CARE, judge, "delta_accuracy")]
        if accuracy.sigmas_from_zero > accuracy.threshold:
            outcomes.append(SUPPORTED)
        elif accuracy.sigmas_from_zero < -accuracy.threshold:
            outcomes.append(NOT_SUPPORTED)
        else:
            outcomes.append(INCONCLUSIVE)
        evidence.append(
            f"vs {judge}: accuracy {accuracy.value:+.2f} pp, σ = {accuracy.sigma:.2f} "
            f"({stats.in_sigmas(accuracy.sigmas_from_zero)} from 0; paper {accuracy.paper_delta:+.2f} pp); "
            f"the paper's McNemar test favours CARE in {100 * accuracy.mcnemar_favours_left:.0f}% of splits "
            f"and {judge} in {100 * accuracy.mcnemar_favours_right:.0f}%")
    if all(outcome == SUPPORTED for outcome in outcomes):
        return SUPPORTED, "; ".join(evidence)
    return (NOT_SUPPORTED if NOT_SUPPORTED in outcomes else INCONCLUSIVE), "; ".join(evidence)


def resolution_lowers_fpr(label_sensitivity):
    """C7: does Resolution lower FPR at unchanged DR on the full corpora, under both label sets?"""
    rates = label_sensitivity.set_index(["labels", "condition"])
    outcomes, evidence = [], []
    for labels in label_sensitivity["labels"].unique():
        fpr_change = rates.loc[(labels, FULL_CARE)].fpr - rates.loc[(labels, STATIC_CARE)].fpr
        dr_change = rates.loc[(labels, FULL_CARE)].dr - rates.loc[(labels, STATIC_CARE)].dr
        outcomes.append(SUPPORTED if fpr_change < 0 and abs(dr_change) < 1e-9 else NOT_SUPPORTED)
        evidence.append(f"{labels}: FPR {fpr_change:+.2f} pp, DR {dr_change:+.2f} pp")
    return _unless_label_sensitive(outcomes), "full corpora, primary run; " + "; ".join(evidence)


def escalation_rate_matches(metrics, configuration):
    """C8: is the reported escalation rate more than 1.96 sigma from the mean of the paper-sized splits?"""
    paper = configuration["reported"]["resolution_funnel"]
    reported = 100 * paper["escalated"] / paper["n"]
    primary_run = configuration["analysis"]["primary_run"]
    call_rate = metrics[(metrics.condition == FULL_CARE) & (metrics.run == primary_run)
                        & (metrics.metric == "llm_call_rate")].set_index("scope")
    over_splits = call_rate.loc[PAPER_SIZED_SPLITS]
    distance = stats.sigmas_between(reported, over_splits.value, over_splits.sd)
    rationale = (
        f"reported {reported:.2f}%; paper-sized splits: mean {over_splits.value:.2f}%, σ = {over_splits.sd:.2f} "
        f"({stats.in_sigmas(distance)} from the mean); full corpora {call_rate.loc[FULL_CORPORA].value:.2f}%")
    within = abs(distance) <= stats.sigma_threshold(configuration["paper_sized_splits"]["level"])
    return (NOT_CONTRADICTED if within else NOT_SUPPORTED), rationale


def judge_never_allows_dangerous(label_sensitivity):
    """C9: does the judge ever turn a DANGEROUS command into ALLOW, under both label sets?"""
    judged = label_sensitivity.dropna(subset=["judge_allow_dangerous_per_run"]).set_index("labels")
    outcomes = [SUPPORTED if total == 0 else NOT_SUPPORTED for total in judged.judge_allow_dangerous_total]
    evidence = "; ".join(
        f"{labels}: DANGEROUS commands the judge allowed, per run {row.judge_allow_dangerous_per_run}"
        for labels, row in judged.iterrows())
    first = judged.iloc[0]
    evidence += f" ({int(first.commands_audited)} of {int(first.commands_in_question)} such commands audited)"
    return _unless_label_sensitive(outcomes), "full corpora, all runs; " + evidence


def highest_f1(paired_differences):
    """C10: does a CARE variant beat every comparator in F1, or is every variant beaten by one?

    Uses the threshold that holds for the three comparators at once (2.39 sigma, Bonferroni),
    because the strongest comparator is only known after the results.
    """
    f1 = paired_differences[(paired_differences.metric == "delta_F1") & paired_differences.right.isin(COMPARATORS)]
    by_variant = [f1[f1.left == variant] for variant in CARE_VARIANTS if (f1.left == variant).any()]
    some_variant_wins = any((rows.sigmas_from_zero > rows.threshold_simultaneous).all() for rows in by_variant)
    every_variant_beaten = bool(by_variant) and all(
        (rows.sigmas_from_zero < -rows.threshold_simultaneous).any() for rows in by_variant)
    strongest_comparator = f1.loc[f1.groupby("left").value.idxmin()]
    evidence = "; ".join(
        f"{row.left} - {row.right}: F1 {row.value:+.2f} pp, σ = {row.sigma:.2f} "
        f"({stats.in_sigmas(row.sigmas_from_zero)} from 0)"
        for row in strongest_comparator.itertuples())
    evidence += (f"; separated only beyond {strongest_comparator.threshold_simultaneous.iloc[0]:.2f}σ; "
                 "coverage: 6 of the paper's 12 rows")
    outcome = SUPPORTED if some_variant_wins else NOT_SUPPORTED if every_variant_beaten else INCONCLUSIVE
    return outcome, evidence


def latency(comparison):
    """C11: never judged; hardware and serving differ."""
    observed = comparison[comparison.metric == "latency_mean"].set_index("condition").observed
    return INCONCLUSIVE, (
        f"observed mean {observed[STATIC_CARE]:.2f} ms (static) and {observed[FULL_CARE]:.2f} ms (with Resolution) "
        "on a laptop CPU with a hosted API; the paper used 4xH100 with local vLLM, so the values are not comparable")


def _unless_label_sensitive(outcomes):
    """The outcome both label sets agree on, or *inconclusive (label-sensitive)*."""
    return outcomes[0] if len(set(outcomes)) == 1 else LABEL_SENSITIVE
