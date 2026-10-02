# -*- coding: utf-8 -*-
"""ТЗ-v4.3 «Вердикт-конвейер»: морфология пре-чека (A), источник пинов (B),
repair-канал (C).

Реальный инцидент 02.10 13:37: пре-чек глоссария отфлаговал 185 пар, арбитр
вернул 185 crippled-вердиктов, repair переиздал 0 — мягкий канал доставлял
ноль, потому что ~99% флагов были морфологически слепыми ложными
срабатываниями, а строгий фильтр ответа repair выбрасывал эхо-ответ целиком.

Экономика (тот самый корпус 185 пар из repair-дампа):
    было (оба глоссария + regex-стемы)      185 флагов
    стало (только modpack + pymorphy3)       43 флага
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


# ---------- A.1/A.2: морфология пре-чека -------------------------------------

# формулировки ТЗ v4.3 A.2: склонения пинов НЕ флаг, реальные отклонения — флаг
_MODPACK = {
    "Nether": "Незер",
    "Ore Pieces": "Кусочки руды",
    "Lapis Lazuli": "Лазурит",
    "Power": "Сила",
    "Villager": "Жители",
}


@pytest.mark.parametrize("source,translation", [
    ("Mine the Nether Ruby", "Добудь Незерного Рубина"),          # незер+ного (4 буквы)
    ("Collect copper Ore Pieces", "Собери Кусочков медной руды"),  # кусочк+ов
    ("Find some Lapis Lazuli", "Найди немного Лазурита"),          # лазурит+а
    ("Gather Nether Quartz", "Собери Незерского кварца"),
    ("Smelt the Ore Pieces now", "Переплавь Кусочки руды сейчас"),
])
def test_v43_a_no_flag_on_pin_inflections(source, translation):
    flagged = core._qa_glossary_violations(
        [{"id": 0, "source": source, "translation": translation}], {}, _MODPACK)
    assert flagged == [], flagged


@pytest.mark.parametrize("source,translation,pin", [
    ("Unleash all the Power", "Вся мощь", "Power"),
    ("A Villager walks by", "Крестьянин идёт", "Villager"),
    ("The Power is out", "Энергия кончилась", "Power"),
])
def test_v43_a_flag_on_real_deviation(source, translation, pin):
    flagged = core._qa_glossary_violations(
        [{"id": 0, "source": source, "translation": translation}], {}, _MODPACK)
    assert [f["id"] for f in flagged] == [0], flagged
    assert [en for en, _ in flagged[0]["missed_pins"]] == [pin], flagged[0]


def test_v43_a_pymorphy_normal_forms_available():
    """pymorphy3 стоит в зависимостях — морфология обязана быть настоящей."""
    assert core._qa_morph_analyzer() is not None, "pymorphy3 не установлен"
    forms = core._qa_normal_forms("Незерного")
    assert "незерный" in forms, forms
    assert core._qa_normal_forms("Кусочков") & core._qa_normal_forms("Кусочки")
    # падеже-толерантность: разные падежи одного слова совпадают
    assert core._qa_normal_forms("Лазурита") & core._qa_normal_forms("Лазурит")
    assert core._qa_normal_forms("Силы") & core._qa_normal_forms("Сила")


def test_v43_a_prefix_fallback_without_pymorphy(monkeypatch):
    """Без словаря остаётся префиксное совпадение ≥5 символов."""
    monkeypatch.setattr(core, "_QA_MORPH", None)
    monkeypatch.setattr(core, "_QA_MORPH_TRIED", True)
    monkeypatch.setattr(core, "_QA_MORPH_CACHE", {})
    # префикс «незер» (5) -> Незерного признаётся формой пина
    assert core._qa_ru_pin_present("Незер", "Добудь Незерного Рубина")
    # короткие слова префиксом не матчатся: «Свет» != «светло»
    assert not core._qa_ru_pin_present("Свет", "стало светло")
    monkeypatch.undo()


def test_v43_a_short_pin_outside_capitalised_phrase():
    """Короткий пин внутри длинной капитализированной фразы — не термин."""
    mp = {"Light": "Свет", "Stone": "Камень", "Table": "Стол", "Lead": "Свинец"}
    batch = [
        {"id": 0, "source": "Portal from &lWhite Light&r", "translation": "Портал из белого света"},
        {"id": 1, "source": "Make &lEnd Stone&r", "translation": "Сделай эндерняк"},
        {"id": 2, "source": "Make &lLead&r (2x)", "translation": "Сделай &lПоводок&r (2x)"},
        {"id": 3, "source": "Craft the Lead Ingot", "translation": "Создай Свинцовый слиток"},
    ]
    flagged = core._qa_glossary_violations(batch, {}, mp)
    assert [f["id"] for f in flagged] == [2, 3], flagged


def test_v43_a_english_term_kept_is_not_a_miss():
    """Термин, который переводчик осознанно оставил латиницей, — не пропуск."""
    mp = {"Storage": "Хранилище", "Techopolis": "Технополис"}
    batch = [{"id": 0, "source": "Unlocks Toms Storage, allows crafting",
              "translation": "Открывает Toms Storage, позволяет крафтить"}]
    assert core._qa_glossary_violations(batch, {}, mp) == []


def test_v43_a_resource_tags_are_not_prose():
    """#namespace:path не должен читаться как упоминание пина."""
    mp = {"Planks": "Доски", "Nether": "Незер"}
    batch = [{"id": 0, "source": "Any #techopolis:nether_planks",
              "translation": "Любой #techopolis:nether_planks"}]
    assert core._qa_glossary_violations(batch, {}, mp) == []


def test_v43_a_munching_longest_pin_wins():
    """Пин, вложенный в более длинный пин, не даёт отдельного флага."""
    mp = {"Table": "Стол", "Crafting Table": "Верстак"}
    batch = [{"id": 0, "source": "A huge 9x9 &lCrafting Table&r here",
              "translation": "Огромный &lВерстак&r тут"}]
    assert core._qa_glossary_violations(batch, {}, mp) == []


def test_v43_a_acceptance_corpus_under_40():
    """Приёмка: на реальном корпусе инцидента флагов ≤ 40 (было 185)."""
    dump_dir = os.path.expanduser("~/.snbt_localizer/logs/qa_dump")
    import glob
    corpus = {}
    for path in glob.glob(os.path.join(dump_dir, "20261002_1357*repair*")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        for item in data:
            if isinstance(item, dict) and item.get("source") and item.get("translation"):
                corpus[item["source"]] = item["translation"]
    if len(corpus) < 50:
        pytest.skip("дампы инцидента недоступны")
    glossary_path = os.path.expanduser("~/.snbt-tr/glossaries/minecraft_a64392edbc.json")
    if not os.path.exists(glossary_path):
        pytest.skip("modpack-глоссарий инцидента недоступен")
    with open(glossary_path, encoding="utf-8") as fh:
        terms = json.load(fh)["terms"]
    vanilla_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "resources", "vanilla_ru.json")
    with open(vanilla_path, encoding="utf-8") as fh:
        vanilla = json.load(fh)
    batch = [{"id": i, "source": s, "translation": t}
             for i, (s, t) in enumerate(corpus.items())]
    # production calls it exactly like this: load_vanilla_glossary() + the
    # modpack terms — vanilla as a WITNESS, modpack as the enforcer
    flagged = core._qa_glossary_violations(batch, vanilla, terms)
    assert len(flagged) <= 40, f"пре-чек снова флудит: {len(flagged)}/{len(batch)}"
    # и он ещё и не молчит: настоящие пропуски пинов остаются видны
    pins = {en for f in flagged for en, _ in f["missed_pins"]}
    assert {"Grass Block", "Ore Pieces", "Blaze"} & pins, pins


# ---------- B.3/B.4/B.5: источник пинов, только modpack, предохранитель ------

def test_v43_b_vanilla_glossary_is_not_enforced():
    """B.4: vanilla — только prompt-подсказка, не источник флагов."""
    vanilla = {"Power": "Сила", "Villager": "Крестьянин", "Lead": "Поводок"}
    batch = [{"id": 0, "source": "Use the Power of the Villager",
              "translation": "Используй мощь крестьянина"}]
    assert core._qa_glossary_violations(batch, vanilla, {}) == []
    assert core._qa_glossary_violations(batch, {}, {}) == []


def test_v43_b_origin_is_logged():
    """B.3: каждая строка лога говорит, откуда пин."""
    mp = {"Power": "Сила", "Nether": "Незер"}
    flagged = core._qa_glossary_violations(
        [{"id": 0, "source": "Unleash all the Power", "translation": "Вся мощь"}], {}, mp)
    assert flagged, "флаг обязателен для этой пары"
    assert flagged[0]["pin_origins"] == {"Power": "modpack"}, flagged[0]
    lines = []
    core._qa_log_pin_origins(flagged, lines.append)
    assert any("pin 'Power' from: modpack" in l for l in lines), lines
    assert any("flagged 1 pair(s) — pin sources: modpack: 1 pin(s)" in l for l in lines), lines


def test_v43_b_suspicious_fuse_logs_but_keeps_flags(tmp_path):
    """B.5: >50 флагов за прогон — строка SUSPICIOUS, флаги не отбрасываются."""
    import tests.test_qa_phase as tq

    n = core._QA_FLAG_SUSPICIOUS + 3

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if ids_only:
            return []
        return []

    pairs = {f"Ship the Power core {i}": f"Отправь ядро {i}" for i in range(n)}
    tr = tq.make_translator_stub()
    tr.modpack_glossary_terms = {"Power": "Сила"}
    cfg = tq.qa_config(str(tmp_path), update_glossary=False)
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tr, tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert any(f"glossary pre-check flagged {n}" in l for l in lines), lines
    assert any(f"SUSPICIOUS (>{core._QA_FLAG_SUSPICIOUS})" in l for l in lines), lines


# ---------- C.6/C.7/C.8: repair-канал ----------------------------------------

def _repair_candidates(n=3):
    return [{"id": i, "source": f"Craft the Lead Ingot {i}",
             "translation": f"Создай слиток {i}",
             "note": "glossary pin missing from the translation"}
            for i in range(n)]


def test_v43_c_echo_answer_is_not_dropped():
    """C.7: эхо входного массива (id+note+source+translation) больше не теряется."""
    cands = _repair_candidates(3)
    echo = json.dumps([{"id": c["id"], "note": c["note"], "source": c["source"],
                        "translation": c["translation"]} for c in cands], ensure_ascii=False)
    out = core._qa_repair_answer(cands, echo)
    # эхо повторяет ТЕКУЩИЙ перевод -> ничего не «исправлено», но и не выброшено:
    # записи доходят до нормализации и становятся warning'ами
    probs = core._qa_normalize_problems(out, cands, {})
    assert len(probs) == 3, probs
    assert all(p["severity"] == "warning" for p in probs), probs


def test_v43_c_plain_replacement_map_is_used():
    """C.7: {id, translation} без схемы -> soft-фикс через обычный гейт."""
    cands = _repair_candidates(2)
    answer = json.dumps([{"id": 0, "translation": "Создай Свинец слиток 0"},
                         {"id": 1, "translation": "Создай Свинец слиток 1"}], ensure_ascii=False)

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if ids_only:
            return []
        if phase == "arb":
            return []
        if phase == "repair":
            return json.loads(answer)
        return []

    import tests.test_qa_phase as tq
    pairs = {c["source"]: c["translation"] for c in cands}
    tr = tq.make_translator_stub()
    tr.modpack_glossary_terms = {"Lead": "Свинец"}
    cfg = tq.qa_config(None, update_glossary=False)
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tr, tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert pairs["Craft the Lead Ingot 0"] == "Создай Свинец слиток 0", pairs
    assert pairs["Craft the Lead Ingot 1"] == "Создай Свинец слиток 1", pairs
    assert any("re-issued" in l for l in lines), lines
    assert not any("0/2 re-issued" in l for l in lines), lines


def test_v43_c_bare_strings_aligned_positionally():
    cands = _repair_candidates(2)
    out = core._qa_repair_answer(cands, json.dumps(["Создай Свинец слиток 0",
                                                    "Создай Свинец слиток 1"]))
    assert sorted(p["id"] for p in out) == [0, 1], out
    assert all(p["severity"] == "soft" for p in out), out


def test_v43_c_source_map_shape_is_not_duplicated():
    """{source: translation} без id -> РОВНО один вердикт, не два."""
    cands = _repair_candidates(1)
    out = core._qa_repair_answer(cands, json.dumps([{cands[0]["source"]: "Слиток Свинца"}]))
    assert [p["id"] for p in out] == [0], out
    assert out[0]["severity"] == "soft" and out[0]["suggested"] == "Слиток Свинца", out


def test_v43_c_idless_schema_answer_is_positional():
    """Полностью без-id схема ровно по числу кандидатов -> ids по порядку."""
    cands = _repair_candidates(2)
    answer = json.dumps([{"category": "GLOSSARY_VIOLATION", "severity": "soft",
                          "issue": "pin 0", "suggested": "Слиток 0"},
                         {"category": "GLOSSARY_VIOLATION", "severity": "soft",
                          "issue": "pin 1", "suggested": "Слиток 1"}], ensure_ascii=False)
    out = core._qa_repair_answer(cands, answer)
    assert sorted(p["id"] for p in out) == [0, 1], out
    assert all(p.get("category") for p in out), out


def test_v43_c_full_schema_passes_through():
    cands = _repair_candidates(1)
    answer = json.dumps([{"id": 0, "category": "TERM_INCONSISTENT", "severity": "soft",
                          "issue": "pin missed", "suggested": "Создай Свинец слиток"}],
                        ensure_ascii=False)
    out = core._qa_repair_answer(cands, answer)
    assert len(out) == 1 and out[0]["category"] == "TERM_INCONSISTENT", out
    probs = core._qa_normalize_problems(out, cands, {})
    assert probs[0]["severity"] == "soft" and probs[0]["suggested"] == "Создай Свинец слиток", probs


def test_v43_c_zero_reissued_warning(tmp_path):
    """C.8: пустой ответ repair при N>0 входных — явный warning."""
    import tests.test_qa_phase as tq

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if ids_only:
            return []
        if phase == "arb":
            return []
        return []          # repair отвечает пустотой

    pairs = {"Craft the Lead Ingot": "Создай Свинцовый слиток"}
    tr = tq.make_translator_stub()
    tr.modpack_glossary_terms = {"Lead": "Свинец"}
    cfg = tq.qa_config(None, update_glossary=False)
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tr, tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert any("repair: 0/1 re-issued" in l for l in lines), lines


def test_v43_c_repair_request_and_answer_are_dumped(tmp_path, monkeypatch):
    """C.6: в дампе есть И запрос И ответ repair-фазы."""
    import tests.test_qa_phase as tq
    monkeypatch.setenv("SNBT_QA_DEBUG", "1")
    monkeypatch.setattr(core, "_QA_DUMP_DIR", tmp_path / "qa_dump")

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if ids_only:
            return []
        if phase == "arb":
            return []
        if phase == "repair":
            core._qa_dump_raw(phase, batch_label, "[]")
            return []
        return []

    pairs = {"Craft the Lead Ingot": "Создай Свинцовый слиток"}
    tr = tq.make_translator_stub()
    tr.modpack_glossary_terms = {"Lead": "Свинец"}
    cfg = tq.qa_config(None, update_glossary=False)
    log, _lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tr, tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    dumps = [p.name for p in (tmp_path / "qa_dump").glob("*.json")]
    assert any("repair_req" in n for n in dumps), dumps
    assert any(n.split("_", 2)[2].startswith("repair_") and "req" not in n for n in dumps), dumps
