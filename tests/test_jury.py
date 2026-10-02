# -*- coding: utf-8 -*-
"""ТЗ-Жюри: тесты жюри (фаза-1 голосование, консенсус, foreman 2.5, живучесть,
порог, датасет-поля, юнит-тесты parse_qa_judges/_qa_bump_effort/threshold)."""
import json
import tempfile

import pytest

import core
import tests.test_qa_phase as tq


# ---------- helpers ----------------------------------------------------------


def jury_config(tmpdir, judges, threshold=2, dataset=False):
    cfg = tq.qa_config(tmpdir, update_glossary=False)
    cfg["judges"] = judges
    cfg["jury_threshold"] = threshold
    cfg["dataset"] = dataset
    return cfg


def run_jury(pairs, cfg, fake_send, tr=None, cache=None, check=None):
    """Wire the fake _qa_send and run run_qa_phase; returns (log lines, pairs)."""
    core._qa_send = fake_send
    log, lines = tq.collect_logs(None)
    tr = tr or tq.make_translator_stub()
    cache = cache or tq.FakeCache()
    core.run_qa_phase(pairs, cfg, tr, cache, log, check)
    return lines, pairs


def make_judge_fake(flags_by_judge, verdicts_by_judge=None, dying_judges=(),
                    base_model="test-model/low"):
    """fake _qa_send: ids phase -> flag list of the judge whose model matches;
    full phase -> per-judge verdicts. Judge identity = substring of j_model.
    NOTE: the foreman runs with the BUMPED primary model (marker 'medium'
    would collide with the primary's 'test-model' substring) — identify the
    foreman call by phase == 'foreman' FIRST, then fall back to markers."""
    verdicts_by_judge = verdicts_by_judge or {}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kwargs):
        if any(d in (model or "") for d in dying_judges):
            raise RuntimeError("all QA keys failed for judge")
        if ids_only:
            for marker, flags in flags_by_judge.items():
                if marker in (model or ""):
                    return [{"id": pid} for pid in flags
                            if any(p.get("id") == pid for p in batch)]
            return []
        if phase == "foreman":
            for marker, verdicts in verdicts_by_judge.items():
                if marker == "foreman":
                    return [dict(v) for v in verdicts
                            if any(p.get("id") == v.get("id") for p in batch)]
            return []
        for marker, verdicts in verdicts_by_judge.items():
            if marker in (model or ""):
                return [dict(v) for v in verdicts
                        if any(p.get("id") == v.get("id") for p in batch)]
        return []
    return fake_send


# ---------- unit: parse_qa_judges / bump / threshold -------------------------


def test_parse_qa_judges_single():
    cfg = {"keys": ["k1"], "provider": "Crusoe Cloud", "model": "m/low"}
    judges = core.parse_qa_judges(cfg)
    assert len(judges) == 1
    assert judges[0]["name"] == "j1" and judges[0]["api_keys"] == ["k1"]


def test_parse_qa_judges_extras():
    cfg = {"keys": ["k1"], "provider": "Crusoe Cloud", "model": "m/low",
           "judges": [{"name": "J2", "api_key": "k2", "model": "m2",
                       "base_url": "https://x", "temperature": 0.3,
                       "effort": "high", "enabled": True}]}
    judges = core.parse_qa_judges(cfg)
    assert len(judges) == 2
    j2 = judges[1]
    assert j2["name"] == "J2" and j2["api_keys"] == ["k2"] and j2["model"] == "m2"
    assert j2["custom_base_url"] == "https://x"
    assert j2["temperature"] == 0.3 and j2["effort"] == "high"


def test_parse_qa_judges_json_string_and_caps():
    cfg = {"keys": ["k1"], "provider": "Crusoe Cloud", "model": "m/low",
           "judges": json.dumps([{"name": "a", "api_key": "k2", "model": "m2"},
                                 {"name": "b", "model": "no-key"},
                                 {"api_key": "k3", "model": "m3"},
                                 {"api_key": "k4", "model": "m4"},
                                 {"api_key": "k5", "model": "m5"}])}
    judges = core.parse_qa_judges(cfg)
    # m12003: record without api_key now falls back to the provider pool;
    # with NO provider_pool in qa_params it takes the primary keys (k1),
    # so "b" survives. At most 3 extras; default name jN.
    assert len(judges) == 4
    assert [j["name"] for j in judges] == ["j1", "a", "b", "j4"]
    assert judges[2]["api_keys"] == ["k1"]


def test_qa_bump_effort_steps():
    assert core._qa_bump_effort("m/low") == "m/medium"
    assert core._qa_bump_effort("m/medium") == "m/high"
    assert core._qa_bump_effort("m/high") == "m/xhigh"
    assert core._qa_bump_effort("m/xhigh") == "m/xhigh"  # top stays
    assert core._qa_bump_effort("plain") == "plain"  # bare model: no suffix -> unchanged


def test_qa_consensus_threshold():
    assert core._qa_consensus_threshold(1, 2) == 1   # single judge = itself
    assert core._qa_consensus_threshold(2, 2) == 2
    assert core._qa_consensus_threshold(3, 2) == 2
    assert core._qa_consensus_threshold(3, 5) == 3   # clamp to n
    assert core._qa_consensus_threshold(4, 1) == 1   # clamp to >=1


# ---------- e2e: two judges agree -> consensus apply -------------------------


def test_jury_two_judges_consensus_applies(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(2)}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}])
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0], "judge-two": [0]},
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}]})
    lines, out = run_jury(pairs, cfg, fake)
    assert out["Craft the Lead Ingot 0"] == "Создай Свинец слиток 0"
    assert out["Craft the Lead Ingot 1"] == "Создай слиток 1"  # untouched
    joined = "\n".join(lines)
    assert "[JURY] jury: j1 1 finding(s), j2 1 finding(s)" in joined
    assert "confirmed 1, disputed 0" in joined
    assert "disputed" not in joined or "disputed 0" in joined.split("[JURY] foreman")[0]


def test_jury_disagreement_goes_to_foreman_confirmed(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(3)}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}])
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0], "judge-two": [0, 2]},
        # phase 2 (primary model): verdict for pair 0
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}],
            # foreman: identified by phase == 'foreman'
            "foreman": [
                {"id": 2, "category": "TERM_INCONSISTENT", "severity": "soft",
                 "issue": "term", "suggested": "Создай Свинец слиток 2"}]})
    lines, out = run_jury(pairs, cfg, fake)
    joined = "\n".join(lines)
    assert "confirmed 1, disputed 1" in joined
    assert "[JURY] #2 disputed (j1 pass, j2 flag) -> foreman: confirmed" in joined
    assert out["Craft the Lead Ingot 2"] == "Создай Свинец слиток 2"
    assert "[JURY] foreman: confirmed 1, cleared 0" in joined


def test_jury_disagreement_foreman_cleared(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(2)}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}])
    fake = make_judge_fake(
        flags_by_judge={"test-model": [], "judge-two": [1]},
        verdicts_by_judge={"foreman": []})  # foreman says nothing -> cleared
    lines, out = run_jury(pairs, cfg, fake)
    joined = "\n".join(lines)
    assert "[JURY] #1 disputed (j1 pass, j2 flag) -> foreman: cleared" in joined
    assert out["Craft the Lead Ingot 1"] == "Создай слиток 1"  # untouched
    assert "[JURY] foreman: confirmed 0, cleared 1" in joined


def test_jury_dead_judge_run_continues(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(2)}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}])
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0]},
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}]},
        dying_judges=("judge-two",))
    lines, out = run_jury(pairs, cfg, fake)
    joined = "\n".join(lines)
    assert "died in phase 1" in joined and "its votes are excluded" in joined
    assert "single-judge mode" in joined
    assert out["Craft the Lead Ingot 0"] == "Создай Свинец слиток 0"


def test_jury_all_judges_dead_aborts(tmp_path):
    pairs = {"Craft the Lead Ingot 0": "Создай слиток 0"}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}])
    fake = make_judge_fake(flags_by_judge={"test-model": [0]},
                           dying_judges=("test-model", "judge-two"))
    core._qa_send = fake
    log, lines = tq.collect_logs(None)
    # run_qa_phase wraps the abort into a benign "phase skipped" log line
    # (the top-level except in _run_qa_phase_async's caller); the pairs
    # are kept as-is and the run ends without an exception.
    core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    joined = "\n".join(lines)
    assert "all QA judges died in phase 1" in joined
    assert pairs["Craft the Lead Ingot 0"] == "Создай слиток 0"


def test_jury_threshold_two_of_three(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(4)}
    cfg = jury_config(str(tmp_path), [
        {"name": "J2", "api_key": "k2", "model": "judge-two/low", "enabled": True},
        {"name": "J3", "api_key": "k3", "model": "judge-three/low", "enabled": True}],
        threshold=2)
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0, 1], "judge-two": [0], "judge-three": [2]},
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}]})
    lines, out = run_jury(pairs, cfg, fake)
    joined = "\n".join(lines)
    # pair 0: 3 votes -> confirmed; pair 1: 1 vote -> disputed; pair 2: 1 vote -> disputed
    assert "confirmed 1, disputed 2" in joined
    assert "threshold 2/3" in joined
    assert out["Craft the Lead Ingot 0"] == "Создай Свинец слиток 0"
    # foreman cleared/disputed pairs stay untouched
    assert out["Craft the Lead Ingot 1"] == "Создай слиток 1"


def test_jury_dataset_consensus_fields(tmp_path):
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(2)}
    cfg = jury_config(str(tmp_path), [
        {"name": "JUDGE2", "api_key": "k2", "model": "judge-two/low", "enabled": True}],
        dataset=True)
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0], "judge-two": [0]},
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}]})
    # the writer writes to core.DATASET_DIR — point it at tmp_path
    orig_dir = core.DATASET_DIR
    core.DATASET_DIR = tmp_path
    try:
        run_jury(pairs, cfg, fake)
    finally:
        core.DATASET_DIR = orig_dir
    # find the dataset jsonl
    import glob as g
    files = sorted(g.glob(str(tmp_path / "**" / "*.jsonl"), recursive=True))
    assert files, "dataset jsonl not written"
    recs = [json.loads(l) for l in open(files[-1], encoding="utf-8") if l.strip()]
    by_pid = {r.get("pair_id"): r for r in recs}
    r0 = by_pid.get(0)
    assert r0 is not None
    assert r0.get("consensus") == "applied"
    assert r0.get("foreman") in ("none", None)
    llm = r0.get("llm") or []
    assert any(v.get("judge") == "j1" for v in llm)


def test_jury_single_judge_backcompat(tmp_path):
    """No extra judges -> exactly today's behavior, single-judge logs."""
    pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(2)}
    cfg = jury_config(str(tmp_path), judges=[])
    fake = make_judge_fake(
        flags_by_judge={"test-model": [0]},
        verdicts_by_judge={"test-model": [
            {"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
             "issue": "term", "suggested": "Создай Свинец слиток 0"}]})
    lines, out = run_jury(pairs, cfg, fake)
    joined = "\n".join(lines)
    assert "[JURY] single judge: 1 finding(s), threshold 1/1, confirmed 1" in joined
    assert out["Craft the Lead Ingot 0"] == "Создай Свинец слиток 0"
    assert "jury: j1" not in joined  # no multi-judge stats line
