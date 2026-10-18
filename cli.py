import os
import re
import sys
import asyncio
import json
import ctypes
import random
import httpx
import logging
from pathlib import Path
from typing import List, Optional, Dict
from logging.handlers import RotatingFileHandler
from core import SNBTManager, EXCLUDED_DIRS, TranslationCache, UnifiedTranslator, AbortException, get_base_url, is_valid_custom_instance, PROVIDER_DEFAULTS, JSONManager, find_quests_dir
from config import ConfigManager, PROVIDER_ALIASES, PROVIDER_ENDPOINTS, LANG_ALIASES, ENV_KEY_MAP, SETTINGS_KEY_MAP, APP_VERSION
from cli_ui import ui, UIHandler, mask_key
try:
    from PyQt6.QtCore import QSettings
except ImportError:
    QSettings = None

SERVICE_MODEL_KEYWORDS = {"orpheus", "tts", "whisper", "embed", "moderation", "safety", "guard", "reward"}
KEYLESS_PROVIDERS = ("Google Translate (Free)", "Ollama (Local / Free)")
LOG = logging.getLogger("snbt_localizer.cli")

def has_kubejs_lang(instance_path: Path) -> bool:
    for kubejs_dir in (instance_path / "kubejs", instance_path / "minecraft" / "kubejs",
                       instance_path / ".minecraft" / "kubejs"):
        if not kubejs_dir.is_dir():
            continue
        try:
            for lang_dir in kubejs_dir.rglob("lang"):
                if lang_dir.is_dir() and (lang_dir / "en_us.json").is_file():
                    return True
        except (PermissionError, OSError):
            continue
    return False

def find_all_quest_dirs(instance_path: Path) -> list[Path]:
    quest_dirs = []
    MAX_DEPTH = 3

    standard_paths = [
        instance_path / "config" / "ftbquests" / "quests",
        instance_path / "minecraft" / "config" / "ftbquests" / "quests",
        instance_path / ".minecraft" / "config" / "ftbquests" / "quests",
    ]
    for cp in standard_paths:
        if cp.exists() and cp.is_dir():
            quest_dirs.append(cp)

    def scan(base: Path, depth: int = 0):
        if depth > MAX_DEPTH:
            return
        try:
            with os.scandir(base) as it:
                for entry in it:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name.startswith('.') and entry.name != ".minecraft":
                        continue
                    path = Path(entry.path)
                    if path.name == "quests" and path.parent.name == "ftbquests":
                        if path not in quest_dirs:
                            quest_dirs.append(path)
                    if depth < MAX_DEPTH:
                        scan(path, depth + 1)
        except (PermissionError, Exception):
            return

    scan(instance_path)
    if not quest_dirs and is_valid_custom_instance(instance_path):
        quest_dirs.append(instance_path)
    if not quest_dirs and has_kubejs_lang(instance_path):
        quest_dirs.append(instance_path)
    return quest_dirs


def setup_logging(debug=False):
    root_logger = logging.getLogger("snbt_localizer")
    if root_logger.handlers:
        return
    root_logger.setLevel(logging.DEBUG)

    log_dir = os.path.expanduser("~/.snbt_localizer/logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
    root_logger.addHandler(file_handler)

    console_handler = UIHandler(ui)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    # Records marked _cb_shown were already printed via the print() log
    # callback (qa_log/_health_log); drop them here so the console shows
    # each line exactly once. The file handler keeps them.
    console_handler.addFilter(lambda r: not getattr(r, "_cb_shown", False))
    root_logger.addHandler(console_handler)

    root_logger.propagate = False

def render_cli_progress(current, total, prefix="", suffix=""):
    bar_len = 30
    filled_len = int(round(bar_len * current / float(total))) if total else 0
    bar = '█' * filled_len + '░' * (bar_len - filled_len)
    percent = round(100.0 * current / float(total), 1) if total else 0.0
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()

def get_launcher_paths() -> list[tuple[Path, str]]:
    home = Path.home()
    paths = []
    
    if sys.platform == "win32":
        appdata = Path(os.getenv("APPDATA", home / "AppData/Roaming"))
        localappdata = Path(os.getenv("LOCALAPPDATA", home / "AppData/Local"))
        paths = [
            (appdata / "PrismLauncher/instances", "PrismLauncher"),
            (appdata / "ElyPrismLauncher/instances", "ElyPrismLauncher"),
            (appdata / "MultiMC/instances", "MultiMC"),
            (appdata / "PolyMC/instances", "PolyMC"),
            (appdata / ".minecraft/versions", ".minecraft"),
            (appdata / ".minecraft/profiles", ".minecraft"),
            (appdata / ".tlauncher/legacy/Minecraft/versions", "TLauncher"),
            (appdata / ".tlauncher/legacy/Minecraft/profiles", "TLauncher"),
            (appdata / ".tlauncher/versions", "TLauncher"),
            (appdata / ".tlauncher/profiles", "TLauncher"),
            (appdata / ".klauncher/versions", "KLauncher"),
            (appdata / ".klauncher/profiles", "KLauncher"),
            (appdata / ".sklauncher/instances", "SKLauncher"),
            (appdata / ".sklauncher/profiles", "SKLauncher"),
            (appdata / "ATLauncher/instances", "ATLauncher"),
            (appdata / "gdlauncher_carbon/instances", "GDLauncher"),
            (appdata / "gdlauncher/instances", "GDLauncher"),
            (appdata / ".technic/modpacks", "Technic"),
            (appdata / ".feather/user/instances", "Feather"),
            (appdata / ".salwyrr/instances", "Salwyrr"),
            (appdata / ".crystallauncher/instances", "CrystalLauncher"),
            (appdata / ".launcherfenenix/versions", "LauncherFenix"),
            (appdata / ".launcherfenenix/profiles", "LauncherFenix"),
            (appdata / ".aresclient/instances", "AresClient"),
            (appdata / ".pojavlauncher/minecraft/versions", "PojavLauncher"),
            (localappdata / ".ftba/instances", "FTBA"),
            (localappdata / "ModrinthApp/profiles", "ModrinthApp"),
            (home / "curseforge/minecraft/Instances", "CurseForge"),
            (home / "Documents/curseforge/minecraft/Instances", "CurseForge"),
            (home / ".lunarclient/offline/multiver", "LunarClient"),
        ]
    elif sys.platform == "darwin":
        paths = [
            (home / "Library/Application Support/PrismLauncher/instances", "PrismLauncher"),
            (home / "Library/Application Support/ElyPrismLauncher/instances", "ElyPrismLauncher"),
            (home / "Library/Application Support/MultiMC/instances", "MultiMC"),
            (home / "Library/Application Support/PolyMC/instances", "PolyMC"),
            (home / "Library/Application Support/minecraft/versions", ".minecraft"),
            (home / "Library/Application Support/minecraft/profiles", ".minecraft"),
            (home / "Library/Application Support/.tlauncher/legacy/Minecraft/versions", "TLauncher"),
            (home / "Library/Application Support/.tlauncher/legacy/Minecraft/profiles", "TLauncher"),
            (home / "Library/Application Support/.tlauncher/versions", "TLauncher"),
            (home / "Library/Application Support/.klauncher/versions", "KLauncher"),
            (home / "Library/Application Support/ModrinthApp/profiles", "ModrinthApp"),
            (home / "Library/Application Support/FTBA/instances", "FTBA"),
            (home / ".ftba/instances", "FTBA"),
            (home / "Library/Application Support/gdlauncher_carbon/instances", "GDLauncher"),
            (home / "Library/Application Support/gdlauncher/instances", "GDLauncher"),
            (home / "Library/Application Support/ATLauncher/instances", "ATLauncher"),
            (home / "Library/Application Support/.sklauncher/instances", "SKLauncher"),
            (home / "Library/Application Support/technic/modpacks", "Technic"),
            (home / "Library/Application Support/.feather/user/instances", "Feather"),
            (home / ".salwyrr/instances", "Salwyrr"),
            (home / ".crystallauncher/instances", "CrystalLauncher"),
            (home / ".launcherfenenix/versions", "LauncherFenix"),
            (home / ".aresclient/instances", "AresClient"),
            (home / ".pojavlauncher/minecraft/versions", "PojavLauncher"),
            (home / ".lunarclient/offline/multiver", "LunarClient"),
            (home / "Documents/curseforge/minecraft/Instances", "CurseForge"),
        ]
    else:
        paths = [
            (home / ".local/share/PrismLauncher/instances", "PrismLauncher"),
            (home / ".local/share/ElyPrismLauncher/instances", "ElyPrismLauncher"),
            (home / ".local/share/multimc/instances", "MultiMC"),
            (home / ".local/share/PolyMC/instances", "PolyMC"),
            (home / ".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances", "PrismLauncher (Flatpak)"),
            (home / ".local/share/ModrinthApp/profiles", "ModrinthApp"),
            (home / ".local/share/FTBA/instances", "FTBA"),
            (home / ".ftba/instances", "FTBA"),
            (home / ".local/share/gdlauncher_carbon/instances", "GDLauncher"),
            (home / ".local/share/gdlauncher/instances", "GDLauncher"),
            (home / ".local/share/ATLauncher/instances", "ATLauncher"),
            (home / ".minecraft/versions", ".minecraft"),
            (home / ".minecraft/profiles", ".minecraft"),
            (home / ".var/app/com.mojang.Minecraft/.minecraft/versions", ".minecraft (Flatpak)"),
            (home / ".var/app/com.mojang.Minecraft/.minecraft/profiles", ".minecraft (Flatpak)"),
            (home / ".tlauncher/legacy/Minecraft/versions", "TLauncher"),
            (home / ".tlauncher/legacy/Minecraft/profiles", "TLauncher"),
            (home / ".tlauncher/versions", "TLauncher"),
            (home / ".klauncher/versions", "KLauncher"),
            (home / ".sklauncher/instances", "SKLauncher"),
            (home / ".technic/modpacks", "Technic"),
            (home / ".feather/user/instances", "Feather"),
            (home / ".salwyrr/instances", "Salwyrr"),
            (home / ".crystallauncher/instances", "CrystalLauncher"),
            (home / ".launcherfenenix/versions", "LauncherFenix"),
            (home / ".aresclient/instances", "AresClient"),
            (home / ".pojavlauncher/minecraft/versions", "PojavLauncher"),
            (home / ".pojavlauncher/versions", "PojavLauncher"),
            (home / ".lunarclient/offline/multiver", "LunarClient"),
            (home / "curseforge/minecraft/Instances", "CurseForge"),
            (home / "Documents/curseforge/minecraft/Instances", "CurseForge"),
        ]
    return paths

def normalize_path(path: str) -> Path:
    expanded = os.path.expanduser(path)
    absolute = os.path.abspath(expanded)
    path_obj = Path(absolute)
    if path_obj.exists() and path_obj.is_dir():
        return path_obj
    
    launcher_paths = get_launcher_paths()
    
    target_name = Path(path).name.lower()
    for base, _ in launcher_paths:
        if not base.exists():
            continue
        try:
            for sub in base.iterdir():
                if sub.is_dir() and sub.name.lower() == target_name:
                    logging.getLogger("snbt_localizer.cli").info(f"Resolved instance '{sub.name}' -> '{sub}'")
                    return sub
        except Exception:
            pass
    
    die(f"Path does not exist: {path} -> {absolute}")

def is_interactive() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except:
        return False

def get_cli_settings():
    if QSettings is None:
        return None
    return QSettings("MineAI", "SNBT-Localizer")

def save_cli_setting(key: str, value: str):
    settings = get_cli_settings()
    if settings:
        settings.setValue(key, value)
        settings.sync()

def load_cli_setting(key: str, default: str = "") -> str:
    settings = get_cli_settings()
    if settings:
        val = settings.value(key, default)
        return str(val) if val else default
    return default


# ---------------------------------------------------------------------------
# Shared wizard steps
# ---------------------------------------------------------------------------

def _scan_instances(config: ConfigManager, with_quest_dirs: bool = False) -> list:
    """(name, path, launcher, quest_dirs) for every launcher instance + custom path."""
    instances = []
    seen = set()
    for base, launcher_name in get_launcher_paths():
        if not base.exists():
            continue
        try:
            for sub in base.iterdir():
                if not sub.is_dir() or str(sub) in seen:
                    continue
                quests_path = sub / "config" / "ftbquests" / "quests"
                if not quests_path.exists():
                    quests_path = sub / "minecraft" / "config" / "ftbquests" / "quests"
                if quests_path.exists() and quests_path.is_dir():
                    qdirs = find_all_quest_dirs(sub) if with_quest_dirs else [quests_path]
                    instances.append((sub.name, str(sub), launcher_name, qdirs or [quests_path]))
                    seen.add(str(sub))
                elif with_quest_dirs:
                    qdirs = find_all_quest_dirs(sub)
                    if qdirs:
                        instances.append((sub.name, str(sub), launcher_name, qdirs))
                        seen.add(str(sub))
        except Exception:
            pass
    for custom_path in config.custom_instances_paths:
        p = Path(custom_path)
        if str(p) in seen or not is_valid_custom_instance(p):
            continue
        qdirs = find_all_quest_dirs(p) if with_quest_dirs else [p]
        instances.append((p.name, str(p), "Custom", qdirs or [p]))
        seen.add(str(p))
    return instances


def _pick_instance(config: ConfigManager, instances: list, manual_prompt: str = "Enter path to modpack") -> tuple:
    """Interactive instance menu. Returns (quest_dir, quest_dirs)."""
    instances = sorted(instances, key=lambda x: x[1])
    last_instance = load_cli_setting("cli_last_instance", "")
    last_found = False
    if last_instance:
        for i, (_, path, _, _) in enumerate(instances):
            if path == last_instance:
                instances.insert(0, instances.pop(i))
                last_found = True
                break
    items = []
    for i, (name, path, launcher, qdirs) in enumerate(instances):
        note = f"[{launcher}]"
        if i == 0 and last_found:
            note += " (last used)"
        if len(qdirs) > 1:
            note += " [Multiple Folders]"
        items.append((name, note))
    ui.menu("Step 1 · Modpack instance", items, 0, ["Enter path manually..."])
    while True:
        idx = ui.choose(len(instances) + 1, 0)
        if idx < len(instances):
            quest_dir = Path(instances[idx][1])
            save_cli_setting("cli_last_instance", str(quest_dir))
            return quest_dir, list(instances[idx][3])
        custom_path = ui.ask(manual_prompt)
        if not custom_path:
            continue
        quest_dir = normalize_path(custom_path)
        config.add_custom_path(str(quest_dir))
        save_cli_setting("cli_last_instance", str(quest_dir))
        return quest_dir, [quest_dir]


def _lang_from_config(config: ConfigManager) -> tuple[str, str]:
    """Saved target_lang may be a code ('ru_ru'), a name, an alias, or the
    GUI combo text ('Russian (ru_ru)')."""
    raw = str(getattr(config, "target_lang", "") or "ru_ru")
    try:
        return config.resolve_language(raw)
    except Exception:
        pass
    from core import parse_target_lang
    name, code = parse_target_lang(raw)
    try:
        return config.resolve_language(code)
    except Exception:
        return name or code, code


def _resolve_lang_arg(lang_arg: str) -> tuple[str, str]:
    lang_input = lang_arg.lower()
    if lang_input in LANG_ALIASES:
        return LANG_ALIASES[lang_input]
    for alias, (name, code) in LANG_ALIASES.items():
        if lang_input == code or lang_input == name.lower():
            return name, code
    die(f"Unknown language: {lang_arg}")


def _pick_language(parsed=None, step: str = "Step 5 · Target language") -> tuple[str, str]:
    if parsed and getattr(parsed, "lang", None):
        lang_name, lang_code = _resolve_lang_arg(parsed.lang)
        save_cli_setting("cli_last_lang", lang_code)
        ui.info(f"Language from command line: {lang_name} ({lang_code})")
        return lang_name, lang_code
    seen_codes = set()
    langs = []
    for alias, (name, code) in LANG_ALIASES.items():
        if code not in seen_codes:
            seen_codes.add(code)
            langs.append((name, code))
    last_lang = load_cli_setting("cli_last_lang", "")
    default_idx = 0
    lang_found = False
    for i, (name, code) in enumerate(langs):
        if last_lang and (code == last_lang or name == last_lang):
            default_idx, lang_found = i, True
            break
    ui.menu(step, [(name, f"{code}" + (" (last used)" if lang_found and i == default_idx else ""))
                   for i, (name, code) in enumerate(langs)], default_idx)
    idx = ui.choose(len(langs), default_idx)
    lang_name, lang_code = langs[idx]
    save_cli_setting("cli_last_lang", lang_code)
    return lang_name, lang_code


async def _pick_model(provider: str, api_key: str | None, parsed=None, step: str = "Step 4 · Model") -> str:
    if parsed and getattr(parsed, "model", None):
        model = parsed.model
        save_cli_setting(f"cli_last_model_{provider}", model)
        ui.info(f"Model from command line: {model}")
        return model
    with_spinner = ui.rich and ui.color
    if with_spinner:
        with ui.console.status(f"[dim]Fetching models for {provider}...", spinner="dots"):
            models = await fetch_models(provider, api_key)
    else:
        models = await fetch_models(provider, api_key)
    models = list(models)
    recommended = "gemini-3.1-flash-lite" if ("gemini" in provider.lower() or "google" in provider.lower()) else None
    last_model = load_cli_setting(f"cli_last_model_{provider}", "")

    def sort_key(m):
        if m == last_model:
            return (0, m)
        if recommended and recommended in m:
            return (1, m)
        if ("nvidia" in provider.lower() or "nim" in provider.lower()) and "nemotron" in m.lower():
            return (2, m)
        return (3, m)

    models.sort(key=sort_key)
    all_models = list(models)
    if not models:
        fallback = PROVIDER_DEFAULTS.get(provider)
        if not fallback:
            die(f"No models available for {provider} and no default model. Pass -m/--model to specify one explicitly.")
        ui.warn(f"No models fetched from API, using: {fallback}")
        save_cli_setting(f"cli_last_model_{provider}", fallback)
        return fallback
    filter_text = ""
    while True:
        items = []
        for i, m in enumerate(models):
            note = ""
            if i == 0 and m == last_model:
                note = "(last used)"
            elif recommended and recommended in m:
                note = "[RECOMMENDED]"
            items.append((m, note))
        title = step + (f"  ·  filter: {filter_text}" if filter_text else "") + f"  ·  {len(models)}/{len(all_models)}"
        ui.menu(title, items, 0)
        choice = ui.choose(len(models), 0, allow_text=True, text="Choice (number, text to filter, 'all' to reset)")
        if isinstance(choice, int):
            model = models[choice]
            save_cli_setting(f"cli_last_model_{provider}", model)
            return model
        if choice.lower() == "all":
            models, filter_text = list(all_models), ""
            continue
        filtered = [m for m in all_models if choice.lower() in m.lower()]
        if filtered:
            models, filter_text = filtered, choice
        else:
            ui.warn("No models match that filter")


def _pick_key(provider: str, parsed=None) -> str | None:
    if provider in KEYLESS_PROVIDERS:
        return None
    settings_key = SETTINGS_KEY_MAP.get(provider)
    if parsed and getattr(parsed, "key", None):
        api_key = parsed.key
        if settings_key and api_key:
            save_cli_setting(settings_key, api_key)
        ui.info("API key from command line")
        return api_key
    env_key = load_key_from_env_or_settings(provider)
    if env_key:
        user_key = ui.ask(f"Step 3 · API key — Enter to use saved {mask_key(env_key)}, or type a new one")
        api_key = user_key or env_key
    else:
        while True:
            api_key = ui.ask(f"Step 3 · API key for {provider}")
            if api_key:
                break
            ui.warn("API Key cannot be empty")
    if settings_key and api_key:
        save_cli_setting(settings_key, api_key)
    return api_key


async def run_setup_wizard(config: ConfigManager, parsed=None) -> tuple[Path, str, str | None, str | None, str, str]:
    ui.rule("Setup Wizard")

    if parsed and getattr(parsed, "dir", None) is not None:
        quest_dir = normalize_path(parsed.dir)
        config.add_custom_path(str(quest_dir))
        ui.info(f"Directory from command line: {quest_dir}")
    else:
        instances = _scan_instances(config)
        if not instances:
            ui.warn("No modpack instances with FTB Quests found.")
            custom_path = ui.ask("Enter path to modpack manually")
            if not custom_path:
                die("No path provided")
            quest_dir = normalize_path(custom_path)
            config.add_custom_path(str(quest_dir))
        else:
            quest_dir, _ = _pick_instance(config, instances)
    ui.ok(f"Instance: {quest_dir}")

    providers = list(dict.fromkeys(PROVIDER_ALIASES.values()))
    if parsed and getattr(parsed, "provider", None):
        provider_alias = parsed.provider.lower()
        if provider_alias in PROVIDER_ALIASES:
            provider = PROVIDER_ALIASES[provider_alias]
        else:
            die(f"Unknown provider alias: {parsed.provider}")
        save_cli_setting("cli_last_provider", provider)
        ui.info(f"Provider from command line: {provider}")
    else:
        last_provider = load_cli_setting("cli_last_provider", "")
        default_idx = providers.index(last_provider) if last_provider in providers else 0
        ui.menu("Step 2 · Provider", [(p, "(last used)" if p == last_provider else "") for p in providers], default_idx)
        provider = providers[ui.choose(len(providers), default_idx)]
        save_cli_setting("cli_last_provider", provider)
    ui.ok(f"Provider: {provider}")

    if provider == "Mixed Providers":
        result = await run_mix_setup_wizard(config, parsed)
        if result is None:
            die("Mixed Providers setup cancelled.")
        quest_dir, lang_name, lang_code = result
        config.provider = provider
        config.target_lang = lang_code
        config.quest_dir = quest_dir
        config.save_to_settings()
        return quest_dir, provider, None, None, lang_name, lang_code

    api_key = _pick_key(provider, parsed)
    model = None if provider == "Google Translate (Free)" else await _pick_model(provider, api_key, parsed)
    if model:
        ui.ok(f"Model: {model}")
    lang_name, lang_code = _pick_language(parsed)
    ui.ok(f"Language: {lang_name} ({lang_code})")

    config.provider = provider
    config.model = model
    config.target_lang = lang_code
    config.quest_dir = quest_dir
    config.policy = "Complement (Дополнить)"
    if api_key:
        config.set_api_keys(provider, [api_key] + [k for k in config.get_api_keys(provider) if k != api_key])
    config.save_to_settings()
    return quest_dir, provider, api_key, model, lang_name, lang_code


async def run_mix_setup_wizard(config: ConfigManager, parsed=None) -> tuple[Path, str, str] | None:
    ui.rule("Mixed Providers Setup")

    if parsed and getattr(parsed, "dir", None):
        quest_dir = normalize_path(parsed.dir)
        config.add_custom_path(str(quest_dir))
        ui.info(f"Directory from command line: {quest_dir}")
    else:
        instances = _scan_instances(config, with_quest_dirs=True)
        if instances:
            quest_dir, _ = _pick_instance(config, instances)
        else:
            ui.warn("No modpack instances with FTB Quests found.")
            custom_path = ui.ask("Enter path to modpack manually")
            if not custom_path:
                return None
            quest_dir = normalize_path(custom_path)
            config.add_custom_path(str(quest_dir))
    ui.ok(f"Instance: {quest_dir}")

    providers = [p for p in dict.fromkeys(PROVIDER_ALIASES.values()) if p != "Mixed Providers"]
    if parsed and getattr(parsed, "mix", False):
        selected_providers = providers
        ui.info("Using all available providers for Mixed mode")
    else:
        saved = []
        if QSettings is not None:
            raw = QSettings("MineAI", "SNBT-Localizer").value("mixed_providers", [])
            saved = [raw] if isinstance(raw, str) else list(raw or [])
        ui.menu("Step 2 · Providers for Mixed mode",
                [(p, "(saved)" if p in saved else "") for p in providers], -1)
        choice = ui.ask("Numbers separated by space, Enter = all")
        if choice:
            selected_indices = []
            for part in choice.replace(",", " ").split():
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(providers) and idx not in selected_indices:
                        selected_indices.append(idx)
                except ValueError:
                    pass
            if not selected_indices:
                ui.err("No valid providers selected.")
                return None
            selected_providers = [providers[i] for i in selected_indices]
        else:
            selected_providers = providers
        if QSettings is not None:
            settings = QSettings("MineAI", "SNBT-Localizer")
            settings.setValue("mixed_providers", selected_providers)
            settings.sync()

    # An explicit -k key belongs to ONE provider (detected by prefix) —
    # storing it under every provider would later leak it to the wrong
    # endpoint. Unknown prefixes keep the legacy assign-to-all behavior.
    cli_key = getattr(parsed, "key", None) if parsed else None
    cli_key_owner = None
    if cli_key:
        from core import detect_provider
        cli_key_owner = detect_provider(cli_key)

    for prov in selected_providers:
        ui.rule(prov)
        if cli_key and (not cli_key_owner or cli_key_owner == prov):
            api_key = cli_key
            save_cli_setting(SETTINGS_KEY_MAP.get(prov, f"{prov}_api_key"), api_key)
            config.set_api_keys(prov, [api_key] + [k for k in config.get_api_keys(prov) if k != api_key])
            ui.info(f"API key from command line for {prov}")
        else:
            api_key = load_key_from_env_or_settings(prov)
            if not api_key:
                api_key = ui.ask(f"API key for {prov} (Enter to skip)")
                if api_key:
                    save_cli_setting(SETTINGS_KEY_MAP.get(prov, f"{prov}_api_key"), api_key)
                    config.set_api_keys(prov, [api_key])
                else:
                    ui.warn(f"Skipping {prov} - no API key provided.")
                    continue
            else:
                ui.info(f"Using saved key {mask_key(api_key)}")

        if parsed and getattr(parsed, "model", None):
            model = parsed.model
            ui.info(f"Model from command line for {prov}: {model}")
        else:
            models = await fetch_models(prov, api_key)
            if models:
                ui.menu(f"Model for {prov}", [(m, "") for m in models], 0)
                model = models[ui.choose(len(models), 0)]
            else:
                model = PROVIDER_DEFAULTS.get(prov, "")
                ui.warn(f"No models fetched for {prov}, using default: {model or '-'}")
        save_cli_setting(f"cli_last_model_{prov}", model)

    lang_name, lang_code = _pick_language(parsed, step="Step 3 · Target language")
    ui.ok(f"Language: {lang_name} ({lang_code})")
    config.provider = "Mixed Providers"
    config.target_lang = lang_code
    config.quest_dir = quest_dir
    config.save_to_settings()
    return quest_dir, lang_name, lang_code

def die(msg: str, code: int = 1) -> None:
    logging.getLogger("snbt_localizer.cli").error(msg)
    sys.exit(code)

def load_key_from_env_or_settings(provider: str) -> str | None:
    try:
        from PyQt6.QtCore import QSettings
        settings = QSettings("MineAI", "SNBT-Localizer")
        pool_val = settings.value(f"api_keys_pool_{provider}", "")
        if pool_val:
            lines = [line.strip() for line in str(pool_val).splitlines() if line.strip()]
            if lines:
                return lines[0]
    except ImportError:
        pass

    env_var = ENV_KEY_MAP.get(provider)
    if env_var:
        val = os.getenv(env_var)
        if val:
            return val
    settings_key = SETTINGS_KEY_MAP.get(provider)
    if settings_key:
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("MineAI", "SNBT-Localizer")
            val = settings.value(settings_key, "")
            if val:
                return str(val)
        except ImportError:
            pass
    if provider == "NVIDIA NIM":
        val = os.getenv("NVIDIA_API_KEY")
        if val:
            return val
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("MineAI", "SNBT-Localizer")
            val = settings.value("nvidia_api_key", "")
            if val:
                return str(val)
        except ImportError:
            pass
        val = os.getenv("NVIDIA_NIM_API_KEY")
        if val:
            return val
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("MineAI", "SNBT-Localizer")
            val = settings.value("nvidia_nim_api_key", "")
            if val:
                return str(val)
        except ImportError:
            pass
    return None

async def fetch_models(provider: str, api_key: str | None) -> list[str]:
    endpoint = PROVIDER_ENDPOINTS.get(provider)
    if not endpoint:
        return []
    headers = {}
    if api_key:
        if "Anthropic" in provider:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        elif provider != "Ollama (Local / Free)":
            headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if "Cohere" in provider:
                    models = [m.get("name") or m.get("id") if isinstance(m, dict) else m for m in data.get("models", [])]
                else:
                    models = [m["id"] for m in data.get("data", [])]
                return [m for m in models if not any(kw in m.lower() for kw in SERVICE_MODEL_KEYWORDS)]
            # Silent [] turns into an unusable empty model picker - log why
            logging.getLogger("snbt_localizer.cli").warning(
                f"fetch_models: {provider} returned HTTP {resp.status_code}"
            )
    except Exception as e:
        logging.getLogger("snbt_localizer.cli").warning(f"fetch_models: {provider} request failed: {e}")
    return []


async def cmd_list_models(config: ConfigManager, provider: str) -> int:
    # Prefer a key given on THIS command line (-k) over the saved one.
    pool_keys = config.get_api_keys(provider)
    api_key = pool_keys[0] if pool_keys else load_key_from_env_or_settings(provider)
    models = await fetch_models(provider, api_key)
    if not models:
        LOG.warning(f"No models found for {provider}")
        return 1
    last_model = load_cli_setting(f"cli_last_model_{provider}", "")
    ui.table(f"Models · {provider} ({len(models)})", ["#", "Model", ""],
             [(i + 1, m, "last used" if m == last_model else "") for i, m in enumerate(models)],
             styles=["dim", "", "dim"])
    return 0


def cmd_fastdir(config: ConfigManager = None) -> tuple[Path, list[Path]] | None:
    instances = []
    root_to_quest_dirs = {}
    for base, launcher_name in get_launcher_paths():
        if not base.exists():
            continue
        try:
            for sub in base.iterdir():
                if sub.is_dir():
                    quest_dirs = find_all_quest_dirs(sub)
                    if quest_dirs:
                        instances.append((sub.name, str(sub), launcher_name, quest_dirs))
                        root_to_quest_dirs[str(sub)] = quest_dirs
        except Exception:
            pass
    if config is not None:
        for custom_path in config.custom_instances_paths:
            p = Path(custom_path)
            if is_valid_custom_instance(p):
                quest_dirs = find_all_quest_dirs(p)
                if quest_dirs and str(p) not in root_to_quest_dirs:
                    instances.append((p.name, str(p), "Custom", quest_dirs))
                    root_to_quest_dirs[str(p)] = quest_dirs
    if not instances:
        LOG.warning("No modpack instances with FTB Quests found.")
        return None
    return _pick_instance(config, instances)

def resolve_policy(policy: str) -> str:
    mapping = {
        "complement": "Complement (Дополнить)",
        "overwrite": "Overwrite (Перезаписать)",
        "skip": "Skip (Пропустить)",
    }
    if not policy:
        return "Complement (Дополнить)"
    # Idempotent: config.policy may already hold the canonical value -
    # lowercasing it back into the alias map would silently reset to Complement
    p = policy.lower().split('(')[0].strip()
    if p in mapping:
        return mapping[p]
    return policy

def parse_key_model_pairs(api_keys: List[str]) -> List[Dict[str, str | None]]:
    pairs = []
    for k in api_keys:
        if "\\" in k:
            parts = k.split("\\", 1)
            pairs.append({"key": parts[0].strip(), "model": parts[1].strip() if len(parts) > 1 else None})
        else:
            pairs.append({"key": k, "model": None})
    return pairs

def find_modpack_root_from_quest_dir(qd: Path) -> Path:
    curr = Path(qd).resolve()
    while curr != curr.parent:
        if curr.name in ("config", "minecraft"):
            return curr.parent
        curr = curr.parent
    # Never fall back to an arbitrary ancestor: rglob("lang") from $HOME or /
    # scans gigabytes of unrelated trees for hours
    return Path(qd).resolve()

def modpack_name_for_quest_dir(qd: Path) -> str:
    """Instance/modpack name used to tag cache rows — same naming the GUI uses
    (instance dir for Prism/MultiMC layouts, pack dir otherwise)."""
    start = Path(qd).resolve()
    curr = start
    while curr != curr.parent:
        if (curr / "instance.cfg").is_file() or (curr / "minecraft").is_dir():
            return curr.name
        if curr.name in ("minecraft", ".minecraft", "overrides"):
            return curr.parent.name
        if (curr / "config").is_dir() or (curr / "mods").is_dir() or (curr / "kubejs").is_dir():
            return curr.name
        curr = curr.parent
    return start.name


def _collect_json_lang_dirs(quest_dirs: list[Path]) -> tuple[list[Path], dict]:
    json_lang_dirs = set()
    json_modpack_names = {}
    for qd in quest_dirs:
        modpack_root = find_modpack_root_from_quest_dir(qd)
        try:
            for lang_dir in modpack_root.rglob("lang"):
                if "resourcepacks" in lang_dir.parts or any(x in lang_dir.parts for x in EXCLUDED_DIRS):
                    continue
                if lang_dir.is_dir() and (lang_dir / "en_us.json").exists():
                    json_lang_dirs.add(lang_dir.parent)
                    json_modpack_names.setdefault(lang_dir.parent, modpack_name_for_quest_dir(qd))
        except Exception as e:
            LOG.warning(f"Lang scan skipped for {modpack_root}: {e}")
    return sorted(json_lang_dirs, key=str), json_modpack_names


def _collect_snbt_files(quest_dirs: list[Path], lang_code: str) -> tuple[list[Path], dict]:
    lang_re = re.compile(r'^[a-z]{2}_[a-z]{2}\.snbt$', re.IGNORECASE)
    all_files = []
    file_modpack = {}
    for qd in quest_dirs:
        target_dir = find_quests_dir(qd)
        files = [p for p in target_dir.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
        loc_files = [p for p in files if lang_re.match(p.name) and p.parent.name.lower() == "lang"]
        others = [p for p in files if p not in loc_files]
        selected = list(others)
        if loc_files:
            source = next((p for p in loc_files if p.name.lower() == "en_us.snbt"), None)
            if source is None:
                source = next((p for p in loc_files if lang_code.lower() not in p.name.lower()), None)
            if source is not None:
                selected = [source] + others
        name = modpack_name_for_quest_dir(qd)
        for f in selected:
            if f not in file_modpack:
                all_files.append(f)
                file_modpack[f] = name
    return all_files, file_modpack


def _build_mixed_pool(config: ConfigManager, provider: str, model: str | None, api_keys: List[str]) -> list:
    if provider != "Mixed Providers":
        return [{"provider": provider, "api_key": k, "model": model or "", "base_url": get_base_url(provider)} for k in api_keys]
    from core import resolve_mixed_pool
    pairs = parse_key_model_pairs(api_keys)
    all_providers = [p for p in dict.fromkeys(PROVIDER_ALIASES.values()) if p != "Mixed Providers"]
    selected = all_providers
    settings = get_cli_settings()
    if settings is not None:
        raw = settings.value("mixed_providers", [])
        raw = [raw] if isinstance(raw, str) else list(raw or [])
        if raw:
            selected = [p for p in raw if p in all_providers] or all_providers
    saved_keys, saved_models, defaults = {}, {}, {}
    for p in selected:
        saved_keys[p] = list(config.get_api_keys(p) or [])
        saved_models[p] = (settings.value(f"model_{p}", "") if settings is not None else "") or load_cli_setting(f"cli_last_model_{p}", "")
        defaults[p] = PROVIDER_DEFAULTS.get(p, "")
    return resolve_mixed_pool(pairs, saved_keys, saved_models, defaults)


def _build_qa_params(config: ConfigManager, provider: str, model: str | None, lang_name: str, quest_dirs: list[Path]):
    try:
        if not getattr(config, "qa_enabled", False):
            return None
        qa_provider = config.qa_provider or config.utility_provider or provider
        qa_model = config.qa_model or config.utility_model or model or ""
        qa_custom_url = (config.custom_base_url or None) if qa_provider in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)") else None
        j1 = json.loads(config.qa_judge1) if isinstance(config.qa_judge1, str) and config.qa_judge1.strip() else {}
        if not isinstance(j1, dict):
            j1 = {}
        extra_keys = [str(j1.get("api_key")).strip()] if j1.get("api_key") else []
        if j1.get("base_url"):
            qa_custom_url = str(j1["base_url"]).strip() or qa_custom_url
        j1_temp = j1.get("temperature")
        return {
            "keys": [],
            "extra_keys": extra_keys,
            "provider": qa_provider,
            "model": qa_model,
            "custom_base_url": qa_custom_url,
            "qa_temperature_override": float(j1_temp) if isinstance(j1_temp, (int, float)) else None,
            "update_glossary": bool(getattr(config, "qa_update_glossary", True)),
            "batch_size": int(getattr(config, "qa_batch_size", 40) or 40),
            "temperature": float(getattr(config, "qa_temperature", 0.0) or 0.0),
            "dataset": bool(getattr(config, "qa_dataset", True)),
            "verdict_cache": bool(getattr(config, "qa_verdict_cache", True)),
            "judges": json.loads(config.qa_judges or "[]"),
            "jury_threshold": int(getattr(config, "qa_jury_threshold", 2) or 2),
            "provider_pool": {p: list(ks) for p, ks in config.api_keys_pool.items()},
            "modpack_root": find_modpack_root_from_quest_dir(quest_dirs[0]) if quest_dirs else None,
            "lang_name": lang_name,
        }
    except Exception as e:
        LOG.warning(f"QA phase setup skipped: {e}")
        return None


async def _glossary_prescan(config, translator, provider, model, api_keys, mixed_pool, lang_name, quest_dirs, all_files):
    try:
        from core import _find_all_snbt_strings, ensure_modpack_glossary, find_modpack_root
        texts = []
        for f in all_files:
            src = f.with_suffix(".snbt.bak")
            if not (src.exists() and src.stat().st_size > 0):
                src = f
            try:
                content = src.read_text(encoding="utf-8")
            except Exception:
                continue
            for item in _find_all_snbt_strings(content):
                key = item.get("key", "")
                if (key == "title" or key.endswith(".title") or key == "subtitle" or key.endswith(".quest_subtitle")) and len(item.get("value", "")) < 250:
                    texts.append(item["value"])
        utility_provider = getattr(config, "utility_provider", "") or provider
        utility_model = getattr(config, "utility_model", "") or model
        utility_keys, utility_mixed = api_keys, mixed_pool
        if getattr(config, "utility_provider", "") and config.utility_provider != "Mixed Providers":
            pool_keys = config.get_api_keys(config.utility_provider)
            if pool_keys:
                utility_keys = pool_keys
                utility_mixed = [{"provider": config.utility_provider, "api_key": k, "model": utility_model or "",
                                  "base_url": get_base_url(config.utility_provider)} for k in pool_keys]
            else:
                LOG.info(f"Glossary pre-scan: utility provider '{config.utility_provider}' has no keys — using the main provider.")
        if utility_provider in KEYLESS_PROVIDERS or not texts or not quest_dirs:
            return []
        first_root = find_modpack_root(quest_dirs[0])
        if not first_root:
            return []
        LOG.info("Glossary pre-scan: extracting recurring mod terms...")
        glossary = await ensure_modpack_glossary(
            texts, first_root, utility_keys, utility_provider, utility_model, lang_name,
            mixed_pool=utility_mixed, custom_base_url=config.custom_base_url or None, logger=LOG.info)
        if glossary.terms:
            translator.modpack_glossary_terms = glossary.terms
            LOG.info(f"Modpack glossary active: {len(glossary.terms)} terms pinned.")
            return glossary.terms
    except Exception as e:
        LOG.warning(f"Glossary pre-scan skipped: {e}")
    return []


def _make_translator(config, provider, model, api_keys, lang_name, lang_code, mixed_pool):
    return UnifiedTranslator(
        api_keys, provider, model or "", config.custom_context, lang_name, lang_code,
        mixed_pool=mixed_pool, batch_size=config.batch_size, min_batch_size=config.min_batch_size,
        max_concurrent_requests=config.max_concurrent_requests, custom_base_url=config.custom_base_url or None)


async def run_translation(config: ConfigManager, provider: str, model: str | None, api_keys: List[str], lang_name: str, lang_code: str, quest_dirs: list[Path], concurrency: Optional[int] = None, resource_pack_mode: bool = False, t_titles: bool = True, t_subs: bool = True, t_desc: bool = True, dry_run: bool = False) -> int:
    from core import set_temperature, reset_request_timeout, health_reset, health_mark_start, health_summary_lines, qa_run_open, qa_run_close, close_shared_httpx_clients
    if isinstance(quest_dirs, (str, Path)):
        quest_dirs = [Path(quest_dirs)]
    quest_dirs = [Path(q) for q in quest_dirs]
    try:
        set_temperature(config.temperature)
    except Exception:
        pass

    mixed_pool = _build_mixed_pool(config, provider, model, api_keys)
    if provider == "Mixed Providers" and not mixed_pool:
        LOG.error("No API keys available for Mixed Providers. Save keys in the GUI or pass -k.")
        return 1

    all_files, file_modpack = _collect_snbt_files(quest_dirs, lang_code)
    json_lang_dirs, json_modpack_names = _collect_json_lang_dirs(quest_dirs)
    policy = resolve_policy(config.policy)
    qa_params = _build_qa_params(config, provider, model, lang_name, quest_dirs)
    scope = ", ".join(n for n, on in (("titles", t_titles), ("subtitles", t_subs), ("descriptions", t_desc)) if on) or "nothing"

    key_text = (f"{len(api_keys)} · " + " ".join(mask_key(k) for k in api_keys[:6]) + (" …" if len(api_keys) > 6 else "")) if api_keys else "-"
    if provider == "Mixed Providers":
        key_text = f"{len(mixed_pool)} key(s) across " + ", ".join(dict.fromkeys(e.get("provider", "?") for e in mixed_pool))
    ui.kv("Run", [
        ("Provider", provider),
        ("Model", model or ("per key" if provider == "Mixed Providers" else "-")),
        ("Language", f"{lang_name} ({lang_code})"),
        ("Keys", key_text),
        ("Policy", policy),
        ("Parallel files", str(concurrency or 1)),
        ("Scope", scope),
        ("QA", (f"on · {qa_params['provider']} / {qa_params['model'] or '-'}" if qa_params else "off")),
        ("Quest dirs", "\n".join(str(q) for q in quest_dirs)),
        ("SNBT files", str(len(all_files))),
        ("JSON lang dirs", str(len(json_lang_dirs))),
    ] + ([("Resource pack", "yes")] if resource_pack_mode else []))

    if dry_run:
        def rel(p: Path) -> str:
            for q in quest_dirs:
                try:
                    return str(p.relative_to(find_quests_dir(q))) or "."
                except Exception:
                    continue
            return str(p)
        rows = [(i + 1, rel(f), file_modpack.get(f, "")) for i, f in enumerate(all_files)]
        rows += [("json", str(d), json_modpack_names.get(d, d.name)) for d in json_lang_dirs]
        ui.table("Dry run · files that would be processed", ["#", "File", "Modpack"], rows, styles=["dim", "", "dim"])
        return 0

    if not all_files and not json_lang_dirs:
        LOG.warning("No .snbt files found")
        return 0

    try:
        translator = _make_translator(config, provider, model, api_keys, lang_name, lang_code, mixed_pool)
    except ValueError as e:
        LOG.error(str(e))
        return 1

    try:
        c = TranslationCache(target_lang_code=lang_code)
        c.autofix_records(log=LOG.info)
        c.close()
    except Exception as e:
        LOG.warning(f"Cache auto-fix skipped: {e}")

    reset_request_timeout()
    health_reset()
    health_mark_start()
    _owns_qa_scope = qa_run_open()
    qa_logger = LOG.info

    _mp_glossary_terms = []
    if all_files:
        _mp_glossary_terms = await _glossary_prescan(config, translator, provider, model, api_keys, mixed_pool, lang_name, quest_dirs, all_files)

        total_files = len(all_files)
        sem = asyncio.Semaphore(concurrency or 1)
        file_retries: Dict[int, int] = {}
        strings_done: Dict[int, int] = {}
        strings_total: Dict[int, int] = {}
        files_done = 0
        progress = ui.progress()

        def refresh(note=None):
            progress.update("strings", completed=sum(strings_done.values()), total=sum(strings_total.values()), note=note)

        def make_callback(idx):
            def cb(chunk_done, total_chunks, done_strings=0, total_strings=0, *a, **kw):
                strings_done[idx] = done_strings
                strings_total[idx] = total_strings
                note = "QA audit" if kw.get("stage") == "qa" else None
                try:
                    refresh(note)
                except Exception:
                    pass
            return cb

        async def process_single_file(idx, f):
            nonlocal files_done
            async with sem:
                while True:
                    local_manager = SNBTManager("", provider, model or "", config.custom_context, lang_name, lang_code,
                                                concurrency_limit=1, translator=translator,
                                                modpack=file_modpack.get(f), qa_params=qa_params)
                    try:
                        LOG.info(f"Processing: {f.name}")
                        progress.update("files", description=f"Files · {f.name}"[:48])
                        await local_manager.process_file(f, t_titles, t_subs, t_desc, LOG.info, None, policy, progress_callback=make_callback(idx))
                        files_done += 1
                        progress.update("files", completed=files_done)
                        break
                    except AbortException:
                        raise
                    except ValueError:
                        # A deterministic ValueError (bad SNBT, stable invalid
                        # response) never resolves on retry: cap the attempts
                        file_retries[idx] = file_retries.get(idx, 0) + 1
                        if file_retries[idx] >= 2 or not getattr(translator, "mixed_pool", None):
                            raise
                        continue
                    finally:
                        local_manager.close()

        try:
            with progress:
                progress.add("files", "Files", total_files)
                progress.add("strings", "Strings", 0)
                await asyncio.gather(*[process_single_file(i, f) for i, f in enumerate(all_files)])
                progress.finish("files")
                progress.finish("strings")
        except (AbortException, ValueError):
            await close_shared_httpx_clients()
            LOG.error("Критическая ошибка: все ключи невалидны. Перевод прерван.")
            qa_run_close(_owns_qa_scope, logger=qa_logger)
            return 1

        try:
            for line in health_summary_lines():
                LOG.info(line)
        except Exception:
            pass
        ui.ok(f"Успешно обработано {len(all_files)} файлов квестов (.snbt). Для применения квестов введите в игре команду: /ftbquests reload")

    if json_lang_dirs:
        translator = _make_translator(config, provider, model, api_keys, lang_name, lang_code, mixed_pool)
        if _mp_glossary_terms:
            translator.modpack_glossary_terms = _mp_glossary_terms
        cache = TranslationCache(target_lang_code=lang_code)
        cache.autofix_records(log=LOG.info)
        for base_dir in json_lang_dirs:
            LOG.info(f"JSON translation mode detected. Processing lang files in {base_dir}...")
            progress = ui.progress()
            manager = JSONManager(base_dir, lang_code, translator, cache,
                                  modpack=json_modpack_names.get(base_dir, base_dir.name),
                                  policy=policy, resource_pack_mode=resource_pack_mode, qa_params=qa_params,
                                  progress_callback=lambda d, t: progress.update("json", completed=d, total=t))
            try:
                with progress:
                    progress.add("json", f"JSON · {base_dir.name}", 0)
                    # console chatter only (print, no logging): core already logs file-worthy lines
                    translated_count = await manager.process(log_callback=print, check_status=None)
                    progress.finish("json")
                ui.ok(f"JSON translation completed for {base_dir}. Translated {translated_count} strings. In Minecraft, run '/ftbquests reload' or restart the game to apply changes.")
            except Exception as e:
                LOG.error(f"JSON translation failed for {base_dir}: {e}")
                cache.close()
                qa_run_close(_owns_qa_scope, logger=qa_logger)
                return 1

        if resource_pack_mode:
            modpack_root = json_lang_dirs[0]
            while len(modpack_root.parts) > 1:
                if (modpack_root / "mods").is_dir() or (modpack_root / "config").is_dir() or (modpack_root / "kubejs").is_dir():
                    break
                modpack_root = modpack_root.parent
            pack_dir = modpack_root / "resourcepacks" / f"Modpack_Local_{lang_code}"
            if (pack_dir / "pack.mcmeta").exists():
                ui.ok(f"Ресурс-пак успешно создан/обновлен по пути: {pack_dir}")
                if (pack_dir / "pack.png").exists():
                    LOG.info("  └─ Фирменная иконка pack.png успешно добавлена в ресурс-пак!")
                else:
                    LOG.warning("  └─ Предупреждение: Иконка pack.png пропущена (логотип logo.png не найден в ресурсах)")
            else:
                LOG.error(f"ВНИМАНИЕ: Ошибка создания ресурс-пака по пути: {pack_dir}. Проверьте права доступа к папке.")
        cache.close()
    elif resource_pack_mode:
        LOG.warning("ВНИМАНИЕ: Флаг -r / --resource-pack передан, но в модпаке не найдена папка KubeJS (kubejs/assets/). Ресурс-пак не был создан.")

    try:
        qa_run_close(_owns_qa_scope, logger=qa_logger)
    except Exception:
        pass
    await close_shared_httpx_clients()
    return 0


# ---------------------------------------------------------------------------
# Extra commands (GUI parity): key verification, translation-memory tools
# ---------------------------------------------------------------------------

def _run_keys_and_model(config: ConfigManager, provider: str) -> tuple[list[str], str]:
    keys = list(config.get_api_keys(provider) or [])
    if not keys:
        k = load_key_from_env_or_settings(provider)
        keys = [k] if k else []
    settings = get_cli_settings()
    model = config.model or (settings.value(f"model_{provider}", "") if settings is not None else "") or load_cli_setting(f"cli_last_model_{provider}", "") or PROVIDER_DEFAULTS.get(provider, "")
    return keys, str(model or "")


async def cmd_verify_keys(config: ConfigManager) -> int:
    from core import test_key_with_question, fetch_provider_balance, TEST_QUESTIONS
    provider = config.provider
    specs = []  # (key, provider, model, tag)
    if provider == "Mixed Providers":
        for e in _build_mixed_pool(config, provider, None, config.get_api_keys(provider) or []):
            specs.append((e.get("api_key", ""), e.get("provider", ""), e.get("model", ""), "main"))
    else:
        keys, model = _run_keys_and_model(config, provider)
        specs = [(k, provider, model, "main") for k in keys]
    try:
        j1 = json.loads(config.qa_judge1 or "{}")
        if isinstance(j1, dict) and j1.get("api_key"):
            specs.append((str(j1["api_key"]), config.qa_provider or provider, str(j1.get("model") or config.qa_model or ""), "judge 1"))
        for i, j in enumerate(json.loads(config.qa_judges or "[]"), 2):
            if isinstance(j, dict) and j.get("api_key") and j.get("model") and j.get("enabled", True) in (True, "true", 1):
                specs.append((str(j["api_key"]), str(j.get("provider") or provider), str(j["model"]), f"judge {i}"))
    except Exception as e:
        LOG.warning(f"Judge specs skipped: {e}")
    seen = set()
    specs = [s for s in specs if not ((s[0], s[2]) in seen or seen.add((s[0], s[2])))]
    if not specs:
        ui.err(f"No API keys saved for {provider}. Pass -k or set keys in the GUI.")
        return 1
    question = random.choice(TEST_QUESTIONS)
    ui.kv("Key check", [("Provider", provider), ("Keys", str(len(specs))), ("Question", question)])

    async def one(spec):
        key, prov, model, tag = spec
        if prov in KEYLESS_PROVIDERS + ("Custom (OpenAI-compatible)",):
            return spec, "Active", "", ""
        try:
            status, answer = await test_key_with_question(prov, key, model, question)
        except Exception as e:
            status, answer = "Unreachable", repr(e)[:80]
        balance = ""
        if status == "Active":
            try:
                balance = await fetch_provider_balance(prov, key) or ""
            except Exception:
                balance = ""
        return spec, status, (answer or "")[:80].replace("\n", " "), balance

    if ui.rich and ui.color:
        with ui.console.status("[dim]Testing keys...", spinner="dots"):
            results = await asyncio.gather(*[one(s) for s in specs])
    else:
        results = await asyncio.gather(*[one(s) for s in specs])
    style = {"Active": "[ok]", "Invalid": "[err]", "Unreachable": "[err]", "Timeout": "[warn]"}
    rows = []
    active = 0
    for (key, prov, model, tag), status, answer, balance in results:
        active += status == "Active"
        st = f"{style.get(status, '[warn]')}{status}[/]" if ui.rich else status
        rows.append((tag, prov, mask_key(key), model or "-", st, balance or "-", answer))
    ui.table("Results", ["Role", "Provider", "Key", "Model", "Status", "Balance", "Answer"], rows,
             styles=["dim", "", "key", "", "", "", "dim"])
    (ui.ok if active else ui.err)(f"{active}/{len(results)} key(s) active")
    return 0 if active else 1


async def cmd_cache(config: ConfigManager, parsed) -> int:
    from core import get_target_script, script_violation_reason, set_temperature
    action = parsed.cache
    lang_name, lang_code = _lang_from_config(config)
    query = getattr(parsed, "search", None)
    limit = int(getattr(parsed, "limit", None) or 50)
    modpack = getattr(parsed, "modpack", None)
    yes = bool(getattr(parsed, "yes", False))
    cache = TranslationCache(target_lang_code=lang_code)
    try:
        if action == "stats":
            size_mb, count = cache.get_stats()
            packs = cache.get_unique_modpacks()
            ui.kv("Translation memory", [("Database", cache.db_path), ("Language", f"{lang_name} ({lang_code})"),
                                         ("Records", f"{count}"), ("Size", f"{size_mb:.2f} MB"),
                                         ("Modpacks", ", ".join(str(p) for p in packs) if packs else "-")])
            return 0
        if action in ("list", "search"):
            if action == "search" and not query:
                die("--cache search requires --search QUERY")
            rows = cache.get_all_records(search_query=query, limit=limit, modpack_filter=modpack)
            if not rows:
                ui.warn("No records found")
                return 0
            ui.table(f"Translation memory · {lang_code} · {len(rows)} record(s)" + (f" · '{query}'" if query else ""),
                     ["Original", "Translation", "Modpack", "Created"],
                     [(o, t, (m or "-")[:22], (d or "")[:10]) for o, t, m, d in rows], styles=["", "", "dim", "dim"],
                     ratios=[3, 3, None, None])
            return 0
        if action == "clear":
            size_mb, count = cache.get_stats()
            if count == 0:
                ui.info("Cache is already empty")
                return 0
            if not yes and (not is_interactive() or not ui.confirm(f"Delete {count} records ({size_mb:.2f} MB) for {lang_code} and every other language?", False)):
                ui.warn("Cancelled")
                return 1
            cache.clear_all()
            ui.ok("Translation cache cleared")
            return 0
        if action == "autofix":
            fixed = cache.autofix_records(log=LOG.info)
            ui.ok(f"Repaired {fixed} cached translation(s)" if fixed else "Cache is clean - no broken placeholders found")
            return 0
        if action == "heal":
            fixed = cache.autofix_records(log=LOG.info)
            if fixed:
                ui.ok(f"Repaired {fixed} cached translation(s) with broken placeholders")
            script = get_target_script(lang_code)
            violations = cache.find_script_violations(script)
            if not violations:
                ui.ok("Cache is clean - no wrong-language garbage found")
                return 0
            reason_names = {
                'garbage_chars': 'replacement/zero-width characters',
                'cjk_symbols': 'CJK symbols leaked into non-CJK text',
                'mixed_script': 'words mixing two alphabets (e.g. "Лимитite")',
                'not_target_lang': 'text is >=90% not in the target language',
            }
            ui.table(f"Garbage translations · {len(violations)}", ["Reason", "Count"],
                     [(reason_names.get(r, r), sum(1 for v in violations if v[2] == r)) for r in dict.fromkeys(v[2] for v in violations)])
            provider = config.provider
            if provider in ("Mixed Providers", "Google Translate (Free)"):
                ui.err("Heal needs an LLM provider: pass -p/-m (Mixed/Google are not supported here).")
                return 1
            keys, model = _run_keys_and_model(config, provider)
            if not keys and provider not in KEYLESS_PROVIDERS:
                ui.err(f"No API keys for {provider}; pass -k.")
                return 1
            if not yes and (not is_interactive() or not ui.confirm(f"Re-translate {len(violations)} record(s) with {provider} / {model or '-'}?", True)):
                ui.warn("Cancelled")
                return 1
            set_temperature(config.temperature)
            translator = UnifiedTranslator(keys, provider, model, config.custom_context, lang_name, lang_code,
                                           batch_size=config.batch_size, custom_base_url=config.custom_base_url or None)
            healed = failed = 0
            bs = max(1, int(config.batch_size or 50))
            progress = ui.progress()
            with progress:
                progress.add("heal", "Healing", len(violations))
                for i in range(0, len(violations), bs):
                    chunk = violations[i:i + bs]
                    try:
                        results = await translator.translate([v[0] for v in chunk], LOG.info, None, config.custom_context)
                    except Exception as e:
                        LOG.warning(f"Heal batch failed: {e}")
                        results = None
                    if results is None or len(results) != len(chunk):
                        failed += len(chunk)
                    else:
                        updates = {}
                        for (orig, _bad, reason, _mp), new_trans in zip(chunk, results):
                            if not isinstance(new_trans, str) or not new_trans or (new_trans == orig and reason != 'not_target_lang') or script_violation_reason(new_trans, script):
                                failed += 1
                                continue
                            updates[orig] = new_trans
                            healed += 1
                        if updates:
                            cache.update_records(updates)
                    progress.update("heal", completed=min(i + bs, len(violations)))
            (ui.ok if healed else ui.warn)(f"Healed {healed}, kept old value for {failed}")
            return 0
        die(f"Unknown cache action: {action}")
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _apply_titles_scope(config: ConfigManager, parsed) -> tuple[bool, bool, bool]:
    settings = get_cli_settings()
    def saved(k):
        return (settings.value(k, "true") == "true") if settings is not None else True
    t_titles = saved("cb_titles") and not getattr(parsed, "no_titles", False)
    t_subs = saved("cb_subs") and not getattr(parsed, "no_subs", False)
    t_desc = saved("cb_desc") and not getattr(parsed, "no_desc", False)
    return t_titles, t_subs, t_desc


async def main_async() -> int:
    config = ConfigManager()
    config.prune_invalid_paths()
    parsed = config.parse_cli_args()
    ui.configure(color=not getattr(parsed, "no_color", False))
    setup_logging(getattr(parsed, "debug", False))

    if getattr(parsed, "version", False):
        print(f"snbt-tr {APP_VERSION}")
        return 0

    cache_action = getattr(parsed, "cache", None)
    cli_action = any([getattr(parsed, "list_models", False), getattr(parsed, "clear_cache", False),
                      getattr(parsed, "fastdir", False), getattr(parsed, "verify_keys", False), cache_action,
                      getattr(parsed, "dry_run", False)])
    wants_cli = cli_action or any(getattr(parsed, a, None) for a in ("provider", "model", "dir", "lang", "key", "mix"))

    if getattr(parsed, "gui", False) or (not is_interactive() and "PYTEST_CURRENT_TEST" not in os.environ and not wants_cli):
        import gui
        gui.main()
        return 0

    if is_interactive() and not getattr(parsed, "version", False):
        ui.banner(APP_VERSION, "FTB Quests / KubeJS localizer · logs: ~/.snbt_localizer/logs/app.log")

    if getattr(parsed, "list_models", False):
        return await cmd_list_models(config, config.provider)
    if getattr(parsed, "verify_keys", False):
        return await cmd_verify_keys(config)
    if cache_action:
        return await cmd_cache(config, parsed)
    if getattr(parsed, "clear_cache", False):
        parsed.cache = "clear"
        rc = await cmd_cache(config, parsed)
        sys.exit(rc)

    t_titles, t_subs, t_desc = _apply_titles_scope(config, parsed)
    dry_run = bool(getattr(parsed, "dry_run", False))
    if dry_run:
        # a preview must never change the saved GUI/CLI configuration
        global save_cli_setting
        config.save_to_settings = lambda *a, **k: None
        config.add_custom_path = lambda *a, **k: None
        save_cli_setting = lambda *a, **k: None
    resource_pack = bool(getattr(parsed, "resource_pack", False))

    if getattr(parsed, "fastdir", False):
        result = cmd_fastdir(config)
        if not result:
            return 1
        quest_dir, quest_dirs = result
        provider = config.provider
        if provider == "Mixed Providers":
            api_keys = [k for keys in config.api_keys_pool.values() for k in keys]
        else:
            api_keys = config.get_api_keys(provider)
        if not api_keys and provider not in KEYLESS_PROVIDERS:
            k = load_key_from_env_or_settings(provider)
            api_keys = [k] if k else []
            if not api_keys:
                die(f"No API key saved for {provider}. Run the wizard once or pass -k.")
        model = config.model or load_cli_setting(f"cli_last_model_{provider}", "") or None
        lang_name, lang_code = _lang_from_config(config)
        concurrency = max(config.concurrency, len(api_keys), 5) if provider == "Mixed Providers" else max(1, min(config.concurrency, 10))
        config.quest_dir = quest_dir
        config.save_to_settings()
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency,
                                     resource_pack, t_titles=t_titles, t_subs=t_subs, t_desc=t_desc, dry_run=dry_run)

    if getattr(parsed, "mix", False):
        result = await run_mix_setup_wizard(config, parsed)
        if not result:
            return 1
        quest_dir, lang_name, lang_code = result
        provider = "Mixed Providers"
        api_keys = [k for keys in config.api_keys_pool.values() for k in keys]
        model = None
    else:
        quest_dir, provider, api_key, model, lang_name, lang_code = await run_setup_wizard(config, parsed)
        if provider == "Mixed Providers":
            api_keys = [k for keys in config.api_keys_pool.values() for k in keys]
        else:
            api_keys = [api_key] if api_key else []

    quest_dirs = find_all_quest_dirs(quest_dir) or [quest_dir]
    if provider == "Mixed Providers":
        concurrency = max(config.concurrency, len(api_keys), 5)
    else:
        concurrency = max(1, min(config.concurrency, 10))
    return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency,
                                 resource_pack, t_titles=t_titles, t_subs=t_subs, t_desc=t_desc, dry_run=dry_run)


def main() -> None:
    try:
        if os.name == "nt":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mineai.snbt-tr.localizer.1.0")
            except Exception:
                pass
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        LOG.error("[SIGINT] Получен сигнал прерывания. Безопасная остановка (Graceful Shutdown)...")
        sys.exit(130)
    except Exception:
        LOG.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
