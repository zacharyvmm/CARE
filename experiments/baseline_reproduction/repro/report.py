"""Analysis tables, claim verdicts (PROTOCOL.md Sec. 6), figures and Markdown rendering.

Everything here is a pure function of the saved observations + split + config,
so tables and figures can be regenerated from results/observations.parquet.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from . import stats as S

CONDITIONS = ["NoGuard", "PromptOnly", "LLMJudge", "NeMo self-check", "CARE (w/o Resolution)", "CARE"]
METRICS = [("f1", "F1"), ("dr", "DR"), ("fpr", "FPR")]
# RedCode-Exec bash scenarios characterised from their own task text (exploratory, post hoc, D9).
REDCODE_WEAKNESS = {12, 15, 16, 20, 22, 23, 25}


# ------------------------------------------------------------------ helpers
def preds(obs, ids, condition, rep):
    d = obs[(obs.condition == condition) & (obs.rep == rep)].set_index("command_id")
    return d.loc[ids, "prediction_dangerous"].to_numpy(bool), d.loc[ids]


def conditions_in(obs):
    return [c for c in CONDITIONS if c in set(obs.condition)]


def reps_of(obs, c):
    return sorted(int(r) for r in obs[obs.condition == c].rep.unique())


# ------------------------------------------------------------------ main metrics (long format)
def metrics_long(obs, split, cfg, experiment="main", split_name="reconstructed-main-seed42"):
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


def comparison(metrics, cfg):
    rep = cfg["reported"]["table_ii"]
    primary = cfg["analysis"]["primary_run"]
    rows = []
    for c, vals in rep["rows"].items():
        for key, name in METRICS + [("latency_ms", "latency_mean")]:
            sel = metrics[(metrics.condition == c) & (metrics.rep == primary) & (metrics.metric == (name if key != "latency_ms" else "latency_mean"))]
            if sel.empty:
                continue
            o = sel.iloc[0]
            spread = metrics[(metrics.condition == c) & (metrics.aggregation == "mean over runs") & (metrics.metric == name)]
            r = vals[key]
            if key == "latency_ms":
                status = "not directly comparable (different hardware and LLM serving)"
                lo = hi = np.nan
            else:
                lo, hi = o.ci_lo, o.ci_hi
                status = "consistent" if lo - 1e-9 <= r <= hi + 1e-9 else "inconsistent"
            rows.append(dict(source=rep["cite"], condition=c, metric=name, unit=o.unit, reported=r,
                             observed=o.value, ci_lo=lo, ci_hi=hi, ci_method=o.get("ci_method"),
                             run_min=spread.ci_lo.iloc[0] if len(spread) else np.nan,
                             run_max=spread.ci_hi.iloc[0] if len(spread) else np.nan,
                             abs_diff=o.value - r, rel_diff=(o.value - r) / r if r else np.nan,
                             status=status,
                             comparison_basis="same corpora and recipe, reconstructed population (not the authors' 549 items)"))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ secondary tables
def by_source(obs, split, rep=1):
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


def mcnemar_table(obs, split, cfg, rep=1):
    ids, y = split.command_id.to_numpy(), split.label_dangerous.to_numpy(bool)
    paper = {(r["left"], r["right"]): r for r in cfg["reported"]["table_viii"]["rows"]}
    pairs = [("CARE (w/o Resolution)", "PromptOnly"), ("CARE (w/o Resolution)", "LLMJudge"),
             ("CARE (w/o Resolution)", "NeMo self-check"), ("CARE", "LLMJudge"), ("CARE", "CARE (w/o Resolution)")]
    rows = []
    for a, b in pairs:
        if a in set(obs.condition) and b in set(obs.condition):
            lo, ro, py, pe = S.mcnemar(preds(obs, ids, a, rep)[0] == y, preds(obs, ids, b, rep)[0] == y)
            pp = paper.get((a, b), {})
            rows.append(dict(left=a, right=b, left_only=lo, right_only=ro, p_yates=py, p_exact=pe,
                             paper_left_only=pp.get("left_only"), paper_right_only=pp.get("right_only"),
                             paper_p=pp.get("p")))
    return pd.DataFrame(rows)


def funnel(obs, split):
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
    esc = st.provisional.eq("WARN").to_numpy() & st.skip_predicate.isna().to_numpy()
    rows = []
    for name, region in [("static only (no judge)", np.zeros_like(warn)),
                         ("perfect judge on escalated commands", esc),
                         ("perfect judge on every WARN command", warn)]:
        p = np.where(region, y, static)
        m = S.point_metrics(y, p)
        rows.append(dict(bound=name, n_region=int(region.sum()), f1=100 * m["f1"], dr=100 * m["dr"], fpr=100 * m["fpr"]))
    return pd.DataFrame(rows)


def static_eval(split, care_cache):
    from care import CARE
    if "_guard" not in care_cache:
        care_cache["_guard"] = CARE(use_judge=False)
    p = []
    for c in split.command:
        if c not in care_cache:
            care_cache[c] = care_cache["_guard"].analyze(c)["decision"] == "DENY"
        p.append(care_cache[c])
    p = np.array(p, bool)
    m = S.point_metrics(split.label_dangerous.to_numpy(bool), p)
    return {k: 100 * m[k] for k in ("f1", "dr", "fpr")}


# ------------------------------------------------------------------ claims (PROTOCOL.md Sec. 6)
def claims(cmp, mc, fun, metrics, seeds, cfg):
    primary = cfg["analysis"]["primary_run"]
    out = []

    def row(cid, claim, cite, outcome, evidence):
        out.append(dict(claim_id=cid, claim=claim, paper_source=cite, outcome=outcome, evidence=evidence))

    for cid, cond in [("C1", "CARE (w/o Resolution)"), ("C2", "CARE"), ("C3", "PromptOnly"),
                      ("C4", "LLMJudge"), ("C5", "NeMo self-check")]:
        t = cmp[(cmp.condition == cond) & cmp.metric.isin(["F1", "DR", "FPR"])]
        if t.empty:
            row(cid, f"Table II row {cond}", "Table II", "inconclusive", "condition not executed")
            continue
        k = int((t.status == "consistent").sum())
        outcome = {3: "supported", 0: "not supported"}.get(k, "partially supported")
        ev = "; ".join(f"{r.metric} reported {r.reported:.2f} vs observed {r.observed:.2f} [{r.ci_lo:.1f}, {r.ci_hi:.1f}] -> {r.status}"
                       for r in t.itertuples())
        if cond == "CARE (w/o Resolution)" and seeds is not None:
            ev += (f"; F1 over {len(seeds)} alternative split seeds: max {seeds.f1.max():.2f}, "
                   f"95% range {seeds.f1.quantile(.025):.2f}-{seeds.f1.quantile(.975):.2f}")
        row(cid, f"Table II row '{cond}': F1/DR/FPR", "Table II", outcome, ev)

    sig = mc[(mc.left == "CARE (w/o Resolution)") & mc.right.isin(["PromptOnly", "LLMJudge"])]
    if len(sig) == 2:
        same = (sig.left_only > sig.right_only).all()
        outcome = ("supported" if same and (sig.p_yates < 0.05).all() else
                   "partially supported" if same else "not supported")
        row("C6", "CARE (w/o Resolution) significantly outperforms PromptOnly and LLMJudge (McNemar)",
            "Sec. V-A1, Table VIII", outcome,
            "; ".join(f"vs {r.right}: {r.left_only}/{r.right_only} discordant, p_Yates={r.p_yates:.3g} "
                      f"(paper {r.paper_left_only}/{r.paper_right_only}, p={r.paper_p:.2g})" for r in sig.itertuples()))

    g = lambda c, m: metrics[(metrics.condition == c) & (metrics.rep == primary) & (metrics.metric == m)].value.iloc[0]  # noqa: E731
    if "CARE" in set(metrics.condition):
        dfpr, ddr = g("CARE", "FPR") - g("CARE (w/o Resolution)", "FPR"), g("CARE", "DR") - g("CARE (w/o Resolution)", "DR")
        outcome = ("supported" if dfpr < 0 and abs(ddr) < 1e-9 else
                   "partially supported" if dfpr < 0 else "not supported")
        row("C7", "Resolution lowers FPR (1.82 -> 0.91) at unchanged DR", "Sec. V-A1", outcome,
            f"primary run: dFPR = {dfpr:+.2f} pp, dDR = {ddr:+.2f} pp")
        f = fun[fun.rep == primary].iloc[0]
        n = int(metrics[(metrics.condition == "CARE") & (metrics.rep == primary)].n.iloc[0])
        lo, hi = S.wilson(int(f.escalated), n)
        rp = cfg["reported"]["resolution_funnel"]["escalated"] / 549
        row("C8", "About 4.2% of commands (23/549) reach the LLM judge", "Abstract-level claim; App. A.F",
            "supported" if lo <= rp <= hi else "not supported",
            f"observed {int(f.escalated)}/{n} = {100 * f.escalated / n:.2f}% [Wilson {100 * lo:.1f}, {100 * hi:.1f}] vs reported {100 * rp:.2f}%")
        bad = fun.judge_allow_dangerous
        row("C9", "The judge never converts a DANGEROUS command to ALLOW", "App. A.F",
            "supported" if (bad == 0).all() else "not supported",
            f"DANGEROUS-labelled judge ALLOWs per run: {list(map(int, bad))} (label quality: see report)")
        f1s = {c: g(c, "F1") for c in set(metrics.condition)}
        best = max(f1s, key=f1s.get)
        row("C10", "CARE attains the highest F1 among the evaluated guards", "Table II",
            "supported" if best.startswith("CARE") else "not supported",
            f"highest F1 (primary run): {best} {f1s[best]:.2f}; coverage: 6 of the paper's 12 rows")
        lat = g("CARE (w/o Resolution)", "latency_mean")
        row("C11", "CARE (w/o Resolution) mean latency 0.34 ms; CARE 2.32 ms", "Table II", "inconclusive",
            f"observed static mean {lat:.2f} ms on a laptop CPU; full-CARE latency dominated by hosted-API round trips; "
            "hardware and serving differ, so not directly comparable")
    return pd.DataFrame(out)


# ------------------------------------------------------------------ figures
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OURS, PAPER = "#2a78d6", "#eb6834"  # validated categorical slots 1 and 2


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def figures(cmp, seeds, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    os.makedirs(outdir, exist_ok=True)
    t = cmp[cmp.metric.isin(["F1", "DR", "FPR"]) & (cmp.condition != "NoGuard")]
    conds = [c for c in CONDITIONS if c in set(t.condition)][::-1]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True, facecolor=SURFACE)
    for ax, (m, title) in zip(axes, [("F1", "F1 % ↑"), ("DR", "Detection rate % ↑"), ("FPR", "False-positive rate % ↓")]):
        _style(ax)
        d = t[t.metric == m].set_index("condition").loc[conds]
        yy = np.arange(len(conds))
        ax.hlines(yy, d.ci_lo, d.ci_hi, color=OURS, lw=2)
        ax.plot(d.observed, yy, "o", ms=8, color=OURS, mec=SURFACE, mew=2, label="Observed, run 1 (95% CI)")
        ax.plot(d.reported, yy, "D", ms=8, mfc="none", mec=PAPER, mew=2, label="Reported (Table II)")
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_yticks(yy, conds, color=INK)
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.08), ncol=2, frameon=False, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "reported_vs_observed.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)

    if seeds is not None:
        fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=SURFACE)
        _style(ax)
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.hist(seeds.f1, bins=20, color=OURS, edgecolor=SURFACE, linewidth=2)
        ax.axvline(84.99, color=PAPER, lw=2, ls="--")
        ax.text(84.99, ax.get_ylim()[1] * 0.95, "reported 84.99 ", color=INK, va="top", ha="right")
        s42 = seeds.loc[seeds.seed == 42, "f1"].iloc[0]
        ax.axvline(s42, color=INK2, lw=1)
        ax.text(s42, ax.get_ylim()[1] * 0.80, " seed 42 (primary)", color=INK2, va="top")
        ax.set_xlabel(f"CARE (w/o Resolution) F1 %, {len(seeds)} reconstructed splits", color=INK)
        ax.set_ylabel("splits", color=INK)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "split_seed_sensitivity.png"), dpi=160, facecolor=SURFACE)
        plt.close(fig)


# ------------------------------------------------------------------ markdown
def md_table(df, floatfmt=".2f"):
    def f(v):
        if isinstance(v, (float, np.floating)):
            return "—" if np.isnan(v) else format(v, floatfmt)
        return str(v).replace("|", "\\|")
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def results_markdown(cmp, metrics, claims_t, mc, fun, src, rc, oracle, seeds, variants, cfg, mode):
    p = cfg["analysis"]["primary_run"]
    L = []
    if mode != "full":
        L.append(f"> **{mode.upper()} MODE — NOT A REPRODUCTION.** Numbers below come from a reduced run.\n")
    L.append("### Claim verdicts (rules frozen in PROTOCOL.md §6)\n")
    L.append(md_table(claims_t[["claim_id", "claim", "paper_source", "outcome", "evidence"]]))
    L.append("\n### Reported vs observed (Table II; primary run = run %d)\n" % p)
    t = cmp[cmp.metric.isin(["F1", "DR", "FPR"])].copy()
    t["observed [95% CI]"] = t.apply(lambda r: f"{r.observed:.2f} [{r.ci_lo:.1f}, {r.ci_hi:.1f}]", axis=1)
    static = {"NoGuard", "CARE (w/o Resolution)"}
    t["range over runs"] = t.apply(lambda r: ("deterministic" if r.condition in static else "single run")
                                   if np.isnan(r.run_min) else f"{r.run_min:.2f}–{r.run_max:.2f}", axis=1)
    L.append(md_table(t[["condition", "metric", "reported", "observed [95% CI]", "abs_diff", "range over runs", "status"]]))
    flips = metrics[metrics.metric == "decision_flip_rate"][["condition", "value"]].rename(columns={"value": "decision flip rate across runs (%)"})
    if len(flips):
        L.append("\n" + md_table(flips))
    lat = cmp[cmp.metric == "latency_mean"][["condition", "reported", "observed"]].rename(
        columns={"reported": "reported mean ms", "observed": "observed mean ms"})
    L.append("\nLatency (not directly comparable: laptop CPU and a hosted API vs. 4×H100 + local vLLM):\n")
    L.append(md_table(lat))
    cost = metrics[metrics.metric.isin(["prompt_tokens", "completion_tokens", "cost"])]
    if len(cost):
        c = cost.groupby("metric").value.sum()
        L.append(f"\nLLM usage over all runs: {int(c.get('prompt_tokens', 0)):,} prompt + "
                 f"{int(c.get('completion_tokens', 0)):,} completion tokens, cost ${c.get('cost', 0):.4f} (OpenRouter-reported).\n")
    L.append("\n### Paired McNemar tests (primary run; two-sided, Yates as in Table VIII)\n")
    L.append(md_table(mc, ".3g"))
    L.append("\n### Resolution funnel (paper App. A.F: 117 WARN → 94 skipped → 23 judged → 3 ALLOW, 0 DANGEROUS)\n")
    L.append(md_table(fun.drop(columns=["run_id"])))
    L.append("\n### Upper bounds for any Resolution judge on the released static stack (derived)\n")
    L.append(md_table(oracle))
    L.append("\n### Per-source rates (primary run; Wilson 95% CI)\n")
    s = src.assign(cell=src.apply(lambda r: f"{r.value:.1f} [{r.ci_lo:.0f}–{r.ci_hi:.0f}]", axis=1),
                   col=src.apply(lambda r: f"{r.source} {r.metric} (n={r.n})", axis=1))
    L.append(md_table(s.pivot(index="condition", columns="col", values="cell").loc[[c for c in CONDITIONS if c in set(s.condition)]].reset_index()))
    L.append("\n### RedCode-Exec detections by scenario (primary run; scenario kind is post hoc, D9)\n")
    L.append(md_table(rc.pivot_table(index=["scenario", "kind", "n"], columns="condition", values="detected").reset_index(), ".0f"))
    if seeds is not None:
        L.append(f"\n### Split-construction sensitivity (CARE w/o Resolution, {len(seeds)} seeds, deterministic)\n")
        q = seeds.f1.quantile([.025, .5, .975])
        L.append(f"F1 median {q[.5]:.2f}, 95% range {q[.025]:.2f}–{q[.975]:.2f}, max {seeds.f1.max():.2f} (reported 84.99).\n")
    if variants is not None:
        L.append("\n### Construction variants (CARE w/o Resolution; V2 is exploratory and post hoc)\n")
        L.append(md_table(variants))
    return "\n".join(L) + "\n"
