import asyncio
import json
import logging
import os
import re
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
    # Hermetic by default: the verdict cache and the dataset writer are
    # OFF unless a test explicitly opts in — otherwise every legacy test
    # reads/writes the developer's real ~/.snbt-tr state.
    return {
        "keys": ["test-key"],
        "provider": "Crusoe Cloud",
        "model": "test-model/low",
        "custom_base_url": None,
        "update_glossary": update_glossary,
        "modpack_root": modpack_root,
        "lang_name": "Russian",
        "dataset": False,
        "verdict_cache": False,
    }


# --- 1. hard -> retranslation via translator --------------------------------
def test_hard_retranslates():
    pairs = {"Broken sentence here": "ПЛОХАЯ СТРОКА"}

    problems = [{"id": 0, "category": "UNTRANSLATED", "severity": "hard",
                 "issue": "left English words", "suggested": None, "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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
    # codes are PRESERVED in the original translation: with Tier B live,
    # a lost-code original is machine-caught (CODES_MISMATCH -> hard retry)
    # BEFORE the soft verdict can apply. Keep the codes so this test still
    # exercises the soft-fix path.
    pairs = {src: "&lИмпортёр подключает&r"}

    problems = [{"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
                 "issue": "term inconsistent", "suggested": "&lИмпортёр&r подключается",
                 "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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


# --- 3. soft suggestion failing validation -> constraint retry (ТЗ3.1-2) -------
def test_soft_invalid_suggestion_warns():
    src = "Craft a &lGold Ingot&r now"
    orig = "Сделай &lЗолотой слиток&r сейчас"
    pairs = {src: orig}

    # suggested loses the format code -> validation must fail
    problems = [{"id": 0, "category": "STYLE", "severity": "soft",
                 "issue": "style", "suggested": "Сделай Золотой слиток сейчас",
                 "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

        return problems

    # ТЗ3.1-2: the stub retranslation ALSO loses the codes -> the constraint
    # retry result is invalid too -> the string must stay untouched.
    class BadT:
        provider = "Test"
        model = "stub"
        mixed_pool = None
        modpack_glossary_terms = {}

        async def translate(self, texts, logger=print, check_status=None, context=""):
            return [t.replace("&l", "").replace("&r", "") for t in texts]

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = BadT()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert pairs[src] == orig, "invalid suggestion AND invalid retry must NOT replace the string"
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

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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
    # SANDBOX the vanilla glossary: with the real ~/.snbt-tr glossary live,
    # the pair 'Bad string one' hits the vanilla pin String=Нить, the arbiter
    # is asked, and (ТЗ3-3) an unresolved flagged pair flows to tier C repair —
    # a legitimate third scan. With an empty glossary the only scans are
    # pass 1 + pass 2.
    orig_load = core.load_vanilla_glossary
    core.load_vanilla_glossary = lambda: {}
    pairs = {"Bad string one": "Плохая строка один"}

    call_count = {"n": 0, "arb": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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
        core.load_vanilla_glossary = orig_load

    # pass 1 scan + retranslate + pass 2 scan = 2 MAIN scan calls; NO third.
    # The deterministic glossary pre-check may add at most ONE arbitration
    # mini-batch call on top of that.
    assert call_count["n"] == 2, f"scan ran {call_count['n']} times, expected exactly 2"
    assert call_count["arb"] <= 1, f"arbitration ran {call_count['arb']} times"
    assert any("still" in l or "hard" in l for l in lines), lines


# --- 6. soft advice-only -> constraint retry fixes it (ТЗ3.1-2) -----------------
def test_soft_without_suggested_warns():
    src = "Some quest line"
    orig = "Какая-то строка квеста"
    pairs = {src: orig}

    problems = [{"id": 0, "category": "PROPER_NOUN", "severity": "soft",
                 "issue": "inconsistent noun", "suggested": None, "glossary_fix": None}]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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

    # ТЗ3.1-2: advice without a replacement is no longer a dead end — the
    # finding becomes a constraint on ONE retry; a valid result is applied.
    # The stub returns '[retried]Some quest line' (codes/numbers intact) so
    # it passes validation and replaces the original.
    assert pairs[src] == "[retried]Some quest line", pairs
    assert any("constraint retry fixed" in l for l in lines), lines


# --- 7. clean case: no problems at all ---------------------------------------
def test_clean_case_no_changes():
    pairs = {"All good": "Всё хорошо"}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if check_status:
            await check_status()
        if ids_only:
            return [{"id": p["id"]} for p in batch]
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

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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
    # ТЗ-v4.3 B.4: ONLY the modpack glossary is enforced; the vanilla file is
    # an arbitration witness, never a flag source. The pins live in the
    # modpack argument now (the `vanilla` dict below is deliberately inert).
    vanilla = {"Lead": "Свинец", "Crafting Table": "Верстак"}
    modpack = {"Lead": "Свинец", "Crafting Table": "Верстак",
               "Cloche": "Колпак", "Space Parts": "Космические детали"}
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
    # the vanilla dict alone may not flag anything
    assert GV(batch, vanilla, {}) == []
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

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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
        # ТЗ-v4.3 B.4: the pre-check enforces the MODPACK glossary only
        tr.modpack_glossary_terms = {"Lead": "Свинец", "Cloche": "Колпак"}
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    # Speed-pack п.5: the applied soft fix sends the pair to the pass-2
    # rescan, so the scan is called twice (main + pass-2) now.
    assert calls["scan"] == 2 and calls["arb"] == 1, calls
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


# --- 15a. CJK battery: wrong-language output is a hard machine verdict ------
# The user-visible contract: a translation that came out in Chinese/Japanese/
# Korean (or half of it did) for a non-CJK target is flagged BEFORE the LLM
# audit and retranslated — the judge never sees it.
def test_cjk_leak_is_hard_on_cyrillic_target():
    SV = core._qa_script_violations
    batch = [
        {"id": 0, "source": "Craft the table", "translation": "制作工作台"},        # full Chinese
        {"id": 1, "source": "Craft the table", "translation": "Сделай 工作台 тут"},  # half Chinese
        {"id": 2, "source": "Craft the table", "translation": "クラフトする"},        # Japanese kana
        {"id": 3, "source": "Craft the table", "translation": "제작하다"},           # Korean hangul
        {"id": 4, "source": "Craft the table", "translation": "Ｈｅｌｌｏ мир"},      # full-width forms
        {"id": 5, "source": "Craft the table", "translation": "Сделай верстак"},    # clean
    ]
    ids = {p["id"]: r for p, r in SV(batch, "cyrillic")}
    for bad_id in (0, 1, 2, 3, 4):
        assert ids.get(bad_id) == "cjk_symbols", (bad_id, ids)
    assert 5 not in ids, ids


def test_cjk_target_language_rules():
    # get_target_script mapping
    assert core.get_target_script("zh_cn") == "cjk"
    assert core.get_target_script("zh_tw") == "cjk"
    assert core.get_target_script("ja_jp") == "cjk"
    assert core.get_target_script("ko_kr") == "hangul"
    assert core.get_target_script("ru_ru") == "cyrillic"
    assert core.get_target_script("unknown_lang") == "latin"

    SV = core._qa_script_violations
    # CJK target: Chinese output is FINE...
    assert not SV([{"id": 0, "source": "Craft the table", "translation": "制作工作台"}], "cjk")
    # ...but Russian output in a Chinese target is not_target_lang
    ids = {p["id"]: r for p, r in SV([{"id": 0, "source": "Craft the table",
                                       "translation": "Сделай верстак сейчас"}], "cjk")}
    assert ids.get(0) == "not_target_lang", ids
    # hangul target: Korean is fine, Latin-only output is not
    assert not SV([{"id": 0, "source": "Craft the table", "translation": "제작하다"}], "hangul")
    ids = {p["id"]: r for p, r in SV([{"id": 0, "source": "Craft the table",
                                       "translation": "Сделай верстак сейчас"}], "hangul")}
    assert ids.get(0) == "not_target_lang", ids


def test_cjk_pair_retranslated_before_audit():
    # End-to-end: the machine tier catches the Chinese output and the main
    # translator gets a second chance; the auditor must not see the CJK text.
    pairs = {
        "Craft the table": "制作工作台",
        "All fine here": "Всё хорошо тут",
    }
    seen_sources = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        seen_sources.extend(p["source"] for p in batch)
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
                assert context == "qa-script-retry", context
                return ["Сделай верстак"]
        log, lines = collect_logs(None)
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        run_qa_phase(pairs, cfg, T(), cache, log, None)
    finally:
        core._qa_send = orig_send
    assert pairs["Craft the table"] == "Сделай верстак", pairs
    assert any("cjk_symbols" in l for l in lines), lines
    # Design: a script-fixed pair STAYS in the audit (unlike glue/machine
    # pairs) — the judge re-checks the fresh translation, never the CJK one.
    assert "Craft the table" in seen_sources, seen_sources


# --- 16. БАГ 7: script-artifact pair retranslated before the audit -----------
def test_script_violation_retranslates():
    pairs = {
        "Stop the machine now": "S&lnow",
        "All fine here": "Всё хорошо тут",
    }
    calls = {"translate": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

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


# --- ТЗ2.2-4: ru morphology in the glossary pre-check -------------------------
def test_tz22_ru_morphology_matches_inflections():
    batch = [{"id": 0, "source": "Combine the Moon Stone dust", "translation": "Смешай Лунного камня пыль"}]
    hits = core._qa_glossary_violations(
        batch, vanilla_gloss={}, modpack_terms={"Moon Stone": "Лунный камень"})
    # the pin IS present in inflected form (Лунного камня) -> NO violation
    assert hits == [], hits


def test_tz22_ru_morphology_flags_real_misses():
    batch = [{"id": 0, "source": "Combine the Moon Stone dust", "translation": "Смешай лунной скалы пыль"}]
    hits = core._qa_glossary_violations(
        batch, vanilla_gloss={}, modpack_terms={"Moon Stone": "Лунный камень"})
    assert [h["id"] for h in hits] == [0], hits  # pin missing -> violation flagged


def test_tz22_ru_inflect_pattern_battery():
    P = core._qa_ru_inflect_pattern
    # adjective stem cut (ый/ий/ой/ая/ое/ые/ие), vowel cut, case tail up to 3 letters
    for ru in ("Лунный", "Лунного", "Лунные", "Свинец", "Свинца", "Слитки", "Слитка", "Верстак", "Верстаками"):
        pat = re.compile(rf"^{P(ru)}$", re.IGNORECASE)
        assert pat.match(ru), (ru, P(ru))
    # a DIFFERENT root must NOT match even with the tail: Свинец != Свинцовому
    pat_lead = re.compile(rf"^{P('Свинец')}$", re.IGNORECASE)
    assert not pat_lead.match("Свинцовому")


# --- ТЗ2.2-2: no_category verdicts are demoted to warnings, not dropped --------
def test_tz22_no_category_demoted_to_warning():
    batch = [{"id": 0, "source": "Craft the thing", "translation": "Скрафти вещь"}]
    raw = [
        {"id": 0, "severity": "soft", "issue": "term drift: вещь vs предмет", "suggested": "Скрафти предмет"},
        {"id": 1, "category": "", "severity": "soft", "issue": "", "suggested": None},  # empty too
    ]
    batch = [{"id": 0, "source": "Craft the thing", "translation": "Скрафти вещь"},
             {"id": 1, "source": "Smelt the ore", "translation": "Переплавь руду"}]
    stats = {}
    out = core._qa_normalize_problems(raw, batch, stats)
    warnings = [p for p in out if p.get("severity") == "warning"]
    assert len(warnings) == 2, out
    assert all(p["category"] == "" for p in warnings)
    assert any("term drift" in p["issue"] for p in warnings), warnings
    assert any("uncategorized verdict" in p["issue"] for p in warnings), warnings
    # the raw issue text survives when present
    assert any("term drift" in p["issue"] for p in warnings), warnings
    # duplicates by (id, "") count as duplicate drops
    stats2 = {}
    raw_dup = [raw[0], dict(raw[0])]
    out2 = core._qa_normalize_problems(raw_dup, batch, stats2)
    assert len(out2) == 1 and stats2.get("duplicate") == 1, (out2, stats2)


def test_tz22_warning_verdicts_apply_as_warnings_only():
    pairs = {"Craft the thing": "Скрафти вещь"}
    captured = {}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            return [{"id": p["id"]} for p in batch]

        return [{"id": 0, "severity": "soft", "issue": "term drift", "suggested": "Скрафти предмет"}]

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

    # nothing applied: the pair is untouched, no cache write
    assert pairs["Craft the thing"] == "Скрафти вещь", pairs
    assert not cache.saved, cache.saved
    assert any("[no category/soft]" in l and "term drift" in l for l in lines), lines


# --- ТЗ2.2-1: the main prompt mandates category+suggested ---------------------
def test_tz22_prompt_mandatory_fields():
    pr = core.QA_PROMPT_TEMPLATE.replace("{target_language}", "Russian")
    assert "MANDATORY FIELDS" in pr
    assert "are DISCARDED without being applied" in pr
    assert 'full corrected string in "suggested"' in pr
    # JSON sample braces survive the .replace()-based rendering
    assert '[{{"id"' in pr


# --- ТЗ2.2-3: arbitration option (c) + visible pin conflict -------------------
def test_tz22_arbitration_option_c_and_conflict(tmp_path=None):
    import tempfile as _t
    from pathlib import Path as _P
    td = tmp_path or _P(_t.mkdtemp())
    # prompt side: (c) is spelled out and pairs serialize as JSON
    pr = core._qa_glossary_compliance_prompt(
        [{"id": 45, "source": "Lead ingot", "translation": "Поводок слиток",
          "missed_pins": [("Lead", "Свинец")]}], "Russian")
    assert "(c) the pinned translation itself is wrong" in pr
    arr = json.loads(pr.split("missed_pins):\n", 1)[1].strip())
    assert arr[0]["missed_pins"] == [["Lead", "Свинец"]]

    # apply side: existing pin kept, conflict becomes a VISIBLE warning
    orig_dir = core.GLOSSARY_DIR
    core.GLOSSARY_DIR = _P(td) / "glossaries"
    core.GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        gloss = ModpackGlossary(str(td))
        gloss.terms["Lead"] = "Свинец"
        gloss.save()

        pairs = {"Attach the Lead to the collar": "Прикрепи поводок к ошейнику"}
        logs = []

        async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0", ids_only=False, **kwargs):
            if ids_only:
                return [{"id": p["id"]} for p in batch]

            if phase == "arb":
                return [{"id": batch[0]["id"], "category": "GLOSSARY_AWKWARD", "severity": "soft",
                         "issue": "dog-leash context: the Lead pin itself is wrong here",
                         "suggested": "Прикрепи поводок к ошейнику",
                         "glossary_fix": {"en": "Lead", "ru": "Поводок"}}]
            return []

        orig_send = core._qa_send
        core._qa_send = fake_send

        class Tr:
            provider = "Test"
            model = "stub"
            mixed_pool = None
            modpack_glossary_terms = {"Lead": "Свинец"}

        try:
            cfg = qa_config(tempfile.gettempdir(), modpack_root=str(td))
            run_qa_phase(pairs, cfg, Tr(), FakeCache(), logs.append, None)
        finally:
            core._qa_send = orig_send

        g2 = ModpackGlossary(str(td))
        # ТЗ3.1-addendum B: an explicit GLOSSARY_AWKWARD arbitration verdict
        # (branch (c): dog-leash homonym pin) CORRECTS the pin in place with
        # a visible log — the conflict is no longer a dead-end warning.
        assert g2.terms.get("Lead") == "Поводок", g2.terms
        corrected = [l for l in logs if "pin corrected" in l]
        assert corrected and "Поводок" in corrected[0] and "Свинец" in corrected[0], logs
        assert pairs["Attach the Lead to the collar"] == "Прикрепи поводок к ошейнику", pairs
    finally:
        core.GLOSSARY_DIR = orig_dir


# --- ТЗ3-2: tier B machine verdicts -------------------------------------------
def test_tz3_machine_problems_battery():
    MP = core._qa_machine_problems
    batch = [
        {"id": 0, "source": "Smelt the ore now", "translation": "Переплавь руду руду сейчас"},  # glue
        {"id": 1, "source": "Craft the Marsium Part", "translation": "Craft the Marsium Part"},  # full copy
        {"id": 2, "source": "AE2", "translation": "AE2"},                                  # acronym skip
        {"id": 3, "source": "Mekanism", "translation": "Mekanism"},                        # whitelist skip
        {"id": 4, "source": "#minecraft:logs", "translation": "#minecraft:logs"},              # tech string
        {"id": 5, "source": "Craft &lLead&r Ingot", "translation": "Создай Lead Ingot"},       # codes lost
        {"id": 6, "source": "Smelt 5 ores", "translation": "Переплавь 6 руды"},                # numbers
        {"id": 7, "source": "All fine here", "translation": "Всё хорошо тут"},                 # clean
    ]
    out = MP(batch)
    by = {p["id"]: p for p in out}
    assert by[0]["category"] == "GLUE_ARTIFACT" and by[0]["severity"] == "hard"
    assert "руду" in by[0]["issue"]
    assert by[1]["category"] == "UNTRANSLATED" and "full copy" in by[1]["issue"]
    assert by[5]["category"] == "CODES_MISMATCH"
    assert by[6]["category"] == "NUMBERS_MISMATCH"
    for skip_id in (2, 3, 4, 7):
        assert skip_id not in by, (skip_id, by)
    # every machine verdict is already normalized
    for p in out:
        assert p["severity"] == "hard" and p["suggested"] is None and p["glossary_fix"] is None
        assert p["issue"].startswith("machine:")


# --- ТЗ3-3: custom {id, problems:[...]} schema unwrapping ----------------------
def test_tz3_flatten_raw_verdicts():
    F = core._qa_flatten_raw_verdicts
    raw = [
        {"id": 3, "problems": [
            {"category": "TERM_INCONSISTENT", "severity": "soft", "issue": "a"},
            {"id": 7, "category": "STYLE", "severity": "soft", "issue": "b"},   # own id wins
        ]},
        {"id": 4, "category": "STYLE", "severity": "soft", "issue": "flat"},    # flat passes through
        {"id": 5, "problems": "not a list"},                                     # garbage -> itself
        "junk",
    ]
    out = F(raw)
    ids = [p.get("id") for p in out]
    assert ids == [3, 7, 4, 5], out
    assert out[0]["category"] == "TERM_INCONSISTENT"


# --- ТЗ3-3b: repair prompt carries candidates with notes -----------------------
def test_tz3_repair_prompt_json():
    cands = [{"id": 1, "source": "Lead ingot", "translation": "Поводок слиток",
              "note": "glossary pin missing: Lead=Свинец"}]
    pr = core._qa_repair_prompt(cands, "Russian")
    assert "Verdict repair" in pr and "Russian" in pr
    marker = "note):\n"
    assert marker in pr
    arr = json.loads(pr.split(marker, 1)[1].strip())
    assert arr[0]["id"] == 1 and arr[0]["note"].startswith("glossary pin"), arr


# --- ТЗ3-3b: crippled verdicts go to tier C repair and get applied ------------
def test_tz3_tier_c_repair_end_to_end(tmp_path=None):
    import tempfile as _t
    from pathlib import Path as _P
    td = tmp_path or _P(_t.mkdtemp())
    orig_dir = core.GLOSSARY_DIR
    core.GLOSSARY_DIR = _P(td) / "glossaries"
    core.GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    orig_load = core.load_vanilla_glossary
    core.load_vanilla_glossary = lambda: {}
    try:
        gloss = ModpackGlossary(str(td))
        gloss.terms["Lead"] = "Свинец"
        gloss.save()

        class Tr:
            provider = "Test"
            model = "stub"
            mixed_pool = None
            modpack_glossary_terms = {"Lead": "Свинец"}

        phases = []

        async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                            logger, check_status, temperature=None,
                            phase="main", batch_label="0", ids_only=False, **kwargs):
            phases.append(phase)
            if ids_only:
                # Speed-pack п.3 phase 1: route the pairs the old 'main'
                # answer would have flagged (crippled 1 + healthy 2).
                return [{"id": 1}, {"id": 2}]
            if phase == "main":
                return [{"id": 1, "issue": "strange wording, looks off"},          # crippled
                        {"id": 2, "category": "STYLE", "severity": "soft",
                         "issue": "caps", "suggested": "Нормальный стиль"}]        # healthy
            if phase == "arb":
                return []  # arbiter silent -> flagged pair flows to tier C
            if phase == "repair":
                assert "Verdict repair" in prompt
                out = []
                for p in batch:
                    assert "note" in p, p
                    if "Lead" in p["source"]:
                        out.append({"id": p["id"], "category": "TERM_INCONSISTENT",
                                    "severity": "soft", "issue": "pin missed",
                                    "suggested": "Сделай &lСвинец&r (2x)"})
                    else:
                        out.append({"id": p["id"], "category": "STYLE", "severity": "soft",
                                    "issue": "reword", "suggested": "Переформулированная фраза тут"})
                return out
            return []

        orig_send = core._qa_send
        core._qa_send = fake_send
        try:
            logs = []
            pairs = {
                "Make &lLead&r (2x)": "Сделай &lПоводок&r (2x)",
                "Strange phrase here": "Странная фраза",
                "Some title case": "Нормальный стиль",
            }
            cfg = qa_config(str(td), modpack_root=str(td))
            cache = FakeCache()
            run_qa_phase(pairs, cfg, Tr(), cache, logs.append, None)
        finally:
            core._qa_send = orig_send

        # Speed-pack п.5: tier C repair fixes make pass-2 rescan the changed pairs.
        # ТЗ-Жюри: phase-1 phase label now carries the judge tag ('phase1-j1').
        assert phases == ["phase1-j1", "main", "arb", "repair", "pass2"], phases
        assert pairs["Make &lLead&r (2x)"] == "Сделай &lСвинец&r (2x)", pairs
        assert pairs["Strange phrase here"] == "Переформулированная фраза тут", pairs
        assert any("tier C repair" in l for l in logs), logs
        # the crippled verdict ALSO surfaced as a warning in the main pass
        assert any("[no category/soft]" in l and "strange wording" in l for l in logs), logs
    finally:
        core.GLOSSARY_DIR = orig_dir
        core.load_vanilla_glossary = orig_load


# --- ТЗ3-1: the pre-scan is additive (pins are never re-asked) ----------------
def test_tz3_prescan_additive(tmp_path=None):
    import tempfile as _t
    from pathlib import Path as _P
    td = tmp_path or _P(_t.mkdtemp())
    orig_dir = core.GLOSSARY_DIR
    core.GLOSSARY_DIR = _P(td) / "glossaries"
    core.GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    orig_extract = core.extract_glossary_candidates
    orig_translate = core.translate_glossary_terms
    try:
        gloss = ModpackGlossary(str(td))
        gloss.terms["Cloche"] = "Колпак"
        gloss.save()

        # the extractor feeds the pinned term AND a new one as candidates
        core.extract_glossary_candidates = lambda texts, **kw: ["Cloche", "Zephyrium Plate"]

        async def hostile_translate(terms, *a, **kw):
            # a hostile utility model that wants to re-pin EVERYTHING
            return {t: "Клеш" for t in terms}

        core.translate_glossary_terms = hostile_translate

        import asyncio as _a

        async def drive():
            return await core.ensure_modpack_glossary(
                ["Zephyrium Plate", "Cloche"], str(td), ["k"], "Test", "stub",
                "Russian", logger=lambda m: None)

        _a.run(drive())
        g2 = ModpackGlossary(str(td))
        # existing pin survived the hostile re-pin attempt (additive only)
        assert g2.terms.get("Cloche") == "Колпак", g2.terms
        # the NEW term was asked and added
        assert g2.terms.get("Zephyrium Plate") == "Клеш", g2.terms
    finally:
        core.GLOSSARY_DIR = orig_dir
        core.extract_glossary_candidates = orig_extract
        core.translate_glossary_terms = orig_translate


# --- ТЗ3-2b/5: machine wins over the LLM on the same id; catch-matrix logs ------
def test_tz3_machine_wins_and_catch_matrix():
    GOOD = {"Smelt the ore": "Переплавь руду"}

    class Tr:
        provider = "Test"
        model = "stub"
        mixed_pool = None
        modpack_glossary_terms = {}

        async def translate(self, texts, logger=print, check_status=None, context=""):
            return [GOOD.get(t, f"[retried]{t}") for t in texts]

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            # Speed-pack п.3 phase 1: machine-caught pairs (glue id 1, codes
            # id 2) never reach the LLM scan — only the LLM-only pair 3 is
            # routed to the full verdict scan.
            return [{"id": 3}]
        # phase 2: full verdicts for the flagged pair
        return [{"id": 3, "category": "STYLE", "severity": "soft",
                 "issue": "caps", "suggested": "Открой карту мира"}]

    orig_send = core._qa_send
    orig_load = core.load_vanilla_glossary
    core._qa_send = fake_send
    core.load_vanilla_glossary = lambda: {}
    try:
        logs = []
        pairs = {
            "Craft the Technium Part": "Craft the Technium Part",   # script pre-check: not_target_lang
            "Smelt the ore": "Переплавь руду руду",                 # machine: glue (LLM overlap)
            "Craft &lLead&r Ingot": "Создай Lead Ingot",            # machine: codes
            "Open the map": "Открой карту",                         # LLM-only soft
        }
        cfg = qa_config(tempfile.gettempdir())
        cache = FakeCache()
        run_qa_phase(pairs, cfg, Tr(), cache, logs.append, None)
    finally:
        core._qa_send = orig_send
        core.load_vanilla_glossary = orig_load

    # machine retranslations won
    assert pairs["Smelt the ore"] == "Переплавь руду", pairs
    assert pairs["Craft &lLead&r Ingot"] == "[retried]Craft &lLead&r Ingot", pairs
    assert pairs["Craft the Technium Part"] == "[retried]Craft the Technium Part", pairs
    # LLM-only verdict still applied (phase 2)
    assert pairs["Open the map"] == "Открой карту мира", pairs
    # Speed-pack п.3: machine-caught + script-fixed pairs are EXCLUDED from
    # the LLM scan (their LLM verdicts would be dropped anyway). The full-copy
    # pair is caught by the script pre-check (not_target_lang) BEFORE the
    # machine scan, so the machine itself sees only 2 pairs.
    assert any("excluded from the LLM scan" in l for l in logs), logs
    assert any("machine scan (tier B): 1 CODES_MISMATCH, 1 GLUE_ARTIFACT" in l for l in logs), logs
    cm = [l for l in logs if "catch-matrix" in l]
    assert cm and "machine 2 pair(s) deterministic" in cm[0] and "flagged 1" in cm[0], cm


# --- ТЗ-dataset: writer schema -------------------------------------------------
def test_dataset_writer_schema(tmp_path):
    import json as _json
    orig_dir = core.DATASET_DIR
    core.DATASET_DIR = tmp_path
    try:
        w = core.QADataSetWriter("/some/pack root", {"pack": "Pack", "model": "m"})
        for i in range(3):
            w.add({"pair_id": i, "source": f"s{i}", "mt": f"m{i}", "final": None,
                   "machine": [], "llm": [], "action": "clean", "retry": None})
        n = w.finish()
        assert n == 3, n
        lines = w.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4, lines
        meta = _json.loads(lines[0])
        assert meta["meta"] is True and meta["model"] == "m", meta
        rec = _json.loads(lines[1])
        for k in ("pair_id", "source", "mt", "final", "machine", "llm", "action", "retry"):
            assert k in rec, (k, rec)
        assert rec["action"] == "clean" and rec["final"] is None
    finally:
        core.DATASET_DIR = orig_dir


# --- ТЗ-dataset: dead path never breaks the run -------------------------------
def test_dataset_writer_dead_path(tmp_path):
    core.DATASET_DIR = tmp_path / "proc" / "not" / "writable" / "denied"
    # NOTE: unlike tmp_path itself, a missing tree that CANNOT be created is
    # hard to guarantee portably; /proc/1/root/xxx is used on Linux instead.
    import sys as _sys
    if _sys.platform.startswith("linux"):
        core.DATASET_DIR = __import__("pathlib").Path("/proc/1/root/definitely_denied_ds")
    logs = []
    w = core.QADataSetWriter("/pack", {"pack": "P"}, logger=logs.append)
    w.add({"pair_id": 0})
    assert w.finish() is None
    assert any("dataset writer disabled" in l for l in logs), logs
    # after the failure adds are silent, no second warning
    w.add({"pair_id": 1})
    w.finish()
    assert len([l for l in logs if "disabled" in l]) == 1, logs
    core.DATASET_DIR = __import__("pathlib").Path.home() / ".snbt-tr" / "datasets"


# --- ТЗ-dataset: e2e through run_qa_phase --------------------------------------
def test_dataset_e2e_records(tmp_path):
    import json as _json
    core.DATASET_DIR = tmp_path
    try:
        srcs = {
            "Clean pair here": "Чистая пара",
            "The &lImporter&r connects": "&lИмпортёр подключает&r",
        }
        pairs = {
            "Clean pair here": "Чистая пара",
            "The &lImporter&r connects": "Импортёр подключается",   # codes lost -> machine
        }
        llm = [{"id": 1, "category": "STYLE", "severity": "soft",
                "issue": "style fix", "suggested": "&lИмпортёр подключает&r"}]

        async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, phase="main", **kwargs):
            if ids_only:
                return [{"id": p["id"]} for p in batch]
            # ТЗ-v4 D10: pass-2 rescans the retranslated pair; this legacy
            # test asserts the retranslate result is the FINAL one, so the
            # fake answers "clean" for the pass-2 scan.
            if phase == "pass2":
                return []
            return llm if any(p["id"] == 1 for p in batch) else []

        orig_send = core._qa_send
        core._qa_send = fake_send
        try:
            logs = []
            tr = make_translator_stub()
            cache = FakeCache()
            cfg = qa_config(str(tmp_path), modpack_root=str(tmp_path))
            cfg["dataset"] = True
            run_qa_phase(pairs, cfg, tr, cache, logs.append, None)
        finally:
            core._qa_send = orig_send

        # machine caught the lost codes on pair 1: retranslated (stub)
        assert pairs["The &lImporter&r connects"] == "[retried]The &lImporter&r connects", pairs
        files = list(tmp_path.rglob("*.jsonl"))
        assert len(files) == 1, files
        lines = files[0].read_text(encoding="utf-8").splitlines()
        recs = [_json.loads(l) for l in lines if not _json.loads(l).get("meta")]
        assert len(recs) == 2, recs
        by_src = {r["source"]: r for r in recs}
        clean = by_src["Clean pair here"]
        assert clean["action"] == "clean" and clean["final"] is None and clean["machine"] == []
        # machine-caught pair: action retranslated, mt->final differ
        m = by_src["The &lImporter&r connects"]
        assert m["action"] == "retranslated", m
        assert m["mt"] == "Импортёр подключается" and m["final"] == "[retried]The &lImporter&r connects", m
        assert m["machine"] and m["machine"][0]["category"] == "CODES_MISMATCH", m
        # LLM verdict on the machine-caught id was dropped; it must not be
        # listed as a trusted llm finding on the record
        assert m["llm"] == [], m
        assert any("dataset:" in l and "records" in l for l in logs), logs
    finally:
        core.DATASET_DIR = __import__("pathlib").Path.home() / ".snbt-tr" / "datasets"



# --- Speed-pack п.4: verdict cache --------------------------------------------
def _vcache_class_for(tmp_path):
    """QAVerdictCache with the sqlite default redirected into tmp_path.

    Subclassing (not monkeypatching __init__) keeps the class identity for
    isinstance/staticmethod access while pinning the db location away from
    the developer's real ~/.snbt-tr — and without touching os.environ.
    """
    class _SandboxedCache(core.QAVerdictCache):
        def __init__(self, db_path=None):
            super().__init__(db_path=tmp_path / "qa_cache.sqlite")
    return _SandboxedCache


def test_verdict_cache_hash_sensitivity(tmp_path):
    """Hash changes with source, translation AND config."""
    c = core.QAVerdictCache(db_path=tmp_path / "qa_cache.sqlite")
    try:
        h = core.QAVerdictCache.config_hash("model/high", 0.2, 40, "PROMPT")
        k1 = core.QAVerdictCache.key("src", "mt", h)
        k2 = core.QAVerdictCache.key("src ", "mt", h)
        k3 = core.QAVerdictCache.key("src", "mt2", h)
        h2 = core.QAVerdictCache.config_hash("model/low", 0.2, 40, "PROMPT")
        k4 = core.QAVerdictCache.key("src", "mt", h2)
        h3 = core.QAVerdictCache.config_hash("model/high", 0.2, 40, "PROMPT2")
        k5 = core.QAVerdictCache.key("src", "mt", h3)
        hb = core.QAVerdictCache.config_hash("model/high", 0.2, 40, "PROMPT")
        k6 = core.QAVerdictCache.key("src", "mt", hb)
        assert len({k1, k2, k3, k4, k5}) == 5, "hash collision across variants"
        assert k6 == k1, "same inputs must give the same key"
        assert len(k1) == 40 and all(ch in "0123456789abcdef" for ch in k1)
    finally:
        c.close()


def test_verdict_cache_clean_skip_and_changed_line(tmp_path):
    """Run 1 audits; run 2 skips clean pairs; a changed line is re-audited."""
    import asyncio as _a

    srcs = {f"Source line {i}": f"Перевод {i}" for i in range(5)}
    scanned: list = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        scanned.extend(p["id"] for p in batch)
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    # Sandbox the sqlite location WITHOUT touching HOME/XDG (those are
    # process-wide and poison later QSettings-based tests): patch the class
    # so the default db_path lands inside tmp_path.
    orig_cls = core.QAVerdictCache
    core.QAVerdictCache = _vcache_class_for(tmp_path)
    try:
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(str(tmp_path), modpack_root=str(tmp_path))
        cfg["verdict_cache"] = True

        logs1 = []
        run_qa_phase(dict(srcs), cfg, tr, cache, logs1.append, None)
        assert sorted(scanned) == [0, 1, 2, 3, 4], scanned
        assert any("marked clean" in l for l in logs1), logs1
        assert not any("skipped in phase 1" in l for l in logs1), logs1

        # Run 2: identical input — the phase-1 scan sees nothing
        scanned.clear()
        logs2 = []
        run_qa_phase(dict(srcs), cfg, tr, cache, logs2.append, None)
        assert scanned == [], scanned
        assert any("clean pair(s) skipped in phase 1" in l for l in logs2), logs2

        # Run 3: change one translation — only that pair is scanned
        changed = dict(srcs)
        changed["Source line 2"] = "Изменённая строка 2"
        scanned.clear()
        logs3 = []
        run_qa_phase(changed, cfg, tr, cache, logs3.append, None)
        assert scanned == [2], scanned
        assert any("4 clean pair(s) skipped in phase 1" in l for l in logs3), logs3
    finally:
        core._qa_send = orig_send
        core.QAVerdictCache = orig_cls


def test_verdict_cache_disabled_full_scan(tmp_path):
    """verdict_cache=False -> no sqlite, no skips: behaviour identical to the
    pre-cache pipeline (every pair goes to phase 1)."""
    srcs = {"A line": "Перевод", "B line": "Вторая"}
    scanned: list = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, ids_only=False, **kwargs):
        scanned.extend(p["id"] for p in batch)
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    orig_cls = core.QAVerdictCache
    core.QAVerdictCache = _vcache_class_for(tmp_path)
    try:
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(str(tmp_path), modpack_root=str(tmp_path))
        cfg["verdict_cache"] = False

        for run in range(2):
            scanned.clear()
            logs = []
            run_qa_phase(dict(srcs), cfg, tr, cache, logs.append, None)
            assert sorted(scanned) == [0, 1], (run, scanned)
            assert not any("skipped in phase 1" in l for l in logs), (run, logs)
        assert not (tmp_path / ".snbt-tr" / "qa_cache.sqlite").exists()
    finally:
        core._qa_send = orig_send
        core.QAVerdictCache = orig_cls



# --- Speed-pack п.5: pass-2 rescans soft fixes too -----------------------------
def test_pass2_rescans_soft_fixed(tmp_path):
    """A soft-fixed pair goes to the pass-2 rescan together with the hard
    retranslated ones (and is rescanned once even if touched twice)."""
    scanned: list = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger, check_status, temperature=None, phase="main", batch_label="0", ids_only=False, **kwargs):
        if check_status:
            await check_status()
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        if phase == "pass2":
            scanned.extend(p["id"] for p in batch)
            return []
        probs = []
        for p in batch:
            if p["id"] == 0:
                probs.append({"id": 0, "category": "STYLE", "severity": "soft",
                              "issue": "bad style", "suggested": f"Стиль {p['source']}"})
            if p["id"] == 1:
                probs.append({"id": 1, "category": "UNTRANSLATED", "severity": "hard",
                              "issue": "english left", "suggested": None})
        return probs

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        pairs = {"Src 0": "Перевод 0", "Src 1": "Перевод 1", "Src 2": "Перевод 2"}
        run_qa_phase(pairs, cfg, tr, cache, log, None)
        assert sorted(scanned) == [0, 1], scanned
        assert any("rescanning 2 changed pair(s) (1 retranslated, 1 soft-fixed)" in l for l in lines), lines
        # the soft fix itself was applied
        assert pairs["Src 0"] == "Стиль Src 0", pairs
    finally:
        core._qa_send = orig_send



# --- Нит 1 (m11236): arbitration chunks of 40 through a workerpool --------------
def test_arb_chunks_of_40_and_parallel_keys():
    """278 flagged pairs -> 7 arb batches of 40; workers with separate keys;
    every _qa_scan_pairs call sees <= 40 pairs and gets ONE key."""
    from core import _QA_ARB_CHUNK
    assert _QA_ARB_CHUNK == 40
    arb_calls = []          # (len(batch), keys, batch_label)
    n_flagged = 278

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            return []       # nobody flagged in phase 1
        if phase == "arb":
            arb_calls.append((len(batch), list(keys), batch_label))
            # verdicts use PER-BATCH ids: answer for the first pair of the chunk;
            # the suggested fix keeps the source's number so the validation gate
            # (_qa_multisets) accepts it
            first = batch[0]
            m = re.search(r"(\d+)$", first["source"])
            suffix = m.group(1) if m else ""
            return [{"id": first["id"], "category": "TERM_INCONSISTENT",
                     "severity": "soft", "issue": "pin missed",
                     "suggested": f"Создай Свинец слиток {suffix}".strip()}]
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        # ТЗ-v4.3 B.4: the pre-check enforces the MODPACK glossary only
        tr.modpack_glossary_terms = {"Lead": "Свинец"}
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        # 278 pairs, every one misses the 'Lead' pin -> flagged by the pre-check
        pairs = {f"Craft the Lead Ingot {i}": f"Создай слиток {i}" for i in range(n_flagged)}
        cfg = dict(cfg)
        cfg["keys"] = ["key-AAAA", "key-BBBB", "key-CCCC"]
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    # 7 chunks of up to 40 (278 = 6*40 + 38)
    sizes = sorted(c[0] for c in arb_calls)
    assert sizes == [38] + [40] * 6, sizes
    # every arb call got exactly ONE key (workerpool semantics)
    assert all(len(c[1]) == 1 for c in arb_calls), arb_calls
    # batch labels are 1..7
    labels = sorted(int(c[2]) for c in arb_calls)
    assert labels == list(range(1, 8)), labels
    # log mentions the chunked arbitration
    assert any("arbitrating (7 batch(es) of up to 40)" in l for l in lines), lines
    # ids are global: each chunk's verdict applied to ITS first pair
    for i in (0, 40, 80, 120, 160, 200, 240):
        assert pairs[f"Craft the Lead Ingot {i}"] == f"Создай Свинец слиток {i}", (i, pairs[f"Craft the Lead Ingot {i}"])
    # non-first pairs keep their translations (verdicts answered only for the first)
    assert pairs["Craft the Lead Ingot 1"] == "Создай слиток 1", pairs["Craft the Lead Ingot 1"]


def test_arb_single_chunk_still_works():
    """A small flagged set (1 chunk) keeps the old single-call semantics."""
    arb_calls = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None,
                        phase="main", batch_label="0", ids_only=False, **kwargs):
        if ids_only:
            return []
        if phase == "arb":
            arb_calls.append((len(batch), list(keys)))
            return [{"id": batch[0]["id"], "category": "TERM_INCONSISTENT",
                     "severity": "soft", "issue": "Lead must be Свинец",
                     "suggested": "Создай Свинец слиток"}]
        return []

    orig_send = core._qa_send
    core._qa_send = fake_send
    try:
        log, lines = collect_logs(None)
        tr = make_translator_stub()
        # ТЗ-v4.3 B.4: the pre-check enforces the MODPACK glossary only
        tr.modpack_glossary_terms = {"Lead": "Свинец"}
        cache = FakeCache()
        cfg = qa_config(tempfile.gettempdir())
        pairs = {"Craft the Lead Ingot": "Создай Свинцовый слиток"}
        run_qa_phase(pairs, cfg, tr, cache, log, None)
    finally:
        core._qa_send = orig_send

    assert arb_calls == [(1, ["test-key"])], arb_calls
    assert pairs["Craft the Lead Ingot"] == "Создай Свинец слиток", pairs
    assert any("arbitrating (1 batch(es) of up to 40)" in l for l in lines), lines


# --- Нит 2 (m11236): the pin-position line is in the translation prompt ---------
def test_translation_prompt_has_pin_position_rule():
    from core import UnifiedTranslator
    tr = UnifiedTranslator(api_keys=["k"], provider="Crusoe Cloud",
                           model="m", target_lang_name="Russian")
    assert ("Glossary pins translate ONLY their matching source terms"
            in tr.prompt), tr.prompt[-400:]
    # the line sits between the no-duplication rule and the Latin-spacing rule
    i_pin = tr.prompt.index("Glossary pins translate ONLY")
    i_dup = tr.prompt.index("Each source term appears exactly ONCE")
    i_lat = tr.prompt.index("Keep the word spacing of untranslated Latin names")
    assert i_dup < i_pin < i_lat


def test_travel_anchors_battery_prompt_assembly():
    """Батарея 'Travel Anchors and Staff': the assembled effective prompt
    carries BOTH the pin rule and the batch-local pins — the model must not
    insert Энтро-пыль anywhere except its own term positions."""
    import core as c
    # vanilla glossary has Entro-Dust pinned as Энтро-пыль in this battery
    gloss = {"Entro-Dust": "Энтро-пыль", "Travel Anchors and Staff": "Маяки и посох путешествий"}
    texts = ["Craft Travel Anchors and Staff from Entro-Dust"]
    suffix = c.build_glossary_context(texts, gloss, limit=40,
                                       label="Official Minecraft terminology")
    assert "Entro-Dust=Энтро-пыль" in suffix, suffix
    assert "Travel Anchors and Staff=Маяки и посох путешествий" in suffix, suffix
    # the base prompt + suffix assembly keeps the pin-position rule
    from core import UnifiedTranslator
    tr = UnifiedTranslator(api_keys=["k"], provider="Crusoe Cloud",
                           model="m", target_lang_name="Russian")
    effective = tr.prompt + suffix
    assert "Glossary pins translate ONLY their matching source terms" in effective
    # build_user_content keeps it all together
    uc = c.build_user_content(effective, texts, "chapter.snbt")
    assert "Glossary pins translate ONLY" in uc
    assert "Entro-Dust=Энтро-пыль" in uc


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
