"""The configuration of one execution: config.yaml, plus how this run is carried out.

    configuration = Configuration.from_environment()
    configuration["llm"]["model"]        # any value of config.yaml
    configuration.full                   # the protocol, or a smoke test?
    configuration.query_llm_live         # query the LLM now, or reuse the committed observations?

Environment variables:

    REPRO_MODE           "full" (default) or "smoke" (a few commands, one run; never a reproduction)
    OPENROUTER_API_KEY   when set, the LLM guards are queried live
    REPRO_REUSE_LLM=1    reuse the committed observations even though a key is set
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

EXPERIMENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # experiments/baseline_reproduction
REPOSITORY = os.path.dirname(os.path.dirname(EXPERIMENT))


@dataclass(frozen=True)
class Configuration:
    values: dict             # config.yaml
    mode: str                # "full" or "smoke"
    query_llm_live: bool
    output_directory: str
    run_label: str           # prefix of `run_id` in the observations
    llm_runs: int            # runs per LLM guard
    api_key: str | None = field(default=None, repr=False)   # never printed or written

    @classmethod
    def from_environment(cls, environment=os.environ, config_file=None):
        with open(config_file or os.path.join(EXPERIMENT, "config.yaml"), encoding="utf-8") as file:
            values = yaml.safe_load(file)
        mode = environment.get("REPRO_MODE", "full").lower()
        assert mode in ("full", "smoke"), mode
        full = mode == "full"
        api_key = environment.get("OPENROUTER_API_KEY")
        configuration = cls(
            values=values,
            mode=mode,
            query_llm_live=api_key is not None and environment.get("REPRO_REUSE_LLM", "0") != "1",
            output_directory=os.path.join(EXPERIMENT, "results" if full else "results/smoke"),
            run_label="confirmatory-v2" if full else "smoke-v2",
            llm_runs=values["llm"]["runs"] if full else 1,
            api_key=api_key)
        os.makedirs(configuration.output_directory, exist_ok=True)
        return configuration

    def __getitem__(self, section):
        return self.values[section]

    @property
    def full(self):
        return self.mode == "full"

    def __str__(self):
        mode = "FULL protocol" if self.full else "SMOKE MODE — NOT A REPRODUCTION"
        llm = ("queried live in this session" if self.query_llm_live
               else "not queried: the committed observations are reused")
        return f"Mode:    {mode}\nLLM:     {llm}\nOutputs: {os.path.relpath(self.output_directory, EXPERIMENT)}/"

    def label_audit(self):
        """command_id -> audited label, from data/label_audit.yaml (sensitivity analysis only)."""
        with open(os.path.join(EXPERIMENT, self["analysis"]["label_audit"]), encoding="utf-8") as file:
            return {item["command_id"]: item["audited_label"] for item in yaml.safe_load(file)["items"]}
