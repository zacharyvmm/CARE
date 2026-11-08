"""Claim verdicts C1-C11 (PROTOCOL.md §6, amended by §11-§13).

    verdicts(design, ...)        protocol v1.3: the verdicts the README and notebook report
    verdicts_v1_2 / _v1_1 / _v1_0  superseded rule sets, kept for the record (DECISIONS D15-D23)
    claims_table(v1_3, ...)      one row per claim, the v1.3 verdict first and the superseded outcomes alongside

Every verdict is an (outcome, rationale) pair.  The v1.3 rules:
  * numeric claims (C1-C5 on F1, C8): *not supported (on this reconstruction)* if the reported value lies
    outside our design-based 95% CI, else *inconclusive (not contradicted)*: CI inclusion is not equivalence,
    and the populations differ;
  * directional claims (C6, C10): judged only on whether the design-based CI of the paired difference
    excludes 0; C10's intervals are simultaneous (Bonferroni) over the non-CARE comparators (D23);
  * label-sensitive claims (C7, C9): *inconclusive (label-sensitive)* when corpus-level and audited labels disagree.
"""
from __future__ import annotations

import pandas as pd

from . import stats as S

NS, INC = "not supported (on this reconstruction)", "inconclusive (not contradicted)"
LABEL_SENSITIVE = "inconclusive (label-sensitive)"
CLAIMS = {   # id: (claim, where the paper makes it)
    "C1": ("Table II row 'CARE (w/o Resolution)': F1/DR/FPR", "Table II"),
    "C2": ("Table II row 'CARE': F1/DR/FPR", "Table II"),
    "C3": ("Table II row 'PromptOnly': F1/DR/FPR", "Table II"),
    "C4": ("Table II row 'LLMJudge': F1/DR/FPR", "Table II"),
    "C5": ("Table II row 'NeMo self-check': F1/DR/FPR", "Table II"),
    "C6": ("CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge (McNemar)", "Sec. V-A1, Table VIII"),
    "C7": ("Resolution lowers FPR (1.82 -> 0.91) at unchanged DR", "Sec. V-A1"),
    "C8": ("About 4.2% of commands (23/549) reach the LLM judge", "Abstract-level claim; App. A.F"),
    "C9": ("The judge never converts a DANGEROUS command to ALLOW", "App. A.F"),
    "C10": ("CARE attains the highest F1 among the evaluated guards", "Table II"),
    "C11": ("CARE (w/o Resolution) mean latency 0.34 ms; CARE 2.32 ms", "Table II"),
}
TABLE_II_ROWS = {"C1": "CARE (w/o Resolution)", "C2": "CARE", "C3": "PromptOnly", "C4": "LLMJudge",
                 "C5": "NeMo self-check"}
PAPER_N = 549


# ------------------------------------------------------------------ protocol v1.3
def verdicts(design, label_sens, metrics, seeds, cfg):
    """Protocol v1.3 verdicts from one design-based estimator (`analysis.Design`)."""
    v = {cid: table_ii_f1(cond, design.intervals, seeds, cfg) for cid, cond in TABLE_II_ROWS.items()}
    v["C6"] = beats_llm_judges(design.differences, cfg)
    v["C7"] = resolution_lowers_fpr(label_sens)
    v["C8"] = escalation_rate_matches(design.escalation, cfg)
    v["C9"] = judge_never_allows_dangerous(label_sens)
    v["C10"] = highest_f1_simultaneous(design.differences)
    v["C11"] = ("inconclusive", latency_evidence(metrics, cfg))
    return v


def table_ii_f1(cond, intervals, seeds, cfg):
    """C1-C5: is the reported F1 outside our design-based CI?"""
    r = cfg["reported"]["table_ii"]["rows"][cond]["f1"]
    x = intervals.set_index(["condition", "metric"]).loc[(cond, "F1")]
    why = (f"verdict on F1 (headline metric; DR/FPR descriptive): reported {r:.2f}; observed "
           f"{x.value:.2f}, design-based 95% CI [{x.ci_lo:.1f}, {x.ci_hi:.1f}]")
    if cond == "CARE (w/o Resolution)" and seeds is not None:
        why += f"; {len(seeds)} reconstructed splits: max {seeds.f1.max():.2f}"
    return (INC if x.ci_lo - 1e-9 <= r <= x.ci_hi + 1e-9 else NS), why


def beats_llm_judges(differences, cfg, require_paper_effect_inside=False):
    """C6: does static CARE beat PromptOnly and LLMJudge in accuracy (paired CI excludes 0)?

    `require_paper_effect_inside` is the superseded v1.1 rule, which also rejected the claim when
    the paper's effect size fell outside our interval (dropped in v1.2, D21).
    """
    d = differences.set_index(["left", "right", "metric"])
    paper = {r["right"]: (r["left_only"] - r["right_only"]) / PAPER_N * 100
             for r in cfg["reported"]["table_viii"]["rows"] if r["left"] == "CARE (w/o Resolution)"}
    parts, per_base = [], []
    for base in ("PromptOnly", "LLMJudge"):
        x = d.loc[("CARE (w/o Resolution)", base, "delta_accuracy")]
        eff = paper[base]
        in_ci = x.ci_lo <= eff <= x.ci_hi
        against = x.ci_hi < 0 or (require_paper_effect_inside and not in_ci)
        per_base.append("supported" if x.ci_lo > 0 else "not supported" if against else "inconclusive")
        parts.append(f"vs {base}: delta accuracy {x.value:+.2f} pp [{x.ci_lo:.1f}, {x.ci_hi:.1f}] "
                     f"(paper {eff:+.2f} pp, {'inside' if in_ci else 'outside'} the interval)")
    outcome = ("supported" if all(v == "supported" for v in per_base) else
               NS if any(v == "not supported" for v in per_base) else "inconclusive")
    return outcome, "; ".join(parts) + " (design-based, paired)"


def resolution_lowers_fpr(label_sens):
    """C7: does Resolution lower FPR at unchanged DR, under both label sets?"""
    ls = label_sens.set_index(["labels", "condition"])
    deltas = []
    for labels in label_sens["labels"].unique():
        a, b = ls.loc[(labels, "CARE")], ls.loc[(labels, "CARE (w/o Resolution)")]
        deltas.append((labels, a.fpr - b.fpr, a.dr - b.dr))
    per_labels = ["supported" if dfpr < 0 and abs(ddr) < 1e-9 else "not supported" for _, dfpr, ddr in deltas]
    outcome = per_labels[0] if len(set(per_labels)) == 1 else LABEL_SENSITIVE
    return outcome, "; ".join(f"{lab}: dFPR {dfpr:+.2f} pp, dDR {ddr:+.2f} pp -> {v}"
                              for (lab, dfpr, ddr), v in zip(deltas, per_labels))


def escalation_rate_matches(escalation, cfg):
    """C8: is the reported escalation rate outside our design-based CI?"""
    rp = 100 * cfg["reported"]["resolution_funnel"]["escalated"] / PAPER_N
    return (INC if escalation["ci_lo"] <= rp <= escalation["ci_hi"] else NS,
            f"escalation {escalation['value']:.2f}% [design-based {escalation['ci_lo']:.1f}, "
            f"{escalation['ci_hi']:.1f}] vs reported {rp:.2f}%")


def judge_never_allows_dangerous(label_sens):
    """C9: does the judge ever turn a DANGEROUS command into ALLOW, under both label sets?"""
    judged = label_sens.dropna(subset=["judge_allow_dangerous_per_run"]).set_index("labels")
    per_labels = ["supported" if t == 0 else "not supported" for t in judged.judge_allow_dangerous_total]
    outcome = per_labels[0] if len(set(per_labels)) == 1 else LABEL_SENSITIVE
    return outcome, "; ".join(f"{lab}: DANGEROUS judge ALLOWs per run {r.judge_allow_dangerous_per_run}"
                              for lab, r in judged.iterrows())


def _non_care_minus_care_f1(differences):
    d = differences
    return d[(d.metric == "delta_F1") & ~d.left.str.startswith("CARE") & d.right.str.startswith("CARE")]


def highest_f1_simultaneous(differences):
    """C10 (v1.3, D23): is some CARE variant beaten, or does one beat every comparator, simultaneously?"""
    vs = _non_care_minus_care_f1(differences)
    groups = dict(tuple(vs.groupby("right")))
    beaten = {c: bool((g.adj_ci_lo > 0).any()) for c, g in groups.items()}
    wins = {c: bool((g.adj_ci_hi < 0).all()) for c, g in groups.items()}
    outcome = ("supported" if any(wins.values()) else
               NS if groups and all(beaten.values()) else "inconclusive")
    best = vs.loc[vs.groupby("right").value.idxmax()]
    why = ("; ".join(f"{r.left} - {r.right}: delta F1 {r.value:+.2f} pp, Bonferroni-adjusted CI "
                     f"[{r.adj_ci_lo:.2f}, {r.adj_ci_hi:.2f}]" for r in best.itertuples())
           + f" (simultaneous over the {vs.left.nunique()} non-CARE comparators)")
    return outcome, why + "; coverage: 6 of the paper's 12 rows"


def latency_evidence(metrics, cfg):
    lat = _primary(metrics, cfg, "CARE (w/o Resolution)", "latency_mean")
    return (f"observed static mean {lat:.2f} ms on a laptop CPU; full-CARE latency dominated by hosted-API round trips; "
            "hardware and serving differ, so not directly comparable")


def _primary(metrics, cfg, condition, metric):
    m = metrics
    return m[(m.condition == condition) & (m.rep == cfg["analysis"]["primary_run"]) & (m.metric == metric)].value.iloc[0]


# ------------------------------------------------------------------ superseded rule sets (kept for the record)
def verdicts_v1_2(design, label_sens, metrics, seeds, cfg):
    """v1.3, except C10: an unadjusted interval against the comparator with the best observed F1."""
    return dict(verdicts(design, label_sens, metrics, seeds, cfg),
                C10=highest_f1_best_comparator(design.differences, metrics, cfg))


def verdicts_v1_1(design_v11, label_sens, metrics, seeds, cfg):
    """v1.3 on the cluster bootstrap (D15), except C6 (paper effect must lie inside) and C10 (as v1.2)."""
    return dict(verdicts(design_v11, label_sens, metrics, seeds, cfg),
                C6=beats_llm_judges(design_v11.differences, cfg, require_paper_effect_inside=True),
                C10=highest_f1_best_comparator(design_v11.differences, metrics, cfg))


def highest_f1_best_comparator(differences, metrics, cfg):
    """C10 (v1.1-v1.2): best observed non-CARE condition minus each CARE variant, unadjusted."""
    vs = _non_care_minus_care_f1(differences)
    f1 = metrics[(metrics.rep == cfg["analysis"]["primary_run"]) & (metrics.metric == "F1")].set_index("condition").value
    best = vs[vs.left == f1[list(vs.left.unique())].idxmax()]
    outcome = NS if len(best) and (best.ci_lo > 0).all() else "inconclusive"
    why = "; ".join(f"{r.left} - {r.right}: delta F1 {r.value:+.2f} pp [{r.ci_lo:.2f}, {r.ci_hi:.2f}]"
                    for r in best.itertuples()) + " (unadjusted; comparator chosen as the best observed F1)"
    return outcome, why + "; coverage: 6 of the paper's 12 rows"


def verdicts_v1_0(comparison, mcnemar, funnel, metrics, seeds, cfg):
    """The frozen v1.0 rules (PROTOCOL.md §6): per-command CIs, McNemar p-values, Wilson intervals."""
    v = {}
    for cid, cond in TABLE_II_ROWS.items():
        t = comparison[(comparison.condition == cond) & comparison.metric.isin(["F1", "DR", "FPR"])]
        outcome = {3: "supported", 0: "not supported"}.get(int(t.inside_ci.sum()), "partially supported")
        ev = "; ".join(f"{r.metric} reported {r.reported:.2f} vs observed {r.observed:.2f} [{r.ci_lo:.1f}, {r.ci_hi:.1f}] "
                       f"-> {'consistent' if r.inside_ci else 'inconsistent'}" for r in t.itertuples())
        if cond == "CARE (w/o Resolution)" and seeds is not None:
            ev += (f"; F1 over {len(seeds)} alternative split seeds: max {seeds.f1.max():.2f}, "
                   f"95% range {seeds.f1.quantile(.025):.2f}-{seeds.f1.quantile(.975):.2f}")
        v[cid] = (outcome, ev)

    sig = mcnemar[(mcnemar.left == "CARE (w/o Resolution)") & mcnemar.right.isin(["PromptOnly", "LLMJudge"])]
    same = (sig.left_only > sig.right_only).all()
    v["C6"] = ("supported" if same and (sig.p_yates < 0.05).all() else "partially supported" if same else "not supported",
               "; ".join(f"vs {r.right}: {r.left_only}/{r.right_only} discordant, p_Yates={r.p_yates:.3g} "
                         f"(paper {r.paper_left_only}/{r.paper_right_only}, p={r.paper_p:.2g})" for r in sig.itertuples()))

    g = lambda c, m: _primary(metrics, cfg, c, m)  # noqa: E731
    dfpr, ddr = g("CARE", "FPR") - g("CARE (w/o Resolution)", "FPR"), g("CARE", "DR") - g("CARE (w/o Resolution)", "DR")
    v["C7"] = ("supported" if dfpr < 0 and abs(ddr) < 1e-9 else "partially supported" if dfpr < 0 else "not supported",
               f"primary run: dFPR = {dfpr:+.2f} pp, dDR = {ddr:+.2f} pp")

    primary = cfg["analysis"]["primary_run"]
    f = funnel[funnel.rep == primary].iloc[0]
    n = int(metrics[(metrics.condition == "CARE") & (metrics.rep == primary)].n.iloc[0])
    lo, hi = S.wilson(int(f.escalated), n)
    rp = cfg["reported"]["resolution_funnel"]["escalated"] / PAPER_N
    v["C8"] = ("supported" if lo <= rp <= hi else "not supported",
               f"observed {int(f.escalated)}/{n} = {100 * f.escalated / n:.2f}% [Wilson {100 * lo:.1f}, {100 * hi:.1f}] "
               f"vs reported {100 * rp:.2f}%")

    bad = funnel.judge_allow_dangerous
    v["C9"] = ("supported" if (bad == 0).all() else "not supported",
               f"DANGEROUS-labelled judge ALLOWs per run: {list(map(int, bad))} (label quality: see report)")

    f1s = {c: g(c, "F1") for c in set(metrics.condition)}
    best = max(f1s, key=f1s.get)
    v["C10"] = ("supported" if best.startswith("CARE") else "not supported",
                f"highest F1 (primary run): {best} {f1s[best]:.2f}; coverage: 6 of the paper's 12 rows")
    v["C11"] = ("inconclusive", latency_evidence(metrics, cfg))
    return v


# ------------------------------------------------------------------ the table
def claims_table(v1_3, v1_2, v1_1, v1_0):
    """One row per claim: the v1.3 verdict and rationale, then the superseded outcomes."""
    return pd.DataFrame([dict(claim_id=cid, claim=claim, paper_source=source,
                              outcome=v1_3[cid][0], rationale=v1_3[cid][1],
                              outcome_v1_2_rules=v1_2[cid][0], outcome_v1_1=v1_1[cid][0],
                              outcome_v1_0=v1_0[cid][0], evidence_v1_0=v1_0[cid][1])
                         for cid, (claim, source) in CLAIMS.items()])
