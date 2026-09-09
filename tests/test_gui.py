import pytest
pytestmark = pytest.mark.gui

import asyncio
import sys
import pytest
import tempfile
import sqlite3
import os
import shutil
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QMessageBox
from gui import App, TranslationMemoryTab
from core import resolve_mixed_pool, UnifiedTranslator, TranslationCache
from config import ConfigManager, PROVIDER_DEFAULTS



def test_gui_provider_key_isolation(qtbot, monkeypatch):
    import gui
    from unittest.mock import MagicMock
    from PyQt6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(gui, "UpdateChecker", MagicMock)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "/mock/modpack/dir")
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    from gui import App
    app = App()
    qtbot.addWidget(app)
    app.settings.clear()
    app.config.api_keys_pool.clear()
    app.config.model = None
    app.config.provider = "Google Translate (Free)"
    qtbot.wait(100)

    app.provider_box.setCurrentText("Groq Cloud (Fast)")
    qtbot.wait(100)
    app.key_pool_edit.setPlainText("groq_secret_key_123")
    qtbot.wait(100)
    app.save_current_settings()
    qtbot.wait(100)

    app.provider_box.setCurrentText("NVIDIA NIM")
    qtbot.wait(100)
    assert app.key_pool_edit.toPlainText() != "groq_secret_key_123"

    app.key_pool_edit.setPlainText("nvidia_nim_key_456")
    qtbot.wait(100)
    app.save_current_settings()
    qtbot.wait(100)

    app.provider_box.setCurrentText("Groq Cloud (Fast)")
    qtbot.wait(100)
    assert app.key_pool_edit.toPlainText() == "groq_secret_key_123"

    app.provider_box.setCurrentText("NVIDIA NIM")
    qtbot.wait(100)
    assert app.key_pool_edit.toPlainText() == "nvidia_nim_key_456"

def test_translation_memory_tab_clear_cache(qtbot):
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        from gui import TranslationMemoryTab
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"key1": "val1", "key2": "val2"})
        tab = TranslationMemoryTab(cache)
        qtbot.addWidget(tab)
        assert tab.table.rowCount() == 2

        tab._confirm_clear_cache = lambda: True
        tab._on_clear_cache()
        assert tab.table.rowCount() == 0
        assert len(cache.get_all_records()) == 0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_tab_disabled_during_work(qtbot):
    from gui import App, ModelLoader
    from unittest.mock import patch, MagicMock

    with patch('gui.Worker') as mock_worker, patch('gui.ModelLoader.run'):
        mock_worker.return_value.start = MagicMock()
        mock_worker.return_value.isRunning.return_value = False
        app = App()
        qtbot.addWidget(app)

        assert app.tabs.isTabEnabled(1) == True

        with qtbot.capture_exceptions():
            app.btn_run.click()
            qtbot.wait(100)

        assert app.tabs.isTabEnabled(1) == False

def test_translation_memory_tab_gui(qtbot):
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        from gui import TranslationMemoryTab
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test_key": "test_val"})
        tab = TranslationMemoryTab(cache)
        qtbot.addWidget(tab)
        assert tab.table.rowCount() == 1
        assert tab.table.item(0, 0).text() == "test_key"
        assert tab.table.item(0, 1).text() == "test_val"
        tab.table.item(0, 1).setText("new_val")
        tab._on_item_changed(tab.table.item(0, 1))
        assert tab.pending_updates["test_key"] == "new_val"
        tab.table.selectRow(0)
        tab._on_delete_selected()
        assert tab.table.rowCount() == 0
        assert "test_key" in tab.pending_deletions
        assert "test_key" not in tab.pending_updates
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_app_has_tabs(qtbot):
    from gui import App
    app = App()
    qtbot.addWidget(app)
    assert hasattr(app, 'tabs')
    assert app.tabs.count() == 4
    assert app.tabs.tabText(0) == "Workspace"
    assert app.tabs.tabText(1) == "Translation Memory"
    assert app.tabs.tabText(2) == "Settings"
    assert app.tabs.tabText(3) == "Credits"

def test_translation_memory_tab_search_debounce(qtbot):
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        tab = TranslationMemoryTab(cache)
        qtbot.addWidget(tab)

        tab.search_timer.timeout.disconnect()
        with patch.object(tab, '_perform_search') as mock_search:
            tab.search_timer.timeout.connect(tab._perform_search)
            tab.search_input.setText("word")
            tab._on_search_changed()
            qtbot.wait(100)
            mock_search.assert_not_called()

            tab.search_timer.timeout.emit()
            mock_search.assert_called_once()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_translation_memory_tab_pagination(qtbot):
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        updates = {f"key_{i}": f"val_{i}" for i in range(505)}
        cache.save_batch(updates)

        tab = TranslationMemoryTab(cache)
        qtbot.addWidget(tab)

        assert tab.table.rowCount() == 500
        assert tab.load_more_btn.isEnabled()

        tab.load_more_btn.click()
        qtbot.wait(100)

        assert tab.table.rowCount() == 505
        assert not tab.load_more_btn.isEnabled()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_translation_memory_tab_save_changes(qtbot):
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"apple": "яблоко", "banana": "банан"})

        tab = TranslationMemoryTab(cache)
        qtbot.addWidget(tab)

        rows = {tab.table.item(r, 0).text(): r for r in range(tab.table.rowCount())}
        assert set(rows) == {"apple", "banana"}

        tab.table.item(rows["apple"], 1).setText("new_apple")
        tab._on_item_changed(tab.table.item(rows["apple"], 1))

        tab.table.selectRow(rows["banana"])
        tab._on_delete_selected()

        tab.save_changes_btn.click()
        qtbot.wait(100)

        records = cache.get_all_records()
        assert len(records) == 1
        assert records[0][0] == "apple"
        assert records[0][1] == "new_apple"
        assert len(tab.pending_updates) == 0
        assert len(tab.pending_deletions) == 0
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_bidirectional_language_sync(qtbot):
    from gui import App, TranslationMemoryTab
    from core import TranslationCache
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test1": "тест1", "test2": "тест2"})
        cache.close()

        from PyQt6.QtCore import QSettings
        QSettings("MineAI", "SNBT-Localizer").clear()

        app = App()
        qtbot.addWidget(app)
        qtbot.wait(100)

        app.translation_memory_tab.cache.close()
        app.translation_memory_tab.db_path = db_path
        app.translation_memory_tab.set_language_code("ru_ru")
        app.translation_memory_tab.lang_filter.setCurrentText("Russian (ru_ru)")
        qtbot.wait(100)

        assert app.lang_box.currentText() == app.translation_memory_tab.lang_filter.currentText()

        app.lang_box.setCurrentText("Spanish (es_es)")
        qtbot.wait(600)
        assert app.translation_memory_tab.lang_filter.currentText() == "Spanish (es_es)"
        assert app.translation_memory_tab.cache.table_name == "cache_es_es"

        app.translation_memory_tab.lang_filter.setCurrentText("German (de_de)")
        qtbot.wait(600)
        assert app.lang_box.currentText() == "German (de_de)"
        assert app.translation_memory_tab.cache.table_name == "cache_de_de"

        assert app.settings.value("target_lang") == "German (de_de)"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_language_sync_no_infinite_loop(qtbot):
    from gui import App
    from PyQt6.QtCore import QSettings
    QSettings("MineAI", "SNBT-Localizer").clear()

    app = App()
    qtbot.addWidget(app)
    qtbot.wait(100)

    call_count = 0
    def count_calls(text):
        nonlocal call_count
        call_count += 1

    app.lang_box.blockSignals(True)
    app.lang_box.setCurrentText("Russian (ru_ru)")
    app.lang_box.blockSignals(False)
    qtbot.wait(100)

    app.lang_box.currentTextChanged.disconnect()
    app.lang_box.currentTextChanged.connect(count_calls)
    app.lang_box.setCurrentText("German (de_de)")
    qtbot.wait(100)

    assert call_count == 1

def test_modpack_column_migration():
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cursor = cache.conn.cursor()
        cursor.execute("PRAGMA table_info(cache_ru_ru)")
        columns = [col[1] for col in cursor.fetchall()]
        assert "modpack" in columns
        cursor.execute("PRAGMA index_list(cache_ru_ru)")
        indexes = [idx[1] for idx in cursor.fetchall()]
        assert any("modpack" in idx for idx in indexes)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_save_batch_with_modpack():
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test": "тест"}, modpack="FTB Skies")
        cursor = cache.conn.cursor()
        cursor.execute("SELECT modpack FROM cache_ru_ru WHERE orig = 'test'")
        result = cursor.fetchone()
        assert result[0] == "FTB Skies"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_save_batch_without_modpack():
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test": "тест"})
        cursor = cache.conn.cursor()
        cursor.execute("SELECT modpack FROM cache_ru_ru WHERE orig = 'test'")
        result = cursor.fetchone()
        assert result[0] is None
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_filter_by_modpack():
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test1": "тест1"}, modpack="FTB Skies")
        cache.save_batch({"test2": "тест2"}, modpack="Create Above")
        cache.save_batch({"test3": "тест3"})
        records = cache.get_all_records(modpack_filter="FTB Skies")
        assert len(records) == 1
        assert records[0][0] == "test1"
        assert records[0][2] == "FTB Skies"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_get_unique_modpacks():
    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
        db_path = f.name
    try:
        cache = TranslationCache(db_path=db_path, target_lang_code="ru_ru")
        cache.save_batch({"test1": "тест1"}, modpack="FTB Skies")
        cache.save_batch({"test2": "тест2"}, modpack="Create Above")
        cache.save_batch({"test3": "тест3"})
        modpacks = cache.get_unique_modpacks()
        assert set(modpacks) == {"FTB Skies", "Create Above"}
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_model_reload_on_key_change(qtbot, monkeypatch):
    import gui
    from unittest.mock import MagicMock

    monkeypatch.setattr(gui, "UpdateChecker", MagicMock)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    app = App()
    qtbot.addWidget(app)
    app.settings.clear()

    triggered = []
    monkeypatch.setattr(app, "_trigger_loader", lambda provider, key: triggered.append((provider, key)))

    app.provider_box.setCurrentText("Groq Cloud (Fast)")
    qtbot.wait(100)
    triggered.clear()

    app.key_pool_edit.setPlainText("gsk_new_user_key")
    qtbot.wait(800)
    assert ("Groq Cloud (Fast)", "gsk_new_user_key") in triggered

def test_verification_label_shows_answers(qtbot, monkeypatch):
    import gui
    from unittest.mock import MagicMock

    monkeypatch.setattr(gui, "UpdateChecker", MagicMock)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    app = App()
    qtbot.addWidget(app)

    app.on_verification_complete(
        {"k1": "Active", "k2": "Invalid", "k3": "Timeout"},
        {"k1": "Blue", "k2": "", "k3": ""},
        "What color is the sky on a clear day?",
    )
    label = app.lbl_key_status.text()
    assert "1/3 active" in label
    assert "[1] Blue" in label
    assert "[2] (Invalid)" in label
    assert "[3] (Timeout)" in label
    assert "What color is the sky on a clear day?" in label

def test_key_verifier_worker(qtbot, monkeypatch):
    import gui

    async def fake_test(provider, key, model, question, timeout=20.0):
        assert question in gui.TEST_QUESTIONS
        return ("Active", "Blue") if key == "k1" else ("Invalid", "")

    monkeypatch.setattr(gui, "test_key_with_question", fake_test)
    worker = gui.KeyVerifierWorker([("k1", "OpenAI", "m"), ("k2", "OpenAI", "m")])
    with qtbot.waitSignal(worker.verification_complete, timeout=5000) as blocker:
        worker.start()
    results = blocker.args[0]
    answers = blocker.args[1]
    question = blocker.args[2]
    assert results == {"k1": "Active", "k2": "Invalid"}
    assert answers == {"k1": "Blue", "k2": ""}
    assert question in gui.TEST_QUESTIONS

# ==================== v1.6.0: Local Contextual RAG Mod Scanner Tests ====================
