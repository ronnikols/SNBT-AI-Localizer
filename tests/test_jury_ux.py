# -*- coding: utf-8 -*-
"""UX-переделка ТЗ-Жюри: таблица судей = единственный QA-пикер.

Проверяется (критика юзера m11965/m11979/m11981/m12003):
- старый пикер qa_provider_combo/qa_model_box исчез; судья №1 = строка 0
  таблицы с теми же виджетами (combo + GhostSuffixLineEdit + completer);
- _judges_collect отдаёт ТОЛЬКО extras (строки 1..3); judge1_provider/model
  читаются из строки 0;
- пустой api_key судьи → пул его провайдера (provider_pool из qa_params);
- rows cap 4, удаление не трогает строку 0;
- настройки старых версий (config.qa_provider/qa_judges) поднимаются.
"""
import json
import os
import sys

import pytest

QT = pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui  # noqa: E402
import core  # noqa: E402
from config import ConfigManager  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _mk_tab(qapp, **cfg_over):
    cfg = ConfigManager()
    cfg.qa_provider = cfg_over.get("qa_provider", "")
    cfg.qa_model = cfg_over.get("qa_model", "")
    cfg.qa_judges = json.dumps(cfg_over.get("judges", []), ensure_ascii=False)
    return gui.SettingsTab(cfg)


def test_old_picker_widgets_gone(qapp):
    """Старые виджеты удалены — новых сжатий/дублей быть не может."""
    tab = _mk_tab(qapp)
    assert not hasattr(tab, "qa_provider_combo")
    assert not hasattr(tab, "qa_model_box")
    assert not hasattr(tab, "_qa_loader")
    # таблица есть, скролл-обёртка не нужна для проверки пикера


def test_judge1_is_row0_and_collect_skips_it(qapp):
    """Судья №1 = строка 0; _judges_collect отдаёт только extras."""
    tab = _mk_tab(qapp, qa_provider="Groq Cloud (Fast)",
                  qa_model="llama-3.3-70b/low",
                  judges=[{"name": "j2", "provider": "OpenAI", "base_url": "",
                           "api_key": "sk_test", "model": "gpt-5",
                           "temperature": 0.3, "enabled": True}])
    assert tab.judges_table.rowCount() == 2
    assert tab.judge1_provider() == "Groq Cloud (Fast)"
    assert tab.judge1_model() == "llama-3.3-70b/low"
    extras = tab._judges_collect()
    assert len(extras) == 1
    assert extras[0]["name"] == "j2"
    assert extras[0]["provider"] == "OpenAI"
    assert extras[0]["api_key"] == "sk_test"
    assert extras[0]["model"] == "gpt-5"
    assert extras[0]["temperature"] == 0.3
    # строка 0 НЕ входит в extras — она синхронится отдельно
    assert all(e["name"] != "j1 (primary QA model)" for e in extras)


def test_row_cap_four_and_delete_keeps_primary(qapp):
    """Cap 4 строки; удаление не трогает судью №1."""
    tab = _mk_tab(qapp)
    for _ in range(6):
        tab._judges_add_row()
    assert tab.judges_table.rowCount() == 4
    tab.judges_table.selectRow(1)
    tab._judges_del_selected()
    assert tab.judges_table.rowCount() == 3
    assert tab.judges_table.item(0, 1).text() == "j1 (primary QA model)"
    # удаление строки 0 — no-op
    tab.judges_table.selectRow(0)
    tab._judges_del_selected()
    assert tab.judges_table.rowCount() == 3
    assert tab.judges_table.item(0, 1).text() == "j1 (primary QA model)"


def test_primary_row_all_cells_editable(qapp):
    """m12653: ВСЕ поля судьи №1 редактируются (ключ/URL/температура/имя),
    пустые ключ/URL = пул провайдера с главного экрана."""
    from PyQt6.QtCore import Qt
    tab = _mk_tab(qapp)
    for col in (1, 3, 4, 6):
        item = tab.judges_table.item(0, col)
        assert item is not None, f"row0 col{col} item missing"
        assert item.flags() & Qt.ItemFlag.ItemIsEditable, (
            f"row0 col{col} must be editable")
    # provider/model строки 0 живые
    prov = tab.judges_table.cellWidget(0, 2)
    assert prov is not None
    box = tab.judges_table.cellWidget(0, 5)
    assert box is not None and box.isEditable()
    # overrides: пустые ячейки = {} — пул дефолтов
    assert tab.judge1_overrides() == {}
    # ввод ключа появляется в overrides
    tab.judges_table.item(0, 4).setText("k-j1")
    tab.judges_table.item(0, 3).setText("https://x.example/v1")
    tab.judges_table.item(0, 6).setText("0.4")
    ov = tab.judge1_overrides()
    assert ov == {"api_key": "k-j1", "base_url": "https://x.example/v1",
                  "temperature": 0.4}


def test_extra_judge_empty_key_falls_back_to_provider_pool(qapp):
    """m12003: пустой api_key судьи → пул его провайдера с воркспейса."""
    tab = _mk_tab(qapp, judges=[{
        "name": "j2", "provider": "Groq Cloud (Fast)", "base_url": "",
        "api_key": "", "model": "llama-3.3-70b", "temperature": None,
        "enabled": True}])
    extras = tab._judges_collect()
    assert extras and extras[0]["api_key"] == ""
    qa_params = {
        "provider": "Crusoe Cloud", "keys": ["k1"],
        "model": "m/high", "judges": extras,
        "provider_pool": {"Groq Cloud (Fast)": ["gsk_pool1", "gsk_pool2"],
                          "Crusoe Cloud": ["cru1"]},
        "custom_base_url": None, "temperature": 0.2,
    }
    judges = core.parse_qa_judges(qa_params)
    assert len(judges) == 2
    assert judges[0]["api_keys"] == ["k1"]
    assert judges[1]["api_keys"] == ["gsk_pool1", "gsk_pool2"]


def test_settings_tab_smoke_in_scroll(qapp):
    """Settings-вкладка живёт в QScrollArea — размеры не сжимаются."""
    tab = _mk_tab(qapp)
    hint = tab.minimumSizeHint()
    assert hint.height() > 400  # целая страница, не сжатая в 2 строки


def test_judge_model_completer_and_ghost_suffix(qapp):
    """Model-поля судей — GhostSuffixLineEdit('/low') + QCompleter."""
    tab = _mk_tab(qapp)
    from gui import GhostSuffixLineEdit
    box = tab.judges_table.cellWidget(0, 5)
    assert isinstance(box.lineEdit(), GhostSuffixLineEdit)
    assert box.completer() is not None
    tab._judges_add_row()
    box2 = tab.judges_table.cellWidget(1, 5)
    assert isinstance(box2.lineEdit(), GhostSuffixLineEdit)
    assert box2.completer() is not None


def test_judge_test_specs(qapp):
    """Test Keys видит жюри: свои ключи судей, пулы провайдеров,
    выкл. судья пропущен, дубликат key+model не тестируется дважды."""
    cfg = ConfigManager()
    cfg.qa_provider = "Crusoe Cloud"
    cfg.qa_model = "cru-main/high"
    cfg.set_api_keys("Crusoe Cloud", ["pool-cru-1", "pool-cru-2"])
    cfg.set_api_keys("RunInfra", ["pool-ri-1"])
    cfg.qa_judge1 = json.dumps({"api_key": "j1-own-key"})
    cfg.qa_judges = json.dumps([
        {"name": "j2", "provider": "RunInfra", "base_url": "",
         "api_key": "", "model": "kimi/high", "temperature": None,
         "enabled": True},
        {"name": "j3", "provider": "Crusoe Cloud", "base_url": "",
         "api_key": "pool-cru-1", "model": "cru-main/high",
         "temperature": None, "enabled": False},
    ])
    tab = gui.SettingsTab(cfg)
    specs = tab._judge_test_specs()
    # j1: свой ключ + модель j1
    assert ("j1-own-key", "Crusoe Cloud", "cru-main/high", "j1") in specs
    # j2: пустой ключ -> весь пул RunInfra
    assert ("pool-ri-1", "RunInfra", "kimi/high", "j2") in specs
    # j3 выключен (enabled: False) — его спеки не попадают
    assert not any(tag == "j3" for k, p, m, tag in specs)
    # дедупликация (key+model) в verify_keys, не здесь: j1 и j3 модели
    # совпадают, но ключи разные — оба тестируются
    j1_rows = [s for s in specs if s[3] == "j1"]
    assert len(j1_rows) == 1


def test_judge_test_button_per_row(qapp):
    """ТЗ-v4 A4: у КАЖДОЙ строки судьи своя кнопка Test."""
    from PyQt6.QtWidgets import QPushButton
    tab = _mk_tab(qapp)
    assert tab.judges_table.columnCount() == 8
    assert tab.judges_table.horizontalHeaderItem(7).text() == "Test"
    btn0 = tab.judges_table.cellWidget(0, 7)
    assert isinstance(btn0, QPushButton)
    assert btn0.text() == "Test"
    tab._judges_add_row(provider="Crusoe Cloud", api_key="cr_x", model="m/x")
    btn1 = tab.judges_table.cellWidget(1, 7)
    assert isinstance(btn1, QPushButton)
    # кнопки разных строк — разные объекты
    assert btn0 is not btn1


def test_judge_row_spec_own_key_and_pool_fallback(qapp):
    """A4: ключ строки, иначе пул провайдера; без модели — None."""
    cfg = ConfigManager()
    cfg.qa_provider = "Crusoe Cloud"
    cfg.qa_model = "cru-main/high"
    cfg.set_api_keys("Crusoe Cloud", ["pool-cru-1", "pool-cru-2"])
    cfg.set_api_keys("RunInfra", ["pool-ri-1", "pool-ri-2"])
    cfg.qa_judge1 = json.dumps({"api_key": "j1-own-key"})
    cfg.qa_judges = json.dumps([
        {"name": "j2", "provider": "RunInfra", "base_url": "",
         "api_key": "", "model": "kimi/high", "temperature": None,
         "enabled": True},
    ])
    tab = gui.SettingsTab(cfg)
    # j1: свой ключ (overrides), модель строки 0
    spec0 = tab._judge_row_spec(0)
    assert spec0 == (["j1-own-key"], "Crusoe Cloud", "cru-main/high", "j1")
    # j2: пустой ключ -> весь пул RunInfra
    spec1 = tab._judge_row_spec(1)
    assert spec1 == (["pool-ri-1", "pool-ri-2"], "RunInfra", "kimi/high", "j2")
    # пустая модель -> None (тестировать нечего)
    box = tab.judges_table.cellWidget(1, 5)
    box.setCurrentText("")
    assert tab._judge_row_spec(1) is None
    # require_enabled: выключенная строка пропускается
    box.setCurrentText("kimi/high")
    cb1 = tab.judges_table.cellWidget(1, 0)
    cb1.setChecked(False)
    assert tab._judge_row_spec(1, require_enabled=True) is None
    assert tab._judge_row_spec(1) is not None  # без флага — видна


def test_judge_test_done_sets_ok_and_fail(qapp):
    """A4: результат теста — '✓ OK' / '✗ N/M' + per-key детали в tooltip."""
    tab = _mk_tab(qapp)
    tab._judges_add_row(provider="Crusoe Cloud", api_key="cr_good", model="m/x")
    btn = tab.judges_table.cellWidget(1, 7)
    # все ключи живы
    tab._on_judge_test_done(1, {"cr_good": ("Active", "42")})
    assert btn.text() == "✓ OK"
    tip = btn.toolTip()
    assert "cr_good" in tip and "Active" in tip and "42" in tip
    # частичный провал
    tab._on_judge_test_done(1, {"cr_good": ("Active", "42"),
                                "cr_bad": ("Invalid key", "rejected")})
    assert btn.text() == "✗ 1/2"
    assert "cr_bad" in btn.toolTip() and "Invalid key" in btn.toolTip()
    # пустой результат — не падает, подсказка про app.log
    tab._on_judge_test_done(1, {})
    assert btn.text() == "Test"
    assert "app.log" in btn.toolTip()


def test_judge_test_row_without_model_shows_hint(qapp):
    """A4: клик Test по строке без модели — подсказка, без краша/сети."""
    tab = _mk_tab(qapp)
    tab._judges_add_row()  # пустая строка: модель не задана
    btn = tab.judges_table.cellWidget(1, 7)
    tab._judge_test_row(btn)
    assert btn.text() == "…"
    assert "model" in btn.toolTip().lower()
    assert not getattr(tab, "_judge_test_workers", {})
