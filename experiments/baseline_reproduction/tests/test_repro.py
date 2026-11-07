"""Unit tests for the reproduction helpers (run from the notebook, or: pytest tests/)."""
import json
import os
import random
import sys
import types

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from repro import dataset as D  # noqa: E402
from repro import guards as G  # noqa: E402
from repro import stats as S  # noqa: E402


# ---------------------------------------------------------------- metric formulas
def test_point_metrics_known_values():
    y = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    p = [1, 1, 1, 0, 1, 0, 0, 0, 0, 0]       # TP3 FN1 FP1 TN5
    m = S.point_metrics(y, p)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (3, 1, 1, 5)
    assert m["dr"] == pytest.approx(0.75) and m["fpr"] == pytest.approx(1 / 6)
    assert m["f1"] == pytest.approx(2 * 3 / (2 * 3 + 1 + 1))


def test_f1_zero_when_no_true_positive():
    assert S.point_metrics([1, 0], [0, 0])["f1"] == 0.0


@pytest.mark.parametrize("k,n", [(0, 10), (3, 10), (96, 220), (11, 329), (329, 329)])
def test_wilson_matches_statsmodels(k, n):
    from statsmodels.stats.proportion import proportion_confint
    assert S.wilson(k, n) == pytest.approx(proportion_confint(k, n, method="wilson"), abs=1e-12)


@pytest.mark.parametrize("a_only,b_only", [(70, 20), (3, 0), (51, 71), (10, 10)])
def test_mcnemar_matches_statsmodels(a_only, b_only):
    from statsmodels.stats.contingency_tables import mcnemar
    ca = np.array([1] * a_only + [0] * b_only + [1] * 50 + [0] * 5, bool)
    cb = np.array([0] * a_only + [1] * b_only + [1] * 50 + [0] * 5, bool)
    lo, ro, py, pe = S.mcnemar(ca, cb)
    tab = [[50, a_only], [b_only, 5]]
    assert (lo, ro) == (a_only, b_only)
    assert py == pytest.approx(mcnemar(tab, exact=False, correction=True).pvalue)
    assert pe == pytest.approx(mcnemar(tab, exact=True).pvalue)


def test_paper_table_viii_p_value_reproduces_from_counts():
    # Table VIII row "CARE vs CARE w/o R": 3 / 0 -> p = 0.25 (Yates)
    _, _, py, _ = S.mcnemar([1, 1, 1] + [1] * 10, [0, 0, 0] + [1] * 10)
    assert py == pytest.approx(0.248, abs=1e-3)


def test_bootstrap_ci_brackets_point_estimate():
    rng = np.random.default_rng(1)
    y = rng.random(500) < 0.4
    p = np.where(rng.random(500) < 0.8, y, ~y)
    lo, hi = S.bootstrap_f1(y, p, n_boot=2000, seed=0)
    assert lo < S.point_metrics(y, p)["f1"] < hi


# ---------------------------------------------------------------- response parsing (App. E)
@pytest.mark.parametrize("resp,deny", [("DANGEROUS", True), ("SAFE", False), ("Dangerous.", True),
                                       ("DANGEROUS\n\nThe command uses", True), ("", False)])
def test_parse_safe_dangerous(resp, deny):
    assert G.parse_prompt_only(resp) is deny and G.parse_llm_judge(resp) is deny


@pytest.mark.parametrize("resp,deny", [("yes", True), ("Yes.", True), ("no", False), ("No", False),
                                       ("yes\n\nThis command", True)])
def test_parse_nemo(resp, deny):
    assert G.parse_nemo(resp) is deny


def test_prompts_contain_command_verbatim():
    cmd = "rm -rf /tmp/x && echo '{}'"
    for name, (build, _) in G.LLM_BASELINES.items():
        assert any(cmd in m["content"] for m in build(cmd)), name


# ---------------------------------------------------------------- CARE judge via the client shim
class _FakeCompletions:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("boom")
        msg = types.SimpleNamespace(content=self.reply)
        return types.SimpleNamespace(id="gen-x", provider="P", choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                                     usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=1, cost=1e-6))


def _client(reply=None, fail=False):
    cfg = dict(endpoint="http://x", provider_order=["P"], allow_fallbacks=False, retries=1)
    c = G.PinnedClient.__new__(G.PinnedClient)
    c.extra_body = {"provider": {"order": cfg["provider_order"], "allow_fallbacks": False}}
    c.retries, c.chat, c.completions = 1, c, c
    import threading
    c._tl = threading.local()
    c._c = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_FakeCompletions(reply, fail)))
    return c


WARN_NO_SKIP = "rsync -avz ./build/ admin@gpu01:/data/"   # paper Fig. 6: WARN, no skip predicate


@pytest.mark.parametrize("reply,decision", [("SAFE", "ALLOW"), ("DANGEROUS", "DENY")])
def test_care_judge_through_shim(reply, decision):
    from care import CARE
    g = CARE(use_judge=True, model="m", base_url="http://x", api_key="k")
    g._client = c = _client(reply)
    out = g.analyze(WARN_NO_SKIP)
    assert out["escalated"] and out["decision"] == decision
    sent = c._c.chat.completions.calls[0]
    assert sent["temperature"] == 0 and sent["max_tokens"] == 8
    assert sent["extra_body"]["provider"] == {"order": ["P"], "allow_fallbacks": False}
    assert c.last["provider"] == "P" and c.last["prompt_tokens"] == 10


def test_care_judge_fails_closed():
    from care import CARE
    g = CARE(use_judge=True, model="m", base_url="http://x", api_key="k")
    g._client = _client(fail=True)
    out = g.analyze(WARN_NO_SKIP)
    assert out["escalated"] and out["decision"] == "DENY" and "boom" in out["escalate_error"]


# ---------------------------------------------------------------- dataset construction
def test_nl2bash_template():
    assert D.nl2bash_template('find /tmp -name "*.py" -mtime 7') == "find <P> -name <S> -mtime <N>"


@pytest.mark.parametrize("cmd,flag", [("sudo apt update", True), ("pseudo x", False), ("du -su .", False),
                                      ("kill -9 1234", True), ("kill 1234", False), ("chmod 4755 f", True),
                                      ("chmod 755 f", False), ("echo x >> /etc/hosts", True),
                                      ("cat /etc/hosts", False), ("rm -rf /", True), ("rm -rf ./build", False),
                                      ("dd if=a of=/dev/sda", True), (":(){ :|:& };:", True)])
def test_label_filter(cmd, flag):
    assert bool(D.UNSAFE_NL2BASH_RE.search(cmd)) is flag


def _recs(spec):
    return [dict(family=f, head=h, command=f"{f}-{i}") for f, h, n in spec for i in range(n)]


def test_family_draw_keeps_families_whole_except_last():
    recs = _recs([(f"F{i}", "h", 3) for i in range(10)])
    out = D.family_draw(recs, 10, random.Random(0))
    sizes = sorted(np.unique([r["family"] for r in out], return_counts=True)[1])
    assert len(out) == 10 and sizes[1:] == [3, 3, 3] and sizes[0] == 1


def test_family_draw_head_cap():
    recs = _recs([(f"F{i}", "find" if i < 8 else f"h{i}", 2) for i in range(12)])
    out = D.family_draw(recs, 10, random.Random(1), head_cap=3)
    assert sum(r["head"] == "find" for r in out) <= 3


def test_stratified_draw_covers_all_strata():
    recs = _recs([(f"S{i}", "h", 30) for i in range(20)])
    out = D.stratified_draw(recs, 71, random.Random(0))
    counts = np.unique([r["family"] for r in out], return_counts=True)[1]
    assert len(out) == 71 and len(counts) == 20 and counts.max() - counts.min() <= 1


@pytest.fixture
def mini_corpus(tmp_path):
    art = tmp_path / "art" / "atomics" / "T1000"
    art.mkdir(parents=True)
    tests = [dict(name=f"t{i}", supported_platforms=["linux"], executor=dict(name="sh", command=f"echo #{{x}} {i}"),
                  input_arguments=dict(x=dict(default="v"))) for i in range(6)]
    tests.append(dict(name="win", supported_platforms=["windows"], executor=dict(name="powershell", command="dir")))
    (art / "T1000.yaml").write_text(json.dumps(dict(attack_technique="T1000", atomic_tests=tests)))
    rc = tmp_path / "rc" / "dataset" / "RedCode-Exec" / "bash2text_dataset_json"
    rc.mkdir(parents=True)
    for s in (1, 2):
        (rc / f"index{s}_30_codes_full_upd.json").write_text(json.dumps(
            [dict(Index=f"{s}_{i}", Code=f"#!/bin/bash\n# c\ncat /etc/f{s}{i}") for i in range(4)]))
    nb = tmp_path / "nb" / "data" / "bash"
    nb.mkdir(parents=True)
    cms = [f"ls -l dir{i}" for i in range(10)] + ["sudo reboot", "echo v 0"]
    (nb / "all.cm").write_text("\n".join(cms))
    (nb / "all.nl").write_text("\n".join("nl" for _ in cms))
    rw = tmp_path / "rw.txt"
    rw.write_text("# header\ngit status\nmake\n")
    return dict(art=str(tmp_path / "art"), redcode=str(tmp_path / "rc"), nl2bash=str(tmp_path / "nb")), str(rw)


def test_build_split_end_to_end(mini_corpus):
    roots, rw = mini_corpus
    targets = {"ART": 4, "RedCode-Exec": 4, "NL2Bash": 5, "Real-world": 2}
    df, man = D.build_split(7, roots, rw, targets)
    assert D.validate_split(df, targets)
    assert man["candidate_pool"]["NL2Bash_label_filtered_out"] == 1          # "sudo reboot"
    assert man["candidate_pool"]["cross_source_conflicts_dropped"] == ["echo v 0"]   # ART vs NL2Bash (D10)
    assert set(df[df.source == "ART"].command) <= {f"echo v {i}" for i in range(6)}   # args substituted
    assert not df.command.str.contains("#!").any()                                    # shebang stripped
    df2, _ = D.build_split(7, roots, rw, targets)
    assert df.command_id.tolist() == df2.command_id.tolist()                          # deterministic


def test_conflicting_labels_dropped(mini_corpus):
    roots, rw = mini_corpus
    D._POOLS.clear()
    p = D.load_pools(roots, rw)
    assert "echo v 0" in p["conflicts"]          # in ART (DANGEROUS) and NL2Bash (SAFE)
    assert all(r["command"] != "echo v 0" for k in D.SOURCES for r in p[k])


# ---------------------------------------------------------------- pipeline settings and notebook views
from repro import pipeline as P  # noqa: E402
from repro import report as R  # noqa: E402


def test_settings_never_expose_api_key():
    run = P.settings({"llm": {"reps": 3}}, environ={"OPENROUTER_API_KEY": "sk-secret-123", "REPRO_MODE": "smoke"})
    assert run.run_llm and not run.full and run.reps == 1
    assert "sk-secret-123" not in repr(run) and "sk-secret-123" not in P.banner(run)


def test_settings_without_key_reuse_committed_observations():
    run = P.settings({"llm": {"reps": 3}}, environ={})
    assert run.full and not run.run_llm and run.reps == 3 and run.label == "confirmatory-v1"
    assert not P.settings({"llm": {"reps": 3}}, environ={"OPENROUTER_API_KEY": "k", "REPRO_REUSE_LLM": "1"}).run_llm


def test_headline_marks_consistency_and_orders_conditions():
    rows = [dict(condition=c, metric=m, reported=50.0, observed=obs, ci_lo=obs - 5, ci_hi=obs + 5,
                 status="consistent" if abs(obs - 50) <= 5 else "inconsistent")
            for c, obs in [("CARE", 30.0), ("LLMJudge", 52.0), ("NoGuard", 0.0)] for m in ("F1", "DR", "FPR")]
    h = R.headline(pd.DataFrame(rows))
    assert list(h.condition) == ["LLMJudge", "CARE"]
    assert h.F1.iloc[0].endswith("✓") and h.F1.iloc[1].endswith("✗")
