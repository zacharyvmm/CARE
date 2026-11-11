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

from . import stats as S
from .analysis import CARE_VARIANTS, COMPARATORS, CORPORA, FULL, SPLITS, STATIC

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
TABLE_II_ROWS = {"C1": STATIC, "C2": FULL, "C3": "PromptOnly", "C4": "LLMJudge", "C5": "NeMo self-check"}


def verdicts(comparison, differences, label_sens, metrics, cfg):
    """One row per claim: outcome and rationale."""
    v = {cid: table_ii_f1(cond, comparison) for cid, cond in TABLE_II_ROWS.items()}
    v["C6"] = beats_llm_judges(differences)
    v["C7"] = resolution_lowers_fpr(label_sens)
    v["C8"] = escalation_rate_matches(metrics, cfg)
    v["C9"] = judge_never_allows_dangerous(label_sens)
    v["C10"] = highest_f1(differences)
    v["C11"] = latency(comparison)
    return pd.DataFrame([dict(claim_id=cid, claim=claim, paper_source=source, outcome=v[cid][0], rationale=v[cid][1])
                         for cid, (claim, source) in CLAIMS.items()])


def table_ii_f1(condition, comparison):
    """C1-C5: is the reported F1 more than 1.96 sigma from the mean of the paper-sized splits?"""
    x = comparison.set_index(["condition", "metric"]).loc[(condition, "F1")]
    why = (f"reported F1 {x.reported:.2f}; paper-sized splits: mean {x.observed:.2f}, σ = {x.sigma:.2f}, so the "
           f"reported value is {S.in_sigmas(x.sigmas_from_mean)} from the mean; best split {x.split_max:.2f}; "
           f"full corpora {x.full_corpora:.2f}")
    return (NOT_CONTRADICTED if x.within_threshold else NOT_SUPPORTED), why


def beats_llm_judges(differences):
    """C6: does CARE (w/o Resolution) beat PromptOnly and LLMJudge in accuracy on the paper-sized splits?"""
    d = differences.set_index(["left", "right", "metric"])
    per_pair, parts = [], []
    for other in ("PromptOnly", "LLMJudge"):
        x = d.loc[(STATIC, other, "delta_accuracy")]
        per_pair.append(SUPPORTED if x.sigmas_from_zero > x.threshold else
                        NOT_SUPPORTED if x.sigmas_from_zero < -x.threshold else INCONCLUSIVE)
        parts.append(f"vs {other}: accuracy {x.value:+.2f} pp, σ = {x.sigma:.2f} ({S.in_sigmas(x.sigmas_from_zero)} from 0; "
                     f"paper {x.paper_delta:+.2f} pp); "
                     f"the paper's McNemar test favours CARE in {100 * x.mcnemar_favours_left:.0f}% of splits "
                     f"and {other} in {100 * x.mcnemar_favours_right:.0f}%")
    outcome = (SUPPORTED if all(v == SUPPORTED for v in per_pair) else
               NOT_SUPPORTED if NOT_SUPPORTED in per_pair else INCONCLUSIVE)
    return outcome, "; ".join(parts)


def resolution_lowers_fpr(label_sens):
    """C7: does Resolution lower FPR at unchanged DR on the full corpora, under both label sets?"""
    ls = label_sens.set_index(["labels", "condition"])
    per_labels, parts = [], []
    for labels in label_sens["labels"].unique():
        dfpr = ls.loc[(labels, FULL)].fpr - ls.loc[(labels, STATIC)].fpr
        ddr = ls.loc[(labels, FULL)].dr - ls.loc[(labels, STATIC)].dr
        per_labels.append(SUPPORTED if dfpr < 0 and abs(ddr) < 1e-9 else NOT_SUPPORTED)
        parts.append(f"{labels}: FPR {dfpr:+.2f} pp, DR {ddr:+.2f} pp")
    return (per_labels[0] if len(set(per_labels)) == 1 else LABEL_SENSITIVE), "full corpora, primary run; " + "; ".join(parts)


def escalation_rate_matches(metrics, cfg):
    """C8: is the reported escalation rate more than 1.96 sigma from the mean of the paper-sized splits?"""
    p = cfg["reported"]["resolution_funnel"]
    reported = 100 * p["escalated"] / p["n"]
    m = metrics[(metrics.condition == FULL) & (metrics.run == cfg["analysis"]["primary_run"])
                & (metrics.metric == "llm_call_rate")].set_index("scope")
    x = m.loc[SPLITS]
    distance = S.sigmas_between(reported, x.value, x.sd)
    why = (f"reported {reported:.2f}%; paper-sized splits: mean {x.value:.2f}%, σ = {x.sd:.2f} "
           f"({S.in_sigmas(distance)} from the mean); full corpora {m.loc[CORPORA].value:.2f}%")
    within = abs(distance) <= S.sigma_threshold(cfg["paper_sized_splits"]["level"])
    return (NOT_CONTRADICTED if within else NOT_SUPPORTED), why


def judge_never_allows_dangerous(label_sens):
    """C9: does the judge ever turn a DANGEROUS command into ALLOW, under both label sets?"""
    judged = label_sens.dropna(subset=["judge_allow_dangerous_per_run"]).set_index("labels")
    per_labels = [SUPPORTED if total == 0 else NOT_SUPPORTED for total in judged.judge_allow_dangerous_total]
    why = "; ".join(f"{labels}: DANGEROUS commands the judge allowed, per run {r.judge_allow_dangerous_per_run}"
                    for labels, r in judged.iterrows())
    first = judged.iloc[0]
    why += f" ({int(first.commands_audited)} of {int(first.commands_in_question)} such commands audited)"
    return (per_labels[0] if len(set(per_labels)) == 1 else LABEL_SENSITIVE), "full corpora, all runs; " + why


def highest_f1(differences):
    """C10: does a CARE variant beat every comparator in F1, or is every variant beaten by one?

    Uses the threshold that holds for the three comparators at once (2.39 sigma, Bonferroni),
    because the strongest comparator is only known after the results.
    """
    d = differences[(differences.metric == "delta_F1") & differences.right.isin(COMPARATORS)]
    by_variant = {c: d[d.left == c] for c in CARE_VARIANTS if (d.left == c).any()}
    wins = any((g.sigmas_from_zero > g.threshold_simultaneous).all() for g in by_variant.values())
    beaten = bool(by_variant) and all((g.sigmas_from_zero < -g.threshold_simultaneous).any() for g in by_variant.values())
    closest = d.loc[d.groupby("left").value.idxmin()]
    why = "; ".join(f"{r.left} - {r.right}: F1 {r.value:+.2f} pp, σ = {r.sigma:.2f} ({S.in_sigmas(r.sigmas_from_zero)} from 0)"
                    for r in closest.itertuples())
    return (SUPPORTED if wins else NOT_SUPPORTED if beaten else INCONCLUSIVE,
            why + f"; separated only beyond {closest.threshold_simultaneous.iloc[0]:.2f}σ; coverage: 6 of the paper's 12 rows")


def latency(comparison):
    """C11: never judged; hardware and serving differ."""
    x = comparison[comparison.metric == "latency_mean"].set_index("condition").observed
    return INCONCLUSIVE, (f"observed mean {x[STATIC]:.2f} ms (static) and {x[FULL]:.2f} ms (with Resolution) on a laptop "
                          "CPU with a hosted API; the paper used 4xH100 with local vLLM, so the values are not comparable")
