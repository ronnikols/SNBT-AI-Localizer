import sys
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from PyQt6.QtCore import Qt, QSettings
from gui import App
from core import resolve_mixed_pool, UnifiedTranslator
from config import ConfigManager, PROVIDER_DEFAULTS

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

def test_cli_mix_flag():
    from config import ConfigManager
    from unittest.mock import patch

    with patch('config.QSettings') as mock_qsettings:
        mock_settings = mock_qsettings.return_value
        mock_settings.value.side_effect = lambda key, default: {
            "api_keys_pool_Groq Cloud (Fast)": "groq_key1\ngroq_key2",
            "api_keys_pool_NVIDIA NIM": "nvapi_key1",
        }.get(key, default)

        config = ConfigManager()
        parsed = config.parse_cli_args(['--mix'])
        assert parsed.mix is True
        assert config.provider == "Mixed Providers"
        assert "Groq Cloud (Fast)" in config.api_keys_pool
        assert "groq_key1" in config.api_keys_pool["Groq Cloud (Fast)"]

def test_cli_mix_flag_api_keys_collection():
    from config import ConfigManager
    from unittest.mock import patch

    with patch('config.QSettings') as mock_qsettings:
        mock_settings = mock_qsettings.return_value
        mock_settings.value.side_effect = lambda key, default: {
            "api_keys_pool_Groq Cloud (Fast)": "groq_key1\ngroq_key2",
            "api_keys_pool_NVIDIA NIM": "nvapi_key1",
            "api_keys_pool_OpenAI": "sk-proj-123",
        }.get(key, default)

        config = ConfigManager()
        config.parse_cli_args(['--mix'])
        if config.provider == "Mixed Providers":
            api_keys = []
            for prov in config.api_keys_pool:
                api_keys.extend(config.api_keys_pool[prov])
        else:
            api_keys = config.get_api_keys()

        assert len(api_keys) == 4
        assert "groq_key1" in api_keys
        assert "groq_key2" in api_keys
        assert "nvapi_key1" in api_keys
        assert "sk-proj-123" in api_keys

def test_model_placeholder_substring_protection():
    translator = UnifiedTranslator(["test_key"], "Groq Cloud (Fast)", "Enter API Key to load models")
    assert translator.model == PROVIDER_DEFAULTS["Groq Cloud (Fast)"]

    translator = UnifiedTranslator(["test_key"], "OpenAI", "LOADING models...")
    assert translator.model == PROVIDER_DEFAULTS["OpenAI"]

    translator = UnifiedTranslator(["test_key"], "Mistral AI", "N/A")
    assert translator.model == PROVIDER_DEFAULTS["Mistral AI"]

    translator = UnifiedTranslator(["test_key"], "NVIDIA NIM", "none (free engine)")
    assert translator.model == PROVIDER_DEFAULTS["NVIDIA NIM"]

def test_provider_specific_model_saving():
    with patch('config.QSettings') as mock_qsettings:
        mock_settings = mock_qsettings.return_value
        mock_settings.value.side_effect = lambda key, default: {
            "provider": "Groq Cloud (Fast)",
            "model": "global-model",
            "model_Groq Cloud (Fast)": "groq-specific-model",
            "target_lang": "ru_ru",
            "concurrency_limit": 3,
            "custom_context": "",
            "policy": "Complement (Дополнить)"
        }.get(key, default)

        config = ConfigManager()
        config.load_from_settings()
        assert config.model == "groq-specific-model"

def test_cli_mix_wizard_enter_fallback():
    saved_keys_by_provider = {
        "Groq Cloud (Fast)": ["gsk_key1"],
        "NVIDIA NIM": ["nvapi_key1"]
    }
    saved_models_by_provider = {
        "Groq Cloud (Fast)": "llama3",
        "NVIDIA NIM": "nemotron"
    }
    default_models_by_provider = {
        "Groq Cloud (Fast)": "fallback-groq",
        "NVIDIA NIM": "fallback-nim"
    }
    pool = resolve_mixed_pool([], saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
    assert len(pool) == 2
    assert pool[0]["provider"] == "Groq Cloud (Fast)"
    assert pool[0]["model"] == "llama3"
    assert pool[1]["provider"] == "NVIDIA NIM"
    assert pool[1]["model"] == "nemotron"

def test_cli_mix_concurrency_escalation():
    from main import main_async
    from unittest.mock import patch, AsyncMock
    import asyncio
    from pathlib import Path

    with patch('main.ConfigManager') as mock_config_manager:
        mock_config = mock_config_manager.return_value
        mock_config.concurrency = 2
        mock_parsed = type('obj', (object,), {'mix': True, 'debug': False, 'clear_cache': False, 'fastdir': False, 'dir': None, 'gui': False})()
        mock_config.parse_cli_args.return_value = mock_parsed
        mock_config.provider = "Mixed Providers"
        mock_config.api_keys_pool = {
            "Groq Cloud (Fast)": ["key1", "key2"],
            "NVIDIA NIM": ["key3"]
        }
        mock_config.get_api_keys.return_value = ["key1", "key2", "key3"]
        mock_config.resolve_language.return_value = ("Russian", "ru_ru")

        with patch('main.run_mix_setup_wizard', new_callable=AsyncMock) as mock_wizard:
            mock_wizard.return_value = (Path("/tmp/test"), "Russian", "ru_ru")

            with patch('main.run_translation', new_callable=AsyncMock) as mock_translate:
                from PyQt6.QtCore import QSettings
                mock_translate.side_effect = lambda *args, **kwargs: QSettings("MineAI-Test", "SNBT-Localizer-Test").sync()
                mock_translate.return_value = 0

                asyncio.run(main_async())

                assert mock_translate.called
                call_args = mock_translate.call_args
                concurrency = call_args[0][7]
                assert concurrency >= 5

def test_provider_specific_cli_model_state():
    from unittest.mock import patch
    from pathlib import Path
    import asyncio
    from config import ConfigManager

    with patch('main.load_cli_setting') as mock_load, \
         patch('main.save_cli_setting') as mock_save, \
         patch('main.fetch_models', new_callable=AsyncMock) as mock_fetch, \
         patch('builtins.input', side_effect=["1", "4", "groq_key", "1", "1"]), \
         patch('main.is_interactive', return_value=True):

        mock_fetch.return_value = ["model1", "model2"]

        mock_load.side_effect = lambda key, default: {
            "cli_last_model_Groq Cloud (Fast)": "groq-model",
            "cli_last_model_NVIDIA NIM": "nim-model"
        }.get(key, default)
        from PyQt6.QtCore import QSettings
        mock_save.side_effect = lambda key, value: QSettings("MineAI-Test", "SNBT-Localizer-Test").setValue(key, value)

        from main import run_setup_wizard
        config = ConfigManager()
        asyncio.run(run_setup_wizard(config))

        assert any(call[0][0] == "cli_last_model_Groq Cloud (Fast)" for call in mock_save.call_args_list)

def test_regular_wizard_mixed_redirect():
    from unittest.mock import patch, AsyncMock
    from pathlib import Path
    import asyncio

    with patch('main.load_cli_setting') as mock_load, \
         patch('main.save_cli_setting') as mock_save, \
         patch('main.run_mix_setup_wizard', new_callable=AsyncMock) as mock_mix_wizard, \
         patch('main.fetch_models', new_callable=AsyncMock) as mock_fetch, \
         patch('builtins.input', side_effect=["1", "8"]), \
         patch('main.is_interactive', return_value=True):

        mock_mix_wizard.return_value = (Path("/tmp/test"), "Russian", "ru_ru")
        mock_fetch.return_value = ["model1", "model2"]
        mock_load.side_effect = lambda key, default: {
            "cli_last_instance": "/tmp/test",
            "cli_last_provider": "Groq Cloud (Fast)",
            "cli_last_lang": "ru_ru"
        }.get(key, default)

        from main import run_setup_wizard
        from config import ConfigManager
        config = ConfigManager()

        result = asyncio.run(run_setup_wizard(config))

        assert result[1] == "Mixed Providers"
        assert result[2] is None
        assert result[3] is None
        assert mock_save.called
        assert any(call[0][0] == "cli_last_provider" for call in mock_save.call_args_list)

def test_cli_settings_persistence_before_translation():
    from main import main_async
    from unittest.mock import patch, AsyncMock
    import asyncio

    async def mock_wizard_side_effect(cfg):
        cfg.provider = "Groq Cloud (Fast)"
        cfg.model = "test_model"
        cfg.target_lang = "ru_ru"
        cfg.quest_dir = Path("/tmp/test")
        cfg.custom_context = ""
        cfg.policy = "Complement (Дополнить)"
        cfg.save_to_settings()
        return (Path("/tmp/test"), "Groq Cloud (Fast)", "test_key", "test_model", "Russian", "ru_ru")

    with patch('main.ConfigManager') as mock_config_manager:
        mock_config = mock_config_manager.return_value
        mock_config.concurrency = 2
        mock_parsed = type('obj', (object,), {'mix': False, 'debug': False, 'clear_cache': False, 'fastdir': False, 'dir': None, 'gui': False})()
        mock_config.parse_cli_args.return_value = mock_parsed
        mock_config.provider = ""
        mock_config.model = None
        mock_config.target_lang = ""
        mock_config.quest_dir = None
        mock_config.custom_context = ""
        mock_config.policy = ""

        with patch('main.run_setup_wizard', new_callable=AsyncMock) as mock_wizard:
            mock_wizard.side_effect = mock_wizard_side_effect

            with patch('main.run_translation', new_callable=AsyncMock) as mock_translate:
                mock_translate.return_value = 0

                asyncio.run(main_async())

                assert mock_config.save_to_settings.called
                assert mock_wizard.called

def test_cli_mix_true_concurrency():
    from main import run_translation
    from unittest.mock import patch, AsyncMock, MagicMock
    from pathlib import Path
    import asyncio

    mock_config = MagicMock()
    mock_config.concurrency = 3
    mock_config.custom_context = ""
    mock_config.policy = "Complement (Дополнить)"

    mock_m = MagicMock()
    mock_m.process_file = AsyncMock(return_value=None)

    test_files = [Path(f"/tmp/test/file{i}.snbt") for i in range(5)]
    mock_quests_dir = MagicMock(spec=Path)
    mock_quests_dir.rglob.return_value = test_files
    mock_quests_dir.exists.return_value = True
    mock_quests_dir.is_dir.return_value = True
    mock_m.find_quests_dir.return_value = mock_quests_dir
    mock_m.translator = MagicMock()

    with patch('main.SNBTManager', return_value=mock_m), \
         patch('main.render_cli_progress'), \
         patch('main.sys') as mock_sys:

        mock_sys.stdout = MagicMock()

        asyncio.run(run_translation(
            mock_config,
            "Groq Cloud (Fast)",
            "test-model",
            ["test_key"],
            "Russian",
            "ru_ru",
            Path("/tmp/test"),
            concurrency=3
        ))

        assert mock_m.process_file.call_count == 5
        assert mock_m.find_quests_dir.called
