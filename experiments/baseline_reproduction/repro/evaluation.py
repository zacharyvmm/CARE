"""Run the guards on the population and record one observation per guard, run and command.

    static_decisions = evaluation.run_static_guards(population)
    observations     = evaluation.query_llm_guards(population, static_decisions, configuration)
                       # or, without an API key:
                       evaluation.reuse_committed_observations(population, static_decisions, configuration)

Reuse is allowed only when the committed replies provably come from the same requests: the
static decisions are re-executed and compared, the request fingerprints must match, and every
reply must carry a unique generation id from inside the live run's time window (D18, D20).
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile

import numpy as np
import pandas as pd

from . import corpora, guards
from .configuration import EXPERIMENT

COMMITTED_RESULTS = os.path.join(EXPERIMENT, "results")
REQUEST_SETTINGS = ("endpoint", "model", "provider_order", "allow_fallbacks", "temperature", "max_tokens")

OBSERVATION_COLUMNS = [
    # which decision this is
    "run_id", "run", "condition", "command_id", "source", "label", "label_dangerous", "in_primary",
    # the decision
    "decision", "prediction_dangerous", "latency_ms",
    # the LLM call behind it, if any
    "llm_called", "model", "provider", "generation_id", "request_utc", "api_latency_ms", "attempts",
    "prompt_tokens", "completion_tokens", "cost_usd", "finish_reason", "raw_response", "error",
    "request_fingerprint", "from_cache",
    # CARE's static trace
    "provisional", "score", "triggered", "fired_rules", "skip_predicate",
]


# ---------------------------------------------------------------- static guards
def run_static_guards(population):
    """NoGuard and CARE (w/o Resolution), run twice to check that they are deterministic."""
    decisions = guards.run_static_guards(population)
    assert _what_was_decided(decisions) == _what_was_decided(guards.run_static_guards(population)), (
        "the static guards are not deterministic")
    print(f"✓ static guards: {len(decisions):,} decisions, identical across two passes")
    return decisions


def run_static_care_on_older_art(directories):
    """The 2026-03-24 Atomic Red Team snapshot with CARE (w/o Resolution)'s decision per command (variant V3)."""
    older_art = corpora.read_older_art(directories)
    return older_art.assign(deny=guards.static_care_denies(older_art.command))


def _what_was_decided(decisions):
    return [(d["condition"], d["command_id"], d["decision"], d.get("score")) for d in decisions]


# ---------------------------------------------------------------- LLM guards, live
def query_llm_guards(population, static_decisions, configuration):
    """CARE (with Resolution) and the three LLM judges, queried live; returns every observation.

    Writes `observations.parquet` and `llm_request_identity.json` (what was requested, so that a
    later reuse can verify it).  An interrupted run resumes from its reply cache.
    """
    llm, output = configuration["llm"], configuration.output_directory
    session_start = _utc_now()
    _require_a_working_llm(population, configuration)
    cache_path = os.path.join(COMMITTED_RESULTS, "cache", f"{configuration.run_label}.jsonl")
    llm_decisions = guards.run_llm_guards(population, llm, configuration.api_key, configuration.llm_runs, cache_path)

    observations = to_observations(static_decisions + llm_decisions, population, configuration.run_label)
    observations.to_parquet(os.path.join(output, "observations.parquet"), index=False, compression="zstd")
    first_request = pd.to_datetime(observations.request_utc.dropna(), utc=True).min()
    identity = dict(
        run_label=configuration.run_label,
        executed_config={name: llm[name] for name in REQUEST_SETTINGS},
        started_utc=min(pd.Timestamp(session_start), first_request).isoformat(),
        finished_utc=_utc_now(),
        request_fingerprints={guard: guards.request_fingerprint(llm, guard) for guard in guards.LLM_GUARDS})
    with open(os.path.join(output, "llm_request_identity.json"), "w") as file:
        json.dump(identity, file, indent=2)
    print("✓ " + describe_llm_calls(observations, "queried live in this session"))
    return observations


def _require_a_working_llm(population, configuration):
    """One command through every LLM guard, outside the cache: stop now if a call fails."""
    with tempfile.TemporaryDirectory() as scratch:
        decisions = guards.run_llm_guards(population.head(1), configuration["llm"], configuration.api_key, 1,
                                          os.path.join(scratch, "probe.jsonl"), progress=lambda *_: None)
    failed = {d["condition"]: d["error"] for d in decisions if d.get("error") is not None}
    assert not failed, f"the LLM is not reachable: {failed}"


# ---------------------------------------------------------------- LLM guards, reused
def reuse_committed_observations(population, static_decisions, configuration):
    """The committed observations of the live confirmatory run, verified rather than re-queried."""
    observations = pd.read_parquet(os.path.join(COMMITTED_RESULTS, "observations.parquet"))
    with open(os.path.join(COMMITTED_RESULTS, "llm_request_identity.json")) as file:
        identity = json.load(file)
    assert observations.run_id.str.startswith("confirmatory-v2").all(), "not this protocol's run"
    if not configuration.full:   # smoke mode keeps its few commands and run 1
        in_smoke = observations.command_id.isin(population.command_id) & (observations.run == 1)
        observations = observations[in_smoke].reset_index(drop=True)
        observations.to_parquet(os.path.join(configuration.output_directory, "observations.parquet"),
                                index=False, compression="zstd")

    fresh_static = to_observations(static_decisions, population, configuration.run_label)
    require_same_static_decisions(fresh_static, observations)
    require_same_requests(identity, observations, configuration["llm"])
    require_replies_from_the_live_run(observations, identity)

    print("✓ static decisions identical to the committed observations")
    print("✓ requested model, serving, decoding and prompts identical to those of the live run")
    print("✓ " + describe_llm_calls(observations, f"reused from the live run of {identity['started_utc'][:19]} UTC"))
    return observations


def require_same_static_decisions(fresh, committed):
    fresh = fresh.set_index(["condition", "command_id"])
    static = committed[committed.condition.isin(guards.STATIC_GUARDS)]
    static = static.set_index(["condition", "command_id"]).loc[fresh.index]
    same_scores = np.allclose(fresh.score.astype(float).fillna(-1), static.score.astype(float).fillna(-1))
    assert fresh.decision.equals(static.decision) and same_scores, (
        "the re-executed static decisions differ from the committed observations")


def require_same_requests(identity, observations, llm):
    """Reuse is allowed only if today's requests would be identical to the executed ones."""
    today = {guard: guards.request_fingerprint(llm, guard) for guard in guards.LLM_GUARDS}
    assert today == identity["request_fingerprints"], (
        "the requested LLM configuration or prompts differ from the executed run; re-run live instead")
    executed = identity["executed_config"]
    requested = {name: llm[name] for name in REQUEST_SETTINGS}
    assert requested == executed, "the LLM configuration differs from the executed one"
    replies = llm_replies(observations)
    assert (replies.model == executed["model"]).all(), "the observations record a different model"
    assert replies.provider.isin(executed["provider_order"]).all(), "a reply came from an unpinned provider"
    assert (replies.request_fingerprint == replies.condition.map(identity["request_fingerprints"])).all(), (
        "a reply was produced by a different request than the one recorded for its guard")


def require_replies_from_the_live_run(observations, identity):
    replies = llm_replies(observations)
    requested = pd.to_datetime(replies.request_utc, utc=True)
    assert requested.notna().all() and replies.generation_id.notna().all(), "LLM replies without request metadata"
    assert replies.generation_id.is_unique, "duplicate generation ids: replies were reused across requests"
    started, finished = pd.Timestamp(identity["started_utc"]), pd.Timestamp(identity["finished_utc"])
    assert ((requested >= started) & (requested <= finished)).all(), (
        "some LLM replies predate or postdate the recorded live run")


# ---------------------------------------------------------------- the observations table
def to_observations(decisions, population, run_label):
    """One row per (guard, run, command): the decision, its LLM call and CARE's trace."""
    labels = population[["command_id", "source", "label", "label_dangerous", "in_primary"]]
    observations = pd.DataFrame(decisions).merge(labels, on="command_id")
    observations.insert(0, "run_id", run_label + "-r" + observations.run.astype(str))
    observations["prediction_dangerous"] = observations.decision.eq("DENY")
    for column in OBSERVATION_COLUMNS:
        if column not in observations:
            observations[column] = None
    return observations[OBSERVATION_COLUMNS].sort_values(["condition", "run", "command_id"]).reset_index(drop=True)


def llm_replies(observations):
    """The observations that are backed by an LLM call."""
    return observations[observations.llm_called.astype(bool)]


def llm_usage(observations):
    """Calls, errors, providers, tokens and cost of the LLM calls behind the observations."""
    replies = llm_replies(observations)
    taken_from_cache = replies.from_cache.fillna(False).astype(bool) if "from_cache" in replies else pd.Series(dtype=bool)
    return dict(calls=int(len(replies)), errors=int(replies.error.notna().sum()),
                providers=replies.provider.value_counts().to_dict(),
                prompt_tokens=int(replies.prompt_tokens.fillna(0).sum()),
                completion_tokens=int(replies.completion_tokens.fillna(0).sum()),
                cost_usd=float(replies.cost_usd.fillna(0).sum()),
                retried_calls=int((replies.attempts.fillna(1) > 1).sum()),
                replies_taken_from_cache=int(taken_from_cache.sum()))


def describe_llm_calls(observations, how):
    usage = llm_usage(observations)
    providers = ", ".join(usage["providers"])
    return (f"{usage['calls']:,} LLM calls ({how}): {usage['errors']} errors, {usage['retried_calls']} retried, "
            f"served by {providers}, US${usage['cost_usd']:.2f}")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
