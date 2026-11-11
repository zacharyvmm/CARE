"""The evaluated population, and the paper's split recipe (paper Table I, Sec. IV-B).

Population: every unique command of the public corpora the paper draws from (PROTOCOL.md §4).

    source                class      what is loaded (decision IDs refer to DECISIONS.md)
    ART (Atomic Red Team) DANGEROUS  every Linux sh/bash atomic test; family = technique YAML
    RedCode-Exec (bash)   DANGEROUS  every bash script; family = risk scenario (D3)
    NL2Bash               SAFE       every command; family = lexical template (D11).  Commands that
                                     perform an operation the paper calls unconditionally dangerous
                                     are evaluated but not counted as SAFE (D5): `in_primary` is False
    Real-world            SAFE       the 30 developer commands in data/manual/ (D4)

Paper-sized splits: the paper evaluates 549 commands drawn from these corpora.  `SplitRecipe`
re-draws a split of that composition from the population, once per seed:

    population, manifest = load_population(roots, real_world_file)
    draws = SplitRecipe(population, composition, head_cap).draw(seeds)   # row positions into `population`
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
from collections import Counter

import numpy as np
import pandas as pd
import yaml

SOURCES = ("ART", "RedCode-Exec", "NL2Bash", "Real-world")
LABEL = {"ART": "DANGEROUS", "RedCode-Exec": "DANGEROUS", "NL2Bash": "SAFE", "Real-world": "SAFE"}

# D5 -- NL2Bash label hygiene: operations the paper itself calls "unconditionally
# dangerous" (Table I, adversarial-benign row), plus disk destruction and fork bombs.
UNSAFE_NL2BASH = [
    r"(^|[\s;|&(`])(sudo|su|doas)(\s|$)",
    r"\bshred\b",
    r"\b(kill|killall|pkill)\b[^|;&]*\s-(9|KILL|SIGKILL)\b",
    r"\bchown\b[^|;&]*\broot\b",
    r"\bchmod\b[^|;&]*\s([ugoa]*\+[rwxt]*s|[2467][0-7]{3})\b",
    r"(>|\btee\b|\bcp\b|\bmv\b|\bsed\s+-i|\brm\b|\bchmod\b|\bchown\b|\bln\b)[^|;&]*\s/etc/",
    r"\bmkfs(\.\w+)?\b|\bfdisk\b|\bdd\b[^|;&]*\bof=/dev/",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(-\S+\s+)*/(\s|\*|$)",
    r":\(\)\s*\{",
]
UNSAFE_NL2BASH_RE = re.compile("|".join(f"(?:{p})" for p in UNSAFE_NL2BASH))

# RedCode-Exec bash scenarios whose scripts contain a software weakness rather than a harmful
# operation.  Our own reading of each scenario's task text; used in diagnostics only (D9).
REDCODE_WEAKNESS_SCENARIOS = {12, 15, 16, 20, 22, 23, 25}


# ---------------------------------------------------------------- one record per command
def strip_script(code):
    """Drop shebang, comment-only and blank lines."""
    return "\n".join(ln.rstrip() for ln in code.splitlines()
                     if ln.strip() and not ln.strip().startswith("#")).strip()


def head_of(cmd):
    tok = cmd.strip().split()
    return os.path.basename(tok[0]) if tok else ""


def nl2bash_template(cmd):
    """Lexical template: mask quoted strings, paths, globs and numbers."""
    t = re.sub(r'"[^"]*"|\'[^\']*\'', "<S>", cmd)
    t = re.sub(r"(?:~|\.{1,2})?/[^\s|;&)<>]*", "<P>", t)
    t = re.sub(r"\S*[*?]\S*", "<G>", t)
    t = re.sub(r"(?<![\w-])\d+(?:\.\d+)?\b", "<N>", t)
    return re.sub(r"\s+", " ", t).strip()


def command_id(source, text):
    return source[:3].lower() + "-" + hashlib.sha1(f"{source}\x00{text}".encode()).hexdigest()[:10]


def record(source, family, command, in_primary=True, **meta):
    return dict(command_id=command_id(source, command), source=source, label=LABEL[source],
                label_dangerous=LABEL[source] == "DANGEROUS", in_primary=in_primary,
                family=family, head=head_of(command), command=command, meta=json.dumps(meta))


# ---------------------------------------------------------------- corpora (records in corpus order)
def load_art(root):
    recs, seen = [], set()
    for fp in sorted(glob.glob(os.path.join(root, "atomics", "T*", "T*.yaml"))):
        try:
            y = yaml.safe_load(open(fp, encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- malformed upstream YAML is skipped
            continue
        tid = y.get("attack_technique")
        for t in y.get("atomic_tests", []) or []:
            ex = t.get("executor") or {}
            if "linux" not in (t.get("supported_platforms") or []) or ex.get("name") not in ("sh", "bash"):
                continue
            cmd = ex.get("command") or ""
            for k, v in (t.get("input_arguments") or {}).items():
                cmd = cmd.replace("#{%s}" % k, str((v or {}).get("default")))
            cmd = strip_script(cmd)
            if not cmd or cmd in seen:
                continue
            seen.add(cmd)
            recs.append(record("ART", tid, cmd, technique=tid, test_name=t.get("name"),
                               guid=t.get("auto_generated_guid")))
    return recs


def load_redcode(root):
    recs, seen = [], set()
    pat = os.path.join(root, "dataset", "RedCode-Exec", "bash2text_dataset_json", "*.json")
    for fp in sorted(glob.glob(pat)):
        scenario = int(re.search(r"index(\d+)_", os.path.basename(fp)).group(1))
        for item in json.load(open(fp, encoding="utf-8")):
            cmd = strip_script(item.get("Code") or "")
            if not cmd or cmd in seen:
                continue
            seen.add(cmd)
            recs.append(record("RedCode-Exec", f"RC-{scenario:02d}", cmd, scenario=scenario, index=item.get("Index")))
    return recs


def load_nl2bash(root):
    base = os.path.join(root, "data", "bash")
    cms = open(os.path.join(base, "all.cm"), encoding="utf-8").read().splitlines()
    nls = open(os.path.join(base, "all.nl"), encoding="utf-8").read().splitlines()
    recs, seen = [], set()
    for i, (cm, nl) in enumerate(zip(cms, nls)):
        cm = cm.strip()
        if not cm or cm in seen:
            continue
        seen.add(cm)
        tpl = nl2bash_template(cm)
        fam = "NB-" + hashlib.sha1(tpl.encode()).hexdigest()[:8]
        recs.append(record("NL2Bash", fam, cm, in_primary=not UNSAFE_NL2BASH_RE.search(cm),   # D5
                           line=i + 1, nl=nl, template=tpl))
    return recs


def load_real_world(path):
    cmds = [ln.strip() for ln in open(path, encoding="utf-8")]
    cmds = [c for c in cmds if c and not c.startswith("#")]
    return [record("Real-world", f"R-{i + 1}", c) for i, c in enumerate(cmds)]


# ---------------------------------------------------------------- the population
def load_population(roots, real_world_file):
    """Every unique command of every corpus, in corpus order; returns (DataFrame, manifest).

    A command string that occurs in two corpora has conflicting labels and is dropped from
    both (D10).  `in_primary` is False for the NL2Bash commands that D5 does not count as SAFE.
    """
    recs = (load_art(roots["art"]) + load_redcode(roots["redcode"])
            + load_nl2bash(roots["nl2bash"]) + load_real_world(real_world_file))
    seen = Counter(r["command"] for r in recs)
    conflicts = sorted(c for c, n in seen.items() if n > 1)
    population = pd.DataFrame([r for r in recs if seen[r["command"]] == 1])
    validate_population(population)
    return population, dict(manifest(population), cross_source_conflicts_dropped=conflicts)


def manifest(population):
    p = population[population.in_primary]
    return dict(n_evaluated=len(population), n_primary=len(p),
                n_dangerous=int(p.label_dangerous.sum()), n_safe=int((~p.label_dangerous).sum()),
                per_source={s: int((p.source == s).sum()) for s in SOURCES},
                nl2bash_not_counted_as_safe=int((~population.in_primary).sum()))


def validate_population(df):
    """Integrity checks; raises AssertionError with a message on failure."""
    assert df.command_id.is_unique, "duplicate command_id"
    assert not df.command.duplicated().any(), "duplicate command text"
    assert df.notna().all().all(), "missing values"
    assert set(df.source) <= set(SOURCES), "unknown source"
    assert (df.label == df.source.map(LABEL)).all(), "labels are corpus-level: one class per source"
    assert df[~df.in_primary].source.eq("NL2Bash").all(), "only NL2Bash commands can be set aside (D5)"
    leaked = df[df.in_primary & (df.source == "NL2Bash")].command.map(lambda c: bool(UNSAFE_NL2BASH_RE.search(c)))
    assert not leaked.any(), "an unsafe NL2Bash command is counted as SAFE (D5)"
    return True


def composition(population):
    """Per source: class, commands, template families, distinct heads, multi-line commands."""
    name = np.where(population.in_primary, population.source, population.source + " (not counted as SAFE, D5)")
    label = np.where(population.in_primary, population.label, "—")
    table = population.assign(group=name, label=label).groupby(["group", "label"], sort=False).agg(
        commands=("command_id", "size"), families=("family", "nunique"), heads=("head", "nunique"),
        multiline=("command", lambda c: int(c.str.contains("\n").sum()))).reset_index()
    return table.rename(columns={"group": "source", "label": "class"})


def redcode_scenario(population):
    """RedCode scenario number per row (NaN for other sources)."""
    rc = population.source == "RedCode-Exec"
    return population.family.where(rc).str[3:].astype(float)


# ---------------------------------------------------------------- the paper's split recipe
def family_draw(families, target, rng, head=None, head_cap=None):
    """Whole families in seeded random order until `target` items are drawn.

    `families` maps family -> its members in corpus order.  The last family may be truncated.
    With `head_cap`, a member is skipped once its head (`head[member]`) has `head_cap` items.
    """
    order = sorted(families)
    rng.shuffle(order)
    out, heads = [], Counter()
    for f in order:
        for item in families[f]:
            if head_cap and heads[head[item]] >= head_cap:
                continue
            out.append(item)
            if head_cap:
                heads[head[item]] += 1
            if len(out) == target:
                return out
    return out


def stratified_draw(strata, target, rng):
    """Round-robin over strata in seeded random order, so every stratum is covered evenly."""
    strata = {s: list(members) for s, members in strata.items()}
    for members in strata.values():
        rng.shuffle(members)
    order = sorted(strata)
    rng.shuffle(order)
    out, i = [], 0
    while len(out) < target and any(strata.values()):
        s = order[i % len(order)]
        if strata[s]:
            out.append(strata[s].pop())
        i += 1
    return out


class SplitRecipe:
    """Draws splits with the paper's Table I composition from the population.

        ART           whole technique families, in random order, until the quota is reached
        RedCode-Exec  round-robin over the risk scenarios, random commands within each
        NL2Bash       whole template families until the quota, at most `head_cap` commands per head
        Real-world    the first `quota` commands (a fixed set)

    Each source has its own random stream, seeded by (seed, source).  Only `eligible` rows can be
    drawn (default: the primary population).  `draw(seeds)` returns one split per seed, as row
    positions into `population`.
    """

    def __init__(self, population, composition, head_cap, eligible=None):
        eligible = population.in_primary.to_numpy() if eligible is None else np.asarray(eligible, bool)
        source, family = population.source.to_numpy(), population.family.to_numpy()
        self.composition, self.head_cap = composition, head_cap
        self.head = population["head"].to_numpy()
        self.families = {s: {} for s in SOURCES}     # source -> {family: [row positions, in corpus order]}
        for pos in np.flatnonzero(eligible).tolist():
            self.families[source[pos]].setdefault(family[pos], []).append(pos)
        for s in SOURCES:
            available = sum(map(len, self.families[s].values()))
            assert available >= composition.get(s, 0), f"{s}: {available} commands, fewer than its quota"

    def draw_source(self, source, seed):
        quota, families = self.composition.get(source, 0), self.families[source]
        rng = random.Random(f"{seed}:{source}")
        if source == "ART":
            return family_draw(families, quota, rng)
        if source == "RedCode-Exec":
            return stratified_draw(families, quota, rng)
        if source == "NL2Bash":
            return family_draw(families, quota, rng, head=self.head, head_cap=self.head_cap)
        return [pos for members in families.values() for pos in members][:quota]

    def draw(self, seeds, sources=SOURCES):
        """One split per seed: {source: (n_seeds, quota) array of row positions into the population}."""
        return {s: np.array([self.draw_source(s, seed) for seed in seeds], dtype=np.int64).reshape(len(seeds), -1)
                for s in sources}


def as_matrix(draws):
    """Join per-source draws into one (n_splits, split_size) matrix of row positions."""
    return np.hstack([draws[s] for s in SOURCES if s in draws])
