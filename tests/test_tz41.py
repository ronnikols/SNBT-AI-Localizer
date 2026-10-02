# -*- coding: utf-8 -*-
"""ТЗ-v4.1: гигиена пин-экстрактора (G13) и одноключевая живучесть (F12).

G13 — реальный инцидент: в глоссарий утекли 22 мусорных пина, среди них
ядовитые. Батарея 13.4: все они обязаны быть ОТВЕРГНУТЫ, валидные — пройти.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


# ---------- G13.4: батарея мусорных пинов из инцидента -----------------------

JUNK_PINS = [
    ("and", "Энтро-пыль"),                                  # союз!
    ("not", "Сделки с жителями отключены"),
    ("the", "Что-то"),
    ("with", "Чем-то"),
    ("from", "Откуда-то"),
    ("when", "Когда-то"),
    ("this", "Этот"),
    ("well", "Хорошо"),
    ("never", "Никогда"),
    ("Created", "Этот предмет был создан для крафта брони"),
    ("made", "Сделанный предмет"),
    ("used", "Используется для чего-то"),
    ("Smelted", "Переплавленный плод хоруса"),
    ("obtained", "Полученный предмет"),
    ("found", "Найденный предмет"),
    ("Dimensional Ore", "Размерных р"),                     # обрывок
    ("Ender Crafter", "Коксовая печь"),                     # другой смысл
    ("Lapis", "пал"),                                       # обрывок
    ("coal", "Угольного шахтёра"),                          # склонённая форма
    ("Coal Miner", "Угольного шахтёра"),
    ("Armor", "Доспехам"),                                  # дательный падеж
    ("Wither", "визеров"),                                  # мн.ч. род.
    ("cloches", "колпаки"),                                 # неверный термин
    ("Villager", "Крестьянин"),                             # неверный смысл
    ("Power", "Сила"),                                      # неверный смысл
]


@pytest.mark.parametrize("en,ru", JUNK_PINS)
def test_g13_junk_pins_rejected(en, ru):
    """13.4: каждый мусорный пин из отчёта обязан быть отвергнут с причиной."""
    reason = core._qa_pin_reject_reason(en, ru)
    assert reason, f"мусорный пин пропущен: {en!r} -> {ru!r}"


VALID_PINS = [
    ("Cloche", "Клош"),
    ("Grout", "Раствор"),
    ("Wither", "Визер"),
    ("Ender Crafter", "Крафтер Энда"),
    ("Dimensional Ore", "Пространственная руда"),
    ("Lapis Lazuli", "Лазурит"),
    ("Coal", "Уголь"),
    ("Villager", "Житель"),
    ("Power", "Энергия"),
    ("Blast Furnace", "Доменная печь"),
    ("Entro Dust", "Энтропийная пыль"),
    ("Chorus Fruit", "Плод хоруса"),
]


@pytest.mark.parametrize("en,ru", VALID_PINS)
def test_g13_valid_pins_pass(en, ru):
    """13.4: валидные термины обязаны проходить фильтр."""
    assert core._qa_pin_reject_reason(en, ru) == "", f"валид отвергнут: {en!r} -> {ru!r}"


def test_g13_extractor_rejects_junk_from_prose():
    """13.1: экстрактор из прозы не отдаёт ядовитые пары."""
    text = ("The word 'and' should be 'Энтро-пыль' here. "
            "Standardize 'Dimensional Ore' as 'Размерных р'. "
            "Unify 'Cloche' as 'Клош'.")
    pins = core._qa_extract_glossary_pins(text, None, "and Dimensional Ore Cloche")
    pairs = dict(pins)
    assert "and" not in pairs
    assert "Dimensional Ore" not in pairs
    assert pairs.get("Cloche") == "Клош"


def test_g13_extractor_requires_term_in_source():
    """Пин обязан относиться к этой паре: en встречается в source."""
    pins = core._qa_extract_glossary_pins(
        "Unify 'Wither' as 'Визер'", None, "A plain stone block")
    assert pins == []


def test_g13_rule_length_cap():
    """13.3: ru не длиннее en ×3."""
    assert core._qa_pin_reject_reason("Created", "Это очень длинное предложение целиком") != ""
    assert core._qa_pin_reject_reason("Coal", "Уголь") == ""


# ---------- G13.2: правка пина только с валидной парой -----------------------

def test_g13_pin_write_revalidates_pair(tmp_path):
    """13.2: _qa_add_glossary_pins НЕ пишет мусорную пару даже при correction."""
    root = tmp_path / "pack"
    root.mkdir()
    logs = []
    core._QA_COUNTERS.update({"glossary": 0, "warnings": 0})
    core._qa_add_glossary_pins([("and", "Энтро-пыль")], 1, logs.append,
                               True, str(root), allow_correction=True)
    gloss = core.ModpackGlossary(str(root))
    assert "and" not in gloss.terms, "ядовитый пин записан в глоссарий!"
    assert core._QA_COUNTERS["warnings"] == 1
    assert any("rejected" in str(l) for l in logs)


def test_g13_pin_write_accepts_valid(tmp_path):
    root = tmp_path / "pack"
    root.mkdir()
    core._QA_COUNTERS.update({"glossary": 0, "warnings": 0})
    core._qa_add_glossary_pins([("Cloche", "Клош")], 1, lambda m: None,
                               True, str(root))
    gloss = core.ModpackGlossary(str(root))
    assert gloss.terms.get("Cloche") == "Клош"
    assert core._QA_COUNTERS["glossary"] == 1


# ---------- F12: одноключевая живучесть --------------------------------------

@pytest.fixture(autouse=True)
def _reset_health_state():
    core.health_reset()
    yield
    core.health_reset()


def test_f12_1_single_key_two_timeouts_no_bench_then_success():
    """12.4(а): пул=1, 2 таймаута, 3-й ок → QA завершён, бенча НЕТ."""
    core.health_set_pool_size(1)
    k = "cs_single_key_0001"
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    assert not core.health_is_benched(k), "пул=1: таймауты не должны бенчить ключ"
    assert core.health_cooldown_remaining(k) > 0, "должен быть cooldown ~2 мин"
    core.health_note_request(k, 2.0)          # 3-я попытка удалась
    assert not core.health_is_benched(k)
    assert core.health_cooldown_remaining(k) == 0.0, "успех снимает cooldown"


def test_f12_1_normal_pool_still_benches():
    """Регресс: обычный пул бенчит после 2 таймаутов, как раньше."""
    core.health_set_pool_size(5)
    k = "cs_pool_key_0002"
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    assert core.health_is_benched(k)


def test_f12_1_unknown_pool_size_keeps_classic_bench():
    """_POOL_SIZE=0 (неизвестно) не должен случайно включать одноключевой режим."""
    assert core._POOL_SIZE == 0
    k = "cs_unknown_pool_0003"
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    assert core.health_is_benched(k)


def test_f12_1_single_key_all_timeouts_abort_counter():
    """12.4(б): пул=1, ВСЕ таймауты → честная смерть по счётчику."""
    core.health_set_pool_size(1)
    k = "cs_single_dead_0004"
    for _ in range(core._SINGLE_KEY_MAX_TIMEOUTS + 1):
        core.health_note_request(k, 30.0, timed_out=True)
    assert core.health_is_benched(k), "постоянно молчащий эндпоинт должен умереть"


def test_v42_bench_is_global_one_pool():
    """4.4: пул ОДИН — бенч бьёт по ключу везде (перевод и QA делят пул)."""
    core.health_set_pool_size(5)
    k = "cs_role_key_0005"
    core.health_bench_now(k, "dead")
    assert core.health_is_benched(k), "забенченный ключ обязан быть вне ротации везде"


def test_v42_summary_counts_benched():
    """[POOL] summary считает забенченные ключи (одна семантика)."""
    core.health_set_pool_size(5)
    k = "cs_summary_key_0007"
    core.health_note_request(k, 1.0)
    core.health_bench_now(k, "judge died")
    lines = core.health_summary_lines()
    assert any("benched" in l for l in lines), lines
    assert "1 key(s) benched" in lines[-1]
    assert core.health_totals()["benched_keys"] == 1


def test_f12_1_cooldown_wait_helper():
    """_qa_cooldown_wait берёт максимум из базовой паузы и cooldown ключа."""
    core.health_set_pool_size(1)
    k = "cs_wait_key_0008"
    assert core._qa_cooldown_wait([k]) == core._QA_TIMEOUT_PAUSE
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    wait = core._qa_cooldown_wait([k])
    assert core._QA_TIMEOUT_PAUSE <= wait <= 180.0
    assert core.health_cooldown_remaining(k) > 0


def test_v42_shared_pool_size_drives_cooldown():
    """4.1/4.4: размер пула один — 5 ключей бенчат, 1 ключ уходит в cooldown."""
    core.health_set_pool_size(5)
    k = "cs_role_size_0009"
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    assert core.health_is_benched(k), "широкий пул обязан бенчить по 2 таймаутам"
    # а одноключевой пул — cooldown, без бенча (12.1 без role-логики)
    core.health_reset()
    core.health_set_pool_size(1)
    k2 = "cs_role_size_0010"
    core.health_note_request(k2, 30.0, timed_out=True)
    core.health_note_request(k2, 30.0, timed_out=True)
    assert not core.health_is_benched(k2)
    assert core.health_cooldown_remaining(k2) > 0


def test_v42_qa_runs_on_shared_provider_pool(tmp_path):
    """4.1/4.3: QA без собственных ключей идёт на ключах пула провайдера,
    legacy-поле «QA ключи» игнорируется с логом."""
    import asyncio
    import tests.test_qa_phase as tq

    qa_key = "cs_qa_benched_0011"
    main_key = "cs_main_alive_0012"
    used = []

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        used.append(list(keys))
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        return []

    cfg = tq.qa_config(tmp_path, update_glossary=False)
    cfg["keys"] = [qa_key]
    cfg["provider_pool"] = {"Crusoe Cloud": [main_key]}
    cfg["dataset"] = False
    cfg["verdict_cache"] = False
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase({"Some text": "Какой-то текст"}, cfg,
                          tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert used, "фаза вообще не пошла — пул провайдера не подключился"
    assert all(main_key in ks for ks in used), used
    assert all(qa_key not in ks for ks in used), used
    assert any("legacy QA key field ignored" in l for l in lines), lines
    assert any("qa pool size = 1" in l for l in lines), lines


# ---------- ТЗ-v4.2: один пул для перевода и QA ------------------------------

def _v42_cfg(tmp_path, pool, keys=None, judges=None):
    import tests.test_qa_phase as tq
    cfg = tq.qa_config(tmp_path, update_glossary=False)
    cfg["provider_pool"] = {"Crusoe Cloud": list(pool)}
    if keys is not None:
        cfg["keys"] = list(keys)
    if judges is not None:
        cfg["judges"] = judges
    cfg["dataset"] = False
    cfg["verdict_cache"] = False
    return cfg


def test_v42_1_qa_runs_parallel_on_provider_pool(tmp_path):
    """4.5(а): QA без своих ключей идёт phase-1 на N ключах пула провайдера
    ПАРАЛЛЕЛЬНО — 5 батчей на 5 ключах укладываются в ОДНУ волну таймаутов,
    а не в 5 последовательных (33 батча ≤ 110% времени перевода)."""
    import asyncio
    import tests.test_qa_phase as tq

    pool = [f"cs_pool_key_{i:04d}" for i in range(5)]
    used = []
    state = {"inflight": 0, "peak": 0}
    SLEEP = 0.15

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        used.append((tuple(keys), batch_label, phase))
        state["inflight"] += 1
        state["peak"] = max(state["peak"], state["inflight"])
        await asyncio.sleep(SLEEP)       # один сетевой круг
        state["inflight"] -= 1
        return []                        # ничего не флагуем — чистая фаза 1

    cfg = _v42_cfg(tmp_path, pool, keys=[])
    # 5 батчей по 40 пар = ровно 5 ключей пула
    pairs = {f"Source string number {i}": f"Русская строка номер {i}" for i in range(200)}
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    p1 = [u for u in used if u[2].startswith("phase1")]
    assert p1, f"фаза 1 не пошла: {used}"
    assert any("qa pool size = 5" in l for l in lines), lines
    # каждый вызов идёт на ОДНОМ ключе, но ключи разные => параллельные потоки
    assert all(len(ks) == 1 for ks, _, _ in p1), p1
    assert len({ks[0] for ks, _, _ in p1}) > 1, f"фаза сериальная на одном ключе: {p1}"
    # 4.1: фаза 1 идёт НАСТОЛЬКО параллельно, сколько живых ключей в пуле —
    # сериальный одноключевой прогон дал бы peak == 1 (инцидент: 36 минут).
    assert state["peak"] >= 3, (f"фаза 1 шла с пиковой параллельностью {state['peak']} "
                                f"при пуле из 5 ключей ({len(p1)} батчей): {p1}")


def test_v42_2_judge_personal_key_joins_pool(tmp_path):
    """4.2: личный ключ судьи j2 добавляется в общий пул, не заменяет его."""
    import tests.test_qa_phase as tq

    pool = ["cs_pool_a_0001", "cs_pool_b_0002"]
    judge_key = "cs_judge_personal_0003"
    seen_keys = set()

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        seen_keys.update(keys)
        if ids_only:
            return []
        return []

    cfg = _v42_cfg(tmp_path, pool, keys=[],
                   judges=[{"name": "j2", "provider": "Crusoe Cloud",
                            "api_key": judge_key, "model": "judge-model/low", "enabled": True}])
    pairs = {f"Source {i}": f"Источник {i}" for i in range(120)}
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    assert judge_key in seen_keys, f"личный ключ судьи не подключился: {seen_keys}"
    assert set(pool) & seen_keys, f"пул провайдера потерялся: {seen_keys}"
    assert any("judge key(s) joined the shared pool" in l for l in lines), lines


def test_v42_3_phase_failure_keeps_precrash_flags(tmp_path):
    """3: пары, зафлагованные ДО падения фазы (ExceptionGroup), попадают в
    unresolved, датасет пишет warning, run total их считает."""
    import tests.test_qa_phase as tq
    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp(prefix="v42_crash_"))

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if ids_only:
            return [{"id": p["id"]} for p in batch]
        if "Glossary compliance arbitration" in prompt:
            raise RuntimeError("auditor died mid-arbitration")
        return []

    pairs = {"Craft the Lead Ingot": "Создай Свинцовый слиток",
             "Simple Cloche farm": "Простая Колпак ферма"}
    cfg = _v42_cfg(tmp_path, ["cs_pool_crash_0001"], keys=[])
    cfg["dataset"] = True
    cfg["modpack_root"] = str(root)
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    ds_seen = {}
    _orig_add = core.QADataSetWriter.add

    def _spy_add(self, record):
        ds_seen[record.get("pair_id")] = record
        return _orig_add(self, record)

    core.qa_run_start()
    core.QADataSetWriter.add = _spy_add
    tr_v = tq.make_translator_stub()
    # ТЗ-v4.3 B.4: пины энфорсит ТОЛЬКО modpack-глоссарий
    tr_v.modpack_glossary_terms = {"Lead": "Свинец", "Cloche": "Колпак"}
    try:
        core.run_qa_phase(pairs, cfg, tr_v, tq.FakeCache(), log, None)
        run_lines = []
        totals = core.qa_run_finish(run_lines.append)
    finally:
        core.QADataSetWriter.add = _orig_add
        core._qa_send = orig
        core.qa_run_finish()
    joined = " ".join(lines)
    assert core._QA_COUNTERS["unresolved"] >= 1, core._QA_COUNTERS
    assert "left unresolved" in joined, lines
    assert totals.get("qa_scanned", 0) >= 2, totals
    warned = [r for r in ds_seen.values() if r.get("action") == "warning"]
    assert warned, ds_seen
    assert all(r.get("action") != "clean" for r in warned), ds_seen


def test_v42_1_single_key_cooldown_without_roles():
    """4.5(г): 12.1-cooldown работает при пул=1 без role-логики."""
    core.health_reset()
    core.health_set_pool_size(1)
    k = "cs_v42_single_0001"
    core.health_note_request(k, 30.0, timed_out=True)
    core.health_note_request(k, 30.0, timed_out=True)
    assert not core.health_is_benched(k), "одноключевой пул забенчил себя"
    assert core.health_cooldown_remaining(k) > 0
    core.health_note_request(k, 1.0)      # успех сбрасывает cooldown
    assert core.health_cooldown_remaining(k) == 0.0


def test_v42_2_key_dies_midphase_no_batch_lost(tmp_path):
    """2: собственный ключ умирает в середине фазы — фаза дозаканчивается на
    остальных ключах пула провайдера, ни один батч не потерян."""
    import asyncio
    import tests.test_qa_phase as tq

    pool = [f"cs_shared_key_{i:04d}" for i in range(3)]
    dying = pool[0]
    scanned_batches = []
    died = {"n": 0}

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url, logger,
                        check_status, temperature=None, phase="main", batch_label="0",
                        ids_only=False, **kw):
        if keys and keys[0] == dying and phase.startswith("phase1"):
            died["n"] += 1
            if died["n"] >= 2:
                # ключ умер на середине фазы — воркер обязан отдать батч обратно
                raise RuntimeError("all QA keys benched — keys failed")
        if ids_only:
            await asyncio.sleep(0.01)
            scanned_batches.append(batch_label)
            return []
        await asyncio.sleep(0.01)
        return []

    cfg = _v42_cfg(tmp_path, pool, keys=[])
    pairs = {f"Source string number {i}": f"Русская строка номер {i}" for i in range(240)}
    log, lines = tq.collect_logs(None)
    orig = core._qa_send
    core._qa_send = fake_send
    try:
        core.run_qa_phase(pairs, cfg, tq.make_translator_stub(), tq.FakeCache(), log, None)
    finally:
        core._qa_send = orig
    # 240 пар / BATCH 40 = 6 батчей фазы 1 — все обязаны быть просканированы
    assert len(set(scanned_batches)) == 6, \
        f"потеряны батчи: просканировано {sorted(set(scanned_batches))} из 6"
    assert not core.health_is_benched(pool[1]), "живой ключ пула внезапно забенчен"
