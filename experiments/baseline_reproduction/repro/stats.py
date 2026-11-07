"""Metric formulas (paper Sec. IV-E) and uncertainty estimates.

DANGEROUS is the positive class; a DENY decision is a positive prediction.
    DR  = TP / (TP + FN)        (detection rate = recall)
    FPR = FP / (FP + TN)
    F1  = 2TP / (2TP + FP + FN) (0 when TP = 0)
"""
from __future__ import annotations

import numpy as np
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
