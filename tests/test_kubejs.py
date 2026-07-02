import json
import os
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock
from core import detect_kubejs_mode, JSONManager, TranslationCache

@pytest.fixture
def mock_translator():
    async def translate_mock(texts, *args, **kwargs):
        return ["Translated"] * len(texts)
    translator = MagicMock()
    translator.translate = AsyncMock(side_effect=translate_mock)
    return translator

@pytest.fixture
def mock_cache(tmp_path):
    db_path = str((tmp_path / "cache.sqlite").resolve())
    return TranslationCache(db_path=db_path, target_lang_code="ru_ru")

def test_detect_kubejs_mode(tmp_path):
    quest_dir = tmp_path / "quests"
    chapters_dir = quest_dir / "chapters"
    chapters_dir.mkdir(parents=True)
    snbt_file = chapters_dir / "test.snbt"
    snbt_file.write_text('title: "{quest.chapter.1.title}"')

    kubejs_dir = tmp_path / "kubejs"
    lang_dir = kubejs_dir / "assets" / "kubejs" / "lang"
    lang_dir.mkdir(parents=True)
    en_us_file = lang_dir / "en_us.json"
    en_us_file.write_text('{}')

    result = detect_kubejs_mode(quest_dir)
    assert result == kubejs_dir.resolve()

    en_us_file.unlink()
    result = detect_kubejs_mode(quest_dir)
    assert result is None

    snbt_file.write_text('title: "Normal Title"')
    en_us_file.write_text('{}')
    result = detect_kubejs_mode(quest_dir)
    assert result is None

def test_kubejs_manager_overwrite(tmp_path, mock_translator, mock_cache):
    kubejs_dir = tmp_path / "kubejs"
    lang_dir = kubejs_dir / "assets" / "kubejs" / "lang"
    lang_dir.mkdir(parents=True)

    en_us_file = lang_dir / "en_us.json"
    en_us_file.write_text(json.dumps({"key1": "Hello", "key2": "World"}))

    ru_ru_file = lang_dir / "ru_ru.json"
    ru_ru_file.write_text(json.dumps({"key1": "Old", "key2": "Old"}))

    manager = JSONManager(
        kubejs_dir,
        "ru_ru",
        mock_translator,
        mock_cache,
        modpack="test",
        policy="Overwrite (Перезаписать)"
    )

    import asyncio
    asyncio.run(manager.process())

    result = json.loads(ru_ru_file.read_text())
    assert result["key1"] == "Translated"
    assert result["key2"] == "Translated"

def test_kubejs_manager_complement(tmp_path, mock_translator, mock_cache):
    kubejs_dir = tmp_path / "kubejs"
    lang_dir = kubejs_dir / "assets" / "kubejs" / "lang"
    lang_dir.mkdir(parents=True)

    en_us_file = lang_dir / "en_us.json"
    en_us_file.write_text(json.dumps({"key1": "Hello", "key2": "World"}))

    ru_ru_file = lang_dir / "ru_ru.json"
    ru_ru_file.write_text(json.dumps({"key1": "Привет"}))

    manager = JSONManager(
        kubejs_dir,
        "ru_ru",
        mock_translator,
        mock_cache,
        modpack="test",
        policy="Complement (Дополнить)"
    )

    import asyncio
    asyncio.run(manager.process())

    result = json.loads(ru_ru_file.read_text())
    assert result["key1"] == "Привет"
    assert result["key2"] == "Translated"

def test_kubejs_worker_execution(tmp_path, qtbot):
    from gui import JSONWorker

    kubejs_dir = tmp_path / "kubejs"
    lang_dir = kubejs_dir / "assets" / "kubejs" / "lang"
    lang_dir.mkdir(parents=True)

    en_us_file = lang_dir / "en_us.json"
    en_us_file.write_text(json.dumps({"key1": "Hello"}))
    ru_ru_file = lang_dir / "ru_ru.json"
    ru_ru_file.write_text("{}")

    async def translate_mock(texts, *args, **kwargs):
        return ["Привет"] * len(texts)
    mock_translator = MagicMock()
    mock_translator.translate = AsyncMock(side_effect=translate_mock)

    mock_cache = MagicMock()
    mock_cache.get = MagicMock(return_value=None)
    mock_cache.save_batch = MagicMock()

    worker = JSONWorker(
        str(kubejs_dir),
        "ru_ru",
        mock_translator,
        mock_cache,
        modpack="test",
        policy="Complement (Дополнить)",
        concurrency=1,
        batch_size=50,
        min_batch_size=1,
        max_concurrent_requests=10
    )

    progress_calls = []
    done_calls = []

    worker.progress_batch.connect(lambda cur, tot: progress_calls.append((cur, tot)))
    worker.done.connect(lambda: done_calls.append(True))

    worker.log.connect(print)
    with qtbot.capture_exceptions() as exceptions:
        worker.start()
        qtbot.waitUntil(lambda: len(progress_calls) > 0, timeout=5000)
        qtbot.waitUntil(lambda: len(done_calls) == 1, timeout=5000)

    assert len(exceptions) == 0
    assert len(progress_calls) > 0
    assert len(done_calls) == 1
