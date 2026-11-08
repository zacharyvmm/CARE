"""The reproduction pipeline, one function per notebook stage.

`baseline_reproduction.ipynb` calls these in order; reading this file top to
bottom is reading the experiment:

    run             = settings(cfg)                          # mode, LLM live or reused, output dir
    integrity       = check_environment(cfg)                 # care/ unmodified, versions recorded
    tests           = run_unit_tests()
    sources         = fetch_sources(cfg)                     # corpora at pinned commits
    pools           = load_pools(cfg, sources.roots)         # every candidate command per corpus
    split, manifest = rebuild_split(cfg, pools, run)         # the 549 commands
    smoke           = preflight(split, cfg, run)
    static_rows     = run_static_guards(split)               # NoGuard, CARE (w/o Resolution)
    obs, llm_run    = query_llm_guards(...)                  # live, or:
                      reuse_llm_observations(...)            #   committed run, verified
    results         = analyse(obs, split, pools, sources, cfg, run)
    paths           = export(results, report_md, run)
    write_provenance(...)

Every stage takes the data it needs as arguments and returns what it produced.
The work itself lives in

    dataset      corpora -> candidate pools -> split
    guards       CARE and the LLM-judge baselines, the pinned LLM client and its cache
    analysis     observations -> metrics, design-based CIs, diagnostics
    sensitivity  static CARE on re-drawn splits: seed sweep, variants, CI coverage
    claims       verdicts C1-C11 (v1.3, with the superseded rule sets alongside)
    stats        the formulas: metrics, Wilson, McNemar, bootstrap weights
    report       figures, views, report.md
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
from . import analysis as A
from . import claims as C
from . import dataset as D
from . import guards as G
from . import sensitivity as SENS
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


def load_pools(cfg, roots, label_filter=None):
    """Every candidate command per corpus (label filter from the config unless given)."""
    ds = cfg["dataset"]
    return D.load_pools(roots, os.path.join(HERE, ds["real_world_file"]),
                        ds["nl2bash_label_filter"] if label_filter is None else label_filter)


def rebuild_split(cfg, pools, run):
    """Rebuild the seed-42 split and require it to equal the committed `data/main_split.parquet`."""
    ds = cfg["dataset"]
    split, manifest = D.build_split(pools, ds["seed"], ds["targets"], ds["nl2bash_head_cap"])
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


def query_llm_guards(split, static_rows, cfg, run):
    """CARE (with Resolution) and the three LLM-judge baselines, `run.reps` times each, queried live.

    Writes `observations.parquet` and `llm_request_identity.json` (what was requested, so that a
    later reuse can verify it).  Replies reused from the resumability cache are counted (`cached_rows`).
    """
    started = _utc_now()
    llm_rows = G.run_llm(split, cfg["llm"], run.api_key, run.reps,
                         os.path.join(HERE, "results/cache", f"{run.label}.jsonl"))
    finished = _utc_now()
    obs = _to_observations(static_rows + llm_rows, split, cfg, run)
    obs.to_parquet(os.path.join(run.out, "observations.parquet"), index=False)
    identity = dict(run_label=run.label, schema="per-row request_fingerprint and from_cache (D18)",
                    how_established="recorded at execution", executed_at_commit=_sh("git", "rev-parse", "HEAD"),
                    executed_config=_request_config(cfg["llm"]), started_utc=started, finished_utc=finished,
                    request_fingerprints={c: G.request_fingerprint(cfg["llm"], c) for c in G.LLM_METHODS})
    json.dump(identity, open(os.path.join(run.out, "llm_request_identity.json"), "w"), indent=2)
    cached = sum(bool(r.get("from_cache")) and r["llm_called"] for r in llm_rows)
    llm_run = dict(executed=True, started_utc=started, finished_utc=finished,
                   executed_in_this_session=cached < sum(r["llm_called"] for r in llm_rows), cached_rows=cached)
    return obs, dict(llm_run, **_llm_usage(obs))


def reuse_llm_observations(split, static_rows, cfg, run):
    """The committed observations of the live confirmatory run, verified rather than re-queried.

    Checks that (a) the static decisions just re-executed equal the committed ones, (b) today's
    requests (model, serving, decoding, prompts) are identical to the executed ones (D20), and
    (c) every committed LLM reply was requested inside the live run's time window with a unique
    generation id (no stale replies).  Smoke mode keeps the smoke subset and run 1.
    """
    committed_path = os.path.join(HERE, "results", "observations.parquet")
    assert os.path.exists(committed_path), "no API key and no committed observations: LLM conditions cannot be evaluated"
    obs = pd.read_parquet(committed_path)
    assert obs.run_id.str.startswith("confirmatory-v1").all(), "committed observations are not from this protocol's run"
    if not run.full:
        obs = obs[obs.command_id.isin(split.command_id) & (obs.rep == 1)].reset_index(drop=True)
        obs.to_parquet(os.path.join(run.out, "observations.parquet"), index=False)
    identity = json.load(open(os.path.join(HERE, "results", "llm_request_identity.json")))
    window = dict(started_utc=identity["started_utc"], finished_utc=identity["finished_utc"])

    _assert_static_matches(_to_observations(static_rows, split, cfg, run), obs)
    _assert_same_requests(identity, obs, cfg["llm"])
    _assert_replies_from_live_run(obs, window)

    print("✓ static decisions identical to the committed observations; LLM observations reused (not re-queried)")
    print("✓ requested model, serving, decoding and prompts are identical to those of the executed run "
          f"(request fingerprints; {identity['how_established'][:40]}…)")
    print(f"✓ all committed LLM replies were requested during the live run "
          f"({window['started_utc'][:19]} – {window['finished_utc'][:19]} UTC), with unique generation ids")
    llm_run = dict(executed=True, **window, executed_in_this_session=False, cached_rows=0,
                   reused_from=os.path.relpath(committed_path, HERE), replies_within_live_window=True,
                   request_identity_verified=True, request_identity_how=identity["how_established"])
    return obs, dict(llm_run, **_llm_usage(obs))


def _to_observations(rows, split, cfg, run):
    return G.to_observations(rows, split, run.label, cfg["llm"]["model"], cfg["dataset"]["seed"])


REQUEST_KEYS = ("endpoint", "model", "provider_order", "allow_fallbacks", "temperature", "max_tokens")


def _request_config(llm_cfg):
    return {k: llm_cfg[k] for k in REQUEST_KEYS}


def _assert_same_requests(identity, obs, llm_cfg):
    """Reuse is allowed only if today's requests would be identical to the executed ones."""
    now = {c: G.request_fingerprint(llm_cfg, c) for c in G.LLM_METHODS}
    assert now == identity["request_fingerprints"], (
        "the requested LLM configuration or prompts differ from the executed run; re-run live instead of reusing")
    assert _request_config(llm_cfg) == identity["executed_config"], "requested LLM configuration differs from the executed one"
    llm = obs[obs.llm_called == True]  # noqa: E712
    assert (llm.model == identity["executed_config"]["model"]).all(), "observations record a different model"
    assert llm.provider.isin(identity["executed_config"]["provider_order"]).all(), "a reply came from an unpinned provider"


def _assert_replies_from_live_run(obs, llm_run):
    llm = obs[obs.llm_called == True]  # noqa: E712
    t = pd.to_datetime(llm.request_utc, utc=True)
    assert t.notna().all() and llm.generation_id.notna().all(), "LLM replies without request metadata"
    assert llm.generation_id.is_unique, "duplicate generation ids: replies were reused across requests"
    lo, hi = pd.Timestamp(llm_run["started_utc"]), pd.Timestamp(llm_run["finished_utc"])
    assert ((t >= lo) & (t <= hi)).all(), "some LLM replies predate or postdate the recorded live run"


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
    # what each guard decided
    metrics: pd.DataFrame          # long format, every condition x run x metric, with per-command CIs
    # design-based inference on the primary run
    design: A.Design               # recipe bootstrap (v1.3, D19, D22): intervals, differences, escalation
    comparison: pd.DataFrame       # reported vs observed (Table II), descriptive
    claims: pd.DataFrame           # C1-C11: v1.3 verdicts, with the v1.2-rule, v1.1 and v1.0 outcomes alongside
    # diagnostics on this population
    mcnemar: pd.DataFrame          # per-command paired tests, as in the paper (Table VIII)
    funnel: pd.DataFrame           # Resolution funnel (App. A.F)
    oracle: pd.DataFrame           # upper bounds for any Resolution judge
    by_source: pd.DataFrame
    redcode: pd.DataFrame
    label_sensitivity: pd.DataFrame  # C7/C9 under corpus-level vs audited labels (D17)
    # split construction (static CARE on re-drawn splits; full mode only, else None)
    seeds: pd.DataFrame | None     # seed sweep
    variants: pd.DataFrame | None  # construction variants V0-V3
    coverage: pd.DataFrame | None  # simulated coverage of the bootstrap intervals (D22)
    calibration: pd.DataFrame | None  # bootstrap spread vs spread over re-drawn splits (D19)
    # superseded, kept for the record
    design_v11: A.Design           # v1.1 cluster bootstrap (D15)


def analyse(obs, split, pools, sources, cfg, run):
    """Every analysis table (§6-§8), from the observations, the split and the corpora."""
    # 1. What each guard decided: point metrics per condition and run
    metrics = A.metrics_long(obs, split, cfg, split_name=run.split_name)

    # 2. Design-based uncertainty: re-run the split recipe on the sample (v1.3)
    weights = A.recipe_weights(split, cfg, order=D.corpus_order(split, pools))
    design = A.design_inference(obs, split, weights, "recipe", cfg)
    design_v11 = A.design_inference(obs, split, A.cluster_weights(split, cfg), "cluster", cfg)   # superseded

    # 3. Reported vs observed, and the paper's own per-command tests
    comparison = A.compare_with_paper(metrics, design.intervals, cfg)
    mcnemar = A.mcnemar_table(obs, split, cfg)

    # 4. Diagnostics on this population
    funnel = A.resolution_funnel(obs, split)
    oracle = A.oracle_bounds(obs, split)
    by_source = A.by_source(obs, split)
    redcode, redcode_items = A.redcode_scenarios(obs, split)
    label_sens = A.label_sensitivity(obs, split, load_label_audit())

    # 5. Split construction: static CARE on re-drawn splits (deterministic, full mode only)
    seeds = variants = coverage = calibration = None
    if run.full:
        care = SENS.StaticCARE()
        seeds = SENS.seed_sweep(pools, cfg, care)
        variants = SENS.construction_variants(split, redcode_items, pools,
                                              pools_unfiltered=load_pools(cfg, sources.roots, label_filter=False),
                                              pools_v3=load_pools(cfg, sources.roots_v3), cfg=cfg, care=care)
        coverage = SENS.bootstrap_coverage(pools, cfg, care)
        calibration = SENS.bootstrap_calibration(pd.concat([design.intervals, design_v11.intervals]), seeds)

    # 6. Claim verdicts: v1.3, with the superseded rule sets alongside
    claims = C.claims_table(
        v1_3=C.verdicts(design, label_sens, metrics, seeds, cfg),
        v1_2=C.verdicts_v1_2(design, label_sens, metrics, seeds, cfg),
        v1_1=C.verdicts_v1_1(design_v11, label_sens, metrics, seeds, cfg),
        v1_0=C.verdicts_v1_0(comparison, mcnemar, funnel, metrics, seeds, cfg))

    return Results(metrics=metrics, design=design, comparison=comparison, claims=claims, mcnemar=mcnemar,
                   funnel=funnel, oracle=oracle, by_source=by_source, redcode=redcode, label_sensitivity=label_sens,
                   seeds=seeds, variants=variants, coverage=coverage, calibration=calibration, design_v11=design_v11)


def load_label_audit():
    """command_id -> audited label, from data/label_audit.yaml (sensitivity analysis only, D17)."""
    import yaml
    with open(os.path.join(HERE, "data", "label_audit.yaml"), encoding="utf-8") as f:
        return {i["command_id"]: i["audited_label"] for i in yaml.safe_load(f)["items"]}


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
             save(pd.concat([r.design.intervals, r.design_v11.intervals], ignore_index=True), "design_intervals.parquet"),
             save(pd.concat([r.design.differences, r.design_v11.differences], ignore_index=True),
                  "design_differences.parquet"),
             save(r.label_sensitivity, "label_sensitivity.parquet"),
             save(r.mcnemar, "mcnemar.parquet"),
             save(r.funnel, "resolution_funnel.parquet"),
             save(r.oracle, "oracle_bounds.parquet"),
             save(r.by_source, "by_source.parquet"),
             save(r.redcode, "redcode_scenarios.parquet")]
    if r.seeds is not None:
        paths += [save(r.seeds, "sensitivity_seeds.parquet"), save(r.variants, "sensitivity_variants.parquet"),
                  save(r.calibration, "bootstrap_calibration.parquet"), save(r.coverage, "bootstrap_coverage.parquet")]
    with open(os.path.join(run.out, "report.md"), "w") as f:
        f.write(report_md)
    return paths


def write_provenance(run, cfg, integrity, tests, sources, manifest, llm_run, smoke, stage_seconds, paths):
    """Write `provenance.json` (everything needed to audit the run) and `validation.json` (pass/fail checks)."""
    rel = lambda p: os.path.relpath(p, HERE)  # noqa: E731
    id_path = os.path.join(run.out if llm_run["executed_in_this_session"] else os.path.join(HERE, "results"),
                           "llm_request_identity.json")
    identity = json.load(open(id_path))
    sha = lambda p: SRC.sha256_file(os.path.join(HERE, p))  # noqa: E731
    provenance = dict(
        generated_utc=_utc_now(), mode=run.mode, run_label=run.label,
        protocol_version=cfg["protocol_version"], protocol_sha256=sha("PROTOCOL.md"),
        config_sha256=sha("config.yaml"), repo_head=integrity["repo_head"],
        method_under_test=dict(cfg["method_under_test"], care_identical_to_release=True),
        paper=cfg["paper"], sources=sources.records,
        split=dict(manifest, sha256=sha("data/main_split.parquet")),
        llm=dict(llm_run, requested_config=cfg["llm"], executed_request_identity=identity),
        environment=integrity["environment"], unit_tests=tests, smoke_check=smoke,
        stage_seconds={k: round(v, 2) for k, v in stage_seconds.items()},
        outputs={rel(p): SRC.sha256_file(p) for p in paths},
    )
    validation = dict(mode=run.mode, unit_tests=tests, smoke_check=smoke, static_deterministic=True,
                      split_identical_to_committed=True,
                      sources_verified=all(s["verified"] for s in sources.records.values()),
                      llm_executed_in_this_session=llm_run["executed_in_this_session"],
                      llm_cached_rows=llm_run.get("cached_rows"),
                      llm_replies_within_live_window=llm_run.get("replies_within_live_window"),
                      llm_request_identity_verified=llm_run.get("request_identity_verified"),
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
