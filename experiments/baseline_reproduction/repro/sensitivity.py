"""How much does split construction matter?  Static CARE on re-drawn splits (no LLM calls).

    seed_sweep             static CARE F1/DR/FPR on splits drawn with seeds 0-99 (§8.4)
    construction_variants  one recipe decision changed at a time: V1, V2, V2b, V3 (§8.4)
    bootstrap_coverage     do the 95% bootstrap intervals cover the recipe's expected value? (§8.5, D22)
    bootstrap_calibration  bootstrap spread vs the spread over re-drawn splits (§8.5, D19)

Only deterministic guards can be re-run on hundreds of splits for free: static CARE, and a
deliberately simple synthetic keyword guard that exists only to give the coverage study a
paired contrast.  Neither is compared with the LLM conditions here.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import analysis as A
from . import dataset as D
from . import stats as S


class StaticCARE:
    """CARE (w/o Resolution) DENY decisions, memoised per command string.

    CARE's static stack is deterministic, and the studies below see the same commands in
    many re-drawn splits, so each command is analysed once.
    """

    def __init__(self):
        from care import CARE
        self.guard, self.memo = CARE(use_judge=False), {}

    def predict(self, split):
        for c in split.command:
            if c not in self.memo:
                self.memo[c] = self.guard.analyze(c)["decision"] == "DENY"
        return np.array([self.memo[c] for c in split.command], bool)

    def evaluate(self, split):
        m = S.point_metrics(split.label_dangerous.to_numpy(bool), self.predict(split))
        return {k: 100 * m[k] for k in ("f1", "dr", "fpr")}


# A deliberately simple, synthetic second guard: used ONLY to give the coverage study a paired contrast
# between two deterministic guards (no LLM needed).  It is not a baseline and is never compared with the paper.
SYNTHETIC_KEYWORD_GUARD = re.compile(r"\b(rm|curl|wget|nc|ncat|chmod|chown|sudo|base64|crontab|ssh|scp|useradd|"
                                     r"iptables|systemctl|kill|dd|mkfifo|python3?|perl)\b")


def keyword_guard_predictions(split):
    return split.command.map(lambda c: bool(SYNTHETIC_KEYWORD_GUARD.search(c))).to_numpy(bool)


def draw(pools, seed, cfg):
    """The split this recipe draws from `pools` with `seed`."""
    ds = cfg["dataset"]
    return D.build_split(pools, seed, ds["targets"], ds["nl2bash_head_cap"])[0]


# ------------------------------------------------------------------ split construction
def seed_sweep(pools, cfg, care):
    first, last = cfg["analysis"]["sensitivity_seeds"]
    return pd.DataFrame([dict(seed=s, **care.evaluate(draw(pools, s, cfg))) for s in range(first, last + 1)])


def construction_variants(split, redcode_items, pools, pools_unfiltered, pools_v3, cfg, care):
    """V0 = the primary split; each other variant changes one recipe decision."""
    seed = cfg["dataset"]["seed"]
    v1 = draw(pools_unfiltered, seed, cfg)
    v3 = draw(pools_v3, seed, cfg)
    weak = split.command_id.isin(redcode_items[redcode_items.kind == "software-weakness"].command_id)
    no_redcode = split.source != "RedCode-Exec"
    art_pools = f"pool {len(pools_v3['art'])} vs {len(pools['art'])}"
    return pd.DataFrame([
        dict(variant="V0 primary", note="seed 42, as protocol", n=len(split), **care.evaluate(split)),
        dict(variant="V1", note="NL2Bash label filter off (D5)", n=len(v1), **care.evaluate(v1)),
        dict(variant="V2 (exploratory, post hoc)", note="RedCode software-weakness scenarios removed (D9)",
             n=int((~weak).sum()), **care.evaluate(split[~weak])),
        dict(variant="V2b", note="RedCode removed", n=int(no_redcode.sum()), **care.evaluate(split[no_redcode])),
        dict(variant="V3", note=f"ART snapshot 2026-03-24 ({art_pools})", n=len(v3), **care.evaluate(v3)),
    ])


# ------------------------------------------------------------------ is the bootstrap valid?
def _coverage_quantities(w, y, care, kw):
    a, b = S.weighted_rates(w, y, care), S.weighted_rates(w, y, kw)
    return {"static CARE F1": a["f1"], "static CARE DR": a["dr"], "static CARE FPR": a["fpr"],
            "keyword guard F1": b["f1"], "delta F1 (static CARE - keyword)": a["f1"] - b["f1"],
            "delta accuracy (static CARE - keyword)": a["acc"] - b["acc"]}


def bootstrap_coverage(pools, cfg, care):
    """Coverage of the 95% bootstrap intervals, by simulation over the recipe itself (D22).

    Target: the expected value of each quantity over splits drawn by the recipe, estimated
    as the mean over `truth_seeds` (independent of the evaluated seeds).  For each split
    drawn with `eval_seeds`, compute the bootstrap interval from that split alone and check
    whether it covers the target.  Both estimators (recipe = primary, cluster = v1.1).
    """
    c = cfg["analysis"]["coverage"]
    level = cfg["analysis"]["ci_level"]

    def point(split):
        y = split.label_dangerous.to_numpy(bool)
        one = np.ones((1, len(split)), dtype=np.int32)
        q = _coverage_quantities(one, y, care.predict(split), keyword_guard_predictions(split))
        return {k: 100 * float(v[0]) for k, v in q.items()}

    truth = pd.DataFrame([point(draw(pools, s, cfg)) for s in range(c["truth_seeds"][0], c["truth_seeds"][1] + 1)]).mean()
    rows = []
    for seed in range(c["eval_seeds"][0], c["eval_seeds"][1] + 1):
        split = draw(pools, seed, cfg)
        y = split.label_dangerous.to_numpy(bool)
        guards = care.predict(split), keyword_guard_predictions(split)
        weights = {"recipe": A.recipe_weights(split, cfg, D.corpus_order(split, pools), n_boot=c["resamples"], seed=seed),
                   "cluster": A.cluster_weights(split, cfg, n_boot=c["resamples"], seed=seed)}
        for estimator, w in weights.items():
            for k, v in _coverage_quantities(w, y, *guards).items():
                lo, hi = S.percentile_ci(100 * v, level)
                rows.append(dict(estimator=estimator, quantity=k, seed=seed, covered=lo <= truth[k] <= hi, width=hi - lo))
    r = pd.DataFrame(rows)
    out = r.groupby(["estimator", "quantity"], sort=False).agg(coverage=("covered", "mean"), mean_width=("width", "mean"),
                                                               n_splits=("seed", "size")).reset_index()
    out["coverage"] *= 100
    out["mc_se"] = np.sqrt(out.coverage * (100 - out.coverage) / out.n_splits)
    out["target"] = out.quantity.map(truth)
    return out[["estimator", "quantity", "target", "coverage", "mc_se", "mean_width", "n_splits"]]


def bootstrap_calibration(intervals, seeds, condition="CARE (w/o Resolution)"):
    """Spread of each bootstrap vs the spread of static CARE's F1 over the re-drawn splits (D19).

    The re-drawn splits are a Monte Carlo estimate of the recipe's sampling distribution.  This
    compares spreads only; interval *coverage* is checked by `bootstrap_coverage` (D22).
    `intervals` holds one row per estimator (see `analysis.design_intervals`).
    """
    rows = [dict(source="100 re-drawn splits (Monte Carlo estimate of the recipe's sampling distribution)",
                 sd=float(seeds.f1.std()),
                 q025=float(seeds.f1.quantile(.025)), q975=float(seeds.f1.quantile(.975)))]
    for r in intervals[(intervals.condition == condition) & (intervals.metric == "F1")].itertuples():
        rows.append(dict(source=f"{r.estimator} bootstrap on the seed-42 split", sd=r.boot_sd, q025=r.ci_lo, q975=r.ci_hi))
    t = pd.DataFrame(rows)
    return t.assign(width=t.q975 - t.q025)
