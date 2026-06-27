import sys
import pytest
from PyQt6.QtCore import Qt
from gui import App
from core import resolve_mixed_pool

def test_resolve_mixed_pool_empty_fallback():
    saved_keys = {
        "Groq Cloud (Fast)": ["gsk_key1"],
        "NVIDIA NIM": ["nvapi-key2"]
    }
    saved_models = {
        "Groq Cloud (Fast)": "llama3",
        "NVIDIA NIM": "nemotron"
    }
    defaults = {
        "Groq Cloud (Fast)": "fallback-groq",
        "NVIDIA NIM": "fallback-nim"
    }
    pool = resolve_mixed_pool([], saved_keys, saved_models, defaults)
    assert len(pool) == 2
    assert pool[0]["api_key"] == "gsk_key1"
    assert pool[0]["provider"] == "Groq Cloud (Fast)"
    assert pool[0]["model"] == "llama3"
    assert pool[1]["api_key"] == "nvapi-key2"
    assert pool[1]["model"] == "nemotron"

def test_resolve_mixed_pool_autodetect():
    pairs = [
        {"key": "gsk_key123", "model": None},
        {"key": "nvapi-key456", "model": None}
    ]
    saved_keys = {}
    saved_models = {
        "Groq Cloud (Fast)": "llama3-saved",
        "NVIDIA NIM": "nemotron-saved"
    }
    defaults = {
        "Groq Cloud (Fast)": "fallback-groq",
        "NVIDIA NIM": "fallback-nim"
    }
    pool = resolve_mixed_pool(pairs, saved_keys, saved_models, defaults)
    assert len(pool) == 2
    assert pool[0]["provider"] == "Groq Cloud (Fast)"
    assert pool[0]["model"] == "llama3-saved"
    assert pool[1]["provider"] == "NVIDIA NIM"
    assert pool[1]["model"] == "nemotron-saved"

def test_gui_provider_key_isolation(qtbot):
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

def test_cli_mixed_pool_backslash_parsing():
    from main import parse_key_model_pairs
    pairs = parse_key_model_pairs(["gsk_123\\llama-model", "nvapi-456"])
    assert len(pairs) == 2
    assert pairs[0]["key"] == "gsk_123"
    assert pairs[0]["model"] == "llama-model"
    assert pairs[1]["key"] == "nvapi-456"
    assert pairs[1]["model"] is None

def test_resolve_mixed_pool_sambanova_detection():
    from core import resolve_mixed_pool

    saved_keys_by_provider = {}
    saved_models_by_provider = {}
    default_models_by_provider = {}

    pairs = [{"key": "sambanova_key_123", "model": None}]
    saved_keys_by_provider = {
        "Sambanova": ["sambanova_key_123"],
        "Groq Cloud (Fast)": []
    }
    pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
    assert len(pool) == 1
    assert pool[0]["provider"] == "Sambanova"

    pairs = [{"key": "sn-abc123", "model": None}]
    saved_keys_by_provider = {}
    pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
    assert len(pool) == 1
    assert pool[0]["provider"] == "Sambanova"

    pairs = [{"key": "550e8400-e29b-41d4-a716-446655440000", "model": None}]
    saved_keys_by_provider = {}
    pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
    assert len(pool) == 1
    assert pool[0]["provider"] == "Sambanova"
