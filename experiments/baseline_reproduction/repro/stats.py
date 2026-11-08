"""Metric formulas (paper Sec. IV-E) and uncertainty estimates.

DANGEROUS is the positive class; a DENY decision is a positive prediction.
    DR  = TP / (TP + FN)        (detection rate = recall)
    FPR = FP / (FP + TN)
    F1  = 2TP / (2TP + FP + FN) (0 when TP = 0)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

Z95 = 1.959963984540054


def confusion(y, yhat):
    y, yhat = np.asarray(y, bool), np.asarray(yhat, bool)
    return (int((y & yhat).sum()), int((~y & yhat).sum()),
            int((y & ~yhat).sum()), int((~y & ~yhat).sum()))


def f1_score(tp, fp, fn):
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def point_metrics(y, yhat):
    tp, fp, fn, tn = confusion(y, yhat)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn,
                dr=tp / (tp + fn) if tp + fn else np.nan,
                fpr=fp / (fp + tn) if fp + tn else np.nan,
                f1=f1_score(tp, fp, fn))


def wilson(k, n, z=Z95):
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def bootstrap_f1(y, yhat, n_boot=10_000, seed=0, level=0.95):
    """Percentile bootstrap CI for F1, resampling commands (the unit of analysis)."""
    y, yhat = np.asarray(y, bool), np.asarray(yhat, bool)
    idx = np.random.default_rng(seed).integers(0, len(y), size=(n_boot, len(y)))
    yy, pp = y[idx], yhat[idx]
    tp = (yy & pp).sum(1); fp = (~yy & pp).sum(1); fn = (yy & ~pp).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(tp > 0, 2 * tp / (2 * tp + fp + fn), 0.0)
    a = (1 - level) / 2
    return tuple(np.quantile(f1, [a, 1 - a]))


def mcnemar(correct_a, correct_b):
    """Paired McNemar test on per-command correctness.
    Returns (a_only, b_only, p_yates, p_exact); Yates as in paper Table VIII."""
    a, b = np.asarray(correct_a, bool), np.asarray(correct_b, bool)
    a_only, b_only = int((a & ~b).sum()), int((~a & b).sum())
    n = a_only + b_only
    if n == 0:
        return a_only, b_only, 1.0, 1.0
    chi2 = (abs(a_only - b_only) - 1) ** 2 / n  # standard Yates form (as statsmodels)
    return a_only, b_only, float(stats.chi2.sf(chi2, 1)), float(stats.binomtest(a_only, n, 0.5).pvalue)


# ---------------------------------------------------------------- design-based (cluster) bootstrap
def cluster_bootstrap_weights(source, family, n_boot=10_000, seed=0, stratified_sources=("RedCode-Exec",)):
    """Resampling weights that mirror how the split was drawn (protocol v1.1, D15).

    Sources sampled by whole template families (ART, NL2Bash, Real-world) resample
    *families* with replacement within the source, keeping the number of families.
    Sources drawn by stratified round-robin (RedCode-Exec, strata = scenarios)
    resample *items* with replacement within each stratum.  Returns an
    (n_boot, n) integer matrix: how many times each command enters each resample.
    """
    source, family = np.asarray(source), np.asarray(family)
    rng = np.random.default_rng(seed)
    w = np.zeros((n_boot, len(source)), dtype=np.int32)
    for s in sorted(set(source)):
        in_s = np.flatnonzero(source == s)
        if s in stratified_sources:
            for f in sorted(set(family[in_s])):
                items = in_s[family[in_s] == f]
                draws = rng.integers(0, len(items), size=(n_boot, len(items)))
                np.add.at(w, (np.arange(n_boot)[:, None], items[draws]), 1)
        else:
            fams = sorted(set(family[in_s]))
            members = [in_s[family[in_s] == f] for f in fams]
            draws = rng.integers(0, len(fams), size=(n_boot, len(fams)))
            counts = np.zeros((n_boot, len(fams)), dtype=np.int32)
            np.add.at(counts, (np.arange(n_boot)[:, None], draws), 1)
            for j, m in enumerate(members):
                w[:, m] += counts[:, [j]]
    return w


def weighted_rates(w, y, yhat):
    """F1, DR, FPR (fractions) for every resample row of weight matrix `w`."""
    y, yhat = np.asarray(y, bool), np.asarray(yhat, bool)
    tp, fp = w @ (y & yhat), w @ (~y & yhat)
    fn, tn = w @ (y & ~yhat), w @ (~y & ~yhat)
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(tp > 0, 2 * tp / (2 * tp + fp + fn), 0.0)
        dr = np.where(tp + fn > 0, tp / (tp + fn), np.nan)
        fpr = np.where(fp + tn > 0, fp / (fp + tn), np.nan)
    return dict(f1=f1, dr=dr, fpr=fpr, acc=(tp + tn) / w.sum(1))


def percentile_ci(x, level=0.95):
    a = (1 - level) / 2
    return tuple(np.nanquantile(np.asarray(x, float), [a, 1 - a]))


def recipe_bootstrap_weights(source, family, head, quotas, n_boot=10_000, seed=0, head_cap=12, order=None,
                             family_sources=("ART", "NL2Bash"), stratified_sources=("RedCode-Exec",),
                             capped_sources=("NL2Bash",)):
    """Resampling weights that re-run the split recipe on the observed sample (protocol v1.2-v1.3, D19, D22).

    Mirrors `dataset.build_split` source by source:
      * family sources (ART, NL2Bash), as `family_draw`: whole families are drawn with replacement
        in random order and their members appended *in corpus order* (`order`) until the source
        quota is reached -- the last family is truncated; NL2Bash skips members whose head already
        has `head_cap` commands;
      * stratified sources (RedCode-Exec), as `stratified_draw`: a random scenario order decides
        which scenarios receive the remainder (quota mod #scenarios) of the round-robin; items are
        drawn with replacement within each scenario;
      * every other source (Real-world) is a fixed, deterministic subset: weight 1.
    Source totals, and so class prevalence, are fixed as in the recipe.  Drawing families and
    items with replacement from the sample is an approximation (no finite-population
    correction); its coverage is checked by simulation (`report.bootstrap_coverage`).
    """
    source, family, head = np.asarray(source), np.asarray(family), np.asarray(head)
    order = np.arange(len(source)) if order is None else np.asarray(order)
    rng = np.random.default_rng(seed)
    w = np.zeros((n_boot, len(source)), dtype=np.int32)
    w[:, ~np.isin(source, list(family_sources) + list(stratified_sources))] = 1
    for s in stratified_sources:
        in_s = np.flatnonzero(source == s)
        if not len(in_s):
            continue
        strata = [in_s[family[in_s] == f] for f in sorted(set(family[in_s]))]
        base, rem = divmod(quotas.get(s, len(in_s)), len(strata))
        for b in range(n_boot):
            extra = set(rng.permutation(len(strata))[:rem])
            for k, items in enumerate(strata):
                np.add.at(w[b], items[rng.integers(0, len(items), base + (k in extra))], 1)
    for s in family_sources:
        in_s = np.flatnonzero(source == s)
        if not len(in_s):
            continue
        fams = sorted(set(family[in_s]))
        members = [in_s[family[in_s] == f] for f in fams]
        members = [m[np.argsort(order[m], kind="stable")] for m in members]
        quota, cap = quotas[s], (head_cap if s in capped_sources else None)
        _, head_code = np.unique(head, return_inverse=True)
        for b in range(n_boot):
            n_draw = quota
            while True:
                seq = np.concatenate([members[j] for j in rng.integers(len(fams), size=n_draw)])
                if cap is not None:
                    seq = seq[pd.Series(head_code[seq]).groupby(head_code[seq]).cumcount().to_numpy() < cap]
                if len(seq) >= quota:
                    break
                n_draw *= 2  # rare: not enough commands before the head cap; draw a longer family sequence
            np.add.at(w[b], seq[:quota], 1)
    return w
