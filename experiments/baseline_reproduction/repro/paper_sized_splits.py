"""The paper's 549-command split, re-drawn many times from the population (paper Table I, Sec. IV-B).

Every number in the paper is a statistic of one split of this composition.  Re-drawing it
shows what that statistic is on our population on average, and how much it varies.

    splits = paper_sized_splits.draw(population, configuration)     # one split per seed
    splits.rows                                                     # (number of splits, 549) row positions
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .corpora import SOURCES

PAPER_SIZED_SPLITS = "paper-sized splits"


@dataclass
class Splits:
    """Splits with the paper's composition: one per seed."""
    seeds: range
    by_source: dict      # source -> (number of splits, quota) row positions into the population

    @property
    def rows(self):
        """(number of splits, split size) row positions into the population."""
        return np.hstack([self.by_source[source] for source in SOURCES if source in self.by_source])

    def __len__(self):
        return len(self.seeds)


def draw(population, configuration):
    """Re-draw the paper's composition from the population, once per seed."""
    recipe = configuration["paper_sized_splits"]
    if not configuration.full:
        recipe = {**recipe, **configuration["smoke"]}   # a few small splits
    first_seed, last_seed = recipe["seeds"]
    seeds = range(first_seed, last_seed + 1)
    by_source = SplitRecipe(population, recipe["composition"], recipe["nl2bash_head_cap"]).draw(seeds)
    splits = Splits(seeds, by_source)
    dangerous = population.label_dangerous.to_numpy()[splits.rows[0]]
    print(f"✓ {len(splits):,} splits of {splits.rows.shape[1]} commands "
          f"({int(dangerous.sum())} DANGEROUS / {int((~dangerous).sum())} SAFE each)")
    return splits


class SplitRecipe:
    """Draws splits with the paper's Table I composition from the population.

        ART           whole technique families, in random order, until the quota is reached
        RedCode-Exec  round-robin over the risk scenarios, random commands within each
        NL2Bash       whole template families until the quota, at most `head_cap` commands per head
        Real-world    the first `quota` commands (a fixed set)

    Each source has its own random stream, seeded by (seed, source).  Only `eligible` rows can be
    drawn (default: the primary population).  `draw(seeds)` returns one split per seed, as row
    positions into the population.
    """

    def __init__(self, population, composition, head_cap, eligible=None):
        eligible = population.in_primary.to_numpy() if eligible is None else np.asarray(eligible, bool)
        source_of, family_of = population.source.to_numpy(), population.family.to_numpy()
        self.composition, self.head_cap = composition, head_cap
        self.head = population["head"].to_numpy()
        self.families = {name: {} for name in SOURCES}   # source -> {family: [rows, in corpus order]}
        for row in np.flatnonzero(eligible).tolist():
            self.families[source_of[row]].setdefault(family_of[row], []).append(row)
        for name in SOURCES:
            available = sum(len(rows) for rows in self.families[name].values())
            assert available >= composition.get(name, 0), f"{name}: {available} commands, fewer than its quota"

    def draw(self, seeds, sources=SOURCES):
        """One split per seed: {source: (number of seeds, quota) array of row positions}."""
        drawn = {}
        for source in sources:
            rows = [self.draw_source(source, seed) for seed in seeds]
            drawn[source] = np.array(rows, dtype=np.int64).reshape(len(seeds), -1)
        return drawn

    def draw_source(self, source, seed):
        quota, families = self.composition.get(source, 0), self.families[source]
        random_stream = random.Random(f"{seed}:{source}")
        if source == "ART":
            return draw_whole_families(families, quota, random_stream)
        if source == "RedCode-Exec":
            return draw_round_robin(families, quota, random_stream)
        if source == "NL2Bash":
            return draw_whole_families(families, quota, random_stream, head=self.head, head_cap=self.head_cap)
        every_row = [row for rows in families.values() for row in rows]
        return every_row[:quota]


def draw_whole_families(families, quota, random_stream, head=None, head_cap=None):
    """Whole families in random order until `quota` items are drawn.

    `families` maps family -> its members in corpus order.  The last family may be truncated.
    With `head_cap`, a member is skipped once its head (`head[member]`) has `head_cap` items.
    """
    order = sorted(families)
    random_stream.shuffle(order)
    drawn, per_head = [], Counter()
    for family in order:
        for member in families[family]:
            if head_cap and per_head[head[member]] >= head_cap:
                continue
            drawn.append(member)
            if head_cap:
                per_head[head[member]] += 1
            if len(drawn) == quota:
                return drawn
    return drawn


def draw_round_robin(strata, quota, random_stream):
    """One item from each stratum in turn, in random order, so every stratum is covered evenly."""
    remaining = {stratum: list(members) for stratum, members in strata.items()}
    for members in remaining.values():
        random_stream.shuffle(members)
    order = sorted(remaining)
    random_stream.shuffle(order)
    drawn, turn = [], 0
    while len(drawn) < quota and any(remaining.values()):
        stratum = order[turn % len(order)]
        if remaining[stratum]:
            drawn.append(remaining[stratum].pop())
        turn += 1
    return drawn
