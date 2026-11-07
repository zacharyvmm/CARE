"""Reconstruct the CARE main evaluation split (paper Table I) from public sources.

The authors' 549-command split is not released with the code, so this script
rebuilds a size- and composition-matched split from the same public corpora,
following the recipe in the paper (Sec. IV-B, Table I):

    source               class      n    paper recipe
    ART (Atomic Red Team) DANGEROUS 137  linux sh/bash atomic tests, family = technique YAML
    Canonical attacks     DANGEROUS  12  author-curated, unreleased -> slots filled from ART (D2)
    RedCode-Exec (bash)   DANGEROUS  71  bash2text_dataset_json, stratified by risk scenario (D3)
    NL2Bash               SAFE      299  head-stratified (cap 12/head), family = lexical template
    Real-world commands   SAFE       30  author-curated, unreleased -> data/manual/ (D4)
    ------------------------------------------------------------------------------
    total                           549  (220 DANGEROUS + 329 SAFE)

Selection is deterministic for a given seed (paper: seed 42).  Sampling is
done over whole template families, so sibling commands (same ART technique
YAML / same NL2Bash lexical template) are either drawn together or not at all.
Decision IDs (D1..Dn) refer to DECISIONS in README.md.

    python experiments/baseline_reproduction/build_dataset.py            # seed 42
    python experiments/baseline_reproduction/build_dataset.py --seed 7 --out /tmp/x.parquet
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import re
import subprocess
from collections import Counter, defaultdict

import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw")
MANUAL = os.path.join(HERE, "data", "manual", "real_world_commands.txt")
DEFAULT_OUT = os.path.join(HERE, "data", "main_split.parquet")

SEED = 42
TARGETS = {"ART": 137 + 12, "RedCode-Exec": 71, "NL2Bash": 299, "Real-world": 30}
NL2BASH_HEAD_CAP = 12

# D5 -- label hygiene for the NL2Bash SAFE class.  NL2Bash is a NL->bash
# translation corpus, not a safety corpus, so a minority of its commands are
# unconditionally dangerous.  We drop exactly the operations the paper itself
# names as "unconditionally dangerous" when building its adversarial-benign
# NL2Bash pool (Table I: sudo, shred, kill -9, root chown, SUID chmod, writes
# under /etc/), plus disk-level destruction and fork bombs.
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


# ---------------------------------------------------------------- helpers
def git_sha(path):
    try:
        return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def strip_script(code):
    """Drop shebang, comment-only and blank lines."""
    out = [ln.rstrip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return "\n".join(out).strip()


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
        except Exception:
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
    cms = open(os.path.join(root, "data", "bash", "all.cm"), encoding="utf-8").read().splitlines()
    nls = open(os.path.join(root, "data", "bash", "all.nl"), encoding="utf-8").read().splitlines()
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
    lines = [ln.strip() for ln in open(path, encoding="utf-8")]
    cmds = [ln for ln in lines if ln and not ln.startswith("#")]
    return [rec("Real-world", "SAFE", f"R-{i + 1}", c) for i, c in enumerate(cmds)]


# ---------------------------------------------------------------- sampling
def family_draw(recs, target, rng, head_cap=None):
    """Draw whole families in seeded random order until `target` is reached.

    With `head_cap`, members whose command head already has `head_cap`
    representatives are skipped (head stratification).  The last family is
    truncated if it overshoots; the remainder is never used anywhere, so no
    family straddles two evaluated partitions.
    """
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
    """Round-robin over strata (families) in seeded order -> even coverage."""
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


_POOL_CACHE = {}


def load_pools(label_filter=True, art_root=None):
    art_root = art_root or os.path.join(RAW, "atomic-red-team")
    key = (label_filter, art_root)
    if key not in _POOL_CACHE:
        nl2bash, dropped = load_nl2bash(os.path.join(RAW, "nl2bash"), label_filter)
        _POOL_CACHE[key] = dict(
            art=load_art(art_root),
            redcode=load_redcode(os.path.join(RAW, "RedCode")),
            nl2bash=nl2bash, nl2bash_dropped=dropped,
            real=load_real_world(MANUAL),
        )
        # D10 -- a command string present in two sources has conflicting labels
        # (e.g. `hostname`, `history -c`: ART=DANGEROUS, NL2Bash=SAFE); drop it everywhere.
        pools = _POOL_CACHE[key]
        seen = Counter(r["command"] for k in ("art", "redcode", "nl2bash", "real") for r in pools[k])
        conflicts = {c for c, n in seen.items() if n > 1}
        for k in ("art", "redcode", "nl2bash", "real"):
            pools[k] = [r for r in pools[k] if r["command"] not in conflicts]
        pools["cross_source_conflicts"] = sorted(conflicts)
    return _POOL_CACHE[key]


def build_split(seed=SEED, label_filter=True, art_root=None):
    """Return (DataFrame, manifest) for the reconstructed main split."""
    p = load_pools(label_filter, art_root)
    rng = lambda src: random.Random(f"{seed}:{src}")  # independent stream per source
    art = family_draw(p["art"], TARGETS["ART"], rng("ART"))
    redcode = stratified_draw(p["redcode"], TARGETS["RedCode-Exec"], rng("RedCode-Exec"))
    nl2bash = family_draw(p["nl2bash"], TARGETS["NL2Bash"], rng("NL2Bash"), head_cap=NL2BASH_HEAD_CAP)
    real = p["real"][: TARGETS["Real-world"]]

    df = pd.DataFrame(art + redcode + nl2bash + real)
    df["label_dangerous"] = df["label"].eq("DANGEROUS")
    assert df["command_id"].is_unique, "command_id collision"
    assert not df["command"].duplicated().any(), "duplicate command across sources"
    df = df.sort_values(["source", "command_id"], kind="stable").reset_index(drop=True)

    manifest = dict(
        seed=seed, label_filter=label_filter, n=len(df),
        n_dangerous=int(df.label_dangerous.sum()), n_safe=int((~df.label_dangerous).sum()),
        per_source=df.source.value_counts().to_dict(),
        candidate_pool=dict(ART=len(p["art"]), RedCode_Exec=len(p["redcode"]),
                            NL2Bash=len(p["nl2bash"]), NL2Bash_label_filtered_out=p["nl2bash_dropped"],
                            Real_world=len(p["real"]),
                            cross_source_conflicts_dropped=p["cross_source_conflicts"]),
        families_drawn=dict(ART=int(df[df.source == "ART"].family.nunique()),
                            RedCode_Exec=int(df[df.source == "RedCode-Exec"].family.nunique()),
                            NL2Bash=int(df[df.source == "NL2Bash"].family.nunique()),
                            NL2Bash_heads=int(df[df.source == "NL2Bash"]["head"].nunique())),
    )
    return df, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--no-label-filter", action="store_true", help="disable NL2Bash label hygiene (D5)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    df, manifest = build_split(a.seed, not a.no_label_filter)
    manifest["sources"] = {
        name: dict(url=url, commit=git_sha(os.path.join(RAW, name)))
        for name, url in [("atomic-red-team", "https://github.com/redcanaryco/atomic-red-team"),
                          ("RedCode", "https://github.com/AI-secure/RedCode"),
                          ("nl2bash", "https://github.com/TellinaTool/nl2bash")]
    }
    # Build in pandas, persist as Parquet.
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    df.to_parquet(a.out, index=False)
    with open(os.path.splitext(a.out)[0] + "_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
