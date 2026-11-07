"""Reconstruct the CARE main evaluation split (paper Table I, Sec. IV-B).

    source               class      n    recipe (decision IDs refer to DECISIONS.md)
    ART (Atomic Red Team) DANGEROUS 137  linux sh/bash atomic tests, family = technique YAML
    Canonical attacks     DANGEROUS  12  unreleased -> slots filled from ART (D2)
    RedCode-Exec (bash)   DANGEROUS  71  stratified round-robin over risk scenarios (D3)
    NL2Bash               SAFE      299  head-stratified (cap 12/head), family = lexical template (D5, D11)
    Real-world commands   SAFE       30  unreleased -> data/manual/ (D4)

Sampling draws whole families in seeded order, so siblings are drawn together
or not at all (D11).  Pure functions of (seed, source roots, config).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict

import pandas as pd
import yaml

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
SOURCES = ("art", "redcode", "nl2bash", "real")


# ---------------------------------------------------------------- helpers
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


def cmd_id(source, text):
    return source[:3].lower() + "-" + hashlib.sha1(f"{source}\x00{text}".encode()).hexdigest()[:10]


def rec(source, label, family, command, **meta):
    return dict(command_id=cmd_id(source, command), source=source, label=label,
                family=family, head=head_of(command), command=command, meta=json.dumps(meta))


# ---------------------------------------------------------------- sources
def load_art(root):
    recs, seen = [], set()
    for fp in sorted(glob.glob(os.path.join(root, "atomics", "T*", "T*.yaml"))):
        try:
            y = yaml.safe_load(open(fp, encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- malformed upstream YAML is skipped (counted below)
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
            recs.append(rec("ART", "DANGEROUS", tid, cmd, technique=tid,
                            test_name=t.get("name"), guid=t.get("auto_generated_guid")))
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
            recs.append(rec("RedCode-Exec", "DANGEROUS", f"RC-{scenario:02d}", cmd,
                            scenario=scenario, index=item.get("Index")))
    return recs


def load_nl2bash(root, label_filter=True):
    base = os.path.join(root, "data", "bash")
    cms = open(os.path.join(base, "all.cm"), encoding="utf-8").read().splitlines()
    nls = open(os.path.join(base, "all.nl"), encoding="utf-8").read().splitlines()
    recs, seen, dropped = [], set(), 0
    for i, (cm, nl) in enumerate(zip(cms, nls)):
        cm = cm.strip()
        if not cm or cm in seen:
            continue
        seen.add(cm)
        if label_filter and UNSAFE_NL2BASH_RE.search(cm):
            dropped += 1
            continue
        tpl = nl2bash_template(cm)
        fam = "NB-" + hashlib.sha1(tpl.encode()).hexdigest()[:8]
        recs.append(rec("NL2Bash", "SAFE", fam, cm, line=i + 1, nl=nl, template=tpl))
    return recs, dropped


def load_real_world(path):
    cmds = [ln.strip() for ln in open(path, encoding="utf-8")]
    cmds = [c for c in cmds if c and not c.startswith("#")]
    return [rec("Real-world", "SAFE", f"R-{i + 1}", c) for i, c in enumerate(cmds)]


# ---------------------------------------------------------------- sampling
def family_draw(recs, target, rng, head_cap=None):
    """Whole families in seeded random order until `target`; optional head cap.
    The last family may be truncated; its remainder is never used."""
    fams = defaultdict(list)
    for r in recs:
        fams[r["family"]].append(r)
    order = sorted(fams)
    rng.shuffle(order)
    out, heads = [], Counter()
    for f in order:
        for r in fams[f]:
            if head_cap and heads[r["head"]] >= head_cap:
                continue
            out.append(r)
            heads[r["head"]] += 1
            if len(out) == target:
                return out
    return out


def stratified_draw(recs, target, rng):
    """Round-robin over strata in seeded order -> even coverage of strata."""
    fams = defaultdict(list)
    for r in recs:
        fams[r["family"]].append(r)
    for f in fams.values():
        rng.shuffle(f)
    order = sorted(fams)
    rng.shuffle(order)
    out, i = [], 0
    while len(out) < target and any(fams.values()):
        f = order[i % len(order)]
        if fams[f]:
            out.append(fams[f].pop())
        i += 1
    return out


_POOLS = {}


def load_pools(roots, real_world_file, label_filter=True):
    key = (roots["art"], roots["redcode"], roots["nl2bash"], real_world_file, label_filter)
    if key not in _POOLS:
        nl2bash, dropped = load_nl2bash(roots["nl2bash"], label_filter)
        pools = dict(art=load_art(roots["art"]), redcode=load_redcode(roots["redcode"]),
                     nl2bash=nl2bash, real=load_real_world(real_world_file))
        # D10 -- a string present in two sources has conflicting labels; drop it everywhere.
        seen = Counter(r["command"] for k in SOURCES for r in pools[k])
        conflicts = sorted(c for c, n in seen.items() if n > 1)
        for k in SOURCES:
            pools[k] = [r for r in pools[k] if r["command"] not in set(conflicts)]
        pools.update(nl2bash_dropped=dropped, conflicts=conflicts)
        _POOLS[key] = pools
    return _POOLS[key]


def build_split(seed, roots, real_world_file, targets, head_cap=12, label_filter=True):
    """Return (DataFrame, manifest dict) for the reconstructed main split."""
    p = load_pools(roots, real_world_file, label_filter)
    rng = lambda src: random.Random(f"{seed}:{src}")  # independent stream per source  # noqa: E731
    parts = (family_draw(p["art"], targets["ART"], rng("ART"))
             + stratified_draw(p["redcode"], targets["RedCode-Exec"], rng("RedCode-Exec"))
             + family_draw(p["nl2bash"], targets["NL2Bash"], rng("NL2Bash"), head_cap=head_cap)
             + p["real"][: targets["Real-world"]])
    df = pd.DataFrame(parts)
    df["label_dangerous"] = df["label"].eq("DANGEROUS")
    df = df.sort_values(["source", "command_id"], kind="stable").reset_index(drop=True)
    by = lambda s: df[df.source == s]  # noqa: E731
    manifest = dict(
        seed=seed, label_filter=label_filter, n=len(df),
        n_dangerous=int(df.label_dangerous.sum()), n_safe=int((~df.label_dangerous).sum()),
        per_source={k: int(v) for k, v in df.source.value_counts().items()},
        candidate_pool=dict(ART=len(p["art"]), RedCode_Exec=len(p["redcode"]), NL2Bash=len(p["nl2bash"]),
                            NL2Bash_label_filtered_out=p["nl2bash_dropped"], Real_world=len(p["real"]),
                            cross_source_conflicts_dropped=p["conflicts"]),
        families_drawn=dict(ART=int(by("ART").family.nunique()),
                            RedCode_Exec=int(by("RedCode-Exec").family.nunique()),
                            NL2Bash=int(by("NL2Bash").family.nunique()),
                            NL2Bash_heads=int(by("NL2Bash")["head"].nunique())),
    )
    return df, manifest


def validate_split(df, targets):
    """Integrity checks; raises AssertionError with a message on failure."""
    assert df.command_id.is_unique, "duplicate command_id"
    assert not df.command.duplicated().any(), "duplicate command text"
    assert df.notna().all().all(), "missing values"
    counts = df.source.value_counts().to_dict()
    assert counts == targets, f"per-source counts {counts} != {targets}"
    lab = df.groupby("source").label.unique().map(list).to_dict()
    assert lab == {"ART": ["DANGEROUS"], "RedCode-Exec": ["DANGEROUS"],
                   "NL2Bash": ["SAFE"], "Real-world": ["SAFE"]}, f"labels by source {lab}"
    assert not df[df.source == "NL2Bash"].command.map(lambda c: bool(UNSAFE_NL2BASH_RE.search(c))).any(), "D5 filter leak"
    return True
