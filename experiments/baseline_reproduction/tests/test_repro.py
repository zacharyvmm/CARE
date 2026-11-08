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


def test_headline_marks_design_ci_inclusion_and_orders_conditions():
    rows = [dict(condition=c, metric=m, reported=50.0, observed=obs, design_ci_lo=obs - 5, design_ci_hi=obs + 5,
                 inside_design_ci=abs(obs - 50) <= 5)
            for c, obs in [("CARE", 30.0), ("LLMJudge", 52.0), ("NoGuard", 0.0)] for m in ("F1", "DR", "FPR")]
    h = R.headline(pd.DataFrame(rows))
    assert list(h.condition) == ["LLMJudge", "CARE"]
    assert h.F1.iloc[0].endswith("∈") and h.F1.iloc[1].endswith("∉")


# ---------------------------------------------------------------- design-based bootstrap (D15)
def _toy_design():
    source = np.array(["ART"] * 6 + ["RedCode-Exec"] * 4 + ["NL2Bash"] * 3)
    family = np.array(["a", "a", "a", "b", "b", "c", "s1", "s1", "s2", "s2", "x", "y", "z"])
    return source, family


def test_cluster_bootstrap_keeps_families_whole_and_strata_sizes():
    source, family = _toy_design()
    w = S.cluster_bootstrap_weights(source, family, n_boot=500, seed=1)
    assert w.shape == (500, 13)
    for f in ("a", "b", "c"):                      # members of a family always share a weight
        idx = np.flatnonzero((source == "ART") & (family == f))
        assert (w[:, idx] == w[:, idx[:1]]).all()
    fam_counts = sum(w[:, np.flatnonzero((source == "ART") & (family == f))[0]] for f in ("a", "b", "c"))
    assert (fam_counts == 3).all()                 # same number of families per resample
    for f in ("s1", "s2"):                         # RedCode: items resampled within each scenario
        assert (w[:, np.flatnonzero(family == f)].sum(1) == 2).all()
    assert (w[:, source == "NL2Bash"].sum(1) == 3).all()
    assert not (w[:, :3] == w[:, 3:4]).all()       # families do vary across resamples


def test_cluster_bootstrap_is_seeded():
    source, family = _toy_design()
    assert (S.cluster_bootstrap_weights(source, family, 50, seed=3) ==
            S.cluster_bootstrap_weights(source, family, 50, seed=3)).all()


def test_weighted_rates_with_unit_weights_equal_point_metrics():
    rng = np.random.default_rng(0)
    y, p = rng.random(40) < .4, rng.random(40) < .5
    r = S.weighted_rates(np.ones((1, 40), dtype=int), y, p)
    m = S.point_metrics(y, p)
    assert np.isclose(r["f1"][0], m["f1"]) and np.isclose(r["dr"][0], m["dr"]) and np.isclose(r["fpr"][0], m["fpr"])
    assert np.isclose(r["acc"][0], (y == p).mean())


# ---------------------------------------------------------------- LLM cache identity (D18)
LLM_CFG = dict(model="m1", endpoint="https://x/api/v1", provider_order=["P"], allow_fallbacks=False,
               temperature=0, max_tokens={"CARE": 8, "PromptOnly": 8, "LLMJudge": 8, "NeMo self-check": 4})


def test_request_fingerprint_changes_with_model_prompt_and_decoding():
    base = G.request_fingerprint(LLM_CFG, "LLMJudge")
    assert base == G.request_fingerprint(dict(LLM_CFG), "LLMJudge")
    assert base != G.request_fingerprint(dict(LLM_CFG, model="m2"), "LLMJudge")
    assert base != G.request_fingerprint(dict(LLM_CFG, temperature=0.7), "LLMJudge")
    assert base != G.request_fingerprint(LLM_CFG, "PromptOnly")
    assert G.request_fingerprint(LLM_CFG, "CARE") != G.request_fingerprint(dict(LLM_CFG, model="m2"), "CARE")


def test_cache_misses_when_fingerprint_differs(tmp_path):
    path = tmp_path / "c.jsonl"
    row = dict(condition="LLMJudge", rep=1, command_id="x", decision="DENY", model="m1",
               request_fingerprint=G.request_fingerprint(LLM_CFG, "LLMJudge"))
    G._Cache(str(path)).put(row)
    cache = G._Cache(str(path))
    assert cache.get(("LLMJudge", 1, "x", G.request_fingerprint(LLM_CFG, "LLMJudge"))) is not None
    assert cache.get(("LLMJudge", 1, "x", G.request_fingerprint(dict(LLM_CFG, model="m2"), "LLMJudge"))) is None


def test_observations_keep_the_model_recorded_with_each_reply():
    split = pd.DataFrame(dict(command_id=["a", "b"], source="ART", label="DANGEROUS", label_dangerous=True))
    rows = [dict(condition="LLMJudge", rep=1, command_id="a", decision="DENY", llm_called=True, model="old-model"),
            dict(condition="LLMJudge", rep=1, command_id="b", decision="ALLOW", llm_called=True)]
    obs = G.to_observations(rows, split, "t", "new-model", 42).set_index("command_id")
    assert obs.loc["a", "model"] == "old-model" and obs.loc["b", "model"] == "new-model"


def test_reuse_rejects_replies_outside_the_live_window():
    obs = pd.DataFrame(dict(llm_called=[True, True], generation_id=["g1", "g2"],
                            request_utc=["2026-11-07T06:51:00+00:00", "2026-11-07T07:30:00+00:00"]))
    run = dict(started_utc="2026-11-07T06:50:00+00:00", finished_utc="2026-11-07T06:52:00+00:00")
    with pytest.raises(AssertionError):
        P._assert_replies_from_live_run(obs, run)
    P._assert_replies_from_live_run(obs.iloc[:1], run)
    with pytest.raises(AssertionError):
        P._assert_replies_from_live_run(obs.assign(generation_id="g1").iloc[[0, 0]], run)


def test_protocol_sections_extracts_requested_sections_only():
    text = R.protocol_sections([2, 11])
    assert text.startswith("## 2. Claims") and "## 11. Amendment v1.1" in text and "## 3. " not in text


# ---------------------------------------------------------------- recipe bootstrap (D19) and reuse identity (D20)
def _toy_recipe():
    source = np.array(["ART"] * 5 + ["NL2Bash"] * 6 + ["RedCode-Exec"] * 4 + ["Real-world"] * 2)
    family = np.array(["a", "a", "a", "b", "c", "n1", "n2", "n3", "n4", "n5", "n6", "s1", "s1", "s2", "s2", "r1", "r2"])
    head = np.array(["-"] * 5 + ["ls", "ls", "ls", "cp", "cp", "rm"] + ["-"] * 6)
    return source, family, head


def test_recipe_bootstrap_fixes_quotas_head_cap_and_fixed_subsets():
    source, family, head = _toy_recipe()
    w = S.recipe_bootstrap_weights(source, family, head, {"ART": 5, "NL2Bash": 6}, n_boot=400, seed=2, head_cap=2)
    assert (w[:, source == "ART"].sum(1) == 5).all() and (w[:, source == "NL2Bash"].sum(1) == 6).all()
    assert (w[:, source == "Real-world"] == 1).all()                     # deterministic subset: never resampled
    for f in ("s1", "s2"):
        assert (w[:, family == f].sum(1) == 2).all()                    # scenario sizes kept
    nl = source == "NL2Bash"
    for h in ("ls", "cp", "rm"):
        assert (w[:, nl & (head == h)].sum(1) <= 2).all()                # head cap respected
    a = np.flatnonzero(family == "a")                                    # truncation keeps family order
    assert (w[:, a[1]] <= w[:, a[0]]).all() and (w[:, a[2]] <= w[:, a[1]]).all()
    assert (S.recipe_bootstrap_weights(source, family, head, {"ART": 5, "NL2Bash": 6}, 50, seed=4, head_cap=2) ==
            S.recipe_bootstrap_weights(source, family, head, {"ART": 5, "NL2Bash": 6}, 50, seed=4, head_cap=2)).all()


def test_reuse_requires_identical_requests():
    identity = dict(request_fingerprints={c: G.request_fingerprint(LLM_CFG, c) for c in G.LLM_METHODS},
                    executed_config={k: LLM_CFG[k] for k in P.REQUEST_KEYS})
    obs = pd.DataFrame(dict(llm_called=[True], model=["m1"], provider=["P"]))
    P._assert_same_requests(identity, obs, LLM_CFG)
    with pytest.raises(AssertionError):
        P._assert_same_requests(identity, obs, dict(LLM_CFG, model="m2"))
    with pytest.raises(AssertionError):
        P._assert_same_requests(identity, obs.assign(provider="Other"), LLM_CFG)
    with pytest.raises(AssertionError):
        P._assert_same_requests(identity, obs.assign(model="m0"), LLM_CFG)


def test_recipe_bootstrap_truncates_in_corpus_order_not_row_order():
    source = np.array(["ART"] * 3)
    family = np.array(["a", "a", "a"])
    head = np.array(["-"] * 3)
    order = np.array([2, 0, 1])                       # corpus order: row 1, then row 2, then row 0
    w = S.recipe_bootstrap_weights(source, family, head, {"ART": 2}, n_boot=50, seed=0, order=order)
    assert (w[:, 1] >= 1).all() and (w[:, 2] >= 1).all() and (w[:, 0] == 0).all()


def test_recipe_bootstrap_randomises_which_scenarios_get_the_remainder():
    source = np.array(["RedCode-Exec"] * 7)
    family = np.array(["s1", "s1", "s1", "s2", "s2", "s3", "s3"])
    w = S.recipe_bootstrap_weights(source, family, np.array(["-"] * 7), {"RedCode-Exec": 7}, n_boot=300, seed=1)
    sizes = np.stack([w[:, family == f].sum(1) for f in ("s1", "s2", "s3")], axis=1)
    assert (sizes.sum(1) == 7).all() and set(np.unique(sizes)) == {2, 3}
    assert all(len(set(sizes[:, k])) == 2 for k in range(3))   # each scenario sometimes gets the extra item

