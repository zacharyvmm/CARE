"""The code behind baseline_reproduction.ipynb.  The notebook is the pipeline; each module is one step of it.

    configuration        config.yaml, and how this execution runs
    sources              fetch the corpora at pinned commits
    corpora              the evaluated population: every command of every corpus
    guards               the six guards (CARE and the LLM judges), the LLM client and its cache
    evaluation           run the guards on the population -> one observation per decision
    paper_sized_splits   the paper's 549-command composition, re-drawn many times
    stats                the formulas
    analysis             Analysis: every table, computed from the observations
    claims               the verdict rules for claims C1-C11
    report               Report: the tables and figures shown in the notebook; report.md
    provenance           RunRecord: the checks before a run and the files written after it
"""
