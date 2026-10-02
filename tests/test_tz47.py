# -*- coding: utf-8 -*-
"""ТЗ v4.7 «Пин-гигиена» — батарея приёмки.

Каждый тест воспроизводит БОЕВОЙ факт с прогонов Liminal Industries.

п.1  QA-путь записи пинов (`_qa_add_glossary_pins`) обходил фильтр
     экстрактора ЦЕЛИКОМ: он звал только `_qa_pin_reject_reason` и никогда
     `_glossary_pin_allowed`. Доказательство живости пути — 10 СТРОЧНЫХ
     пинов на диске (`cloche`, `machinery`, `revealing`, `and`, `for`,
     `stress`, `ritual`, `ponder`, `not mentioned by the ponder`), а
     экстрактор требует заглавную букву (`word_re`) и физически не мог их
     создать. Гейт гибридный: reason + жёсткая проза (глаголы + закрытый
     класс грамматики) + «заглавная ИЛИ многословный». Частотность НЕ
     применяется: ('Power', 'Энергия') и коррекции ветки (c) обязаны
     выживать — совет аудитора это осознанное решение, а не автогенерация.

п.3  Закрытый класс грамматики: заголовок квеста часто начинается с предлога
     с заглавной («Into the Deep», «Always Watching»), поэтому одно правило
     заглавной буквы пропускало числительные/предлоги/наречия.

п.2  Комментарий над `_GLOSSARY_COMMON_WORDS` обещал, что light/power там
     НЕТ, а они там ЕСТЬ. Истина в коде: `Power` -> «Сила» был одним из
     ядов инцидента, частотные автопины запрещены. Комментарий переписан,
     VALID_PINS-тест не тронут (он про другой гейт).

п.4  `force_refresh` удалён подчистую (коммит f655407).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


# ---------- п.1: гейт QA-пути записи -----------------------------------------

# Ровно те строчные пины, что лежали на диске после боевых прогонов.
LOWERCASE_JUNK = [
    ("cloche", "Клош"),
    ("machinery", "Модульные механизмы"),
    ("revealing", "обнажая"),
    ("and", "&93&r &7еще"),
    ("for", "напряжение"),
    ("stress", "напряжение"),
    ("ritual", "ритуальный"),
    ("ponder", "не упомянутая в обзоре"),
    ("not mentioned by the ponder", "не упомянутая в обзоре"),
]


@pytest.mark.parametrize("en,ru", LOWERCASE_JUNK)
def test_v47_lowercase_junk_pins_are_rejected_by_the_write_gate(en, ru):
    """Боевой мусор с диска обязан быть отвергнут на записи."""
    assert core._qa_pin_write_reason(en, ru) != "", f"мусорный пин прошёл: {en!r}"


def test_v47_write_gate_keeps_every_valid_pin():
    """Обратная сторона: валидные термины (13.4) гейт не трогает."""
    valid = [
        ("Cloche", "Клош"), ("Grout", "Раствор"), ("Wither", "Визер"),
        ("Ender Crafter", "Крафтер Энда"), ("Dimensional Ore", "Пространственная руда"),
        ("Lapis Lazuli", "Лазурит"), ("Coal", "Уголь"), ("Villager", "Житель"),
        ("Power", "Энергия"), ("Blast Furnace", "Доменная печь"),
        ("Entro Dust", "Энтропийная пыль"), ("Chorus Fruit", "Плод хоруса"),
        ("Carpet", "Ковёр"), ("Refinery", "Рафинери"),
        ("Machinery", "Механизмы"), ("Ritual", "Ритуал"),
    ]
    for en, ru in valid:
        assert core._qa_pin_write_reason(en, ru) == "", f"валид отвергнут: {en!r} -> {ru!r}"


def test_v47_write_gate_is_not_the_frequency_gate():
    """ГЛАВНОЕ решение юзера: частотность на QA-путь НЕ переносится.

    'Liminal' частое (экстрактор его режет как frequent prose), но совет
    аудитора «Liminal -> Лиминальный» обязан пройти: это решение о реальной
    строке, а не автогенерация из прозы.
    """
    assert core._glossary_pin_verdict("Liminal", 12)[0] is False, "экстрактор обязан резать"
    assert core._qa_pin_write_reason("Liminal", "Лиминальный") == "", "гейт записи не должен"

    # ('Power', 'Энергия') — тот самый случай: ядом была ПАРА ('Power','Сила'),
    # а не термин. Явный совет выживает.
    assert core._qa_pin_reject_reason("Power", "Сила") != ""
    assert core._qa_pin_write_reason("Power", "Энергия") == ""


def test_v47_write_gate_requires_a_term_not_a_lowercase_word():
    """Правило 3: EN-терм обязан быть заглавным ИЛИ многословным.

    Многословный строчный термин — легитимен ('blaze burners' с боевого
    глоссария Create выживает), одно строчное слово — нет.
    """
    assert core._qa_pin_write_reason("blaze burners", "всполоховая горелка") == ""
    assert core._qa_pin_write_reason("stress", "напряжение") != ""
    assert core._qa_pin_write_reason("Cloche", "Клош") == ""


def test_v47_gate_is_wired_into_the_write_path(tmp_path):
    """Сквозной: `_qa_add_glossary_pins` больше НЕ принимает строчный мусор."""
    root = tmp_path / "pack"
    root.mkdir()

    core._QA_COUNTERS.update({"glossary": 0, "warnings": 0})
    logs = []
    core._qa_add_glossary_pins(
        [("cloche", "Клош"), ("and", "&93&r &7еще"), ("Cloche", "Клош")],
        1, logs.append, True, str(root))

    gloss = core.ModpackGlossary(str(root))
    assert "cloche" not in gloss.terms, "строчный мусор записан в глоссарий!"
    assert "and" not in gloss.terms, "союз записан в глоссарий!"
    assert gloss.terms.get("Cloche") == "Клош", "валид обязан пройти"
    assert core._QA_COUNTERS["warnings"] == 2, core._QA_COUNTERS
    assert core._QA_COUNTERS["glossary"] == 1, core._QA_COUNTERS
    assert sum("rejected" in str(l) for l in logs) == 2, logs


# ---------- п.3: закрытый класс грамматики -----------------------------------

GRAMMAR = [
    # числительные
    "Two", "Three", "Ten", "Hundred", "First", "Last", "Many", "Both",
    # предлоги
    "With", "From", "Into", "Under", "Along", "Across", "Between", "Like",
    # наречия
    "Always", "Never", "Usually", "Maybe", "Already", "Soon", "Together",
]


@pytest.mark.parametrize("word", GRAMMAR)
def test_v47_grammar_words_are_never_terms(word):
    """«Into the Deep» / «Always Watching» — заголовок с предлога с заглавной
    больше не становится пином."""
    assert not core._glossary_pin_allowed(word), word


def test_v47_grammar_set_leaves_terminology_alone():
    """Нулевая коллатераль, замерено на живых данных."""
    for term in ("Carpet", "Poolrooms", "Reality", "Frame", "Dust", "Refinery",
                 "Renewable", "Furnace", "Liminal", "Generator", "Cobblestone"):
        assert core._glossary_pin_allowed(term), term


def test_v47_grammar_words_never_reach_the_candidate_list():
    """Сквозь экстрактор: заголовок-предлог не попадает в кандидаты."""
    texts = ["Into the Deep", "Always Watching", "Two Moons", "Carpet Floor"] * 3
    cands = core.extract_glossary_candidates(texts, min_occurrences=2, limit=200)
    lowered = {c.casefold() for c in cands}
    for bad in ("into", "always", "two"):
        assert bad not in lowered, (bad, cands)
    assert "carpet" in lowered, cands


# ---------- п.2: комментарий приведён в согласие с кодом ---------------------

def test_v47_common_words_hold_light_and_power_on_purpose():
    """Истина в коде: light/power в общем стоп-листе, и это политика —
    'Power' -> «Сила» был ядом. Комментарий это теперь и говорит."""
    assert "power" in core._GLOSSARY_COMMON_WORDS
    assert "light" in core._GLOSSARY_COMMON_WORDS
    # ...но сам гейт записи их НЕ применяет: явный совет аудитора выживает.
    assert core._qa_pin_write_reason("Power", "Энергия") == ""
    assert core._qa_pin_write_reason("Light", "Свет") == ""


def test_v47_prose_and_grammar_sets_stay_recognisable():
    """Регресс-страховка от случайного опустошения наборов."""
    assert len(core._GLOSSARY_PROSE_WORDS) >= 600
    assert len(core._GLOSSARY_GRAMMAR_WORDS) >= 130
    assert len(core._GLOSSARY_COMMON_WORDS) >= 500
    # 'generates' — глагол (PROSE), 'space'/'fuel'/'pack'/'base'/'magic' — проза.
    for w in ("generates", "space", "fuel", "pack", "base", "magic"):
        assert not core._glossary_pin_allowed(w), w


# ---------- п.4: force_refresh отсутствует -----------------------------------

def test_v47_force_refresh_is_gone():
    """Удалён подчистую: ни параметра, ни упоминаний в репозитории.

    Этот файл исключён из поиска — он лишь упоминает имя, чтобы его оплакивать.
    """
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(["grep", "-rn", "force_refresh", "--include=*.py", "."],
                         cwd=root, capture_output=True, text=True).stdout
    hits = [l for l in out.splitlines() if "test_tz47.py" not in l]
    assert hits == [], "это имя вернулось:\n" + "\n".join(hits)
