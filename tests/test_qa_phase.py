import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

# --- Test infrastructure --------------------------------------------------
sys.path.insert(0, "/home/ronnikols/MineAI_Pro")

from core import run_qa_phase, ModpackGlossary, GLOSSARY_DIR, apply_dictionary, sanitize_with_original

import core


def make_translator_stub():
    """UnifiedTranslator stand-in: retranslates 'bad' strings."""
    class T:
        provider = "Test"
        model = "stub"
        mixed_pool = None
        modpack_glossary_terms = {}

        async def translate(self, texts, logger=print, check_status=None, context=""):
            return [f"[retried]{t}" for t in texts]
    return T()


class FakeCache:
    def __init__(self):
        self.saved = {}

    def save_batch(self, mapping, modpack=None):
        self.saved.update(mapping)

    def close(self):
        pass


def make_glossary_dir(tmpdir, name="testpack"):
    gdir = Path(tmpdir) / "glossaries"
    gdir.mkdir(exist_ok=True)
    return gdir


def run(coro):
    return asyncio.run(coro)


def collect_logs(logger):
    lines = []
    logger and None

    def log(msg):
        lines.append(msg)
    return log, lines


def qa_config(tmpdir, update_glossary=True, modpack_root=None):
    return {
        "keys": ["test-key"],
        "provider": "Crusoe Cloud",
        "model": "test-model/low",
        "custom_base_url": None,
        "update_glossary": update_glossary,
        "modpack_root": modpack_root,
        "lang_name": "Russian",
    }


# --- 1. hard -> retranslation via translator --------------------------------
def test_hard_retranslates():
    pairs = {"Broken sentence here": "ПЛОХАЯ СТРОКА"}

    problems = [{"id": 0, "category": "UNTRANSLATED", "severity": "hard",
                 "issue": "left English words", "suggested": None, "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return problems

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs["Broken sentence here"] == "[retried]Broken sentence here", pairs
    assert cache.saved.get("Broken sentence here") == "[retried]Broken sentence here"
    assert any("hard" in l for l in lines), lines


# --- 2. soft + suggested -> deterministic fix ------------------------------
def test_soft_autofix():
    src = "The &lImporter&r connects"
    pairs = {src: "Импортёр подключается"}

    problems = [{"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
                 "issue": "term inconsistent", "suggested": "&lИмпортёр&r подключается",
                 "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return problems

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs[src] == "&lИмпортёр&r подключается", pairs
    assert cache.saved.get(src) == "&lИмпортёр&r подключается"


# --- 3. soft suggestion failing validation -> warning, string untouched -----
def test_soft_invalid_suggestion_warns():
    src = "Craft a &lGold Ingot&r now"
    orig = "Сделай &lЗолотой слиток&r сейчас"
    pairs = {src: orig}

    # suggested loses the format code -> validation must fail
    problems = [{"id": 0, "category": "STYLE", "severity": "soft",
                 "issue": "style", "suggested": "Сделай Золотой слиток сейчас",
                 "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return problems

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs[src] == orig, "invalid suggestion must NOT replace the string"
    assert any("validation" in l.lower() or "warning" in l.lower() or "not applied" in l.lower() for l in lines), lines


# --- 4. glossary_fix -> additive write ---------------------------------------
def test_glossary_fix_additive(tmp_path):
    modpack_root = tmp_path / "TestPack"
    modpack_root.mkdir()

    src = "Use the Quantum Foundry"
    pairs = {src: "Используй Квантовый литейный цех"}

    problems = [{"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
                 "issue": "inconsistent", "suggested": None,
                 "glossary_fix": {"en": "Quantum Foundry", "ru": "Квантовая кузня"}}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return problems

    orig_send = core._qa_send
    orig_dir = core.GLOSSARY_DIR
    core._qa_send = fake_send
    core.GLOSSARY_DIR = tmp_path / "glossaries"
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(str(modpack_root), update_glossary=True, modpack_root=modpack_root)
        run_qa_phase(pairs, cfg, tr, cache, log, None)
        # second run with a DIFFERENT glossary_fix for the same term must NOT overwrite
        problems[0]["glossary_fix"] = {"en": "Quantum Foundry", "ru": "ПЕРЕЗАПИСАННЫЙ"}
        pairs2 = {src: "Используй Квантовый литейный цех"}
        run_qa_phase(pairs2, cfg, tr, cache, log, None)
        # Read the glossary INSIDE the sandboxed GLOSSARY_DIR scope
        g = ModpackGlossary(modpack_root)
        terms = dict(g.terms)
    finally:
        core._qa_send = orig_send
        core.GLOSSARY_DIR = orig_dir

    assert terms.get("Quantum Foundry") == "Квантовая кузня", terms


# --- 5. no infinite loop: hard on pass 2 -> warning, no third retranslation --
def test_no_infinite_loop():
    pairs = {"Bad string one": "Плохая строка один"}

    call_count = {"n": 0, "arb": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        if "Glossary compliance arbitration" in prompt:
            call_count["arb"] += 1
            return []  # arbiter: the lenient pin (String=Нить) does not fit here
        call_count["n"] += 1
        # always report the same pair as hard, forever
        return [{"id": p["id"], "category": "UNTRANSLATED", "severity": "hard",
                 "issue": "still bad", "suggested": None, "glossary_fix": None}
                for p in batch]

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    # pass 1 scan + retranslate + pass 2 scan = 2 MAIN scan calls; NO third.
    # The deterministic glossary pre-check may add at most ONE arbitration
    # mini-batch call on top of that.
    assert call_count["n"] == 2, f"scan ran {call_count['n']} times, expected exactly 2"
    assert call_count["arb"] <= 1, f"arbitration ran {call_count['arb']} times"
    assert any("still" in l or "hard" in l for l in lines), lines


# --- 6. soft without suggested -> warning, untouched --------------------------
def test_soft_without_suggested_warns():
    src = "Some quest line"
    orig = "Какая-то строка квеста"
    pairs = {src: orig}

    problems = [{"id": 0, "category": "PROPER_NOUN", "severity": "soft",
                 "issue": "inconsistent noun", "suggested": None, "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return problems

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs[src] == orig
    assert any("PROPER_NOUN" in l for l in lines), lines


# --- 7. clean case: no problems at all ---------------------------------------
def test_clean_case_no_changes():
    pairs = {"All good": "Всё хорошо"}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs == {"All good": "Всё хорошо"}
    assert cache.saved == {}
    assert any("scanned 1 pairs" in l for l in lines), lines


# --- 8. _qa_validate_suggestion unit checks ---------------------------------
def test_validate_suggestion():
    src = "Craft a &lGold Ingot&r now"
    ok = core._qa_validate_suggestion(src, "Сделай &lЗолотой слиток&r сейчас")
    assert ok is True
    # lost format code
    assert core._qa_validate_suggestion(src, "Сделай Золотой слиток сейчас") is False
    # numbers changed
    assert core._qa_validate_suggestion("Smelt 5 ores", "Переплавь 6 руды") is False
    # tag kept
    assert core._qa_validate_suggestion("Uses #minecraft:logs", "Использует #minecraft:logs") is True
    assert core._qa_validate_suggestion("Uses #minecraft:logs", "Использует #forge:logs") is False
    # hex codes kept
    assert core._qa_validate_suggestion("Colored &#ff0000red", "Окрашенный &#ff0000красный") is True
    assert core._qa_validate_suggestion("Colored &#ff0000red", "Окрашенный красный") is False


# --- 9. AbortException must propagate ----------------------------------------
def test_abort_propagates():
    from core import AbortException

    pairs = {"Some": "Что-то"}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        if check_status:
            await check_status()
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send

    async def aborting_check():
        raise AbortException("aborted by user")

    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        try:
            run_qa_phase(pairs, cfg, tr, cache, log, aborting_check)
            raise AssertionError("AbortException must propagate through run_qa_phase")
        except AbortException:
            pass
    finally:
        core._qa_send = orig_send


# --- 10. non-abort exception -> phase skipped, translation intact -----------
def test_phase_failure_skips_gracefully():
    pairs = {"Some": "Что-то"}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        raise RuntimeError("boom")

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs == {"Some": "Что-то"}
    assert any("skipped" in l.lower() or "failed" in l.lower() or "kept" in l.lower() for l in lines), lines


# --- 11. БАГ 6: parser picks the LAST valid JSON array, no retries ----------
def test_extract_qa_problems_array():
    # clean array
    arr = core.extract_qa_problems_array('[{"id": 0, "category": "style", "severity": "soft", "issue": "x"}]')
    assert arr and arr[0]["id"] == 0
    # pair dump + array: last balanced array wins
    raw = ('Some model preamble text.\n'
           '{"source": "A", "translation": "Б"}\n'
           '[{"id": 0, "category": "style", "severity": "soft", "issue": "x"},'
           ' {"id": 1, "category": "grammar", "severity": "soft", "issue": "y"}]')
    arr = core.extract_qa_problems_array(raw)
    assert arr and len(arr) == 2 and arr[-1]["id"] == 1
    # think block + fenced array
    raw = '<think>reasoning...</think>\n```json\n[{"id": 2, "category": "style", "severity": "soft", "issue": "z"}]\n```'
    arr = core.extract_qa_problems_array(raw)
    assert arr and arr[0]["id"] == 2
    # garbage -> None
    assert core.extract_qa_problems_array("no json here at all") is None
    # brackets inside strings do not break the scan
    raw = '[{"id": 0, "category": "style", "severity": "soft", "issue": "see [1] and ] here"}]'
    arr = core.extract_qa_problems_array(raw)
    assert arr and arr[0]["issue"].endswith("here")


# --- 12. БАГ 4+1: normalization, escalation, synthesis, dedup -----------------
def test_normalize_problems():
    batch = [
        {"id": 0, "source": "Craft the Lead Ingot", "translation": "Создай Поводок"},
        {"id": 1, "source": "Simple Sawmill", "translation": "Простая лесопилка"},
    ]
    N = core._qa_normalize_problems
    # БАГ 1: hard-category escalated even when the model said soft
    p = N([{"id": 0, "category": "untranslated", "severity": "soft", "issue": "x"}], batch)[0]
    assert p["severity"] == "hard"
    for cat in ("WRONG_DOMAIN", "GRAMMAR", "MEANING_FLIP", "SOURCE_GARBAGE",
                "TRUNCATED", "CODES_MISMATCH", "NUMBERS_MISMATCH"):
        p = N([{"id": 0, "category": cat, "severity": "soft", "issue": "x"}], batch)[0]
        assert p["severity"] == "hard", cat
    # soft categories keep the model's severity (hard kept, soft kept)
    p = N([{"id": 1, "category": "term_inconsistent", "severity": "soft", "issue": "x"}], batch)[0]
    assert p["severity"] == "soft"
    p = N([{"id": 1, "category": "GLUE_ARTIFACT", "severity": "hard", "issue": "x"}], batch)[0]
    assert p["severity"] == "hard"  # no demotion
    # БАГ 4: empty issue synthesized
    p = N([{"id": 1, "category": "STYLE", "severity": "soft", "issue": "   "}], batch)[0]
    assert "source=" in p["issue"] and "STYLE" in p["issue"]
    # dedup by (id, category)
    out = N([{"id": 0, "category": "GRAMMAR", "severity": "soft", "issue": "a"},
             {"id": 0, "category": "GRAMMAR", "severity": "soft", "issue": "b"}], batch)
    assert len(out) == 1
    # unknown id dropped
    assert N([{"id": 99, "category": "STYLE", "severity": "soft", "issue": "x"}], batch) == []
    # bad severity coerced, category uppercased
    p = N([{"id": 0, "category": "style", "severity": "major", "issue": "x"}], batch)[0]
    assert p["severity"] == "soft" and p["category"] == "STYLE"


# --- 13. БАГ 3a: deterministic glossary-compliance machine -------------------
def test_glossary_compliance_machine():
    GV = core._qa_glossary_violations
    vanilla = {"Lead": "Свинец", "Crafting Table": "Верстак"}
    modpack = {"Cloche": "Колпак", "Space Parts": "Космические детали"}
    batch = [
        {"id": 0, "source": "Craft the Lead Ingot", "translation": "Создай Свинцовый слиток"},
        {"id": 1, "source": "Simple Cloche farm", "translation": "Простая Колпак ферма"},
        {"id": 2, "source": "Crafting Tables are cheap", "translation": "Верстаки дешёвые"},   # inflection OK
        {"id": 3, "source": "Place the &lSpace Parts&r here", "translation": "Разместите &lчасти&r тут"},
        {"id": 4, "source": "No glossary here", "translation": "Тут нет терминов"},
    ]
    flagged = GV(batch, vanilla, modpack)
    assert [p["id"] for p in flagged] == [0, 3], flagged
    assert flagged[0]["missed_pins"] == [("Lead", "Свинец")]
    assert flagged[1]["missed_pins"] == [("Space Parts", "Космические детали")]
    # prompt builds as a JSON array of pairs with int ids + missed_pins
    pr = core._qa_glossary_compliance_prompt(flagged, "Russian")
    assert "Glossary compliance arbitration" in pr and "TERM_INCONSISTENT" in pr
    arr = json.loads(pr.split("missed_pins):\n", 1)[1].strip())
    assert arr[0]["id"] == 0 and arr[0]["missed_pins"] == [["Lead", "Свинец"]], arr
    assert arr[1]["id"] == 3 and arr[1]["missed_pins"] == [["Space Parts", "Космические детали"]], arr


# --- 14. БАГ 3a: arbitration applies soft fix through the standard path ------
def test_glossary_arbitration_applies_fix():
    pairs = {
        "Craft the Lead Ingot": "Создай Свинцовый слиток",
        "Simple Cloche farm": "Простая Колпак ферма",
    }
    calls = {"scan": 0, "arb": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0"):
        if "Glossary compliance arbitration" in prompt:
            calls["arb"] += 1
            # the model answers with STRING ids — the ТЗ2.1 regression case
            return [{"id": "0", "category": "term_inconsistent", "severity": "soft",
                     "issue": "Lead must be Свинец", "suggested": "Создай Свинец слиток"}]
        calls["scan"] += 1
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert calls["scan"] == 1 and calls["arb"] == 1, calls
    assert pairs["Craft the Lead Ingot"] == "Создай Свинец слиток", pairs
    assert cache.saved.get("Craft the Lead Ingot") == "Создай Свинец слиток"
    assert any("glossary pre-check flagged" in l for l in lines), lines


# --- 15. БАГ 7: deterministic script-artifact pre-check ---------------------
def test_script_violation_detector():
    SV = core._qa_script_violations
    batch = [
        {"id": 0, "source": "Stop the machine now", "translation": "S&lnow"},           # latin_leak
        {"id": 1, "source": "The block updates", "translation": "Блок Sсейчас"},       # mixed_script
        {"id": 2, "source": "All fine here", "translation": "Всё хорошо тут"},          # clean
        {"id": 5, "source": "Use AE2 Setup", "translation": "Используй AE2 Сетап"},     # mod name legit
        {"id": 6, "source": "The &k&4l&r&0&lVoid", "translation": "&k&4л&r&0&lПустота"},  # obfuscation
        {"id": 8, "source": "Craft the Lead Ingot", "translation": "Craft the Lead Ingot"},  # not_target_lang
    ]
    ids = {p["id"]: r for p, r in SV(batch, "cyrillic")}
    assert ids.get(0) == "latin_leak", ids
    assert ids.get(1) == "mixed_script", ids
    assert ids.get(8) == "not_target_lang", ids
    for clean_id in (2, 5, 6):
        assert clean_id not in ids, (clean_id, ids)
    # target script resolution
    assert core._qa_target_script({"lang_name": "Russian"}, batch) == "cyrillic"
    assert core._qa_target_script({"lang_code": "de_de"}, batch) == "latin"


# --- 16. БАГ 7: script-artifact pair retranslated before the audit -----------
def test_script_violation_retranslates():
    pairs = {
        "Stop the machine now": "S&lnow",
        "All fine here": "Всё хорошо тут",
    }
    calls = {"translate": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, **kwargs):
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        class T:
            provider = "Test"
            model = "stub"
            mixed_pool = None
            modpack_glossary_terms = {}

            async def translate(self, texts, logger=print, check_status=None, context=""):
                calls["translate"] += 1
                assert context == "qa-script-retry", context
                return ["Останови машину сейчас"]
        log, lines = collect_logs(None)
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, T(), cache, log, None)
    finally:
        core._qa_send = orig_send

    assert calls["translate"] == 1, calls
    assert pairs["Stop the machine now"] == "Останови машину сейчас", pairs
    assert cache.saved.get("Stop the machine now") == "Останови машину сейчас"
    assert any("script violation" in l for l in lines), lines
    assert pairs["All fine here"] == "Всё хорошо тут"


# --- ТЗ2.1-2/3: id coercion + drop-reason accounting -------------------------
def test_tz21_id_coercion_and_drop_reasons():
    batch = [{"id": i, "source": f"src {i}", "translation": f"пер {i}"} for i in range(570, 601)]
    raw = [
        {"id": "574", "category": "untranslated", "severity": "soft", "issue": "x"},    # str -> hard
        {"id": 573.0, "category": "glue_artifact", "severity": "soft", "issue": "y"},  # float -> soft
        {"id": 573.0, "category": "GLUE_ARTIFACT", "severity": "soft", "issue": "d"},  # duplicate
        {"id": 999, "category": "term_inconsistent", "severity": "soft", "issue": "z"},  # invalid
    ]
    stats = {}
    out = core._qa_normalize_problems(raw, batch, stats)
    assert sorted((p["id"], p["severity"]) for p in out) == [(573, "soft"), (574, "hard")], out
    assert stats["duplicate"] == 1 and stats["invalid_id"] == 1 and stats["_ids_seen"] == ["999"], stats
    line = core._qa_drop_summary("batch 7", stats, batch)
    assert "1 duplicate" in line and "1 invalid_id" in line, line
    assert "999" in line and "570-600" in line, line
    # no drops -> empty summary (no log line)
    stats2 = {}
    core._qa_normalize_problems(raw[:2], batch, stats2)
    assert core._qa_drop_summary("batch 1", stats2, batch) == ""


# --- ТЗ2.1-4: arbitration prompt is a JSON array with int ids ----------------
def test_tz21_arbitration_prompt_json():
    flagged = [{"id": 45, "source": "Lead ingot", "translation": "Поводок слиток",
                "missed_pins": [("Lead", "Свинец")]}]
    pr = core._qa_glossary_compliance_prompt(flagged, "Russian")
    assert "Glossary compliance arbitration" in pr
    arr = json.loads(pr.split("missed_pins):\n", 1)[1].strip())
    assert arr == [{"id": 45, "source": "Lead ingot",
                    "translation": "Поводок слиток",
                    "missed_pins": [["Lead", "Свинец"]]}], arr
    assert "integer id" in pr


# --- ТЗ2.1-1: raw dump flag ---------------------------------------------------
def test_tz21_raw_dump_flag(tmp_path=None):
    import tempfile
    from pathlib import Path as _P
    td = tmp_path or _P(tempfile.mkdtemp())
    core._QA_DUMP_DIR = _P(td)
    old = os.environ.get("SNBT_QA_DEBUG")
    try:
        os.environ["SNBT_QA_DEBUG"] = "1"
        core._qa_dump_raw("arb", "7L", '[{"id": "574"}]')
        files = list(_P(td).iterdir())
        assert files and "_arb_7L" in files[0].name, files
        assert files[0].read_text(encoding="utf-8") == '[{"id": "574"}]'
        # flag off -> zero I/O
        os.environ.pop("SNBT_QA_DEBUG", None)
        before = set(_P(td).iterdir())
        core._qa_dump_raw("arb", "8", "[]")
        assert set(_P(td).iterdir()) == before
    finally:
        if old is None:
            os.environ.pop("SNBT_QA_DEBUG", None)
        else:
            os.environ["SNBT_QA_DEBUG"] = old


# --- ТЗ2.1 regression: "574"(str) + 573(int) + duplicate -> 2 applied, 1 dup drop
def test_tz21_regression_mixed_ids():
    pairs = {f"src {i}": f"пер {i}" for i in range(570, 575)}
    applied = {"n": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0"):
        # ids mirror the phase's own enumerate() numbering (0..4 here);
        # "3" as str and 2 as int must BOTH resolve, the exact duplicate drop.
        return [
            {"id": "3", "category": "untranslated", "severity": "soft", "issue": "str id"},
            {"id": 2, "category": "untranslated", "severity": "soft", "issue": "int id"},
            {"id": 2, "category": "UNTRANSLATED", "severity": "soft", "issue": "dup"},
        ]

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    # both ids resolved: 2 retranslations happened ([retried] via the stub)
    retrans = [v for v in pairs.values() if v.startswith("[retried]")]
    assert len(retrans) == 2, pairs
    # the duplicate was reported with the reason in the log
    assert any("1 duplicate" in l for l in lines), lines


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                    import tempfile as _t
                    with _t.TemporaryDirectory() as td:
                        from pathlib import Path as _P
                        fn(_P(td))
                else:
                    fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{'ALL OK' if failed == 0 else f'{failed} FAILED'}")
    sys.exit(1 if failed else 0)
