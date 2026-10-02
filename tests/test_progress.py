# -*- coding: utf-8 -*-
"""Единая строка прогресса (жалоба юзера m14241).

До переделки pb_batch жил в трёх несовместимых режимах (файлы / строки /
проценты) и «File 3/8 … 120/900» прыгал по файлам при concurrency>1.
Теперь:
- полоса одна, weighted по files_progress (завершение чанков), range 0..1000;
- файлы/строки/ETA в тексте согласованы;
- JSON-фаза — отдельная процентная полоса, и progress_batch из JSONManager
  больше не дописывает левые ключи в files_progress.
"""
import os
import sys

import pytest

QT = pytest.importorskip("PyQt6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui  # noqa: E402


class _FakeBar:
    """Минимальный QProgressBar-стенд: запоминает последние значения."""

    def __init__(self):
        self.range = None
        self.value = None
        self.format = ""

    def setRange(self, a, b):
        self.range = (a, b)

    def setValue(self, v):
        self.value = v

    def setFormat(self, s):
        self.format = s

    def value_(self):
        return self.value


def _stub():
    """Объект с атрибутами/методами, которые используют обработчики прогресса."""
    class _S:
        pass

    s = _S()
    s.pb_batch = _FakeBar()
    s.files_progress = {}
    s._translation_finished = False
    s.format_eta = lambda sec: gui.App.format_eta(s, sec)
    s._refresh_progress_bar = lambda: gui.App._refresh_progress_bar(s)
    return s


def _call(method, s, *args):
    return getattr(gui.App, method)(s, *args)


def test_batch_progress_marks_file_done():
    """update_batch_progress: файл помечается 1.0, но полоса идёт по СТРОКАМ;
    без известного total строк — фолбэк на файлы."""
    s = _stub()
    s._progress_mode = 'snbt'
    s._progress_total_files = 2
    s._progress_total_strings = 10
    s._progress_done_strings = 2
    _call('update_batch_progress', s, 1, 2)
    assert s.files_progress.get(0) == 1.0
    assert "Files 1/2" in s.pb_batch.format
    # Строки известны: 2/10 строк = 200/1000, а НЕ 500 (1 из 2 файлов).
    assert s.pb_batch.value == 200
    # Без total строк — фолбэк на файлы: 1 из 2 = 500/1000.
    s._progress_total_strings = 0
    _call('update_batch_progress', s, 1, 2)
    assert s.pb_batch.value == 500


def test_chunk_progress_uses_string_fraction():
    """Ключевая регрессия (жалоба m14628): полоса НЕ прыгает в конец, когда
    закрываются пустые файлы ('No new untranslated texts')."""
    s = _stub()
    s._progress_mode = 'snbt'
    s._progress_total_files = 50
    s._progress_total_strings = 1000
    s._progress_done_strings = 100
    # 20 пустых файлов закрылись мгновенно — полоса обязана остаться на 10%.
    for i in range(20):
        _call('update_batch_progress', s, i + 1, 50)
    assert s.pb_batch.value == 100, s.pb_batch.value
    assert "Strings 100/1000" in s.pb_batch.format
    assert "Files 20/50" in s.pb_batch.format


def test_progress_state_is_one_consistent_line():
    """Файлы/строки/ETA в одной строке, без номера текущего файла."""
    s = _stub()
    s._progress_total_files = 0
    _call('update_progress_state', s, 2, 4, "quests.snbt", 120, 400, 90)
    assert s.pb_batch.range == (0, 1000)
    assert "Files 0/4" in s.pb_batch.format
    assert "Strings 120/400" in s.pb_batch.format
    assert "quests.snbt" in s.pb_batch.format
    assert "01:30" in s.pb_batch.format
    assert "File 2/4" not in s.pb_batch.format  # старый сбивающий префикс убран


def test_json_mode_has_own_percent_bar():
    """JSON-фаза: процентная полоса строк; batch-эмиты её не портят."""
    s = _stub()
    s._progress_total_files = 3
    _call('update_progress_state', s, 0, 0, "Translating KubeJS JSON strings",
          25, 100, 0)
    assert s._progress_mode == 'json'
    assert s.pb_batch.range == (0, 100)
    assert s.pb_batch.value == 25
    assert "JSON strings: 25/100 (25%)" == s.pb_batch.format
    # JSONManager's batch(processed, total) must NOT write bogus file keys.
    _call('update_batch_progress', s, 60, 100)
    assert s.files_progress == {}


def test_finished_run_ignores_late_updates():
    """После завершения поздние сигналы не перебивают '100% Completed'."""
    s = _stub()
    s._translation_finished = True
    s.pb_batch.setFormat("Translation Finished! 100% Completed")
    _call('update_progress_state', s, 1, 2, "late.snbt", 1, 10, 5)
    assert s.pb_batch.format == "Translation Finished! 100% Completed"


def test_no_overflow_when_done_exceeds_total():
    """Жалоба m17367: в тексте висело '400/200', полоса стояла на 100%.

    Многострочный 'description: [ ... ]' построчный предпросчёт не видел,
    а перевод эти строки делал — done переполнял total. Теперь denominator
    считает ровно то, что переводится (core._count_translatable_in_content),
    а здесь проверяется страховка на уровне полосы: показать больше total
    нельзя ни при каком рассинхроне.
    """
    s = _stub()
    s._progress_total_files = 1
    s._progress_total_strings = 200
    _call('update_progress_state', s, 0, 1, "chapter.snbt", 400, 200, 0)
    assert s.pb_batch.value == 1000, s.pb_batch.value
    assert "Strings 200/200" in s.pb_batch.format, s.pb_batch.format
    assert "400/200" not in s.pb_batch.format


def test_translatable_counter_matches_the_real_work():
    """Зеркало жалобы m17367 на уровне core: счётчик (denominator полосы)
    обязан совпадать с множеством строк, которые process_file реально шлёт
    в перевод — включая многострочные description-блоки и уникальность."""
    from core import SNBTManager
    content = '''{
	title: "Getting Started"
	description: [
		"First line of the guide"
		"Second line of the guide"
	]
	quests: [
		{ title: "Getting Started"
		  description: [ "Break a log"  "Craft a table" ] }
	]
}'''
    m = SNBTManager("test", "Groq Cloud (Fast)", "test")
    # 5 UNIQUE values: "Getting Started" appears twice (title + nested title)
    # and must count once — process_file translates a SET of values.
    assert m._count_translatable_in_content(content, True, True, True) == 5
