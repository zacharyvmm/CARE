"""Static figures for the reproduction report (PNG, light surface)."""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OURS, PAPER = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 (validated reference palette)


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def metric_dots(main_t, out):
    """F1 / DR / FPR per method: ours (dot + 95% CI) vs paper (hollow diamond)."""
    t = main_t[main_t.method != "NoGuard"].iloc[::-1]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True, facecolor=SURFACE)
    for ax, (key, title) in zip(axes, [("f1", "F1 % ↑"), ("dr", "Detection rate % ↑"),
                                       ("fpr", "False-positive rate % ↓")]):
        _style(ax)
        yy = range(len(t))
        lo, hi, v = 100 * t[f"{key}_lo"], 100 * t[f"{key}_hi"], 100 * t[key]
        ax.hlines(yy, lo, hi, color=OURS, lw=2)
        ax.plot(v, yy, "o", ms=8, color=OURS, mec=SURFACE, mew=2, label="This reproduction (95% CI)")
        ax.plot(t[f"paper_{key}"], yy, "D", ms=8, mfc="none", mec=PAPER, mew=2, label="Paper (Table II)")
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_yticks(list(yy), t.method, color=INK)
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.08), ncol=2, frameon=False, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def seed_hist(seeds_t, out, paper_f1=84.99):
    fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.hist(100 * seeds_t.f1, bins=20, color=OURS, edgecolor=SURFACE, linewidth=2)
    ax.axvline(paper_f1, color=PAPER, lw=2, ls="--")
    ax.text(paper_f1, ax.get_ylim()[1] * 0.95, " paper 84.99", color=INK, va="top", ha="right")
    s42 = 100 * seeds_t.loc[seeds_t.seed == 42, "f1"].iloc[0]
    ax.axvline(s42, color=INK2, lw=1)
    ax.text(s42, ax.get_ylim()[1] * 0.80, " seed 42", color=INK2, va="top")
    ax.set_xlabel("CARE (w/o Resolution) F1 %, 100 reconstructed splits", color=INK)
    ax.set_ylabel("splits", color=INK)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def make_all(main_t, seeds_t, by_src, outdir):
    os.makedirs(outdir, exist_ok=True)
    metric_dots(main_t, os.path.join(outdir, "metrics_vs_paper.png"))
    seed_hist(seeds_t, os.path.join(outdir, "seed_sensitivity.png"))
