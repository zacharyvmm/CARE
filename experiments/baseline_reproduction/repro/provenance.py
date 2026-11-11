"""What makes a run auditable: the checks made before it, and the files written after it.

    record = RunRecord(configuration)
    record.check_environment()      # care/ unmodified, package versions against the lockfile
    record.run_unit_tests()
    ...
    record.write_results(analysis, report)    # tables, report.md, provenance.json, validation.json
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

from . import corpora, evaluation, sources
from .configuration import EXPERIMENT, REPOSITORY

KEY_PACKAGES = ["pandas", "pyarrow", "numpy", "scipy", "statsmodels", "openai", "bashlex", "PyYAML", "matplotlib"]


class RunRecord:
    """Collects the facts of one execution and writes them next to the results."""

    def __init__(self, configuration):
        self.configuration = configuration
        self.environment = None
        self.unit_tests = None

    def check_environment(self):
        """Require `care/` to be exactly the released code, and compare the packages with the lockfile."""
        release = self.configuration["method_under_test"]["release_commit"]
        differs_from_release = _git("diff", "--stat", release, "--", "care/")
        uncommitted = _git("status", "--porcelain", "--", "care/")
        assert not differs_from_release and not uncommitted, "care/ differs from the release: the method is modified"
        print(f"✓ care/ identical to release {release}")

        installed = {package: _installed_version(package) for package in KEY_PACKAGES}
        locked = _locked_versions()
        mismatches = {package: (found, locked[package]) for package, found in installed.items()
                      if package in locked and found != locked[package]}
        print("✓ package versions match the lockfile" if not mismatches
              else f"⚠ versions differ from the lockfile: {mismatches}")

        self.environment = dict(
            python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
            cpu_count=os.cpu_count(), packages=installed, lockfile_mismatches=mismatches,
            repo_head=_git("rev-parse", "HEAD"),
            uncommitted_changes=bool(_git("status", "--porcelain", "--", os.path.relpath(EXPERIMENT, REPOSITORY))))

    def run_unit_tests(self):
        """Run this reproduction's tests and the CARE repository's own tests."""
        command = [sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider",
                   "tests", os.path.join(REPOSITORY, "tests")]
        finished = subprocess.run(command, cwd=EXPERIMENT, text=True, capture_output=True)
        assert finished.returncode == 0, "unit tests failed:\n" + finished.stdout[-2000:]
        self.unit_tests = finished.stdout.strip().splitlines()[-1]
        print("✓ unit tests:", self.unit_tests)

    def write_results(self, analysis, report):
        """Write every table as Parquet, report.md, provenance.json and validation.json."""
        output = self.configuration.output_directory
        written = [os.path.join(output, "observations.parquet")]
        for name, table in analysis.tables().items():
            written.append(os.path.join(output, f"{name}.parquet"))
            table.to_parquet(written[-1], index=False)
        with open(os.path.join(output, "report.md"), "w") as file:
            file.write(report.markdown())
        self._write_json("provenance.json", self._provenance(analysis, written))
        self._write_json("validation.json", self._validation(analysis))
        relative = os.path.relpath(output, EXPERIMENT)
        print(f"✓ wrote {len(written)} tables, report.md, provenance.json and validation.json to {relative}/")

    def _provenance(self, analysis, written):
        """Everything needed to audit the run."""
        configuration, splits = self.configuration, analysis.splits
        return dict(
            generated_utc=_utc_now(), mode=configuration.mode, run_label=configuration.run_label,
            protocol_version=configuration["protocol_version"],
            protocol_sha256=_sha256("PROTOCOL.md"), config_sha256=_sha256("config.yaml"),
            method_under_test=dict(configuration["method_under_test"], care_identical_to_release=True),
            paper=configuration["paper"],
            sources=configuration["sources"],   # every fingerprint was verified when the sources were fetched
            population=dict(corpora.counts(analysis.population), sha256=_sha256(configuration["population"]["file"])),
            paper_sized_splits=dict(
                n=len(splits), seeds=[splits.seeds[0], splits.seeds[-1]],
                split_size=int(splits.rows.shape[1]), level=configuration["paper_sized_splits"]["level"],
                sha256=hashlib.sha256(splits.rows.tobytes()).hexdigest()),
            llm=dict(self._llm_run(analysis), requested_config=configuration["llm"]),
            environment=self.environment, unit_tests=self.unit_tests,
            outputs={os.path.relpath(path, EXPERIMENT): sources.sha256_file(path) for path in written})

    def _validation(self, analysis):
        """The checks this run passed (each stage stops the notebook when its check fails)."""
        llm_run = self._llm_run(analysis)
        return dict(
            mode=self.configuration.mode, unit_tests=self.unit_tests, care_identical_to_release=True,
            sources_verified=True, population_identical_to_committed=True, static_guards_deterministic=True,
            llm_queried_in_this_session=self.configuration.query_llm_live,
            llm_replies_verified_before_reuse=not self.configuration.query_llm_live,
            llm_errors=llm_run["errors"], completed_utc=_utc_now())

    def _llm_run(self, analysis):
        """Usage of the LLM calls and the request identity they were made with."""
        live = self.configuration.query_llm_live
        identity_directory = self.configuration.output_directory if live else evaluation.COMMITTED_RESULTS
        with open(os.path.join(identity_directory, "llm_request_identity.json")) as file:
            identity = json.load(file)
        return dict(evaluation.llm_usage(analysis.observations), queried_in_this_session=live,
                    executed_request_identity=identity)

    def _write_json(self, file_name, content):
        with open(os.path.join(self.configuration.output_directory, file_name), "w") as file:
            json.dump(content, file, indent=2, default=str)


def _git(*arguments):
    return subprocess.run(["git", *arguments], cwd=REPOSITORY, text=True, capture_output=True).stdout.strip()


def _installed_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _locked_versions():
    lockfile = os.path.join(EXPERIMENT, "environment/requirements.lock.txt")
    return dict(line.strip().split("==") for line in open(lockfile) if "==" in line)


def _sha256(relative_path):
    return sources.sha256_file(os.path.join(EXPERIMENT, relative_path))


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
