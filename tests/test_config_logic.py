import pytest
from unittest.mock import patch, MagicMock
from config import ConfigManager


def test_smart_parse_key_gsk_trailing_backslash():
    config = ConfigManager()
    key, model = config.smart_parse_key("gsk_123\\")
    assert key == "gsk_123"
    assert model == "llama-3.3-70b-versatile"


def test_smart_parse_key_nvapi_no_backslash():
    config = ConfigManager()
    key, model = config.smart_parse_key("nvapi-456")
    assert key == "nvapi-456"
    assert model == "nvidia/nemotron-3-ultra"


def test_smart_parse_key_sk_or_with_model():
    config = ConfigManager()
    key, model = config.smart_parse_key("sk-or-789\\custom_model")
    assert key == "sk-or-789"
    assert model == "custom_model"


@patch.object(ConfigManager, "get_api_keys")
def test_get_all_available_keys(mock_get_api_keys):
    mock_get_api_keys.side_effect = lambda provider: {
        "Groq Cloud (Fast)": ["gsk_key1", "gsk_key2"],
        "NVIDIA NIM": ["nvapi_key1"],
        "OpenRouter (Cloud AI)": [],
        "Google Gemini (Free API)": [],
        "Sambanova": [],
    }.get(provider, [])

    config = ConfigManager()
    result = config.get_all_available_keys()

    assert isinstance(result, list)
    assert len(result) == 3
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 3
        provider, key, model = item
        assert provider in ["Groq Cloud (Fast)", "NVIDIA NIM"]
        assert key.startswith(("gsk_", "nvapi-"))
        assert model
