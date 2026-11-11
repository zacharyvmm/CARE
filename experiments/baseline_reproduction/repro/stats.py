"""The formulas (paper Sec. IV-E), on one set of commands or on many splits at once.

DANGEROUS is the positive class; a DENY decision is a positive prediction.

    DR  = TP / (TP + FN)          detection rate (recall)
    FPR = FP / (FP + TN)          false-positive rate
    F1  = 2TP / (2TP + FP + FN)   0 when TP = 0
"""
from __future__ import annotations

import numpy as np
import scipy.stats


# ---------------------------------------------------------------- one set of commands
def confusion_counts(dangerous, denied):
    """(TP, FP, FN, TN) for boolean arrays `dangerous` (the label) and `denied` (the decision)."""
    dangerous, denied = np.asarray(dangerous, bool), np.asarray(denied, bool)
    return (int((dangerous & denied).sum()), int((~dangerous & denied).sum()),
            int((dangerous & ~denied).sum()), int((~dangerous & ~denied).sum()))


def point_metrics(dangerous, denied):
    """Counts, DR, FPR and F1 (fractions) on one set of commands."""
    tp, fp, fn, tn = confusion_counts(dangerous, denied)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn,
                dr=tp / (tp + fn) if tp + fn else np.nan,
                fpr=fp / (fp + tn) if fp + tn else np.nan,
                f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)


def mcnemar_p_yates(left_only, right_only):
    """Two-sided McNemar p-value with Yates' correction; accepts arrays (1 where nothing is discordant)."""
    left_only, right_only = np.asarray(left_only, float), np.asarray(right_only, float)
    discordant = left_only + right_only
    with np.errstate(invalid="ignore", divide="ignore"):
        chi_squared = np.where(discordant > 0, (np.abs(left_only - right_only) - 1) ** 2 / discordant, 0.0)
    return np.where(discordant > 0, scipy.stats.chi2.sf(chi_squared, 1), 1.0)


# ---------------------------------------------------------------- many splits at once
def split_counts(dangerous, denied, rows):
    """Confusion counts in every split.

    `rows` is a (number of splits, split size) matrix of positions into `dangerous` and `denied`.
    Returns a (number of splits, 4) integer array with columns TP, FP, FN, TN.
    """
    dangerous, denied = np.asarray(dangerous, bool)[rows], np.asarray(denied, bool)[rows]
    return np.stack([(dangerous & denied).sum(1), (~dangerous & denied).sum(1),
                     (dangerous & ~denied).sum(1), (~dangerous & ~denied).sum(1)], axis=1)


def rates(counts):
    """F1, DR, FPR and accuracy (fractions) for every row of a (n, 4) TP/FP/FN/TN array."""
    tp, fp, fn, tn = (np.asarray(counts, float)[:, column] for column in range(4))
    with np.errstate(invalid="ignore", divide="ignore"):
        return dict(f1=np.where(tp > 0, 2 * tp / (2 * tp + fp + fn), 0.0),
                    dr=np.where(tp + fn > 0, tp / (tp + fn), np.nan),
                    fpr=np.where(fp + tn > 0, fp / (fp + tn), np.nan),
                    acc=(tp + tn) / (tp + fp + fn + tn))


# ---------------------------------------------------------------- distances in sigma
def sigma_threshold(level=0.95, comparisons=1):
    """How many standard deviations count as "apart".

    The z that spans the central `level` share of a normal distribution: 1.96 for 95%.  With
    several comparisons at once the level is split between them (Bonferroni): 2.39 for three.
    """
    return float(scipy.stats.norm.ppf(1 - (1 - level) / (2 * comparisons)))


def sigmas_between(value, mean, sigma):
    """(value - mean) in units of `sigma`; 0 when they coincide, infinite when they differ and sigma is 0."""
    if np.isclose(value, mean):
        return 0.0
    return float((value - mean) / sigma) if sigma > 0 else float(np.sign(value - mean) * np.inf)


def in_sigmas(distance):
    """A distance formatted in standard deviations, e.g. "+5.8σ" (never "-0.0σ")."""
    return f"{round(distance, 1) + 0.0:+.1f}σ"
