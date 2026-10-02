"""ТЗ v4.5 «Острые углы» — батарея приёмки.

Каждый тест здесь воспроизводит БОЕВОЙ лог-факт и падает, если фикс откатить.

п.2  repair присылает эхо (id/note/source/translation, без category и без
     suggested) -> вердикт демотируется в warning -> [no category/soft] ...
     no safe fix, warning only, soft-fixed 0.  Тест требует soft-fixed > 0.
п.3  экстрактор пинит общеупотребительные слова (Taste/Time/Making/Industrial)
     — в кандидатах их быть не должно, паковые термины (Carpet) остаются.
п.5  морфология в _qa_glossary_violations: «Незерного»/«Кусочков»/«Лазурита»
     не флаг, а отсутствие пина — флаг.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/ronnikols/MineAI_Pro")

import core
from core import run_qa_phase, ModpackGlossary


# --- инфраструктура (как в test_qa_phase.py) --------------------------------
def qa_config(tmpdir, update_glossary=True, modpack_root=None):
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


class FakeCache:
    def __init__(self):
        self.saved = {}

    def save_batch(self, mapping, modpack=None):
        self.saved.update(mapping)

    def close(self):
        pass


class PinTranslator:
    """Переводчик, который умеет вставить пин в строку.

    Имитирует главный канал: получив constraint («pin missing»), модель
    возвращает строку с канонической формой пина. Пак-пин обязан лежать
    в modpack_glossary_terms — именно оттуда его берёт pre-check
    (core.py:6600: modpack_terms = getattr(translator, "modpack_glossary_terms", None)).
    """
    provider = "Test"
    model = "stub"
    mixed_pool = None

    def __init__(self, fixed="Ковёр Пыль"):
        self.fixed = fixed
        self.modpack_glossary_terms = {"Carpet": "Ковёр"}

    async def translate(self, texts, logger=print, check_status=None, context=""):
        return [self.fixed for _ in texts]


def _setting(**kw):
    return {**dict(modpack_root=None, dataset=False, verdict_cache=False), **kw}


# --- п.2: repair-эхо без category/suggested -> soft-fixed > 0 ---------------
def test_v45_repair_echo_still_produces_a_soft_fix():
    """Боевой дамп 20261002_191131_repair_0.json: 5 записей, у ВСЕХ ключи
    ровно ['id','note','source','translation'], translation = текущий перевод.
    Такой ответ не должен означать «no safe fix»."""
    import tempfile as _t
    td = Path(_t.mkdtemp())
    orig_dir = core.GLOSSARY_DIR
    core.GLOSSARY_DIR = td / "glossaries"
    core.GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    orig_load = core.load_vanilla_glossary
    core.load_vanilla_glossary = lambda: {}
    try:
        gloss = ModpackGlossary(str(td))
        gloss.terms["Carpet"] = "Ковёр"
        gloss.save()

        seen_phases = []

        async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                            logger, check_status, temperature=None,
                            phase="main", batch_label="0", ids_only=False, **kwargs):
            seen_phases.append(phase)
            if ids_only:
                # фаза 1 поднимает флаг на паре, которую арбитр не возьмёт
                return [{"id": p["id"]} for p in batch]
            if phase == "main":
                return []
            if phase == "arb":
                return []          # арбитр молчит -> пара едет в tier C repair
            if phase == "repair":
                # БОЕВОЕ ПОВЕДЕНИЕ: эхо кандидата, без category/suggested
                return [{"id": p["id"],
                         "note": p.get("note", ""),
                         "source": p["source"],
                         "translation": p["translation"]} for p in batch]
            return []

        orig_send = core._qa_send
        core._qa_send = fake_send
        try:
            logs = []
            pairs = {"Carpet Dust": "Ковровая Пыль"}
            cfg = qa_config(str(td), modpack_root=str(td))
            tr = PinTranslator(fixed="Ковёр Пыль")
            run_qa_phase(pairs, cfg, tr, FakeCache(), logs.append, None)
        finally:
            core._qa_send = orig_send

        joined = "\n".join(logs)
        assert "repair" in seen_phases, seen_phases
        # Главное требование приёмки v4.5(в): мягкий канал что-то доставил.
        assert core._QA_COUNTERS["soft_fixed"] > 0, joined
        assert "recovered as constraint retries" in joined, joined
        assert "[no category/soft]" not in joined or "recovered" in joined, joined
        assert pairs["Carpet Dust"] != "Ковровая Пыль", pairs
    finally:
        core.GLOSSARY_DIR = orig_dir
        core.load_vanilla_glossary = orig_load


def test_v45_repair_echo_with_a_suggestion_still_applies_it():
    """Если модель всё-таки дала category+suggested — путь не сломан."""
    import tempfile as _t
    td = Path(_t.mkdtemp())
    orig_dir = core.GLOSSARY_DIR
    core.GLOSSARY_DIR = td / "glossaries"
    core.GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    orig_load = core.load_vanilla_glossary
    core.load_vanilla_glossary = lambda: {}
    try:
        gloss = ModpackGlossary(str(td))
        gloss.terms["Carpet"] = "Ковёр"
        gloss.save()

        async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                            logger, check_status, temperature=None,
                            phase="main", batch_label="0", ids_only=False, **kwargs):
            if ids_only:
                return [{"id": p["id"]} for p in batch]
            if phase == "repair":
                return [{"id": p["id"], "category": "TERM_INCONSISTENT",
                         "severity": "soft", "issue": "pin missed",
                         "suggested": "Ковёр Пыль"} for p in batch]
            return []

        orig_send = core._qa_send
        core._qa_send = fake_send
        try:
            logs = []
            pairs = {"Carpet Dust": "Ковровая Пыль"}
            cfg = qa_config(str(td), modpack_root=str(td))
            run_qa_phase(pairs, cfg, PinTranslator(), FakeCache(), logs.append, None)
        finally:
            core._qa_send = orig_send

        assert pairs["Carpet Dust"] == "Ковёр Пыль", pairs
        assert core._QA_COUNTERS["soft_fixed"] > 0, logs
    finally:
        core.GLOSSARY_DIR = orig_dir
        core.load_vanilla_glossary = orig_load


# --- п.3: стоп-лист пинов ---------------------------------------------------
def test_v45_common_words_are_not_pinned():
    """Боевой глоссарий Liminal Industries (44 терма) содержал
    Taste/Time/Making/Industrial -> FP-арбитраж в каждом файле."""
    for term in ("Taste", "Time", "Making", "Industrial", "Always",
                 "Welcome", "Everything", "They", "There", "Simply"):
        assert not core._glossary_pin_allowed(term), term


def test_v45_pack_terms_survive_the_stop_list():
    """Carpet — паковый термин (решение юзера), многословные фразы несут
    контекст и разрешены всегда."""
    for term in ("Carpet", "Poolrooms", "Liminal", "Reality", "Frame", "Dust"):
        assert core._glossary_pin_allowed(term), term
    for term in ("Industrial Mixer", "Time in a Bottle", "Making Clay"):
        assert core._glossary_pin_allowed(term), term


def test_v45_extractor_drops_the_offending_pins():
    """Прогон экстрактора на боевом тексте: запрещённых пинов нет,
    паковые термины остались."""
    texts = [
        "Taste the Rainbow",
        "Time to get some power generation going.",
        "Making Clay is a lot faster now.",
        "The Industrial Mixer needs power.",
        "Clay can be made by washing Carpet Dust in a Poolrooms basin.",
        "Liminal Reality Frame",
    ] * 3
    cands = core.extract_glossary_candidates(texts, min_occurrences=2, limit=200)
    lowered = {c.lower() for c in cands}
    for bad in ("taste", "time", "making", "industrial"):
        assert bad not in lowered, (bad, cands)
    assert "carpet" in lowered, cands
    assert "poolrooms" in lowered, cands


# --- п.5: морфология в _qa_glossary_violations ------------------------------
def test_v45_morphology_accepts_inflected_pins():
    """v4.3 item A: «Незерного»/«Кусочков»/«Лазурита» — это тот же пин,
    флага быть не должно."""
    pairs = [
        ("Nether Brick", "Кирпич Незерного", {"Nether": "Незер"}),
        ("Ore Pieces", "Кусочков руды", {"Ore Pieces": "Кусочки"}),
        ("Lapis Lazuli", "Лазурита немного", {"Lapis Lazuli": "Лазурит"}),
    ]
    for source, translation, terms in pairs:
        batch = [{"id": 0, "source": source, "translation": translation}]
        assert core._qa_glossary_violations(batch, {}, terms) == [], (source, translation)


def test_v45_morphology_still_flags_a_missing_pin():
    """Обратная сторона: пина в переводе НЕТ — флаг остаётся."""
    batch = [{"id": 0, "source": "Nether Brick", "translation": "Кирпич"}]
    out = core._qa_glossary_violations(batch, {}, {"Nether": "Незер"})
    assert len(out) == 1, out


# --- п.4: одна агрегатная JURY-строка за прогон -----------------------------
def test_v45_one_aggregate_jury_line_per_run():
    """Было: [JURY] single judge: ... печатается по-файлово (5 строк в конце
    прогона), агрегатной строки за прогон нет. Стало: одна строка с суммой."""
    core.qa_run_start()
    try:
        for _ in range(5):
            core.qa_run_note_file(10, 0, {"hard": 0},
                                  jury_line="[JURY] single judge: 2 finding(s), "
                                            "threshold 1/1, confirmed 2",
                                  jury_stats={"judges": 1, "live": 1, "threshold": 1,
                                              "findings": {0: 2}, "judged": 10, "agreed": 10,
                                              "confirmed": 2, "disputed": 0})
        lines = []
        core.qa_run_finish(lines.append)
        jury_lines = [l for l in lines if "[JURY]" in l]
        assert len(jury_lines) == 1, lines
        agg = jury_lines[0]
        assert "run total" in agg, agg
        assert "5 file(s)" in agg, agg
        assert "10 finding(s)" in agg, agg
    finally:
        core.qa_run_finish()


def test_v45_aggregate_jury_line_carries_foreman_and_agreement():
    """Жюри из двух судей: агрегатная строка несёт agreement и foreman."""
    core.qa_run_start()
    try:
        core.qa_run_note_file(20, 0, {"hard": 1},
                              jury_line="[JURY] jury: j1 3 finding(s), j2 1 finding(s)",
                              jury_stats={"judges": 2, "live": 2, "threshold": 2,
                                          "findings": {0: 3, 1: 1}, "judged": 10, "agreed": 8,
                                          "confirmed": 2, "disputed": 1,
                                          "foreman_confirmed": 1, "foreman_cleared": 0})
        lines = []
        core.qa_run_finish(lines.append)
        agg = next(l for l in lines if "[JURY]" in l)
        assert "agreement 80%" in agg, agg
        assert "j1 3 finding(s), j2 1 finding(s)" in agg, agg
        assert "foreman confirmed 1, cleared 0" in agg, agg
        assert "disputed 1" in agg, agg
    finally:
        core.qa_run_finish()


def test_v45_legacy_jury_lines_still_replay_without_stats():
    """Файл, записанный без числовой статистики, не теряет свою JURY-строку."""
    core.qa_run_start()
    try:
        core.qa_run_note_file(5, 0, {"hard": 0},
                              jury_line="[JURY] single judge: 1 finding(s), threshold 1/1, confirmed 1")
        lines = []
        core.qa_run_finish(lines.append)
        assert any("single judge" in l for l in lines), lines
    finally:
        core.qa_run_finish()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_v45_frequency_gate_keeps_the_pack_terms_and_drops_the_prose():
    """п.1: одиночное слово пинится только когда оно РЕДКОЕ (порог 3),
    многословная фраза — всегда. Порог виден в логе."""
    logs = []
    texts = (
        ["Carpet Dust"] * 3
        + ["Reality Frame"] * 2
        + ["Renewable Energy"] * 12
        + ["The Furnace burns Fuel"] * 6
        + ["Liminal Space"] * 5
        + ["Cobblestone Generator"] * 2
    )
    cands = core.extract_glossary_candidates(texts, min_occurrences=2, limit=200,
                                             log_pins=logs.append)
    lowered = {c.lower() for c in cands}
    for kept in ("carpet", "dust", "reality", "frame", "cobblestone generator"):
        assert kept in lowered, (kept, cands)
    for dropped in ("renewable", "furnace", "fuel", "liminal", "space"):
        assert dropped not in lowered, (dropped, cands)
    # приёмка ТЗ: решение по каждому пину обязано быть в логе
    assert any("'Carpet' accepted" in l for l in logs), logs
    assert any("'Fuel' rejected (common word" in l for l in logs), logs
    assert any("'Renewable' rejected (frequent prose, freq 12)" in l for l in logs), logs


def test_v45_suppressed_pins_survive_a_save(tmp_path):
    """Регрессия: load() фильтрует пины в READ-TIME VIEW, но save() писал
    `self.terms` — то есть отфильтрованное множество. Любой QA-пиннинг
    (update_glossary, дефолт True) молча СТИРАЛ с диска подавленные пины,
    хотя комментарий обещал «the file itself is left alone». Теперь save()
    сливается с тем, что лежит на диске."""
    import json as _json
    p = tmp_path / "minecraft_deadbeef00.json"
    p.write_text(_json.dumps({"terms": {
        "Time": "Время", "Taste": "Вкус", "Carpet": "Ковёр",
    }}, ensure_ascii=False), encoding="utf-8")

    g = core.ModpackGlossary.__new__(core.ModpackGlossary)
    g.modpack_root, g.terms, g._stored, g.path = None, {}, {}, p
    g.load()
    # навязывается только разрешённое...
    assert g.terms == {"Carpet": "Ковёр"}, g.terms

    # ...но запись нового пина не имеет права стереть подавленные
    g.terms["NewTerm"] = "НовыйТермин"
    g.save()
    saved = _json.loads(p.read_text(encoding="utf-8"))["terms"]
    assert saved["Time"] == "Время", f"подавленный пин стёрт: {saved}"
    assert saved["Taste"] == "Вкус", f"подавленный пин стёрт: {saved}"
    assert saved["NewTerm"] == "НовыйТермин"
    assert saved["Carpet"] == "Ковёр"

    # и при перезагрузке они снова лишь подавляются, а не исчезают
    g2 = core.ModpackGlossary.__new__(core.ModpackGlossary)
    g2.modpack_root, g2.terms, g2._stored, g2.path = None, {}, {}, p
    g2.load()
    assert "Time" not in g2.terms and "Taste" not in g2.terms
    assert "Carpet" in g2.terms and "NewTerm" in g2.terms


def test_v45_zero_flags_after_a_cache_skip_do_not_crash():
    """п.3 приёмки ТЗ v4.6: сужение ids-сетки кэшем при НУЛЕ найденных флагов
    не роняет аудит — файл проходит целиком с исходными строками."""
    import tests.test_qa_phase as tq
    import tests.test_tz44 as t44

    t44._FakeVerdictCache._clean = set()
    pairs = {f"Alpha {i}": f"Альфа {i}" for i in range(1, 13)}

    async def main():
        core.QAVerdictCache = t44._FakeVerdictCache          # hermetic cache
        pf = core._QAPrefetch(t44._params(verdict_cache=True), t44.StubTranslator(),
                              lambda m: None, None, "Russian", 10)
        pf.start()
        pf.feed(pairs.items())
        await pf.finish()
        return pf

    orig_send, orig_scan, orig_cache = core._qa_send, core._qa_scan_pairs, core.QAVerdictCache

    async def fake_send(batch, prompt, keys, provider, model, custom_base_url,
                        logger, check_status, temperature=None, ids_only=False, **kwargs):
        return []                                   # НИ ОДНОГО флага

    try:
        core._qa_scan_pairs = t44._scan_stub(t44.Recorder(), set())
        pf = t44._run(main())
        assert pf.ready and pf.adopt([{"id": i, "source": s, "translation": t}
                                      for i, (s, t) in enumerate(pairs.items(), 1)]) is not None
        for src in ("Alpha 1", "Alpha 2", "Alpha 3"):
            t44._FakeVerdictCache._clean.add(
                t44._FakeVerdictCache.key(src, pairs[src], "cfghash"))

        cfg = t44._params(verdict_cache=True)
        cfg["prefetch"] = pf
        core._qa_send = fake_send
        core._qa_reset_counters()
        out = dict(pairs)
        lines = []
        core.run_qa_phase(out, cfg, t44.StubTranslator(), tq.FakeCache(),
                          lines.append, None)

        assert any("3 clean pair(s) skipped in phase 1" in l for l in lines), lines
        assert not any("phase failed" in l for l in lines), lines
        assert not any("IndexError" in l for l in lines), lines
        assert out == pairs, "файл без флагов обязан пройти без единой правки"
    finally:
        core._qa_send, core._qa_scan_pairs = orig_send, orig_scan
        core.QAVerdictCache = orig_cache

def test_v45_stored_glossary_pins_are_filtered_on_load(tmp_path):
    """п.3 (дыра): глоссарий additive forever — старый файл уже содержит
    Time/Making/Taste. Фильтр при загрузке обязан перестать их навязывать,
    при этом паковые термины (Carpet/Liminal) остаются."""
    import json as _json
    p = tmp_path / "minecraft_deadbeef00.json"
    p.write_text(_json.dumps({"terms": {
        "Time": "Время", "Making": "Создание", "Taste": "Вкус",
        "Industrial": "Индустриальный", "Always": "Всегда",
        "Carpet": "Ковёр", "Liminal": "Лиминальный",
        "Industrial Mixer": "Индустриальный миксер",
    }}, ensure_ascii=False), encoding="utf-8")
    g = core.ModpackGlossary.__new__(core.ModpackGlossary)
    g.modpack_root = None
    g.terms = {}
    g.path = p
    g.load()
    assert "Carpet" in g.terms and g.terms["Carpet"] == "Ковёр"
    assert "Liminal" in g.terms
    assert "Industrial Mixer" in g.terms, "многословный терм разрешён"
    for bad in ("Time", "Making", "Taste", "Industrial", "Always"):
        assert bad not in g.terms, (bad, g.terms)
