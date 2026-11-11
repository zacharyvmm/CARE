"""The evaluated population: every unique command of the corpora the paper draws from.

    source                class      what is loaded (decision IDs refer to DECISIONS.md)
    ART (Atomic Red Team) DANGEROUS  every Linux sh/bash atomic test; family = technique YAML
    RedCode-Exec (bash)   DANGEROUS  every bash script; family = risk scenario (D3)
    NL2Bash               SAFE       every command; family = lexical template (D11).  Commands that
                                     perform an operation the paper calls unconditionally dangerous
                                     are evaluated but not counted as SAFE (D5): `in_primary` is False
    Real-world            SAFE       the 30 developer commands in data/manual/ (D4)

    population = corpora.load_population(directories, configuration)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from collections import Counter

import numpy as np
import pandas as pd
import yaml

from .configuration import EXPERIMENT

SOURCES = ("ART", "RedCode-Exec", "NL2Bash", "Real-world")
FULL_CORPORA = "full corpora"                       # every command that counts toward metrics
SET_ASIDE = "NL2Bash (not counted as SAFE, D5)"     # evaluated, but in no metric
LABEL = {"ART": "DANGEROUS", "RedCode-Exec": "DANGEROUS", "NL2Bash": "SAFE", "Real-world": "SAFE"}

# D5 -- NL2Bash label hygiene: operations the paper itself calls "unconditionally
# dangerous" (Table I, adversarial-benign row), plus disk destruction and fork bombs.
UNSAFE_NL2BASH = re.compile("|".join(f"(?:{pattern})" for pattern in [
    r"(^|[\s;|&(`])(sudo|su|doas)(\s|$)",
    r"\bshred\b",
    r"\b(kill|killall|pkill)\b[^|;&]*\s-(9|KILL|SIGKILL)\b",
    r"\bchown\b[^|;&]*\broot\b",
    r"\bchmod\b[^|;&]*\s([ugoa]*\+[rwxt]*s|[2467][0-7]{3})\b",
    r"(>|\btee\b|\bcp\b|\bmv\b|\bsed\s+-i|\brm\b|\bchmod\b|\bchown\b|\bln\b)[^|;&]*\s/etc/",
    r"\bmkfs(\.\w+)?\b|\bfdisk\b|\bdd\b[^|;&]*\bof=/dev/",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(-\S+\s+)*/(\s|\*|$)",
    r":\(\)\s*\{",
]))

# RedCode-Exec bash scenarios whose scripts contain a software weakness rather than a harmful
# operation.  Our own reading of each scenario's task text; used in diagnostics only (D9).
REDCODE_WEAKNESS_SCENARIOS = {12, 15, 16, 20, 22, 23, 25}


# ---------------------------------------------------------------- the population
def load_population(directories, configuration):
    """Every command of every corpus, rebuilt from the sources and checked against the committed file.

    In smoke mode only a few evenly spaced commands per corpus are kept.
    """
    committed_file = configuration["population"]["file"]
    real_world_file = os.path.join(EXPERIMENT, configuration["population"]["real_world_file"])
    population = read_population(directories, real_world_file)
    committed = pd.read_parquet(os.path.join(EXPERIMENT, committed_file))
    assert committed.equals(population[committed.columns]), f"the rebuilt population differs from {committed_file}"
    print(f"✓ population rebuilt: {len(population):,} commands, identical to {committed_file}")
    if not configuration.full:
        population = _a_few_commands_per_corpus(population, configuration["smoke"]["commands_per_group"])
        print(f"  SMOKE: continuing with {len(population)} commands")
    return population


def read_population(directories, real_world_file):
    """Every unique command of every corpus, in corpus order.

    A command that occurs in two corpora has conflicting labels and is dropped from both (D10).
    """
    records = (read_art(directories["art"]) + read_redcode(directories["redcode"])
               + read_nl2bash(directories["nl2bash"]) + read_real_world(real_world_file))
    occurrences = Counter(record["command"] for record in records)
    population = pd.DataFrame([record for record in records if occurrences[record["command"]] == 1])
    validate(population)
    return population


def validate(population):
    """Integrity checks; raises AssertionError with a message on failure."""
    assert population.command_id.is_unique, "duplicate command_id"
    assert not population.command.duplicated().any(), "duplicate command text"
    assert population.notna().all().all(), "missing values"
    assert set(population.source) <= set(SOURCES), "unknown source"
    assert (population.label == population.source.map(LABEL)).all(), "labels are corpus-level: one class per source"
    set_aside = population[~population.in_primary]
    assert set_aside.source.eq("NL2Bash").all(), "only NL2Bash commands can be set aside (D5)"
    counted_as_safe = population[population.in_primary & (population.source == "NL2Bash")]
    unsafe = counted_as_safe.command.map(is_unsafe_nl2bash)
    assert not unsafe.any(), "an unsafe NL2Bash command is counted as SAFE (D5)"
    return True


def composition(population):
    """Per source: class, commands, template families, distinct heads, multi-line commands."""
    set_aside = ~population.in_primary
    described = population.assign(
        source=np.where(set_aside, SET_ASIDE, population.source),
        label=np.where(set_aside, "—", population.label))
    table = described.groupby(["source", "label"], sort=False).agg(
        commands=("command_id", "size"),
        families=("family", "nunique"),
        heads=("head", "nunique"),
        multiline=("command", lambda commands: int(commands.str.contains("\n").sum())))
    return table.reset_index().rename(columns={"label": "class"})


def counts(population):
    """How many commands are evaluated and how many count toward metrics (for the provenance record)."""
    primary = population[population.in_primary]
    return dict(n_evaluated=len(population), n_primary=len(primary),
                n_dangerous=int(primary.label_dangerous.sum()), n_safe=int((~primary.label_dangerous).sum()),
                per_source={source: int((primary.source == source).sum()) for source in SOURCES},
                nl2bash_not_counted_as_safe=int((~population.in_primary).sum()))


def redcode_scenario(population):
    """RedCode scenario number per row (NaN for the other sources)."""
    is_redcode = population.source == "RedCode-Exec"
    return population.family.where(is_redcode).str[3:].astype(float)


def read_older_art(directories):
    """The 2026-03-24 Atomic Red Team snapshot (construction variant V3), without the commands
    that also occur in NL2Bash (conflicting labels, D10)."""
    older_art = pd.DataFrame(read_art(directories["older_art"]))
    also_in_nl2bash = older_art.command.isin(_nl2bash_commands(directories["nl2bash"]))
    return older_art[~also_in_nl2bash].reset_index(drop=True)


def _a_few_commands_per_corpus(population, how_many):
    """`how_many` evenly spaced commands of each source (and of the set-aside NL2Bash commands)."""
    kept = []
    for _, group in population.groupby(["source", "in_primary"], sort=False):
        positions = np.linspace(0, len(group) - 1, min(how_many, len(group))).astype(int)
        kept.append(group.iloc[positions])
    return pd.concat(kept).sort_index().reset_index(drop=True)


# ---------------------------------------------------------------- one record per command
def record(source, family, command, in_primary=True, **details):
    return dict(command_id=command_id(source, command), source=source, label=LABEL[source],
                label_dangerous=LABEL[source] == "DANGEROUS", in_primary=in_primary,
                family=family, head=head_of(command), command=command, meta=json.dumps(details))


def command_id(source, command):
    return source[:3].lower() + "-" + hashlib.sha1(f"{source}\x00{command}".encode()).hexdigest()[:10]


def head_of(command):
    """The program a command starts with, e.g. `find`."""
    words = command.strip().split()
    return os.path.basename(words[0]) if words else ""


def strip_script(code):
    """Drop shebang, comment-only and blank lines."""
    kept = [line.rstrip() for line in code.splitlines() if line.strip() and not line.strip().startswith("#")]
    return "\n".join(kept).strip()


def nl2bash_template(command):
    """Lexical template of a command: quoted strings, paths, globs and numbers are masked."""
    template = re.sub(r'"[^"]*"|\'[^\']*\'', "<S>", command)
    template = re.sub(r"(?:~|\.{1,2})?/[^\s|;&)<>]*", "<P>", template)
    template = re.sub(r"\S*[*?]\S*", "<G>", template)
    template = re.sub(r"(?<![\w-])\d+(?:\.\d+)?\b", "<N>", template)
    return re.sub(r"\s+", " ", template).strip()


def is_unsafe_nl2bash(command):
    return bool(UNSAFE_NL2BASH.search(command))


# ---------------------------------------------------------------- the corpora (records in corpus order)
def read_art(directory):
    """Every Linux sh/bash atomic test, with its default arguments substituted."""
    records, seen = [], set()
    for path in sorted(glob.glob(os.path.join(directory, "atomics", "T*", "T*.yaml"))):
        try:
            technique = yaml.safe_load(open(path, encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- malformed upstream YAML is skipped
            continue
        technique_id = technique.get("attack_technique")
        for test in technique.get("atomic_tests", []) or []:
            executor = test.get("executor") or {}
            runs_on_linux = "linux" in (test.get("supported_platforms") or [])
            if not runs_on_linux or executor.get("name") not in ("sh", "bash"):
                continue
            command = executor.get("command") or ""
            for name, argument in (test.get("input_arguments") or {}).items():
                command = command.replace("#{%s}" % name, str((argument or {}).get("default")))
            command = strip_script(command)
            if command and command not in seen:
                seen.add(command)
                records.append(record("ART", technique_id, command, technique=technique_id,
                                      test_name=test.get("name"), guid=test.get("auto_generated_guid")))
    return records


def read_redcode(directory):
    """Every RedCode-Exec bash script, one command per script."""
    records, seen = [], set()
    pattern = os.path.join(directory, "dataset", "RedCode-Exec", "bash2text_dataset_json", "*.json")
    for path in sorted(glob.glob(pattern)):
        scenario = int(re.search(r"index(\d+)_", os.path.basename(path)).group(1))
        for item in json.load(open(path, encoding="utf-8")):
            command = strip_script(item.get("Code") or "")
            if command and command not in seen:
                seen.add(command)
                records.append(record("RedCode-Exec", f"RC-{scenario:02d}", command,
                                      scenario=scenario, index=item.get("Index")))
    return records


def read_nl2bash(directory):
    """Every NL2Bash command; the unsafe ones (D5) are kept with `in_primary` False."""
    commands = _nl2bash_commands(directory)
    descriptions = _nl2bash_lines(directory, "all.nl")
    records, seen = [], set()
    for line_number, (command, description) in enumerate(zip(commands, descriptions), start=1):
        if command and command not in seen:
            seen.add(command)
            template = nl2bash_template(command)
            family = "NB-" + hashlib.sha1(template.encode()).hexdigest()[:8]
            records.append(record("NL2Bash", family, command, in_primary=not is_unsafe_nl2bash(command),
                                  line=line_number, nl=description, template=template))
    return records


def read_real_world(path):
    """The developer commands in data/manual/, one per line."""
    lines = [line.strip() for line in open(path, encoding="utf-8")]
    commands = [line for line in lines if line and not line.startswith("#")]
    return [record("Real-world", f"R-{number}", command) for number, command in enumerate(commands, start=1)]


def _nl2bash_commands(directory):
    return [line.strip() for line in _nl2bash_lines(directory, "all.cm")]


def _nl2bash_lines(directory, file_name):
    path = os.path.join(directory, "data", "bash", file_name)
    return open(path, encoding="utf-8").read().splitlines()
