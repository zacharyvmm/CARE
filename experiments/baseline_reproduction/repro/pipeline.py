"""The reproduction pipeline, one function per notebook stage.

`baseline_reproduction.ipynb` calls these in order; reading this file top to
bottom is reading the experiment:

    run          = settings(cfg)
    integrity    = check_environment(cfg)
    tests        = run_unit_tests()
    sources      = fetch_sources(cfg)
    split, manifest = rebuild_split(cfg, sources, run)
    smoke        = preflight(split, cfg, run)
    static_rows  = run_static_guards(split)
    obs, llm_run = run_llm_guards(split, static_rows, cfg, run)
    results      = analyse(obs, split, sources, manifest, cfg, run)
    paths        = export(results, report_md, run)
    write_provenance(...)

Every stage takes the data it needs as arguments and returns what it produced.
The work itself lives in `dataset` (split), `guards` (CARE and baselines),
`stats` (formulas) and `report` (tables, claims, figures).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

import numpy as np
import pandas as pd

from . import HERE, REPO
from . import dataset as D
from . import guards as G
from . import report as R
from . import sources as SRC

KEY_PACKAGES = ["pandas", "pyarrow", "numpy", "scipy", "statsmodels", "openai", "bashlex", "PyYAML", "matplotlib"]
SKIP_IN_INVENTORY = ("data/sources", "data/raw", "results/cache", "results/smoke", "__pycache__",
                     ".ipynb_checkpoints", ".pytest_cache")


# ---------------------------------------------------------------- run settings
@dataclass(frozen=True)
class Run:
    """How this execution runs. Built from environment variables by `settings`."""
    mode: str           # "full" (the protocol) or "smoke" (24 commands, 1 run)
    run_llm: bool       # query the LLM live; otherwise reuse the committed observations
    out: str            # output directory
    label: str          # run_id prefix in observations
    reps: int           # runs per LLM condition
    split_name: str
    api_key: str | None = field(default=None, repr=False)  # never printed or written

    @property
    def full(self):
        return self.mode == "full"


def settings(cfg, environ=os.environ):
    mode = environ.get("REPRO_MODE", "full").lower()
    assert mode in ("full", "smoke"), mode
    key = environ.get("OPENROUTER_API_KEY")
    full = mode == "full"
    run = Run(mode=mode,
              run_llm=key is not None and environ.get("REPRO_REUSE_LLM", "0") != "1",
              out=os.path.join(HERE, "results" if full else "results/smoke"),
              label="confirmatory-v1" if full else "smoke",
              reps=cfg["llm"]["reps"] if full else 1,
              split_name="reconstructed-main-seed42" if full else "smoke-24",
              api_key=key)
    os.makedirs(run.out, exist_ok=True)
    return run


def banner(run):
    mode = "FULL protocol" if run.full else "SMOKE MODE — NOT A REPRODUCTION"
    llm = ("LLM conditions EXECUTED live in this session" if run.run_llm else
           "LLM conditions NOT executed in this session: committed observations are reused")
    return f"**Mode:** {mode}  \n**LLM:** {llm}  \n**Outputs:** `{os.path.relpath(run.out, HERE)}/`"


class StageTimer(dict):
    """`with timer("sources"): ...` records wall-clock seconds as timer["sources_s"]."""

    def __init__(self):
        super().__init__()
        self.start = time.perf_counter()

    @contextlib.contextmanager
    def __call__(self, name):
        t = time.perf_counter()
        yield
        self[f"{name}_s"] = time.perf_counter() - t

    def total(self):
        return time.perf_counter() - self.start


# ---------------------------------------------------------------- stage 1: integrity
def _sh(*args, cwd=REPO):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True).stdout.strip()


def _installed(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def check_environment(cfg):
    """Record the environment, compare it with the lockfile, and assert `care/` is unmodified."""
    lock_path = os.path.join(HERE, "environment/requirements.lock.txt")
    lock = dict(ln.strip().split("==") for ln in open(lock_path) if "==" in ln)
    env = dict(python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
               cpu=(_sh("sh", "-c", "lscpu | sed -n 's/^Model name:[[:space:]]*//p'") or platform.processor()),
               cpu_count=os.cpu_count(), packages={p: _installed(p) for p in KEY_PACKAGES})
    env["lockfile_mismatches"] = {p: (v, lock[p]) for p, v in env["packages"].items() if lock.get(p) and v != lock[p]}

    release = cfg["method_under_test"]["release_commit"]
    unmodified = (_sh("git", "diff", "--stat", release, "--", "care/") == ""
                  and _sh("git", "status", "--porcelain", "--", "care/") == "")
    assert unmodified, "care/ differs from the release commit: the method under test is modified"

    print(f"✓ care/ identical to release {release} (patches: {cfg['method_under_test']['patches']})")
    print("✓ package versions match the lockfile" if not env["lockfile_mismatches"] else
          f"⚠ versions differ from the lockfile: {env['lockfile_mismatches']}")
    return dict(environment=env, repo_head=_sh("git", "rev-parse", "HEAD"))


def run_unit_tests():
    """Run this reproduction's tests and the CARE repository's own tests."""
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                          "tests", os.path.join(REPO, "tests")], cwd=HERE, text=True, capture_output=True)
    tests = dict(returncode=res.returncode, summary=res.stdout.strip().splitlines()[-1])
    assert res.returncode == 0, "unit tests failed:\n" + res.stdout[-2000:]
    print("✓ unit tests:", tests["summary"])
    return tests


# ---------------------------------------------------------------- stage 2: data
@dataclass
class Sources:
    records: dict   # name -> url, commit, license, fingerprint, verified
    roots: dict     # corpus directories for the primary split
    roots_v3: dict  # same, with the 2026-03-24 ART snapshot (variant V3)


def fetch_sources(cfg):
    """Sparse clone of every corpus at its pinned commit, verified against its SHA-256 fingerprint."""
    root = os.path.join(HERE, "data", "sources")
    records = {}
    for name, spec in cfg["sources"].items():
        fp = SRC.fingerprint(SRC.fetch(name, spec, root), spec["patterns"])
        ok = fp == spec["fingerprint"]
        records[name] = dict(url=spec["url"], commit=spec["commit"], license=spec["license"], **fp, verified=ok)
        print(f"{'✓' if ok else '✗'} {name:28s} {spec['commit'][:10]}  {fp['n_files']:4d} files  sha256 {fp['sha256'][:16]}…")
    assert all(r["verified"] for r in records.values()), "source fingerprint mismatch"
    roots = dict(art=f"{root}/atomic-red-team", redcode=f"{root}/RedCode", nl2bash=f"{root}/nl2bash")
    return Sources(records, roots, dict(roots, art=f"{root}/atomic-red-team-2026-03-24"))


def _build(cfg, roots, seed=None, **kw):
    ds = cfg["dataset"]
    return D.build_split(ds["seed"] if seed is None else seed, roots, os.path.join(HERE, ds["real_world_file"]),
                         ds["targets"], **kw)


def rebuild_split(cfg, sources, run):
    """Rebuild the seed-42 split and require it to equal the committed `data/main_split.parquet`."""
    ds = cfg["dataset"]
    split, manifest = _build(cfg, sources.roots, head_cap=ds["nl2bash_head_cap"], label_filter=ds["nl2bash_label_filter"])
    D.validate_split(split, ds["targets"])
    committed = pd.read_parquet(os.path.join(HERE, "data/main_split.parquet"))
    assert committed.equals(split[committed.columns]), "rebuilt split differs from data/main_split.parquet"
    print(f"✓ split rebuilt: {manifest['n']} commands, identical to data/main_split.parquet")
    if not run.full:
        split = split.groupby("source").head(cfg["smoke"]["per_source"]).reset_index(drop=True)
        print(f"  SMOKE: continuing with {len(split)} commands")
    return split, manifest


def preflight(split, cfg, run):
    """Exercise every execution path once before the real run (results are thrown away)."""
    sample = split.groupby("source").head(6)
    static_rows = G.run_static(sample)
    assert len(static_rows) == 2 * len(sample)
    smoke = dict(static_rows=len(static_rows))
    if run.run_llm:
        rows = G.run_llm(sample.head(1), cfg["llm"], run.api_key, 1,
                         os.path.join(HERE, "results/cache/preflight.jsonl"), progress=lambda *_: None)
        smoke["llm_preflight"] = {r["condition"]: (r["decision"], r.get("error")) for r in rows}
        assert all(r.get("error") is None for r in rows), smoke
    print("✓ preflight:", smoke)
    return smoke


# ---------------------------------------------------------------- stage 3: run the guards
def run_static_guards(split):
    """NoGuard and CARE (w/o Resolution), run twice to check that they are deterministic."""
    rows = G.run_static(split)
    key = lambda rs: [(r["condition"], r["command_id"], r["decision"], r.get("score")) for r in rs]  # noqa: E731
    assert key(rows) == key(G.run_static(split)), "static guards are not deterministic"
    print(f"✓ static guards: {len(rows)} decisions, identical across two passes")
    return rows


def run_llm_guards(split, static_rows, cfg, run):
    """CARE (with Resolution) and the three LLM-judge baselines, `run.reps` times each.

    Live mode queries the LLM and writes `observations.parquet`.  Reuse mode (no API key)
    reads the committed file unchanged and checks that the static decisions just
    re-executed are identical to the committed ones.
    """
    obs_path = os.path.join(run.out, "observations.parquet")
    to_obs = lambda rows: G.to_observations(rows, split, run.label, cfg["llm"]["model"], cfg["dataset"]["seed"])  # noqa: E731
    if run.run_llm:
        llm_run = dict(executed=True, executed_in_this_session=True, started_utc=_utc_now())
        llm_rows = G.run_llm(split, cfg["llm"], run.api_key, run.reps,
                             os.path.join(HERE, "results/cache", f"{run.label}.jsonl"))
        llm_run["finished_utc"] = _utc_now()
        obs = to_obs(static_rows + llm_rows)
        obs.to_parquet(obs_path, index=False)
    else:
        assert os.path.exists(obs_path), "no API key and no committed observations: LLM conditions cannot be evaluated"
        obs = pd.read_parquet(obs_path)
        assert obs.run_id.str.startswith(run.label).all(), "committed observations are not from this protocol's run"
        _assert_static_matches(to_obs(static_rows), obs)
        previous = json.load(open(os.path.join(run.out, "provenance.json")))["llm"]
        llm_run = {k: previous[k] for k in ("executed", "started_utc", "finished_utc") if k in previous}
        llm_run.update(executed_in_this_session=False, reused_from=os.path.relpath(obs_path, HERE))
        print("✓ static decisions identical to the committed observations; LLM observations reused (not re-queried)")
    llm_run.update(_llm_usage(obs))
    return obs, llm_run


def _assert_static_matches(fresh, committed):
    fresh = fresh.set_index(["condition", "command_id"])
    old = committed[~committed.condition.isin(G.LLM_METHODS)].set_index(["condition", "command_id"]).loc[fresh.index]
    same_scores = np.allclose(fresh.score.astype(float).fillna(-1), old.score.astype(float).fillna(-1))
    assert fresh.decision.equals(old.decision) and same_scores, "re-executed static decisions differ from committed observations"


def _llm_usage(obs):
    llm = obs[obs.llm_called == True]  # noqa: E712 -- column holds Python bools and None
    return dict(calls=int(len(llm)), errors=int(llm.error.notna().sum()), providers=llm.provider.value_counts().to_dict(),
                prompt_tokens=int(llm.prompt_tokens.fillna(0).sum()),
                completion_tokens=int(llm.completion_tokens.fillna(0).sum()),
                cost_usd=float(llm.cost_usd.fillna(0).sum()), retried_calls=int((llm.attempts.fillna(1) > 1).sum()))


def describe_llm_run(llm_run):
    when = "executed in this session" if llm_run["executed_in_this_session"] else \
        f"reused from the live run of {llm_run.get('started_utc', '?')[:19]} UTC"
    providers = ", ".join(f"{p} ({n})" for p, n in llm_run["providers"].items())
    return (f"**LLM calls:** {llm_run['calls']:,} ({when}); **errors:** {llm_run['errors']}; "
            f"**retried:** {llm_run['retried_calls']}; **served by:** {providers}; "
            f"**tokens:** {llm_run['prompt_tokens']:,} prompt + {llm_run['completion_tokens']:,} completion; "
            f"**cost:** US${llm_run['cost_usd']:.4f}")


def _utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---------------------------------------------------------------- stage 4: analysis
@dataclass
class Results:
    metrics: pd.DataFrame       # long format, every condition x run x metric, with CIs
    comparison: pd.DataFrame    # reported vs observed (Table II)
    claims: pd.DataFrame        # C1-C11 verdicts (PROTOCOL.md Sec. 6)
    mcnemar: pd.DataFrame       # paired tests (Table VIII)
    funnel: pd.DataFrame        # Resolution funnel (App. A.F)
    oracle: pd.DataFrame        # upper bounds for any Resolution judge
    by_source: pd.DataFrame
    redcode: pd.DataFrame
    seeds: pd.DataFrame | None     # static F1 over alternative split seeds (full mode only)
    variants: pd.DataFrame | None  # construction variants V0-V3 (full mode only)


def analyse(obs, split, sources, manifest, cfg, run):
    metrics = R.metrics_long(obs, split, cfg, split_name=run.split_name)
    comparison = R.comparison(metrics, cfg)
    mcnemar = R.mcnemar_table(obs, split, cfg)
    funnel = R.funnel(obs, split)
    redcode, redcode_items = R.redcode_scenarios(obs, split)
    seeds = variants = None
    if run.full:
        seeds, variants = split_sensitivity(split, redcode_items, sources, manifest, cfg)
    return Results(metrics=metrics, comparison=comparison, mcnemar=mcnemar, funnel=funnel,
                   oracle=R.oracle_bounds(obs, split), by_source=R.by_source(obs, split), redcode=redcode,
                   seeds=seeds, variants=variants,
                   claims=R.claims(comparison, mcnemar, funnel, metrics, seeds, cfg))


def split_sensitivity(split, redcode_items, sources, manifest, cfg):
    """Static CARE F1 on alternative splits (deterministic, no LLM): 100 seeds and variants V1-V3."""
    cache = {}
    first, last = cfg["analysis"]["sensitivity_seeds"]
    seeds = pd.DataFrame([dict(seed=s, **R.static_eval(_build(cfg, sources.roots, seed=s)[0], cache))
                          for s in range(first, last + 1)])
    v1 = _build(cfg, sources.roots, seed=42, label_filter=False)[0]
    v3, manifest_v3 = _build(cfg, sources.roots_v3, seed=42)
    weak = split.command_id.isin(redcode_items[redcode_items.kind == "software-weakness"].command_id)
    no_redcode = split.source != "RedCode-Exec"
    art_pools = f"pool {manifest_v3['candidate_pool']['ART']} vs {manifest['candidate_pool']['ART']}"
    variants = pd.DataFrame([
        dict(variant="V0 primary", note="seed 42, as protocol", n=len(split), **R.static_eval(split, cache)),
        dict(variant="V1", note="NL2Bash label filter off (D5)", n=len(v1), **R.static_eval(v1, cache)),
        dict(variant="V2 (exploratory, post hoc)", note="RedCode software-weakness scenarios removed (D9)",
             n=int((~weak).sum()), **R.static_eval(split[~weak], cache)),
        dict(variant="V2b", note="RedCode removed", n=int(no_redcode.sum()), **R.static_eval(split[no_redcode], cache)),
        dict(variant="V3", note=f"ART snapshot 2026-03-24 ({art_pools})", n=len(v3), **R.static_eval(v3, cache)),
    ])
    return seeds, variants


# ---------------------------------------------------------------- stage 5: export
def export(results, report_md, run):
    """Write every analysis table as Parquet plus `report.md`; return the Parquet paths."""
    def save(df, name):
        path = os.path.join(run.out, name)
        df.to_parquet(path, index=False)
        return path

    r = results
    paths = [os.path.join(run.out, "observations.parquet"),
             save(r.metrics.assign(experiment="main"), "metrics.parquet"),
             save(r.comparison, "comparison.parquet"),
             save(r.claims, "claims.parquet"),
             save(r.mcnemar, "mcnemar.parquet"),
             save(r.funnel, "resolution_funnel.parquet"),
             save(r.oracle, "oracle_bounds.parquet"),
             save(r.by_source, "by_source.parquet"),
             save(r.redcode, "redcode_scenarios.parquet")]
    if r.seeds is not None:
        paths += [save(r.seeds, "sensitivity_seeds.parquet"), save(r.variants, "sensitivity_variants.parquet")]
    with open(os.path.join(run.out, "report.md"), "w") as f:
        f.write(report_md)
    return paths


def write_provenance(run, cfg, integrity, tests, sources, manifest, llm_run, smoke, stage_seconds, paths):
    """Write `provenance.json` (everything needed to audit the run) and `validation.json` (pass/fail checks)."""
    rel = lambda p: os.path.relpath(p, HERE)  # noqa: E731
    sha = lambda p: SRC.sha256_file(os.path.join(HERE, p))  # noqa: E731
    provenance = dict(
        generated_utc=_utc_now(), mode=run.mode, run_label=run.label,
        protocol_version=cfg["protocol_version"], protocol_sha256=sha("PROTOCOL.md"),
        config_sha256=sha("config.yaml"), repo_head=integrity["repo_head"],
        method_under_test=dict(cfg["method_under_test"], care_identical_to_release=True),
        paper=cfg["paper"], sources=sources.records,
        split=dict(manifest, sha256=sha("data/main_split.parquet")),
        llm=dict(cfg["llm"], **llm_run), environment=integrity["environment"], unit_tests=tests, smoke_check=smoke,
        stage_seconds={k: round(v, 2) for k, v in stage_seconds.items()},
        outputs={rel(p): SRC.sha256_file(p) for p in paths},
    )
    validation = dict(mode=run.mode, unit_tests=tests, smoke_check=smoke, static_deterministic=True,
                      split_identical_to_committed=True,
                      sources_verified=all(s["verified"] for s in sources.records.values()),
                      llm_executed_in_this_session=llm_run["executed_in_this_session"],
                      llm_errors=llm_run["errors"], completed_utc=provenance["generated_utc"])
    json.dump(provenance, open(os.path.join(run.out, "provenance.json"), "w"), indent=2, default=str)
    json.dump(validation, open(os.path.join(run.out, "validation.json"), "w"), indent=2)
    print("wrote:", *[rel(p) for p in paths], "report.md", "provenance.json", "validation.json", sep="\n  ")
    return provenance


def inventory():
    """Every committed artifact file with its size and SHA-256 prefix."""
    rows = []
    for root, _, files in os.walk(HERE):
        if any(s in root for s in SKIP_IN_INVENTORY):
            continue
        for f in files:
            p = os.path.join(root, f)
            rows.append(dict(path=os.path.relpath(p, HERE), bytes=os.path.getsize(p), sha256=SRC.sha256_file(p)[:16]))
    return pd.DataFrame(rows).sort_values("path").reset_index(drop=True)
