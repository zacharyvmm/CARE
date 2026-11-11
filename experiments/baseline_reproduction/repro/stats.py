"""Metric formulas (paper Sec. IV-E), on one set of commands or on many splits at once.

DANGEROUS is the positive class; a DENY decision is a positive prediction.
    DR  = TP / (TP + FN)        (detection rate = recall)
    FPR = FP / (FP + TN)
    F1  = 2TP / (2TP + FP + FN) (0 when TP = 0)
"""
from __future__ import annotations

import numpy as np
from scipy import stats


# ---------------------------------------------------------------- one set of commands
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


def mcnemar(correct_a, correct_b):
    """Paired McNemar test on per-command correctness.
    Returns (a_only, b_only, p_yates, p_exact); Yates as in paper Table VIII."""
    a, b = np.asarray(correct_a, bool), np.asarray(correct_b, bool)
    a_only, b_only = int((a & ~b).sum()), int((~a & b).sum())
    n = a_only + b_only
    if n == 0:
        return a_only, b_only, 1.0, 1.0
    return a_only, b_only, float(mcnemar_p_yates(a_only, b_only)), float(stats.binomtest(a_only, n, 0.5).pvalue)


def mcnemar_p_yates(a_only, b_only):
    """Two-sided McNemar p-value with Yates' correction; accepts arrays (1 where nothing is discordant)."""
    a_only, b_only = np.asarray(a_only, float), np.asarray(b_only, float)
    n = a_only + b_only
    with np.errstate(invalid="ignore", divide="ignore"):
        chi2 = np.where(n > 0, (np.abs(a_only - b_only) - 1) ** 2 / n, 0.0)
    return np.where(n > 0, stats.chi2.sf(chi2, 1), 1.0)


# ---------------------------------------------------------------- many splits at once
def split_counts(y, yhat, splits):
    """Confusion counts in every split.

    `splits` is an (n_splits, split_size) matrix of positions into `y` / `yhat`.
    Returns an (n_splits, 4) integer array with columns TP, FP, FN, TN.
    """
    y, yhat = np.asarray(y, bool)[splits], np.asarray(yhat, bool)[splits]
    return np.stack([(y & yhat).sum(1), (~y & yhat).sum(1), (y & ~yhat).sum(1), (~y & ~yhat).sum(1)], axis=1)


def rates(counts):
    """F1, DR, FPR and accuracy (fractions) for every row of an (n, 4) TP/FP/FN/TN array."""
    tp, fp, fn, tn = (np.asarray(counts, float)[:, i] for i in range(4))
    with np.errstate(invalid="ignore", divide="ignore"):
        return dict(f1=np.where(tp > 0, 2 * tp / (2 * tp + fp + fn), 0.0),
                    dr=np.where(tp + fn > 0, tp / (tp + fn), np.nan),
                    fpr=np.where(fp + tn > 0, fp / (fp + tn), np.nan),
                    acc=(tp + tn) / (tp + fp + fn + tn))


def central_range(x, level=0.95):
    """The interval that holds the central `level` share of the values in `x`."""
    a = (1 - level) / 2
    lo, hi = np.nanquantile(np.asarray(x, float), [a, 1 - a])
    return float(lo), float(hi)
