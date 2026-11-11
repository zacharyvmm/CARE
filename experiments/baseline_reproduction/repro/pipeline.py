"""The reproduction pipeline, one function per notebook stage.

`baseline_reproduction.ipynb` calls these in order; reading this file top to bottom is reading
the experiment:

    run                  = settings(cfg)                         # mode, LLM live or reused, output dir
    integrity            = check_environment(cfg)                # care/ unmodified, versions recorded
    tests                = run_unit_tests()
    sources              = fetch_sources(cfg)                    # corpora at pinned commits
    population, manifest = load_population(cfg, sources, run)    # every command of every corpus
    checks               = preflight(population, cfg, run)
    static_rows          = run_static_guards(population)         # NoGuard, CARE (w/o Resolution)
    obs, llm_run         = query_llm_guards(...)                 # CARE + 3 LLM judges, live, or:
                           reuse_llm_observations(...)           #   the committed run, verified
    splits               = draw_paper_sized_splits(population, cfg, run)
    results              = analyse(obs, population, splits, sources, manifest, cfg, run)
    paths                = export(results, report_md, run)
    write_provenance(...)

Every stage takes the data it needs as arguments and returns what it produced.  The work itself
lives in

    dataset    corpora -> population; the paper's split recipe
    guards     CARE and the LLM-judge baselines, the pinned LLM client and its cache
    analysis   observations -> metrics on the full corpora and on paper-sized splits, diagnostics
    claims     verdicts C1-C11
    stats      the formulas
    report     figures, views, report.md
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version

import numpy as np
import pandas as pd
import yaml

from . import HERE, REPO
from . import analysis as A
from . import claims as C
from . import dataset as D
from . import guards as G
from . import sources as SRC

KEY_PACKAGES = ["pandas", "pyarrow", "numpy", "scipy", "statsmodels", "openai", "bashlex", "PyYAML", "matplotlib"]
SKIP_IN_INVENTORY = ("data/sources", "results/cache", "results/smoke", "archive", "__pycache__",
                     ".ipynb_checkpoints", ".pytest_cache")
V1_OBSERVATIONS = os.path.join(HERE, "archive/v1/results/observations.parquet")


# ---------------------------------------------------------------- run settings
@dataclass(frozen=True)
class Run:
    """How this execution runs.  Built from environment variables by `settings`."""
    mode: str           # "full" (the protocol) or "smoke" (a few commands, 1 run)
    run_llm: bool       # query the LLM live; otherwise reuse the committed observations
    out: str            # output directory
    label: str          # run_id prefix in observations
    runs: int           # runs per LLM condition
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
              label="confirmatory-v2" if full else "smoke-v2",
              runs=cfg["llm"]["runs"] if full else 1,
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
    return dict(environment=env, repo_head=_sh("git", "rev-parse", "HEAD"),
                uncommitted_changes=bool(_sh("git", "status", "--porcelain", "--", os.path.relpath(HERE, REPO))))


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
    records: dict        # name -> url, commit, license, fingerprint, verified
    roots: dict          # corpus directories
    older_art_root: str  # the 2026-03-24 ART snapshot (construction variant V3)


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
    return Sources(records, roots, f"{root}/atomic-red-team-2026-03-24")


def load_population(cfg, sources, run):
    """Every command of every corpus, rebuilt from the sources and required to equal `data/population.parquet`."""
    p = cfg["population"]
    population, manifest = D.load_population(sources.roots, os.path.join(HERE, p["real_world_file"]))
    committed = pd.read_parquet(os.path.join(HERE, p["file"]))
    assert committed.equals(population[committed.columns]), f"rebuilt population differs from {p['file']}"
    print(f"✓ population rebuilt: {len(population):,} commands, identical to {p['file']}")
    if not run.full:
        k = cfg["smoke"]["commands_per_group"]
        population = population.groupby(["source", "in_primary"], sort=False).head(k).reset_index(drop=True)
        print(f"  SMOKE: continuing with {len(population)} commands")
    return population, manifest


def preflight(population, cfg, run):
    """Exercise every execution path once before the real run (results are thrown away)."""
    sample = population.groupby("source").head(6)
    static_rows = G.run_static(sample)
    assert len(static_rows) == 2 * len(sample)
    checks = dict(static_rows=len(static_rows))
    if run.run_llm:
        with tempfile.TemporaryDirectory() as scratch:   # no cache: every preflight call is a real call
            rows = G.run_llm(sample.head(1), cfg["llm"], run.api_key, 1,
                             os.path.join(scratch, "preflight.jsonl"), progress=lambda *_: None)
        checks["llm_preflight"] = {r["condition"]: (r["decision"], r.get("error")) for r in rows}
        assert all(r.get("error") is None for r in rows), checks
    print("✓ preflight:", checks)
    return checks


# ---------------------------------------------------------------- stage 3: run the guards
def run_static_guards(population):
    """NoGuard and CARE (w/o Resolution), run twice to check that they are deterministic."""
    rows = G.run_static(population)
    key = lambda rs: [(r["condition"], r["command_id"], r["decision"], r.get("score")) for r in rs]  # noqa: E731
    assert key(rows) == key(G.run_static(population)), "static guards are not deterministic"
    print(f"✓ static guards: {len(rows):,} decisions, identical across two passes")
    return rows


def query_llm_guards(population, static_rows, cfg, run):
    """CARE (with Resolution) and the three LLM-judge baselines, `run.runs` times each, queried live.

    Writes `observations.parquet` and `llm_request_identity.json` (what was requested, so that a
    later reuse can verify it).  A run that is interrupted resumes from its call cache; replies
    taken from the cache are counted (`cached_rows`) and keep their original request time.
    """
    session_start = _utc_now()
    llm_rows = G.run_llm(population, cfg["llm"], run.api_key, run.runs,
                         os.path.join(HERE, "results/cache", f"{run.label}.jsonl"))
    obs = G.to_observations(static_rows + llm_rows, population, run.label)
    obs.to_parquet(os.path.join(run.out, "observations.parquet"), index=False, compression="zstd")
    requested = pd.to_datetime(obs.request_utc.dropna(), utc=True)
    window = dict(started_utc=min(pd.Timestamp(session_start), requested.min()).isoformat(), finished_utc=_utc_now())
    identity = dict(run_label=run.label, executed_at_commit=_sh("git", "rev-parse", "HEAD"),
                    executed_config=_request_config(cfg["llm"]), **window,
                    request_fingerprints={c: G.request_fingerprint(cfg["llm"], c) for c in G.LLM_METHODS})
    json.dump(identity, open(os.path.join(run.out, "llm_request_identity.json"), "w"), indent=2)
    cached = sum(bool(r.get("from_cache")) and r["llm_called"] for r in llm_rows)
    llm_run = dict(executed=True, **window, cached_rows=cached,
                   executed_in_this_session=cached < sum(r["llm_called"] for r in llm_rows))
    return obs, dict(llm_run, **_llm_usage(obs))


def reuse_llm_observations(population, static_rows, cfg, run):
    """The committed observations of the live confirmatory run, verified rather than re-queried.

    Checks that (a) the static decisions just re-executed equal the committed ones, (b) today's
    requests (model, serving, decoding, prompts) are identical to the executed ones, and (c) every
    committed LLM reply was requested inside the live run's time window, with a unique generation
    id and the executed request fingerprint.  Smoke mode keeps its few commands and run 1.
    """
    committed_path = os.path.join(HERE, "results", "observations.parquet")
    assert os.path.exists(committed_path), "no API key and no committed observations: LLM conditions cannot be evaluated"
    obs = pd.read_parquet(committed_path)
    assert obs.run_id.str.startswith("confirmatory-v2").all(), "committed observations are not from this protocol's run"
    if not run.full:
        obs = obs[obs.command_id.isin(population.command_id) & (obs.run == 1)].reset_index(drop=True)
        obs.to_parquet(os.path.join(run.out, "observations.parquet"), index=False, compression="zstd")
    identity = json.load(open(os.path.join(HERE, "results", "llm_request_identity.json")))
    window = dict(started_utc=identity["started_utc"], finished_utc=identity["finished_utc"])

    _assert_static_matches(G.to_observations(static_rows, population, run.label), obs)
    _assert_same_requests(identity, obs, cfg["llm"])
    _assert_replies_from_live_run(obs, window)

    print("✓ static decisions identical to the committed observations; LLM observations reused (not re-queried)")
    print("✓ requested model, serving, decoding and prompts are identical to those of the executed run")
    print(f"✓ all committed LLM replies were requested during the live run "
          f"({window['started_utc'][:19]} – {window['finished_utc'][:19]} UTC), with unique generation ids")
    llm_run = dict(executed=True, **window, executed_in_this_session=False, cached_rows=0,
                   reused_from=os.path.relpath(committed_path, HERE), replies_within_live_window=True,
                   request_identity_verified=True)
    return obs, dict(llm_run, **_llm_usage(obs))


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
    assert (llm.request_fingerprint == llm.condition.map(identity["request_fingerprints"])).all(), (
        "a reply was produced by a different request than the one recorded for its condition")


def _assert_replies_from_live_run(obs, window):
    llm = obs[obs.llm_called == True]  # noqa: E712
    t = pd.to_datetime(llm.request_utc, utc=True)
    assert t.notna().all() and llm.generation_id.notna().all(), "LLM replies without request metadata"
    assert llm.generation_id.is_unique, "duplicate generation ids: replies were reused across requests"
    lo, hi = pd.Timestamp(window["started_utc"]), pd.Timestamp(window["finished_utc"])
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
    providers = ", ".join(f"{p} ({n:,})" for p, n in llm_run["providers"].items())
    return (f"**LLM calls:** {llm_run['calls']:,} ({when}); **errors:** {llm_run['errors']}; "
            f"**retried:** {llm_run['retried_calls']}; **served by:** {providers}; "
            f"**tokens:** {llm_run['prompt_tokens']:,} prompt + {llm_run['completion_tokens']:,} completion; "
            f"**cost:** US${llm_run['cost_usd']:.2f}")


def _utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---------------------------------------------------------------- stage 4: paper-sized splits
@dataclass
class Splits:
    """Splits with the paper's composition, re-drawn from the population (one per seed)."""
    seeds: range
    composition: dict
    level: float       # central share of the splits reported as "the range"
    draws: dict        # source -> (n_splits, quota) row positions into the population

    @property
    def matrix(self):
        return D.as_matrix(self.draws)

    def __len__(self):
        return len(self.seeds)


def draw_paper_sized_splits(population, cfg, run):
    """Re-draw the paper's 549-command composition from the population, once per seed."""
    ps = cfg["paper_sized_splits"]
    composition = ps["composition"] if run.full else cfg["smoke"]["composition"]
    first, last = ps["seeds"] if run.full else cfg["smoke"]["seeds"]
    seeds = range(first, last + 1)
    draws = D.SplitRecipe(population, composition, ps["nl2bash_head_cap"]).draw(seeds)
    splits = Splits(seeds, composition, ps["range_level"], draws)
    y = population.label_dangerous.to_numpy()[splits.matrix]
    print(f"✓ {len(splits):,} splits of {splits.matrix.shape[1]} commands "
          f"({int(y[0].sum())} DANGEROUS / {int((~y[0]).sum())} SAFE each)")
    return splits


# ---------------------------------------------------------------- stage 5: analysis
@dataclass
class Results:
    metrics: pd.DataFrame            # long format: every condition x run x metric, on the full corpora and on the splits
    comparison: pd.DataFrame         # Table II, reported vs observed
    differences: pd.DataFrame        # CARE vs each comparator on the paper-sized splits (Table VIII, C6, C10)
    claims: pd.DataFrame             # verdicts C1-C11
    # diagnostics
    funnel: pd.DataFrame             # Resolution funnel (App. A.F)
    oracle: pd.DataFrame             # upper bounds for any Resolution judge
    label_sensitivity: pd.DataFrame  # C7/C9 under corpus-level vs audited labels
    redcode: pd.DataFrame            # denied commands per RedCode scenario
    stability: pd.DataFrame          # run-to-run variation of the LLM conditions
    variants: pd.DataFrame | None    # construction variants V0-V3 (full mode only)
    v1: pd.DataFrame | None          # consistency with the archived v1 run (full mode only)
    # for the figures
    split_f1: dict                   # condition -> F1 of every paper-sized split
    n_splits: int


def analyse(obs, population, splits, sources, manifest, cfg, run):
    """Every analysis table, from the observations, the population and the paper-sized splits."""
    o = A.Observed(obs, population)
    matrix, level = splits.matrix, splits.level

    # 1. What each guard decided: on the full corpora, and on the paper-sized splits
    metrics = pd.concat([A.corpus_metrics(o), A.split_metrics(o, matrix, level)], ignore_index=True)

    # 2. Reported vs observed, and CARE against each comparator
    comparison = A.compare_with_paper(metrics, cfg)
    differences = A.paired_differences(o, matrix, cfg)

    # 3. Resolution: what the judge sees, what any judge could achieve, and how much the labels matter
    funnel = A.resolution_funnel(o, matrix, cfg)
    oracle = A.oracle_bounds(o, matrix, level)
    label_sens = A.label_sensitivity(o, load_label_audit(cfg))

    # 4. Diagnostics
    redcode = A.redcode_scenarios(o)
    stability = A.run_stability(o, metrics)
    variants = v1 = None
    if run.full:
        variants = A.construction_variants(o, cfg, splits.seeds, splits.draws, older_art_snapshot(sources, manifest))
        v1 = A.consistency_with_v1(o, pd.read_parquet(V1_OBSERVATIONS))

    # 5. Claim verdicts
    claims = C.verdicts(comparison, differences, label_sens, metrics, cfg)

    return Results(metrics=metrics, comparison=comparison, differences=differences, claims=claims, funnel=funnel,
                   oracle=oracle, label_sensitivity=label_sens, redcode=redcode, stability=stability,
                   variants=variants, v1=v1, split_f1=A.f1_of_every_split(o, matrix), n_splits=len(splits))


def load_label_audit(cfg):
    """command_id -> audited label, from data/label_audit.yaml (sensitivity analysis only)."""
    with open(os.path.join(HERE, cfg["analysis"]["label_audit"]), encoding="utf-8") as f:
        return {i["command_id"]: i["audited_label"] for i in yaml.safe_load(f)["items"]}


def older_art_snapshot(sources, manifest):
    """The 2026-03-24 ART snapshot with static CARE's decision per command (construction variant V3)."""
    art = pd.DataFrame(D.load_art(sources.older_art_root))
    art = art[~art.command.isin(manifest["cross_source_conflicts_dropped"])].reset_index(drop=True)
    return art.assign(deny=G.static_deny(art.command))


# ---------------------------------------------------------------- stage 6: export
TABLES = {   # file name -> attribute of Results
    "metrics": "metrics", "comparison": "comparison", "paired_differences": "differences", "claims": "claims",
    "resolution_funnel": "funnel", "oracle_bounds": "oracle", "label_sensitivity": "label_sensitivity",
    "redcode_scenarios": "redcode", "run_stability": "stability", "construction_variants": "variants",
    "consistency_with_v1": "v1",
}


def export(results, report_md, run):
    """Write every analysis table as Parquet plus `report.md`; return the Parquet paths."""
    paths = [os.path.join(run.out, "observations.parquet")]
    for name, attribute in TABLES.items():
        table = getattr(results, attribute)
        if table is not None:
            paths.append(os.path.join(run.out, f"{name}.parquet"))
            table.to_parquet(paths[-1], index=False)
    with open(os.path.join(run.out, "report.md"), "w") as f:
        f.write(report_md)
    return paths


def write_provenance(run, cfg, integrity, tests, sources, manifest, splits, llm_run, checks, stage_seconds, paths):
    """Write `provenance.json` (everything needed to audit the run) and `validation.json` (pass/fail checks)."""
    rel = lambda p: os.path.relpath(p, HERE)  # noqa: E731
    sha = lambda p: SRC.sha256_file(os.path.join(HERE, p))  # noqa: E731
    id_dir = run.out if llm_run["executed_in_this_session"] else os.path.join(HERE, "results")
    identity = json.load(open(os.path.join(id_dir, "llm_request_identity.json")))
    provenance = dict(
        generated_utc=_utc_now(), mode=run.mode, run_label=run.label,
        protocol_version=cfg["protocol_version"], protocol_sha256=sha("PROTOCOL.md"),
        config_sha256=sha("config.yaml"), repo_head=integrity["repo_head"],
        uncommitted_changes=integrity["uncommitted_changes"],
        method_under_test=dict(cfg["method_under_test"], care_identical_to_release=True),
        paper=cfg["paper"], sources=sources.records,
        population=dict(manifest, sha256=sha(cfg["population"]["file"])),
        paper_sized_splits=dict(n=len(splits), seeds=[splits.seeds[0], splits.seeds[-1]], composition=splits.composition,
                                range_level=splits.level, sha256=hashlib.sha256(splits.matrix.tobytes()).hexdigest()),
        llm=dict(llm_run, requested_config=cfg["llm"], executed_request_identity=identity),
        environment=integrity["environment"], unit_tests=tests, preflight=checks,
        stage_seconds={k: round(v, 2) for k, v in stage_seconds.items()},
        outputs={rel(p): SRC.sha256_file(p) for p in paths},
    )
    validation = dict(mode=run.mode, unit_tests=tests, preflight=checks, static_deterministic=True,
                      population_identical_to_committed=True,
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
    """Every file of the artifact with its size and SHA-256 prefix (the archive and the caches are left out)."""
    rows = []
    for root, _, files in os.walk(HERE):
        if any(s in root for s in SKIP_IN_INVENTORY):
            continue
        for f in files:
            p = os.path.join(root, f)
            rows.append(dict(path=os.path.relpath(p, HERE), bytes=os.path.getsize(p), sha256=SRC.sha256_file(p)[:16]))
    return pd.DataFrame(rows).sort_values("path").reset_index(drop=True)
