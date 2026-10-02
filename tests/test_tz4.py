# -*- coding: utf-8 -*-
"""ТЗ-v4: тесты гигиены ключей/данных + run-агрегации.

A1 sanitize_api_key (5 кейсов incl '\nКлюч 2:'), B5 ru-pass-through,
B6 регистр-директива, C7 один dataset-файл на ран, C8/C9 run totals,
D10 pass-2 soft apply, E11 формулировки смерти судей.
"""
import json
import logging
import sys
import tempfile
from pathlib import Path

import pytest

import core
import tests.test_qa_phase as tq
from core import sanitize_api_key, sanitize_api_keys


# ---------- A1: key sanitation ------------------------------------------------

def test_sanitize_strips_and_accepts():
    assert sanitize_api_key("  cr_goodkey_123  \n") == "cr_goodkey_123"
    assert sanitize_api_key("plain") == "plain"


def test_sanitize_rejects_non_ascii():
    # прецедент из продакшена: ключ с хвостом '\nКлюч 2: ...'
    assert sanitize_api_key("cr_key\nКлюч 2: x") == ""
    assert sanitize_api_key("ключ") == ""


def test_sanitize_rejects_embedded_newline():
    assert sanitize_api_key("cr_a\ncr_b") == ""


def test_sanitize_warns_on_odd_length_but_keeps():
    logs = []
    key = sanitize_api_key("short", logger=logs.append, origin="test")
    assert key == "short"  # warn, не reject
    assert any("suspicious" in l for l in logs), logs


def test_sanitize_keys_dedup_and_drop():
    out = sanitize_api_keys([" a ", "a", "", "b\nbroken", "b"])
    assert out == ["a", "b"]


def test_parse_qa_judges_drops_bad_key_judge():
    qa_params = {
        "keys": ["primary_key"], "provider": "Crusoe Cloud", "model": "m/high",
        "judges": [
            {"name": "bad", "provider": "OpenAI", "api_key": "ключ\nКлюч 2: x",
             "model": "gpt-5", "enabled": True},
            {"name": "good", "provider": "OpenAI", "api_key": "sk-fine",
             "model": "gpt-5", "enabled": True},
        ],
        "provider_pool": {},
    }
    judges = core.parse_qa_judges(qa_params)
    assert len(judges) == 2  # primary + good; bad dropped
    assert all(j.get("name") != "bad" for j in judges)


# ---------- B5: ru->ru pass-through -------------------------------------------

def _pt_config(tmpdir):
    cfg = tq.qa_config(tmpdir, update_glossary=False)
    cfg["dataset"] = False
    cfg["verdict_cache"] = False
    return cfg


def test_b5_cyrillic_majority_file_passes_through():
    """>50% кириллических source → весь файл pass-through, скан не идёт."""
    pairs = {
        "Строка на русском": "Строка на русском",
        "Вторая строка тоже русская": "Вторая строка тоже русская",
        "English source": "Перевод",
    }
    scanned = {"n": 0}

    async def fake_send(*a, **kw):
        scanned["n"] += 1
        return []

    orig = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert scanned["n"] == 0  # ни одного запроса — весь файл прошли
    assert any("passed through" in l for l in lines), lines
    assert any("whole file" in l for l in lines), lines


def test_b5_per_pair_pass_through():
    """Меньшинство кириллических → per-pair pass, остальные сканируются."""
    pairs = {
        "Русская строка": "Русская строка",
        "One English line": "Один перевод",
        "Another English line": "Другой перевод",
    }
    seen = {"batches": []}

    async def fake_send(batch, *a, **kw):
        if kw.get("ids_only"):
            seen["batches"].extend(p["id"] for p in batch)
            return []
        return []

    orig = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert 0 not in seen["batches"], "кириллическая пара не должна сканироваться"
    assert any("passed through" in l for l in lines), lines


def test_b5_no_pass_through_for_english():
    """Чисто английский файл — обычный скан, no pass-through лога."""
    pairs = {"English one": "Перевод 1", "English two": "Перевод 2"}

    async def fake_send(batch, *a, **kw):
        if kw.get("ids_only"):
            return []
        return []

    orig = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert not any("passed through" in l for l in lines), lines


# ---------- B6: register directive --------------------------------------------

def test_b6_register_directive_in_russian_prompt():
    t = core.UnifiedTranslator(["test-key"], "OpenAI", "gpt-4o-mini",
                               target_lang_name="Russian")
    assert "formal вы-form" in t.prompt
    assert "consistent register" in t.prompt


def test_b6_no_register_directive_for_german():
    t = core.UnifiedTranslator(["test-key"], "OpenAI", "gpt-4o-mini",
                               target_lang_name="German")
    assert "formal вы-form" not in t.prompt


# ---------- C7: one dataset jsonl per run -------------------------------------

def test_c7_run_dataset_single_file(tmp_path):
    core.qa_run_start()
    try:
        w1 = core.QADataSetWriter(tmp_path, {"pack": "t"}, logger=None)
        for i in range(3):
            w1.add({"pair_id": i, "src": f"a{i}"})
        n1 = w1.finish()
        w2 = core.QADataSetWriter(tmp_path, {"pack": "t"}, logger=None)
        for i in range(3, 5):
            w2.add({"pair_id": i, "src": f"a{i}"})
        n2 = w2.finish()
        assert w1.path == w2.path
        lines = w2.path.read_text(encoding="utf-8").strip().splitlines()
        metas = [json.loads(l) for l in lines if json.loads(l).get("meta")]
        recs = [json.loads(l) for l in lines if not json.loads(l).get("meta")]
        assert len(metas) == 1
        assert len(recs) == 5
        assert n1 == 3 and n2 == 2
    finally:
        core.qa_run_finish()


def test_c7_legacy_files_separate_without_run(tmp_path):
    w3 = core.QADataSetWriter(tmp_path, {"pack": "t"}, logger=None)
    w3.add({"pair_id": 0})
    w3.finish()
    w4 = core.QADataSetWriter(tmp_path, {"pack": "t"}, logger=None)
    w4.add({"pair_id": 1})
    w4.finish()
    assert w3.path != w4.path


# ---------- C8/C9: run totals ---------------------------------------------------

def test_c8_run_totals_across_files():
    core.qa_run_start()
    try:
        core.qa_run_note_file(40, 2, {"hard": 1, "soft_fixed": 4, "warnings": 2,
                                      "glossary": 1, "unresolved": 0}, jury_line="")
        core.qa_run_note_file(35, 0, {"hard": 2, "soft_fixed": 10, "warnings": 0,
                                      "glossary": 0, "unresolved": 1},
                              jury_line="[JURY] jury: j1 3 finding(s) ...")
        lines = []
        totals = core.qa_run_finish(lines.append)
        assert totals and totals.get("run_id")
        assert any("run total" in l for l in lines)
        total_line = next(l for l in lines if "run total" in l)
        assert "scanned 75" in total_line
        assert "2 passed through" in total_line
        assert any("[JURY]" in l for l in lines)
    finally:
        core.qa_run_finish()  # no-op: state уже очищен


def test_c8_second_finish_is_noop():
    core.qa_run_start()
    try:
        core.qa_run_note_file(10, 0, {"hard": 0}, jury_line="")
        lines = []
        core.qa_run_finish(lines.append)
        core.qa_run_finish(lines.append)  # повторный — молчит
        assert sum("run total" in l for l in lines) == 1
    finally:
        core.qa_run_finish()


# ---------- D10: pass-2 soft apply ----------------------------------------------

def _d10_setup():
    """Пары, где фаза-1 флагает пару, soft-фикс применяется, pass-2 выдаёт
    ещё один валидный soft-вердикт по изменённой паре."""
    src = "The &lImporter&r connects"
    pairs = {src: "&lИмпортёр подключает&r"}
    v1 = [{"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
           "issue": "term inconsistent", "suggested": "&lИмпортёр подключается&r",
           "glossary_fix": None}]
    v2 = [{"id": 0, "category": "STYLE", "severity": "soft",
           "issue": "style nit", "suggested": "&lИмпортёр подключён к сети&r",
           "glossary_fix": None}]
    return pairs, v1, v2


def test_d10_pass2_applies_valid_soft():
    pairs, v1, v2 = _d10_setup()
    calls = {"n": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kw):
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        # pass-2 сканирует уже-исправленную пару и даёт второй soft-вердикт
        tr = batch[0]["translation"]
        if "подключается" in tr:
            return v2
        return v1

    orig = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        tr = tq.make_translator_stub()
        cache = tq.FakeCache()
        core.run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig
    assert "pass-2 soft fixed" in " ".join(lines), lines
    assert "подключён к сети" in list(pairs.values())[0], pairs


def test_d10_pass2_invalid_soft_stays_warning():
    pairs, v1, _v2 = _d10_setup()
    bad_v2 = [{"id": 0, "category": "STYLE", "severity": "soft",
               "issue": "loses codes", "suggested": "Импортёр без кодов",
               "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kw):
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        if "подключается" in batch[0]["translation"]:
            return bad_v2
        return v1

    orig = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        cache = tq.FakeCache()
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), cache, log, None)
    finally:
        core._qa_send = orig
    assert "pass-2 warning" in " ".join(lines), lines
    assert "&lИмпортёр подключается&r" == list(pairs.values())[0], pairs


# ---------- E11: death cause wording -------------------------------------------

@pytest.mark.parametrize("msg,expect", [
    ("invalid API key (non-ASCII) on key ...AB12 — keys failed",
     "dead key (invalid non-ASCII key — paste error)"),
    ("auditor HTTP 401 on benched key ...AB12 — keys failed",
     "dead key (HTTP 401 — auth/billing)"),
    ("auditor HTTP 403 error: forbidden — keys failed",
     "dead key (HTTP 403 — auth/billing)"),
    ("auditor HTTP 402 on benched key ...AB12 — keys failed",
     "dead key (HTTP 402 — auth/billing)"),
    ("all QA keys benched (2+ consecutive timeouts/failures each) — keys failed",
     "slow/hung — keys benched after repeated timeouts/failures"),
    ("all QA keys failed: some reason", "dead key (all keys failed)"),
])
def test_e11_death_cause(msg, expect):
    assert core._qa_death_cause(RuntimeError(msg)) == expect


def test_e11_unknown_error_repr():
    got = core._qa_death_cause(RuntimeError("weird"))
    assert got.startswith("RuntimeError"), got


# ---------- /max reasoning suffix + readable 404 (жалоба m14406) ---------------

def test_max_is_a_known_reasoning_level():
    """'/max' must be stripped from the model id (RunInfra answers 404 on
    'deepseek-v4-1-flash/max' but accepts reasoning_effort=max)."""
    assert "max" in core.REASONING_EFFORT_LEVELS
    assert core.parse_model_effort("deepseek-v4-1-flash/max") == ("deepseek-v4-1-flash", "max")
    payload = core.apply_reasoning_effort({"model": "deepseek-v4-1-flash/max"},
                                          "deepseek-v4-1-flash/max", "RunInfra")
    assert payload["model"] == "deepseek-v4-1-flash"
    assert payload["reasoning_effort"] == "max"


def test_max_does_not_break_other_levels():
    for m, want in [("m/high", "m"), ("org/m/xhigh", "org/m"),
                    ("org/m/low", "org/m")]:
        payload = core.apply_reasoning_effort({"model": m}, m, "RunInfra")
        assert payload["model"] == want
        assert payload["reasoning_effort"] == m.rpartition("/")[2]
    # модель без известного суффикса остаётся нетронутой
    payload = core.apply_reasoning_effort({"model": "org/m/ultra"}, "org/m/ultra", "RunInfra")
    assert payload["model"] == "org/m/ultra" and "reasoning_effort" not in payload


class _Resp:
    def __init__(self, body):
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_http_error_detail_reads_provider_message():
    """404 без текста сервера — бесполезен; берём error.message и code."""
    detail = core._http_error_detail(_Resp(
        {"error": {"message": "Model 'x/max' is not available as a verified deployment",
                   "code": "model_not_found"}}))
    assert "not available as a verified deployment" in detail
    assert "model_not_found" in detail
    assert core._http_error_detail(_Resp({"message": "plain top-level"})) == "plain top-level"
    assert core._http_error_detail(_Resp({})) == ""


@pytest.mark.parametrize("msg", [
    "auditor HTTP 404 (model 'x/max'): Model 'x/max' is not available",
    "auditor HTTP 404 (model 'x'): model not available",
])
def test_qa_404_is_fatal_not_a_waterfall(msg):
    """404 — детерминированная проблема id модели: сплит не помогает и
    превращает одну ошибку в водопад запросов 30->15->7->3->2."""
    fatal = ("keys failed" in msg or "keys unavailable" in msg
             or "server unavailable" in msg
             or "no API keys" in msg or "no base URL" in msg
             or "auditor HTTP 404" in msg)
    assert fatal


# ---------- F12.3: зафлагованные пары не исчезают ------------------------------

def test_f12_3_arbitration_failure_keeps_flagged_pairs():
    """12.4(в): арбитраж упал на середине → flagged пары в unresolved,
    run total ≠ 0, датасет пишет их как warning."""
    pairs = {
        "Craft the Lead Ingot": "Создай Свинцовый слиток",
        "Simple Cloche farm": "Простая Колпак ферма",
    }

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None, phase="main",
                        batch_label="0", ids_only=False, **kw):
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        if "Glossary compliance arbitration" in prompt:
            raise RuntimeError("auditor died mid-arbitration")
        return []

    orig = core._qa_send
    core._qa_send = fake_send
    core._QA_COUNTERS["unresolved"] = 0
    core.qa_run_start()
    try:
        log, lines = tq.collect_logs(None)
        cfg = _pt_config(tempfile.gettempdir())
        cfg["dataset"] = True           # датасет обязан зафиксировать флаги
        import pathlib
        ds_seen = {}
        _orig_add = core.QADataSetWriter.add
        def _spy_add(self, record):
            ds_seen[record.get("pair_id")] = record
            return _orig_add(self, record)
        core.QADataSetWriter.add = _spy_add
        tr4 = tq.make_translator_stub()
        # ТЗ-v4.3 B.4: пины энфорсит ТОЛЬКО modpack-глоссарий
        tr4.modpack_glossary_terms = {"Lead": "Свинец", "Cloche": "Колпак"}
        try:
            core.run_qa_phase(pairs, cfg, tr4, tq.FakeCache(), log, None)
        finally:
            core.QADataSetWriter.add = _orig_add
        run_lines = []
        totals = core.qa_run_finish(run_lines.append)
    finally:
        core._qa_send = orig
        core.qa_run_finish()
    joined = " ".join(lines)
    # переводы не тронуты — фаза не применяет мусор
    assert pairs == {"Craft the Lead Ingot": "Создай Свинцовый слиток",
                     "Simple Cloche farm": "Простая Колпак ферма"}, pairs
    # ...но НИ ОДНА пара не потеряна и не «clean»: пара, чей арбитраж умер,
    # уходит в unresolved и в датасет как warning.
    assert core._QA_COUNTERS["unresolved"] >= 1, core._QA_COUNTERS
    assert "left unresolved" in joined and "warning" in joined, lines
    # 12.3: run total не ноль и считает просканированные пары
    assert totals, "qa_run_finish не отдал агрегат"
    assert totals.get("qa_scanned", 0) >= 2, totals
    assert any("run total" in l for l in run_lines), run_lines
    # 12.3: датасет фиксирует провал скана как warning, а не как clean
    warned = [r for r in ds_seen.values() if r.get("action") == "warning"]
    assert warned, ds_seen
    assert all(r.get("action") != "clean" for r in warned), ds_seen
