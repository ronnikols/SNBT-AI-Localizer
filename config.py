import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Optional
from core import is_valid_custom_instance, PROVIDER_DEFAULTS

try:
    from PyQt6.QtCore import QSettings
except ImportError:
    QSettings = None

APP_VERSION = "1.1.21"

PROVIDER_ALIASES = {
    "google": "Google Translate (Free)",
    "google_free": "Google Translate (Free)",
    "gemini": "Google Gemini (Free API)",
    "ollama": "Ollama (Local / Free)",
    "groq": "Groq Cloud (Fast)",
    "openrouter": "OpenRouter (Cloud AI)",
    "nvidia": "NVIDIA NIM",
    "nim": "NVIDIA NIM",
    "sambanova": "Sambanova",
    "mixed": "Mixed Providers",
    "mix": "Mixed Providers",
    "openai": "OpenAI",
    "mistral": "Mistral AI",
    "anthropic": "Anthropic (Claude)",
    "claude": "Anthropic (Claude)",
    "cohere": "Cohere",
    "local": "Local LLM / Custom",
    "custom": "Local LLM / Custom",
}

PROVIDER_ENDPOINTS = {
    "Google Gemini (Free API)": "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "Groq Cloud (Fast)": "https://api.groq.com/openai/v1/models",
    "OpenRouter (Cloud AI)": "https://openrouter.ai/api/v1/models",
    "NVIDIA NIM": "https://integrate.api.nvidia.com/v1/models",
    "Ollama (Local / Free)": "http://localhost:11434/v1/models",
    "Sambanova": "https://api.sambanova.ai/v1/models",
    "OpenAI": "https://api.openai.com/v1/models",
    "Mistral AI": "https://api.mistral.ai/v1/models",
    "Anthropic (Claude)": "https://api.anthropic.com/v1/messages",
    "Cohere": "https://api.cohere.ai/v1/chat",
    "Local LLM / Custom": "",
}

LANG_ALIASES = {
    "ru": ("Russian", "ru_ru"),
    "en": ("English", "en_us"),
    "es": ("Spanish", "es_es"),
    "zh": ("Chinese Simplified", "zh_cn"),
    "zh-cn": ("Chinese Simplified", "zh_cn"),
    "zh-tw": ("Chinese Traditional", "zh_tw"),
    "de": ("German", "de_de"),
    "fr": ("French", "fr_fr"),
    "pt": ("Portuguese", "pt_br"),
    "pt-br": ("Portuguese", "pt_br"),
    "ja": ("Japanese", "ja_jp"),
    "ko": ("Korean", "ko_kr"),
}

ENV_KEY_MAP = {
    "Google Gemini (Free API)": "GEMINI_API_KEY",
    "Groq Cloud (Fast)": "GROQ_API_KEY",
    "OpenRouter (Cloud AI)": "OPENROUTER_API_KEY",
    "NVIDIA NIM": "NVIDIA_API_KEY",
    "Sambanova": "SAMBANOVA_API_KEY",
    "OpenAI": "OPENAI_API_KEY",
    "Mistral AI": "MISTRAL_API_KEY",
    "Anthropic (Claude)": "ANTHROPIC_API_KEY",
    "Cohere": "COHERE_API_KEY",
    "Local LLM / Custom": "",
}

SETTINGS_KEY_MAP = {
    "Google Gemini (Free API)": "gemini_api_key",
    "Groq Cloud (Fast)": "groq_api_key",
    "OpenRouter (Cloud AI)": "openrouter_api_key",
    "NVIDIA NIM": "nvidia_api_key",
    "Sambanova": "sambanova_api_key",
    "OpenAI": "openai_api_key",
    "Mistral AI": "mistral_api_key",
    "Anthropic (Claude)": "anthropic_api_key",
    "Cohere": "cohere_api_key",
    "Local LLM / Custom": "",
}

class ConfigManager:
    AVAILABLE_PROVIDERS = [
        "Groq Cloud (Fast)",
        "NVIDIA NIM",
        "OpenRouter (Cloud AI)",
        "Google Gemini (Free API)",
        "Sambanova",
        "OpenAI",
        "Mistral AI",
        "Anthropic (Claude)",
        "Cohere",
        "Google Translate (Free)",
        "Ollama (Local / Free)",
        "Local LLM / Custom"
    ]

    def __init__(self):
        self.quest_dir: Optional[Path] = None
        self.target_lang: str = "ru_ru"
        self.concurrency: int = 2
        self.provider: str = "Google Translate (Free)"
        self.model: Optional[str] = None
        self.custom_context: str = ""
        self.policy: str = "Complement (Дополнить)"
        self.resource_pack_mode: bool = False
        self.api_keys_pool: Dict[str, List[str]] = {prov: [] for prov in PROVIDER_ALIASES.values()}
        self.custom_instances_paths: List[str] = []
        self.batch_size: int = 50
        self.min_batch_size: int = 1
        self.max_concurrent_requests: int = 10

        self.load_from_settings()

    def _settings(self):
        if QSettings is None:
            return None
        return QSettings("MineAI", "SNBT-Localizer")

    def load_from_settings(self):
        s = self._settings()
        if s is None:
            return

        self.provider = s.value("provider", self.provider)
        self.model = s.value("model", self.model)
        if self.provider and self.provider != "Mixed Providers":
            provider_model = s.value(f"model_{self.provider}", "")
            if provider_model:
                self.model = provider_model
        self.target_lang = s.value("target_lang", self.target_lang)
        self.concurrency = int(s.value("concurrency_limit", self.concurrency))
        self.custom_context = s.value("custom_context", self.custom_context)
        self.policy = s.value("policy", self.policy)

        raw = s.value("custom_instances_paths", "")
        if raw:
            self.custom_instances_paths = [p.strip() for p in str(raw).splitlines() if p.strip()]

        self.batch_size = int(s.value("batch_size", 50))
        self.min_batch_size = int(s.value("min_batch_size", 1))
        self.max_concurrent_requests = int(s.value("max_concurrent_requests", 10))
        self.resource_pack_mode = s.value("resource_pack_mode", self.resource_pack_mode)
        if isinstance(self.resource_pack_mode, str):
            self.resource_pack_mode = self.resource_pack_mode.lower() == "true"
        quest_dir_value = s.value("quest_dir", "")
        self.quest_dir = Path(quest_dir_value) if quest_dir_value else None

        for prov in PROVIDER_ALIASES.values():
            raw = s.value(f"api_keys_pool_{prov}", "")
            if raw:
                lines = [line.strip() for line in str(raw).splitlines() if line.strip()]
                seen = set()
                unique = []
                for k in lines:
                    if k not in seen:
                        seen.add(k)
                        unique.append(k)
                self.api_keys_pool[prov] = unique[:10]
            if prov not in self.api_keys_pool:
                self.api_keys_pool[prov] = []

    def save_to_settings(self):
        s = self._settings()
        if s is None:
            return

        s.setValue("provider", self.provider)
        s.setValue("model", self.model or "")
        if self.provider and self.provider != "Mixed Providers":
            s.setValue(f"model_{self.provider}", self.model or "")
        s.setValue("target_lang", self.target_lang)
        s.setValue("concurrency_limit", self.concurrency)
        s.setValue("custom_context", self.custom_context)
        s.setValue("policy", self.policy)
        s.setValue("custom_instances_paths", "\n".join(self.custom_instances_paths))

        for prov, keys in self.api_keys_pool.items():
            s.setValue(f"api_keys_pool_{prov}", "\n".join(keys))

        s.setValue("batch_size", self.batch_size)
        s.setValue("min_batch_size", self.min_batch_size)
        s.setValue("max_concurrent_requests", self.max_concurrent_requests)
        s.setValue("resource_pack_mode", self.resource_pack_mode)
        s.setValue("quest_dir", str(self.quest_dir) if self.quest_dir else "")
        s.sync()

    def parse_cli_args(self, args: Optional[List[str]] = None):
        parser = argparse.ArgumentParser(prog='snbt-tr', add_help=False)
        parser.add_argument("-h", "--help", action="help", help="Show this help message and exit")
        parser.add_argument("-p", "--provider", help="Provider alias (google, gemini, groq, openrouter, nvidia, nim, sambanova)")
        parser.add_argument("-m", "--model", help="Model name (default: provider default)")
        parser.add_argument("-k", "--key", help="API key(s), comma-separated (env/QSettings fallback)")
        parser.add_argument("-l", "--lang", default="ru", help="Language code (default: ru)")
        parser.add_argument("-d", "--dir", default=None, help="Path to quests directory (default: auto-detect)")
        parser.add_argument("-c", "--context", default="", help="Custom translation context")
        parser.add_argument("--policy", default="complement", choices=["complement", "overwrite", "skip"],
                            help="Existing files policy: complement, overwrite, skip (default: complement)")
        parser.add_argument("--concurrency", type=int, default=2,
                            help="Number of parallel translation threads (1-10, default: 3)")
        parser.add_argument("--list-models", action="store_true", help="List available models for provider and exit")
        parser.add_argument("--fastdir", "--fd", action="store_true", help="Scan launcher paths for instances and exit")
        parser.add_argument("--clear-cache", "--clear", action="store_true", help="Clear translation cache and exit")
        parser.add_argument("--debug", action="store_true", help="Enable debug logging to console")
        parser.add_argument('--mix', action='store_true', help='Enable Mixed Provider mode using QSettings key pool')
        parser.add_argument('--gui', action='store_true', help='Launch Graphical User Interface (GUI)')
        parser.add_argument("--batch-size", type=int, default=50,
                            help="Batch size for translation (default: 50)")
        parser.add_argument("--min-batch-size", type=int, default=1,
                            help="Minimum batch size before failing (default: 1)")
        parser.add_argument("--max-concurrent-requests", type=int, default=10,
                            help="Max concurrent API requests (default: 10)")
        parser.add_argument("--resource-pack", "-r", action="store_true", help="Enable Resource Pack Mode for JSON translation")

        parsed = parser.parse_args(args)

        if parsed.provider:
            alias = parsed.provider.lower()
            if alias in PROVIDER_ALIASES:
                self.provider = PROVIDER_ALIASES[alias]
            else:
                logging.getLogger("snbt_localizer.cli").error(f"Unknown provider alias: {parsed.provider}")
                self.provider = "Google Translate (Free)"
                sys.exit(1)

        if parsed.mix:
            self.provider = "Mixed Providers"

        if parsed.model:
            self.model = parsed.model

        if parsed.lang:
            lang_input = parsed.lang.lower()
            if lang_input in LANG_ALIASES:
                self.target_lang = LANG_ALIASES[lang_input][1]
            else:
                for alias, (name, code) in LANG_ALIASES.items():
                    if lang_input == code or lang_input == name.lower():
                        self.target_lang = code
                        break
                else:
                    logging.getLogger("snbt_localizer.cli").error(f"Unknown language: {parsed.lang}")
                    sys.exit(1)

        if parsed.dir:
            self.quest_dir = Path(parsed.dir)

        if parsed.context:
            self.custom_context = parsed.context

        if parsed.policy:
            mapping = {
                "complement": "Complement (Дополнить)",
                "overwrite": "Overwrite (Перезаписать)",
                "skip": "Skip (Пропустить)",
            }
            self.policy = mapping.get(parsed.policy, "Complement (Дополнить)")

        if parsed.concurrency:
            self.concurrency = max(1, min(parsed.concurrency, 10))

        if parsed.batch_size:
            self.batch_size = max(1, parsed.batch_size)
        if parsed.min_batch_size:
            self.min_batch_size = max(1, parsed.min_batch_size)
        if parsed.max_concurrent_requests:
            self.max_concurrent_requests = max(1, parsed.max_concurrent_requests)


        if parsed.key:
            keys = [k.strip() for k in parsed.key.split(",") if k.strip()]
            seen = set()
            unique = []
            for k in keys:
                if k not in seen:
                    seen.add(k)
                    unique.append(k)
            self.api_keys_pool[self.provider] = unique[:10]

        return parsed

    def get_api_keys(self, provider: Optional[str] = None) -> List[str]:
        prov = provider or self.provider
        return self.api_keys_pool.get(prov, [])

    def set_api_keys(self, provider: str, keys: List[str]):
        seen = set()
        unique = []
        for k in keys:
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                unique.append(k)
        self.api_keys_pool[provider] = unique[:10]

    def smart_parse_key(self, entry: str) -> tuple[str, str]:
        entry = entry.strip()
        if "\\" in entry:
            parts = entry.split("\\", 1)
            key = parts[0].strip()
            model = parts[1].strip() if parts[1].strip() else ""
            if model:
                return key, model
            # Trailing backslash with no model - use key part for prefix detection
            entry = key
        
        if entry.startswith("gsk_"):
            return entry, "llama-3.3-70b-versatile"
        if entry.startswith("nvapi-"):
            return entry, "nvidia/nemotron-3-ultra"
        if entry.startswith("sk-or-"):
            return entry, "meta-llama/llama-3.3-70b-instruct:free"
        
        raise ValueError(f"Unknown key format or provider prefix: {entry[:10]}...")

    def get_all_available_keys(self) -> list[tuple[str, str, str]]:
        result = []
        for provider in self.AVAILABLE_PROVIDERS:
            keys = self.get_api_keys(provider)
            if not keys:
                continue
            
            saved_model = ""
            if QSettings is not None:
                settings = QSettings("MineAI", "SNBT-Localizer")
                saved_model = settings.value(f"model_{provider}", "") or ""
            
            default_model = PROVIDER_DEFAULTS.get(provider, "")
            model = saved_model if saved_model else default_model
            
            for key in keys:
                result.append((provider, key, model))
        
        return result

    def resolve_language(self, lang_input: str) -> tuple:
        lang_input = lang_input.lower()
        if lang_input in LANG_ALIASES:
            return LANG_ALIASES[lang_input]
        for alias, (name, code) in LANG_ALIASES.items():
            if lang_input == code or lang_input == name.lower():
                return (name, code)
        raise ValueError(f"Unknown language: {lang_input}")

    def add_custom_path(self, path: str):
        path = str(Path(path).resolve())
        if path not in self.custom_instances_paths:
            self.custom_instances_paths.append(path)
            self.save_to_settings()

    def prune_invalid_paths(self):
        valid_paths = []
        for p in self.custom_instances_paths:
            if is_valid_custom_instance(Path(p)):
                valid_paths.append(p)
        if valid_paths != self.custom_instances_paths:
            self.custom_instances_paths = valid_paths
            self.save_to_settings()
