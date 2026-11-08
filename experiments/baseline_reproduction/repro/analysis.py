"""Analysis tables: pure functions of (observations, split, config).

    metrics_long          what each guard decided, per condition and run (per-command CIs, as in the paper)
    recipe_weights        design-based bootstrap weights: re-run the split recipe on the sample (v1.3, D19, D22)
    design_intervals      F1 / DR / FPR with design-based 95% CIs
    paired_differences    left - right in F1 and accuracy, with design-based (and Bonferroni) CIs
    escalation_rate       share of commands CARE sends to its judge, with a design-based CI
    design_inference      the three above under one estimator, bundled as a `Design`
    compare_with_paper    reported vs observed (Table II), descriptive
    mcnemar_table         the paper's per-command paired tests (Table VIII)
    resolution_funnel, oracle_bounds, by_source, redcode_scenarios, label_sensitivity   diagnostics

Every design-based function takes the bootstrap weight matrix explicitly, so the same code
serves the primary estimator (recipe) and the superseded one (cluster, v1.1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import stats as S

CONDITIONS = ["NoGuard", "PromptOnly", "LLMJudge", "NeMo self-check", "CARE (w/o Resolution)", "CARE"]
METRICS = [("f1", "F1"), ("dr", "DR"), ("fpr", "FPR")]
# RedCode-Exec bash scenarios characterised from their own task text (exploratory, post hoc, D9).
REDCODE_WEAKNESS = {12, 15, 16, 20, 22, 23, 25}
ESTIMATORS = {
    "recipe": "recipe bootstrap: re-runs the split recipe on the sample (fixed source quotas, families in corpus order "
              "until quota, NL2Bash head cap, random RedCode remainder, Real-world fixed) (v1.3, D19, D22)",
    "cluster": "cluster bootstrap: families resampled within source, RedCode items within scenario (v1.1, D15)",
}
DESIGN_PAIRS = [("CARE (w/o Resolution)", "PromptOnly"), ("CARE (w/o Resolution)", "LLMJudge"),
                ("CARE (w/o Resolution)", "NeMo self-check"), ("CARE", "LLMJudge"),
                ("CARE", "CARE (w/o Resolution)")]
NOT_COMPARABLE = ("not directly comparable: reconstructed population (D1-D5, D11, D12), hosted serving (D6), "
                  "NeMo emulation (D7); differences are descriptive")


# ------------------------------------------------------------------ selecting observations
def preds(obs, ids, condition, rep):
    """(DENY predictions aligned with `ids`, the matching observation rows) for one condition and run."""
    d = obs[(obs.condition == condition) & (obs.rep == rep)].set_index("command_id")
    return d.loc[ids, "prediction_dangerous"].to_numpy(bool), d.loc[ids]


def conditions_in(obs):
    return [c for c in CONDITIONS if c in set(obs.condition)]


def reps_of(obs, c):
    return sorted(int(r) for r in obs[obs.condition == c].rep.unique())


# ------------------------------------------------------------------ point metrics (long format)
def metrics_long(obs, split, cfg, experiment="main", split_name="reconstructed-main-seed42"):
    """Every condition x run x metric, with the per-command CIs the paper uses (bootstrap F1, Wilson DR/FPR)."""
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    a = cfg["analysis"]
    rows = []
    for c in conditions_in(obs):
        for rep in reps_of(obs, c):
            p, d = preds(obs, ids, c, rep)
            m = S.point_metrics(y, p)
            run_id = d.run_id.iloc[0]
            base = dict(experiment=experiment, condition=c, run_id=run_id, rep=rep, split=split_name,
                        n=len(y), aggregation="per-run")
            lo, hi = S.bootstrap_f1(y, p, a["bootstrap_resamples"], a["bootstrap_seed"], a["ci_level"])
            rows.append(dict(base, metric="F1", value=100 * m["f1"], unit="%", ci_lo=100 * lo, ci_hi=100 * hi,
                             ci_method="paired percentile bootstrap over commands"))
            for key, k, n in [("DR", m["tp"], m["tp"] + m["fn"]), ("FPR", m["fp"], m["fp"] + m["tn"])]:
                lo, hi = S.wilson(k, n)
                rows.append(dict(base, metric=key, value=100 * k / n, unit="%", ci_lo=100 * lo, ci_hi=100 * hi,
                                 ci_method="Wilson score"))
            for key in ("tp", "fp", "fn", "tn"):
                rows.append(dict(base, metric=key.upper(), value=m[key], unit="count"))
            lat = d.latency_ms.astype(float)
            for key, v in [("latency_mean", lat.mean()), ("latency_median", lat.median()),
                           ("latency_p95", lat.quantile(.95))]:
                rows.append(dict(base, metric=key, value=v, unit="ms"))
            k = int(d.llm_called.sum())
            lo, hi = S.wilson(k, len(d))
            rows.append(dict(base, metric="llm_call_rate", value=100 * k / len(d), unit="%",
                             ci_lo=100 * lo, ci_hi=100 * hi, ci_method="Wilson score"))
            rows.append(dict(base, metric="llm_errors", value=int(d.error.notna().sum()), unit="count"))
            if d.prompt_tokens.notna().any():
                rows.append(dict(base, metric="prompt_tokens", value=float(d.prompt_tokens.sum()), unit="tokens"))
                rows.append(dict(base, metric="completion_tokens", value=float(d.completion_tokens.sum()), unit="tokens"))
                rows.append(dict(base, metric="cost", value=float(d.cost_usd.fillna(0).sum()), unit="USD"))
        # aggregate over runs (secondary)
        if len(reps_of(obs, c)) > 1:
            per = pd.DataFrame([r for r in rows if r["condition"] == c and r["aggregation"] == "per-run"])
            allp = np.stack([preds(obs, ids, c, r)[0] for r in reps_of(obs, c)])
            for metric in ("F1", "DR", "FPR"):
                v = per[per.metric == metric].value
                rows.append(dict(experiment=experiment, condition=c, run_id="all", rep=0, split=split_name,
                                 n=len(y), aggregation="mean over runs", metric=metric, value=v.mean(),
                                 unit="%", ci_lo=v.min(), ci_hi=v.max(), ci_method="min-max over runs"))
            rows.append(dict(experiment=experiment, condition=c, run_id="all", rep=0, split=split_name, n=len(y),
                             aggregation="across runs", metric="decision_flip_rate",
                             value=100 * float((allp.min(0) != allp.max(0)).mean()), unit="%"))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ design-based bootstrap weights
def _design_families(split):
    """Resampling clusters: RedCode scenarios as-is, every other family qualified by its source."""
    return np.where(split.source.eq("RedCode-Exec"), split.family, split.source + ":" + split.family)


def recipe_weights(split, cfg, order, n_boot=None, seed=None):
    """(n_boot, n) weights that re-run the split recipe on the sample (primary, v1.3).

    `order` is each command's position in its corpus (`dataset.corpus_order`): families are
    truncated in that order, exactly as `dataset.family_draw` does.
    """
    a = cfg["analysis"]
    return S.recipe_bootstrap_weights(
        split.source.to_numpy(), _design_families(split), split["head"].to_numpy(), split.source.value_counts().to_dict(),
        a["bootstrap_resamples"] if n_boot is None else n_boot, a["bootstrap_seed"] if seed is None else seed,
        head_cap=cfg["dataset"]["nl2bash_head_cap"], order=order)


def cluster_weights(split, cfg, n_boot=None, seed=None):
    """(n_boot, n) weights of the superseded v1.1 cluster bootstrap (D15), kept for the record."""
    a = cfg["analysis"]
    return S.cluster_bootstrap_weights(split.source.to_numpy(), _design_families(split),
                                       a["bootstrap_resamples"] if n_boot is None else n_boot,
                                       a["bootstrap_seed"] if seed is None else seed)


# ------------------------------------------------------------------ design-based inference (primary run)
@dataclass
class Design:
    """Everything design-based on the primary run, under one bootstrap estimator."""
    intervals: pd.DataFrame     # F1 / DR / FPR per condition with 95% CIs
    differences: pd.DataFrame   # paired differences in F1 and accuracy
    escalation: dict            # CARE's escalation rate with its 95% CI


def design_inference(obs, split, w, estimator, cfg):
    return Design(intervals=design_intervals(obs, split, w, estimator, cfg),
                  differences=paired_differences(obs, split, w, estimator, cfg),
                  escalation=escalation_rate(obs, split, w, estimator, cfg))


def _resampled_rates(obs, split, w, rep):
    """Every non-NoGuard condition's F1/DR/FPR/accuracy in each bootstrap resample."""
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    return {c: S.weighted_rates(w, y, preds(obs, ids, c, rep)[0]) for c in conditions_in(obs) if c != "NoGuard"}


def design_intervals(obs, split, w, estimator, cfg, rep=1):
    """F1, DR and FPR per condition with design-based 95% percentile CIs."""
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    level = cfg["analysis"]["ci_level"]
    rows = []
    for c, boot in _resampled_rates(obs, split, w, rep).items():
        point = S.point_metrics(y, preds(obs, ids, c, rep)[0])
        for key, name in METRICS:
            lo, hi = S.percentile_ci(boot[key], level)
            rows.append(dict(estimator=estimator, condition=c, metric=name, value=100 * point[key],
                             ci_lo=100 * lo, ci_hi=100 * hi, boot_sd=100 * float(np.nanstd(boot[key])),
                             ci_method=ESTIMATORS[estimator]))
    return pd.DataFrame(rows)


def paired_differences(obs, split, w, estimator, cfg, rep=1):
    """Paired differences (left - right) in F1 and accuracy, in percentage points.

    Pairs: DESIGN_PAIRS, plus every non-CARE condition against every CARE variant. The latter
    also carry Bonferroni-adjusted CIs over the non-CARE comparators (C10, D23).
    """
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    level = cfg["analysis"]["ci_level"]
    boot = _resampled_rates(obs, split, w, rep)
    point_f1 = {c: 100 * S.point_metrics(y, preds(obs, ids, c, rep)[0])["f1"] for c in boot}
    others = [c for c in boot if not c.startswith("CARE")]
    versus_care = [(o, c) for c in boot if c.startswith("CARE") for o in others]
    adj_level = 1 - (1 - level) / max(len(others), 1)
    rows = []
    for left, right in dict.fromkeys(DESIGN_PAIRS + versus_care):
        if left not in boot or right not in boot:
            continue
        pl, pr = preds(obs, ids, left, rep)[0], preds(obs, ids, right, rep)[0]
        for key, name, point in [("f1", "F1", point_f1[left] - point_f1[right]),
                                 ("acc", "accuracy", 100 * ((pl == y).mean() - (pr == y).mean()))]:
            delta = 100 * (boot[left][key] - boot[right][key])
            lo, hi = S.percentile_ci(delta, level)
            alo, ahi = S.percentile_ci(delta, adj_level) if (left, right) in versus_care else (np.nan, np.nan)
            rows.append(dict(estimator=estimator, left=left, right=right, metric=f"delta_{name}", value=point,
                             ci_lo=lo, ci_hi=hi, excludes_zero=bool(lo > 0 or hi < 0),
                             adj_ci_lo=alo, adj_ci_hi=ahi, ci_method=ESTIMATORS[estimator]))
    return pd.DataFrame(rows)


def escalation_rate(obs, split, w, estimator, cfg, rep=1):
    """Share of commands CARE escalates to its judge (%), with a design-based 95% CI."""
    ids = split.command_id.to_numpy()
    esc = obs[(obs.condition == "CARE") & (obs.rep == rep)].set_index("command_id").loc[ids].llm_called.to_numpy(bool)
    lo, hi = S.percentile_ci((w @ esc) / w.sum(1), cfg["analysis"]["ci_level"])
    return dict(estimator=estimator, value=100 * esc.mean(), ci_lo=100 * lo, ci_hi=100 * hi)


# ------------------------------------------------------------------ reported vs observed
def compare_with_paper(metrics, intervals, cfg):
    """Reported vs observed, per condition and metric (primary run).

    `inside_ci` / `inside_design_ci` say whether the reported value lies inside our
    95% CI (v1.0 per-command CI / design-based CI).  This is descriptive: an
    interval that does not exclude a value is not evidence of equivalence, and the
    two populations differ, so every row is marked not directly comparable.
    """
    rep = cfg["reported"]["table_ii"]
    primary = cfg["analysis"]["primary_run"]
    rows = []
    for c, vals in rep["rows"].items():
        for key, name in METRICS + [("latency_ms", "latency_mean")]:
            sel = metrics[(metrics.condition == c) & (metrics.rep == primary) & (metrics.metric == name)]
            if sel.empty:
                continue
            o = sel.iloc[0]
            spread = metrics[(metrics.condition == c) & (metrics.aggregation == "mean over runs") & (metrics.metric == name)]
            r = vals[key]
            d = intervals[(intervals.condition == c) & (intervals.metric == name)]   # empty for NoGuard
            assert len(d) <= 1, "comparison expects one design estimator"
            if key == "latency_ms":
                lo = hi = dlo = dhi = np.nan
                inside = inside_d = None
                status = "not comparable (different hardware and LLM serving)"
            else:
                lo, hi = o.ci_lo, o.ci_hi
                dlo, dhi = (d.ci_lo.iloc[0], d.ci_hi.iloc[0]) if len(d) else (np.nan, np.nan)
                inside = bool(lo - 1e-9 <= r <= hi + 1e-9)
                inside_d = bool(dlo - 1e-9 <= r <= dhi + 1e-9) if len(d) else None
                status = "reported inside observed 95% CI" if inside else "reported outside observed 95% CI"
            rows.append(dict(source=rep["cite"], condition=c, metric=name, unit=o.unit, reported=r,
                             observed=o.value, ci_lo=lo, ci_hi=hi, ci_method=o.get("ci_method"),
                             design_ci_lo=dlo, design_ci_hi=dhi,
                             run_min=spread.ci_lo.iloc[0] if len(spread) else np.nan,
                             run_max=spread.ci_hi.iloc[0] if len(spread) else np.nan,
                             abs_diff=o.value - r, rel_diff=(o.value - r) / r if r else np.nan,
                             inside_ci=inside, inside_design_ci=inside_d, status=status,
                             comparability=NOT_COMPARABLE,
                             comparison_basis="same corpora and recipe, reconstructed population (not the authors' 549 items)"))
    return pd.DataFrame(rows)


def mcnemar_table(obs, split, cfg, rep=1):
    """Per-command McNemar tests, as in the paper's Table VIII (assumes independent commands)."""
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    paper = {(r["left"], r["right"]): r for r in cfg["reported"]["table_viii"]["rows"]}
    rows = []
    for a, b in DESIGN_PAIRS:
        if a in set(obs.condition) and b in set(obs.condition):
            lo, ro, py, pe = S.mcnemar(preds(obs, ids, a, rep)[0] == y, preds(obs, ids, b, rep)[0] == y)
            pp = paper.get((a, b), {})
            rows.append(dict(left=a, right=b, left_only=lo, right_only=ro, p_yates=py, p_exact=pe,
                             paper_left_only=pp.get("left_only"), paper_right_only=pp.get("right_only"),
                             paper_p=pp.get("p")))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ diagnostics
def resolution_funnel(obs, split):
    """Per run: static WARN -> skipped by a predicate -> escalated -> judge ALLOW (paper App. A.F)."""
    ids = split.command_id.to_numpy()
    lab = split.set_index("command_id").loc[ids].label_dangerous.to_numpy(bool)
    st = obs[obs.condition == "CARE (w/o Resolution)"].set_index("command_id").loc[ids]
    warn = st.provisional.eq("WARN").to_numpy()
    sk = st.skip_predicate.fillna("")
    rows = []
    for rep in reps_of(obs, "CARE"):
        c = obs[(obs.condition == "CARE") & (obs.rep == rep)].set_index("command_id").loc[ids]
        esc = c.llm_called.to_numpy(bool)
        flip = esc & c.decision.eq("ALLOW").to_numpy()
        rows.append(dict(run_id=c.run_id.iloc[0], rep=rep,
                         provisional_allow=int(st.provisional.eq("ALLOW").sum()),
                         provisional_deny=int(st.provisional.eq("DENY").sum()), warn=int(warn.sum()),
                         warn_safe=int((warn & ~lab).sum()), warn_dangerous=int((warn & lab).sum()),
                         skipped=int((warn & ~esc).sum()), p_rule=int(sk.str.startswith("p_rule").sum()),
                         p_spath=int(sk.eq("p_spath").sum()), p_sem=int(sk.str.startswith("p_sem").sum()),
                         escalated=int(esc.sum()), judge_allow=int(flip.sum()),
                         judge_allow_safe=int((flip & ~lab).sum()), judge_allow_dangerous=int((flip & lab).sum()),
                         judge_errors=int(c.error.notna().sum())))
    return pd.DataFrame(rows)


def oracle_bounds(obs, split):
    """Upper bounds on full-CARE F1 for ANY Resolution judge, given the released static stack.
    Derived from observations (no new runs): a perfect judge on (a) escalated commands,
    (b) all WARN commands (i.e. ignoring the skip predicates)."""
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    st = obs[obs.condition == "CARE (w/o Resolution)"].set_index("command_id").loc[ids]
    static = st.prediction_dangerous.to_numpy(bool)
    warn = st.provisional.eq("WARN").to_numpy()
    esc = warn & st.skip_predicate.isna().to_numpy()
    rows = []
    for name, region in [("static only (no judge)", np.zeros_like(warn)),
                         ("perfect judge on escalated commands", esc),
                         ("perfect judge on every WARN command", warn)]:
        m = S.point_metrics(y, np.where(region, y, static))
        rows.append(dict(bound=name, n_region=int(region.sum()), f1=100 * m["f1"], dr=100 * m["dr"], fpr=100 * m["fpr"]))
    return pd.DataFrame(rows)


def by_source(obs, split, rep=1):
    """DR (DANGEROUS sources) or FPR (SAFE sources) per condition and source, with Wilson CIs."""
    ids = split.command_id.to_numpy()
    rows = []
    for c in conditions_in(obs):
        p, _ = preds(obs, ids, c, rep)
        for src, g in split.assign(pred=p).groupby("source"):
            k, n = int(g.pred.sum()), len(g)
            lo, hi = S.wilson(k, n)
            rows.append(dict(condition=c, source=src, metric="DR" if g.label.iloc[0] == "DANGEROUS" else "FPR",
                             k=k, n=n, value=100 * k / n, ci_lo=100 * lo, ci_hi=100 * hi))
    return pd.DataFrame(rows)


def redcode_scenarios(obs, split, rep=1):
    """(detections per condition and RedCode scenario, the RedCode items with their scenario kind)."""
    ids = split.command_id.to_numpy()
    rc = split[split.source == "RedCode-Exec"].copy()
    rc["scenario"] = rc.meta.map(lambda s: json.loads(s)["scenario"])
    rc["kind"] = np.where(rc.scenario.isin(REDCODE_WEAKNESS), "software-weakness", "operational")
    rows = []
    for c in conditions_in(obs):
        pr = pd.Series(preds(obs, ids, c, rep)[0], index=ids)
        for (s, kind), g in rc.groupby(["scenario", "kind"]):
            rows.append(dict(condition=c, scenario=int(s), kind=kind, n=len(g), detected=int(pr.loc[g.command_id].sum())))
    return pd.DataFrame(rows), rc


def label_sensitivity(obs, split, audit, rep=1):
    """CARE and CARE (w/o Resolution) under the corpus-level labels and under the audited labels (D17).

    `audit` maps command_id -> audited label for the commands on which the two CARE
    conditions disagree in any run (the only items that can move C7/C9).  Prediction-
    dependent selection: a sensitivity analysis, never a replacement primary result.
    """
    ids = split.command_id.to_numpy()
    proxy = split.label_dangerous.to_numpy(bool)
    audited = np.array([audit.get(c, lab) for c, lab in zip(ids, split.label)]) == "DANGEROUS"
    rows = []
    for labels_name, y in [("corpus-level labels (paper Table I convention)", proxy),
                           ("audited labels for judge-changed commands (D17)", audited)]:
        for c in ("CARE (w/o Resolution)", "CARE"):
            m = S.point_metrics(y, preds(obs, ids, c, rep)[0])
            rows.append(dict(labels=labels_name, condition=c, f1=100 * m["f1"], dr=100 * m["dr"], fpr=100 * m["fpr"],
                             n_dangerous=int(y.sum())))
        judged = obs[(obs.condition == "CARE") & obs.llm_called & (obs.decision == "ALLOW")]
        lab = pd.Series(y, index=ids)
        per_run = [int(lab.loc[g.command_id].sum()) for _, g in judged.groupby("rep")]
        rows[-1].update(judge_allow_dangerous_per_run=str(per_run), judge_allow_dangerous_total=sum(per_run))
    return pd.DataFrame(rows)
