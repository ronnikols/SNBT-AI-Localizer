import os
import sys
import asyncio
import ctypes
import httpx
import logging
from pathlib import Path
from typing import List, Optional, Dict
from logging.handlers import RotatingFileHandler
from core import SNBTManager, EXCLUDED_DIRS, parse_target_lang, TranslationCache, UnifiedTranslator, AbortException, get_base_url, detect_provider, is_valid_custom_instance, PROVIDER_DEFAULTS, detect_kubejs_mode, JSONManager
from config import ConfigManager, PROVIDER_ALIASES, PROVIDER_ENDPOINTS, LANG_ALIASES, ENV_KEY_MAP, SETTINGS_KEY_MAP
try:
    from PyQt6.QtCore import QSettings
except ImportError:
    QSettings = None

SERVICE_MODEL_KEYWORDS = {"orpheus", "tts", "whisper", "embed", "moderation", "safety", "guard", "reward"}

def find_all_quest_dirs(instance_path: Path) -> list[Path]:
    quest_dirs = []
    MAX_DEPTH = 3

    standard_paths = [
        instance_path / "config" / "ftbquests" / "quests",
        instance_path / "minecraft" / "config" / "ftbquests" / "quests",
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
                    if entry.name.startswith('.'):
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

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
    console_handler.setFormatter(console_format)
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
            (home / "curseforge/minecraft/Instances", "Instances", "CurseForge"),
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
    return sys.stdin.isatty()

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

async def run_setup_wizard(config: ConfigManager, parsed=None) -> tuple[Path, str, str | None, str | None, str, str]:
    logging.getLogger("snbt_localizer.cli").info("=== SNBT AI Localizer - Setup Wizard ===")

    if parsed and hasattr(parsed, 'dir') and parsed.dir:
        quest_dir = normalize_path(parsed.dir)
        config.add_custom_path(str(quest_dir))
        logging.getLogger("snbt_localizer.cli").info(f"Using directory from command line: {quest_dir}")
    else:
        logging.getLogger("snbt_localizer.cli").info("Step 1: Select modpack instance")
        launcher_paths = get_launcher_paths()
        instances = []
        for base, launcher_name in launcher_paths:
            if not base.exists():
                continue
            try:
                for sub in base.iterdir():
                    if sub.is_dir():
                        quests_path = sub / "config" / "ftbquests" / "quests"
                        if not quests_path.exists():
                            quests_path = sub / "minecraft" / "config" / "ftbquests" / "quests"
                        if quests_path.exists() and quests_path.is_dir():
                            instances.append((sub.name, str(sub), launcher_name))
            except Exception:
                pass

        for custom_path in config.custom_instances_paths:
            p = Path(custom_path)
            if is_valid_custom_instance(p) and not any(str(p) == path_str for _, path_str, _ in instances):
                instances.append((p.name, str(p), "Custom"))

        if not instances:
            logging.getLogger("snbt_localizer.cli").info("No modpack instances with FTB Quests found.")
            custom_path = input("Enter path to modpack manually: ").strip()
            if not custom_path:
                die("No path provided")
            quest_dir = normalize_path(custom_path)
            config.add_custom_path(str(quest_dir))
        else:
            instances = sorted(instances, key=lambda x: x[1])
        last_instance = load_cli_setting("cli_last_instance", "")
        default_idx = 0
        if last_instance:
            for i, (_, path, _) in enumerate(instances):
                if path == last_instance:
                    instances.insert(0, instances.pop(i))
                    default_idx = 0
                    break

        logging.getLogger("snbt_localizer.cli").info("Found instances:")
        for i, (name, path, launcher) in enumerate(instances):
            marker = " (last used)" if i == 0 and last_instance else ""
            logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {name} [{launcher}]{marker}")
        logging.getLogger("snbt_localizer.cli").info(f"  {len(instances) + 1}) Enter path manually...")

        while True:
            choice = input(f"Choice [{default_idx + 1}]: ").strip()
            choice = choice or str(default_idx + 1)
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(instances):
                    quest_dir = Path(instances[idx][1])
                    save_cli_setting("cli_last_instance", str(quest_dir))
                    break
                elif idx == len(instances):
                    custom_path = input("Enter path to modpack: ").strip()
                    if not custom_path:
                        continue
                    quest_dir = normalize_path(custom_path)
                    config.add_custom_path(str(quest_dir))
                    save_cli_setting("cli_last_instance", str(quest_dir))
                    break
            except ValueError:
                pass
            logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

    logging.getLogger("snbt_localizer.cli").info(f"\nSelected: {quest_dir}")

    if parsed and hasattr(parsed, 'provider') and parsed.provider:
        provider_alias = parsed.provider.lower()
        if provider_alias in PROVIDER_ALIASES:
            provider = PROVIDER_ALIASES[provider_alias]
        else:
            provider = parsed.provider
        if provider not in dict.fromkeys(PROVIDER_ALIASES.values()):
            logging.getLogger("snbt_localizer.cli").error(f"Unknown provider: {parsed.provider}")
            sys.exit(1)
        logging.getLogger("snbt_localizer.cli").info(f"Using provider from command line: {provider}")
        save_cli_setting("cli_last_provider", provider)
    else:
        logging.getLogger("snbt_localizer.cli").info("Step 2: Select translation provider")
        providers = list(dict.fromkeys(PROVIDER_ALIASES.values()))
        last_provider = load_cli_setting("cli_last_provider", "")
        default_idx = 0
        if last_provider and last_provider in providers:
            default_idx = providers.index(last_provider)

        logging.getLogger("snbt_localizer.cli").info("Available providers:")
        for i, p in enumerate(providers):
            marker = " (last used)" if i == default_idx else ""
            logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {p}{marker}")

        while True:
            choice = input(f"Choice [{default_idx + 1}]: ").strip()
            choice = choice or str(default_idx + 1)
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(providers):
                    provider = providers[idx]
                    save_cli_setting("cli_last_provider", provider)
                    break
            except ValueError:
                pass
            logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

        logging.getLogger("snbt_localizer.cli").info(f"\nSelected: {provider}")

    if provider == "Mixed Providers":
        save_cli_setting("cli_last_provider", provider)
        result = await run_mix_setup_wizard(config)
        if result is None:
            die("Mixed mode setup cancelled")
        quest_dir, lang_name, lang_code = result
        config.provider = provider
        config.target_lang = lang_code
        config.quest_dir = quest_dir
        config.save_to_settings()
        return quest_dir, provider, None, None, lang_name, lang_code

    api_key = None
    if provider not in ("Google Translate (Free)", "Ollama (Local / Free)"):
        if parsed and hasattr(parsed, 'key') and parsed.key:
            api_key = parsed.key
            settings_key = SETTINGS_KEY_MAP.get(provider)
            if settings_key and api_key:
                save_cli_setting(settings_key, api_key)
            logging.getLogger("snbt_localizer.cli").info("Using API key from command line")
        else:
            logging.getLogger("snbt_localizer.cli").info("\nStep 3: API Key")
            env_key = load_key_from_env_or_settings(provider)
            if env_key:
                masked = "*" * (len(env_key) - 4) + env_key[-4:] if len(env_key) > 4 else "****"
                logging.getLogger("snbt_localizer.cli").info(f"API key detected in system. Press Enter to use it or enter a new one:")
                user_key = input(f"Use saved key [{masked}]: ").strip()
                if user_key:
                    api_key = user_key
                else:
                    api_key = env_key
                settings_key = SETTINGS_KEY_MAP.get(provider)
                if settings_key and api_key:
                    save_cli_setting(settings_key, api_key)
            else:
                while True:
                    api_key = input("API Key: ").strip()
                    if api_key:
                        settings_key = SETTINGS_KEY_MAP.get(provider)
                        if settings_key:
                            save_cli_setting(settings_key, api_key)
                        break
                    logging.getLogger("snbt_localizer.cli").warning("API Key cannot be empty")

    model = None
    if provider != "Google Translate (Free)":
        if parsed and hasattr(parsed, 'model') and parsed.model:
            model = parsed.model
            save_cli_setting(f"cli_last_model_{provider}", model)
            logging.getLogger("snbt_localizer.cli").info(f"Using model from command line: {model}")
        else:
            logging.getLogger("snbt_localizer.cli").info("\nStep 4: Model and Language")
        models = await fetch_models(provider, api_key)
        if "gemini" in provider.lower() or "google" in provider.lower():
            for i in range(len(models)):
                if "gemini-3.1-flash-lite" in models[i] and not models[i].endswith(" [RECOMMENDED]"):
                    models[i] = models[i] + " [RECOMMENDED]"
        last_model = load_cli_setting(f"cli_last_model_{provider}", "")
        default_model = PROVIDER_DEFAULTS.get(provider)
        
        def sort_key(m):
            base = m.replace(" [RECOMMENDED]", "")
            if base == last_model:
                return (0, m)
            if "gemini-3.1-flash-lite" in base:
                return (1, m)
            if "nvidia" in provider.lower() or "nim" in provider.lower():
                if "nemotron" in base.lower():
                    return (2, m)
            return (3, m)
        
        models.sort(key=sort_key)
        all_models = list(models)
        
        while True:
            logging.getLogger("snbt_localizer.cli").info("Available models:")
            for i, m in enumerate(models):
                base = m.replace(" [RECOMMENDED]", "")
                marker = " (last used)" if i == 0 and base == last_model else ""
                logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {m}{marker}")
            
            choice = input(f"Choice [1]: ").strip()
            choice = choice or "1"
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    model = models[idx]
                    model = model.replace(" [RECOMMENDED]", "")
                    save_cli_setting(f"cli_last_model_{provider}", model)
                    break
            except ValueError:
                if choice.lower() == "all":
                    models = list(all_models)
                    continue
                filtered = [m for m in all_models if choice.lower() in m.lower()]
                if filtered:
                    models = filtered
                    continue
                logging.getLogger("snbt_localizer.cli").warning("Invalid choice")
    else:
        model = None

    if parsed and hasattr(parsed, 'lang') and parsed.lang:
        lang_input = parsed.lang.lower()
        if lang_input in LANG_ALIASES:
            lang_name, lang_code = LANG_ALIASES[lang_input]
        else:
            for alias, (name, code) in LANG_ALIASES.items():
                if lang_input == code or lang_input == name.lower():
                    lang_name, lang_code = name, code
                    break
            else:
                logging.getLogger("snbt_localizer.cli").error(f"Unknown language: {parsed.lang}")
                sys.exit(1)
        save_cli_setting("cli_last_lang", lang_code)
        logging.getLogger("snbt_localizer.cli").info(f"Using language from command line: {lang_name} ({lang_code})")
    else:
        seen_codes = set()
        unique_langs = []
        for alias, (name, code) in LANG_ALIASES.items():
            if code not in seen_codes:
                seen_codes.add(code)
                unique_langs.append((alias, (name, code)))

        langs = unique_langs
        last_lang = load_cli_setting("cli_last_lang", "")
        default_idx = 0
        if last_lang:
            for i, (_, (name, code)) in enumerate(langs):
                if code == last_lang or name == last_lang:
                    default_idx = i
                    break

        logging.getLogger("snbt_localizer.cli").info("Available languages:")
        for i, (alias, (name, code)) in enumerate(langs):
            marker = " (last used)" if i == default_idx else ""
            logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {name} ({code}){marker}")

        while True:
            choice = input(f"Choice [{default_idx + 1}]: ").strip()
            choice = choice or str(default_idx + 1)
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(langs):
                    lang_name, lang_code = langs[idx][1]
                    save_cli_setting("cli_last_lang", lang_code)
                    break
            except ValueError:
                pass
            logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

        logging.getLogger("snbt_localizer.cli").info(f"\nSelected: {lang_name} ({lang_code})")
        logging.getLogger("snbt_localizer.cli").info("Starting translation...")

    config.provider = provider
    config.model = model
    config.target_lang = lang_code
    config.quest_dir = quest_dir
    config.custom_context = ""
    config.policy = "Complement (Дополнить)"
    if api_key:
        config.set_api_keys(provider, [api_key])
    config.save_to_settings()
    return quest_dir, provider, api_key, model, lang_name, lang_code

async def run_mix_setup_wizard(config: ConfigManager, parsed=None) -> tuple[Path, str, str] | None:
    logging.getLogger("snbt_localizer.cli").info("=== SNBT AI Localizer - Mixed Mode Setup ===")

    if parsed and hasattr(parsed, 'dir') and parsed.dir:
        quest_dir = normalize_path(parsed.dir)
        config.add_custom_path(str(quest_dir))
        logging.getLogger("snbt_localizer.cli").info(f"Using directory from command line: {quest_dir}")
    else:
        launcher_paths = get_launcher_paths()
        instances = []
        for base, launcher_name in launcher_paths:
            if not base.exists():
                continue
            try:
                for sub in base.iterdir():
                    if sub.is_dir():
                        quests_path = sub / "config" / "ftbquests" / "quests"
                        if not quests_path.exists():
                            quests_path = sub / "minecraft" / "config" / "ftbquests" / "quests"
                        if quests_path.exists() and quests_path.is_dir():
                            instances.append((sub.name, str(sub), launcher_name))
            except Exception:
                pass

        if not instances:
            for base, launcher_name in launcher_paths:
                if not base.exists():
                    continue
                try:
                    for sub in base.iterdir():
                        if sub.is_dir():
                            quest_dirs = find_all_quest_dirs(sub)
                            if quest_dirs:
                                instances.append((sub.name, str(sub), launcher_name, quest_dirs))
                except Exception:
                    pass

            if not instances:
                logging.getLogger("snbt_localizer.cli").info("No modpack instances with FTB Quests found.")
                custom_path = input("Enter path to modpack manually: ").strip()
                if not custom_path:
                    return None
                quest_dir = normalize_path(custom_path)
                config.add_custom_path(str(quest_dir))
            else:
                instances = sorted(instances, key=lambda x: x[1])
            last_instance = load_cli_setting("cli_last_instance", "")
            default_idx = 0
            if last_instance:
                for i, (_, path, _, _) in enumerate(instances):
                    if path == last_instance:
                        instances.insert(0, instances.pop(i))
                        default_idx = 0
                        break

            logging.getLogger("snbt_localizer.cli").info("Found instances:")
            for i, (name, path, launcher, _) in enumerate(instances):
                marker = " (last used)" if i == 0 and last_instance else ""
                folder_note = " [Multiple Folders]" if len(instances[i][3]) > 1 else ""
                logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {name} [{launcher}]{marker}{folder_note}")
            logging.getLogger("snbt_localizer.cli").info(f"  {len(instances) + 1}) Enter path manually...")

            while True:
                choice = input(f"Choice [{default_idx + 1}]: ").strip()
                choice = choice or str(default_idx + 1)
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(instances):
                        quest_dir = Path(instances[idx][1])
                        save_cli_setting("cli_last_instance", str(quest_dir))
                        break
                    elif idx == len(instances):
                        custom_path = input("Enter path to modpack: ").strip()
                        if not custom_path:
                            continue
                        quest_dir = normalize_path(custom_path)
                        config.add_custom_path(str(quest_dir))
                        save_cli_setting("cli_last_instance", str(quest_dir))
                        break
                except ValueError:
                    pass
                logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

    logging.getLogger("snbt_localizer.cli").info(f"\nSelected: {quest_dir}")

    if parsed and hasattr(parsed, 'mix') and parsed.mix:
        selected_providers = [p for p in dict.fromkeys(PROVIDER_ALIASES.values()) if p != "Mixed Providers"]
        logging.getLogger("snbt_localizer.cli").info("Using all available providers for Mixed mode")
    else:
        providers = [p for p in dict.fromkeys(PROVIDER_ALIASES.values()) if p != "Mixed Providers"]
        logging.getLogger("snbt_localizer.cli").info("Select providers for Mixed mode (enter numbers separated by space, or press Enter to use saved keys):")
        for i, p in enumerate(providers, 1):
            logging.getLogger("snbt_localizer.cli").info(f"  {i}) {p}")

        choice = input("Choice: ").strip()
        if choice:
            selected_indices = []
            for part in choice.split():
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(providers):
                        selected_indices.append(idx)
                except:
                    pass
            if not selected_indices:
                logging.getLogger("snbt_localizer.cli").error("No valid providers selected.")
                return None
            selected_providers = [providers[i] for i in selected_indices]
            settings = QSettings("MineAI", "SNBT-Localizer")
            settings.setValue("mixed_providers", selected_providers)
            settings.sync()
        else:
            selected_providers = providers

    for prov in selected_providers:
        if parsed and hasattr(parsed, 'key') and parsed.key:
            api_key = parsed.key
            settings_key = SETTINGS_KEY_MAP.get(prov, f"{prov}_api_key")
            save_cli_setting(settings_key, api_key)
            config.set_api_keys(prov, [api_key])
            logging.getLogger("snbt_localizer.cli").info(f"Using API key from command line for {prov}")
        else:
            api_key = load_key_from_env_or_settings(prov)
            if not api_key:
                api_key = input(f"API Key for {prov}: ").strip()
                if api_key:
                    settings_key = SETTINGS_KEY_MAP.get(prov, f"{prov}_api_key")
                    save_cli_setting(settings_key, api_key)
                    config.set_api_keys(prov, [api_key])
                else:
                    logging.getLogger("snbt_localizer.cli").warning(f"Skipping {prov} - no API key provided.")
                    continue

        if parsed and hasattr(parsed, 'model') and parsed.model:
            model = parsed.model
            save_cli_setting(f"cli_last_model_{prov}", model)
            logging.getLogger("snbt_localizer.cli").info(f"Using model from command line for {prov}: {model}")
        else:
            models = await fetch_models(prov, api_key)
            if models:
                logging.getLogger("snbt_localizer.cli").info(f"\nSelect model for {prov}:")
                for i, m in enumerate(models, 1):
                    logging.getLogger("snbt_localizer.cli").info(f"  {i}) {m}")
                model_choice = input("Choice [1]: ").strip() or "1"
                try:
                    model_idx = int(model_choice) - 1
                    model = models[model_idx] if 0 <= model_idx < len(models) else PROVIDER_DEFAULTS.get(prov, "")
                except:
                    model = PROVIDER_DEFAULTS.get(prov, "")
            else:
                model = PROVIDER_DEFAULTS.get(prov, "")
            save_cli_setting(f"cli_last_model_{prov}", model)

    if parsed and hasattr(parsed, 'lang') and parsed.lang:
        lang_input = parsed.lang.lower()
        if lang_input in LANG_ALIASES:
            lang_name, lang_code = LANG_ALIASES[lang_input]
        else:
            for alias, (name, code) in LANG_ALIASES.items():
                if lang_input == code or lang_input == name.lower():
                    lang_name, lang_code = name, code
                    break
            else:
                logging.getLogger("snbt_localizer.cli").error(f"Unknown language: {parsed.lang}")
                sys.exit(1)
        save_cli_setting("cli_last_lang", lang_code)
        logging.getLogger("snbt_localizer.cli").info(f"Using language from command line: {lang_name} ({lang_code})")
    else:
        seen_codes = set()
        unique_langs = []
        for alias, (name, code) in LANG_ALIASES.items():
            if code not in seen_codes:
                seen_codes.add(code)
                unique_langs.append((alias, (name, code)))

        langs = unique_langs
        last_lang = load_cli_setting("cli_last_lang", "")
        default_idx = 0
        if last_lang:
            for i, (_, (name, code)) in enumerate(langs):
                if code == last_lang or name == last_lang:
                    default_idx = i
                    break

        logging.getLogger("snbt_localizer.cli").info("Available languages:")
        for i, (alias, (name, code)) in enumerate(langs):
            marker = " (last used)" if i == default_idx else ""
            logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {name} ({code}){marker}")

        while True:
            choice = input(f"Choice [{default_idx + 1}]: ").strip()
            choice = choice or str(default_idx + 1)
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(langs):
                    lang_name, lang_code = langs[idx][1]
                    save_cli_setting("cli_last_lang", lang_code)
                    break
            except ValueError:
                pass
            logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

        logging.getLogger("snbt_localizer.cli").info(f"\nSelected: {lang_name} ({lang_code})")
        logging.getLogger("snbt_localizer.cli").info("Starting translation...")
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
                    models = [m["id"] for m in data.get("models", [])]
                else:
                    models = [m["id"] for m in data.get("data", [])]
                return [m for m in models if not any(kw in m.lower() for kw in SERVICE_MODEL_KEYWORDS)]
    except Exception:
        pass
    return []

def select_provider_interactive() -> str:
    providers = list(dict.fromkeys(PROVIDER_ALIASES.values()))
    logging.getLogger("snbt_localizer.cli").info("Select provider:")
    for i, p in enumerate(providers, 1):
        logging.getLogger("snbt_localizer.cli").info(f"  {i}) {p}")
    while True:
        choice = input("Choice [1]: ").strip()
        choice = choice or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                return providers[idx]
        except ValueError:
            pass
        logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

def select_model_interactive(models: list[str], provider: str) -> str:
    if not models:
        default = PROVIDER_DEFAULTS.get(provider)
        if default:
            return default
        die("No models available and no default for provider")
    logging.getLogger("snbt_localizer.cli").info("Select model:")
    for i, m in enumerate(models[:20], 1):
        logging.getLogger("snbt_localizer.cli").info(f"  {i}) {m}")
    if len(models) > 20:
        logging.getLogger("snbt_localizer.cli").info(f"  ... and {len(models) - 20} more")
    default_model = PROVIDER_DEFAULTS.get(provider)
    default_idx = 1
    if default_model and default_model in models:
        default_idx = models.index(default_model) + 1
    while True:
        choice = input(f"Choice [{default_idx}]: ").strip()
        choice = choice or str(default_idx)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
        except ValueError:
            pass
        logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

def select_language_interactive() -> tuple[str, str]:
    langs = list(LANG_ALIASES.items())
    logging.getLogger("snbt_localizer.cli").info("Select language:")
    for i, (alias, (name, code)) in enumerate(langs, 1):
        logging.getLogger("snbt_localizer.cli").info(f"  {i}) {name} ({code})")
    while True:
        choice = input("Choice [1]: ").strip()
        choice = choice or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(langs):
                return langs[idx][1]
        except ValueError:
            pass
        logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

async def cmd_list_models(provider: str) -> int:
    api_key = load_key_from_env_or_settings(provider)
    models = await fetch_models(provider, api_key)
    if not models:
        logging.getLogger("snbt_localizer.cli").warning(f"No models found for {provider}")
        return 1
    logging.getLogger("snbt_localizer.cli").info(f"Models for {provider}:")
    for m in models:
        logging.getLogger("snbt_localizer.cli").info(f"  {m}")
    return 0

def cmd_fastdir(config: ConfigManager = None) -> tuple[Path, list[Path]] | None:
    launcher_paths = get_launcher_paths()
    instances = []
    root_to_quest_dirs = {}

    for base, launcher_name in launcher_paths:
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
        logging.getLogger("snbt_localizer.cli").warning("No modpack instances with FTB Quests found.")
        return None

    last_instance = load_cli_setting("cli_last_instance", "")
    default_idx = 0
    if last_instance:
        for i, (_, path, _, _) in enumerate(instances):
            if path == last_instance:
                instances.insert(0, instances.pop(i))
                default_idx = 0
                break

    logging.getLogger("snbt_localizer.cli").info("Found instances:")
    for i, (name, path, launcher, quest_dirs) in enumerate(instances):
        marker = " (last used)" if i == 0 and last_instance else ""
        folder_note = " [Multiple Folders]" if len(quest_dirs) > 1 else ""
        logging.getLogger("snbt_localizer.cli").info(f"  {i + 1}) {name} [{launcher}]{marker}{folder_note}")

    while True:
        choice = input(f"Choice [{default_idx + 1}]: ").strip()
        choice = choice or str(default_idx + 1)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(instances):
                name, path_str, launcher, quest_dirs = instances[idx]
                quest_dir = Path(path_str)
                save_cli_setting("cli_last_instance", str(quest_dir))
                return (quest_dir, quest_dirs)
        except ValueError:
            pass
        logging.getLogger("snbt_localizer.cli").warning("Invalid choice")

def resolve_policy(policy: str) -> str:
    mapping = {
        "complement": "Complement (Дополнить)",
        "overwrite": "Overwrite (Перезаписать)",
        "skip": "Skip (Пропустить)",
    }
    return mapping.get(policy, "Complement (Дополнить)")

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
    curr = qd.resolve()
    while curr != curr.parent:
        if curr.name in ("config", "minecraft"):
            return curr.parent
        curr = curr.parent
    return qd.parent.parent.parent.parent

async def run_translation(config: ConfigManager, provider: str, model: str | None, api_keys: List[str], lang_name: str, lang_code: str, quest_dirs: list[Path], concurrency: Optional[int] = None, resource_pack_mode: bool = False) -> int:
    logging.getLogger("snbt_localizer.cli").info(f"Provider: {provider}")
    if model:
        logging.getLogger("snbt_localizer.cli").info(f"Model: {model}")
    logging.getLogger("snbt_localizer.cli").info(f"Language: {lang_name} ({lang_code})")
    if api_keys:
        masked_keys = []
        for k in api_keys:
            if len(k) > 4:
                masked_keys.append("*" * (len(k) - 4) + k[-4:])
            else:
                masked_keys.append("****")
        logging.getLogger("snbt_localizer.cli").info(f"API Keys: {', '.join(masked_keys)}")
    else:
        logging.getLogger("snbt_localizer.cli").info("API Keys: Not Set")

    limit = concurrency if concurrency is not None else config.concurrency
    mixed_pool = []
    if provider == "Mixed Providers":
        pairs = parse_key_model_pairs(api_keys)
        all_providers = ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI"]
        if QSettings is not None:
            settings = QSettings("MineAI", "SNBT-Localizer")
            selected_providers = set(settings.value("mixed_providers", []))
        else:
            selected_providers = set()
        if not selected_providers:
            selected_providers = set(all_providers)
        saved_keys_by_provider = {}
        saved_models_by_provider = {}
        default_models_by_provider = {}
        for p in all_providers:
            if p in selected_providers:
                saved_keys_by_provider[p] = config.get_api_keys(p)
                if QSettings is not None:
                    settings = QSettings("MineAI", "SNBT-Localizer")
                    saved_models_by_provider[p] = settings.value(f"model_{p}", "")
                else:
                    saved_models_by_provider[p] = ""
                default_models_by_provider[p] = PROVIDER_DEFAULTS.get(p, "")

        from core import resolve_mixed_pool
        mixed_pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)

        if not mixed_pool:
            logging.getLogger("snbt_localizer.cli").error("No API keys available for Mixed Providers. Configure keys for other providers first.")
            return 1
    else:
        if api_keys:
            for key in api_keys:
                base = get_base_url(provider)
                mixed_pool.append({"provider": provider, "api_key": key, "model": model or "", "base_url": base})

    if provider == "Mixed Providers" and not mixed_pool:
        logging.getLogger("snbt_localizer.cli").error("No valid providers in mixed pool. Configure API keys first.")
        return 1
    translator = UnifiedTranslator(api_keys, provider, model or "", config.custom_context, lang_name, lang_code, mixed_pool=mixed_pool)

    if isinstance(quest_dirs, Path):
        quest_dirs = [quest_dirs]

    json_lang_dirs = set()
    for qd in quest_dirs:
        modpack_root = find_modpack_root_from_quest_dir(qd)
        for lang_dir in modpack_root.rglob("lang"):
            if "resourcepacks" in lang_dir.parts:
                continue
            if lang_dir.is_dir() and (lang_dir / "en_us.json").exists():
                json_lang_dirs.add(lang_dir.parent)
    json_lang_dirs = sorted(json_lang_dirs, key=lambda x: str(x))

    all_files = []
    for qd in quest_dirs:
        try:
            target_dir = SNBTManager("", "", "").find_quests_dir(qd)
        except Exception:
            target_dir = qd
        files = [p for p in target_dir.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
        all_files.extend(files)
    if not files:
        logging.getLogger("snbt_localizer.cli").warning("No .snbt files found")
        return 0
    total_files = len(files)
    logging.getLogger("snbt_localizer.cli").info(
        f"Starting localization. Active Provider: {provider}, Active Model: {model or 'N/A'}, Keys in Pool: {len(api_keys)}"
    )
    logging.getLogger("snbt_localizer.cli").info(f"Found {total_files} files")
    policy = resolve_policy(config.policy)
    file_progress = {idx: 0.0 for idx in range(total_files)}

    def log_with_bar(msg):
        nonlocal first_file
        sys.stdout.write('\r\033[K')
        if not first_file:
            sys.stdout.write('\033[F\033[K')
        else:
            first_file = False
        logging.getLogger("snbt_localizer.cli").info(msg)
        overall = sum(file_progress.values())
        render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")

    def make_file_progress_callback(idx):
        def callback(chunk_idx, total_chunks, *args, **kwargs):
            if total_chunks > 0:
                file_progress[idx] = chunk_idx / total_chunks
            else:
                file_progress[idx] = 0.0
            overall = sum(file_progress.values())
            render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")
        return callback

    semaphore = asyncio.Semaphore(concurrency) if concurrency else asyncio.Semaphore(1)

    async def process_single_file(idx, f):
        async with semaphore:
            while True:
                try:
                    local_manager = SNBTManager(
                        "",
                        provider,
                        model or "",
                        config.custom_context,
                        lang_name,
                        lang_code,
                        concurrency_limit=1,
                        translator=translator
                    )
                    log_with_bar(f"Processing: {f.name}")
                    file_callback = make_file_progress_callback(idx)
                    await local_manager.process_file(f, True, True, True, log_with_bar, None, policy, progress_callback=file_callback)
                    file_progress[idx] = 1.0
                    overall = sum(file_progress.values())
                    render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    break
                except (AbortException, ValueError):
                    if not translator.mixed_pool:
                        raise
                    continue
                except Exception:
                    raise

    tasks = [process_single_file(idx, f) for idx, f in enumerate(files)]
    first_file = True
    try:
        await asyncio.gather(*tasks)
    except (AbortException, ValueError):
        logging.getLogger("snbt_localizer.cli").error("Критическая ошибка: все ключи невалидны. Перевод прерван.")
        return 1
    sys.stdout.write('\n')
    sys.stdout.flush()
    logging.getLogger("snbt_localizer.cli").info("Finished.")
    logging.getLogger("snbt_localizer.cli").info(
        f"Успешно обработано {len(files)} файлов квестов (.snbt). Для применения квестов введите в игре команду: /ftbquests reload"
    )

    if json_lang_dirs:
        translator = UnifiedTranslator(
            api_keys,
            provider,
            model or "",
            config.custom_context,
            lang_name,
            lang_code,
            mixed_pool=mixed_pool,
            batch_size=config.batch_size,
            min_batch_size=config.min_batch_size,
            max_concurrent_requests=config.max_concurrent_requests
        )
        cache = TranslationCache(target_lang_code=lang_code)
        for base_dir in json_lang_dirs:
            logging.getLogger("snbt_localizer.cli").info(f"JSON translation mode detected. Processing lang files in {base_dir}...")
            manager = JSONManager(
                base_dir,
                lang_code,
                translator,
                cache,
                modpack=base_dir.name,
                policy=resolve_policy(config.policy),
                resource_pack_mode=resource_pack_mode
            )
            try:
                translated_count = await manager.process(
                    log_callback=logging.getLogger("snbt_localizer.cli").info,
                    check_status=None
                )
                logging.getLogger("snbt_localizer.cli").info(
                    f"JSON translation completed for {base_dir}. Translated {translated_count} strings. "
                    "In Minecraft, run '/ftbquests reload' or restart the game to apply changes."
                )
            except Exception as e:
                logging.getLogger("snbt_localizer.cli").error(f"JSON translation failed for {base_dir}: {e}")
                return 1

        if resource_pack_mode:
            modpack_root = next(iter(json_lang_dirs))
            while len(modpack_root.parts) > 1:
                if (modpack_root / "mods").is_dir() or (modpack_root / "config").is_dir() or (modpack_root / "kubejs").is_dir():
                    break
                modpack_root = modpack_root.parent
            pack_dir = modpack_root / "resourcepacks" / f"Modpack_Local_{lang_code}"
            pack_mcmeta_path = pack_dir / "pack.mcmeta"
            pack_png_path = pack_dir / "pack.png"

            if pack_mcmeta_path.exists():
                logging.getLogger("snbt_localizer.cli").info(f"Ресурс-пак успешно создан/обновлен по пути: {pack_dir}")
                if pack_png_path.exists():
                    logging.getLogger("snbt_localizer.cli").info("  └─ Фирменная иконка pack.png успешно добавлена в ресурс-пак!")
                else:
                    logging.getLogger("snbt_localizer.cli").warning("  └─ Предупреждение: Иконка pack.png пропущена (логотип logo.png не найден в ресурсах)")
            else:
                logging.getLogger("snbt_localizer.cli").error(f"ВНИМАНИЕ: Ошибка создания ресурс-пака по пути: {pack_dir}. Проверьте права доступа к папке.")
    elif resource_pack_mode:
        logging.getLogger("snbt_localizer.cli").warning(
            "ВНИМАНИЕ: Флаг -r / --resource-pack передан, но в модпаке не найдена папка KubeJS (kubejs/assets/). Ресурс-пак не был создан."
        )

    return 0

async def main_async() -> int:
    config = ConfigManager()
    config.prune_invalid_paths()
    parsed = config.parse_cli_args()
    setup_logging(debug=parsed.debug)

    if parsed.gui:
        from gui import main as gui_main
        gui_main()
        return 0
    cli_logger = logging.getLogger("snbt_localizer.cli")
    
    if parsed.clear_cache:
        if is_interactive():
            confirm = input("Are you sure you want to clear the entire translation cache? (y/n) [n]: ").strip().lower()
            if confirm not in ("y", "yes"):
                logging.getLogger("snbt_localizer.cli").info("Cancelled.")
                return 0
        cache = TranslationCache()
        cache.clear_all()
        logging.getLogger("snbt_localizer.cli").info("Кэш переводов SQLite успешно очищен.")
        sys.exit(0)

    if parsed.fastdir:
        result = cmd_fastdir(config)
        if result is None:
            logging.getLogger("snbt_localizer.cli").warning("No instance selected. Exiting.")
            return 1
        quest_dir, quest_dirs = result

        provider = config.provider
        if config.provider == "Mixed Providers":
            api_keys = []
            for prov in config.api_keys_pool:
                api_keys.extend(config.api_keys_pool[prov])
        else:
            api_keys = config.get_api_keys()
        model = config.model
        lang_name, lang_code = config.resolve_language(config.target_lang)

        if provider == "Mixed Providers":
            concurrency = max(config.concurrency, len(api_keys), 5)
        else:
            concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency, parsed.resource_pack)
    else:
        if parsed.mix:
            result = await run_mix_setup_wizard(config, parsed)
            if result is None:
                return 1
            quest_dir, lang_name, lang_code = result
            quest_dirs = find_all_quest_dirs(quest_dir)
            provider = "Mixed Providers"
            model = None
            api_keys = []
            config.provider = provider
            config.target_lang = lang_code
            config.quest_dir = quest_dir
            config.custom_context = ""
            config.policy = "Complement (Дополнить)"
            config.save_to_settings()
        else:
            quest_dir, provider, api_key, model, lang_name, lang_code = await run_setup_wizard(config, parsed)
            quest_dirs = find_all_quest_dirs(quest_dir)
            if config.provider == "Mixed Providers":
                api_keys = []
                for prov in config.api_keys_pool:
                    api_keys.extend(config.api_keys_pool[prov])
            else:
                api_keys = config.get_api_keys()
            config.save_to_settings()

        if parsed.mix:
            concurrency = max(config.concurrency, len(api_keys), 5)
        else:
            concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency, parsed.resource_pack)

    if parsed.clear_cache:
        if is_interactive():
            confirm = input("Are you sure you want to clear the entire translation cache? (y/n) [n]: ").strip().lower()
            if confirm not in ("y", "yes"):
                logging.getLogger("snbt_localizer.cli").info("Cancelled.")
                return 0
        cache = TranslationCache()
        cache.clear_all()
        logging.getLogger("snbt_localizer.cli").info("Кэш переводов SQLite успешно очищен.")
        sys.exit(0)

    if parsed.fastdir:
        result = cmd_fastdir(config)
        if result is None:
            logging.getLogger("snbt_localizer.cli").warning("No instance selected. Exiting.")
            return 1
        quest_dir, quest_dirs = result

        if parsed.mix:
            provider = "Mixed Providers"
            model = None
            api_keys = []
            lang_name, lang_code = config.resolve_language(config.target_lang)
            if not lang_name:
                lang_name, lang_code = "Russian", "ru_ru"
            concurrency = max(config.concurrency, len(api_keys), 5)
            return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency)

        provider = config.provider
        if config.provider == "Mixed Providers":
            api_keys = []
            for prov in config.api_keys_pool:
                api_keys.extend(config.api_keys_pool[prov])
        else:
            api_keys = config.get_api_keys()
        model = config.model
        lang_name, lang_code = config.resolve_language(config.target_lang)

        need_wizard = False
        if not provider:
            need_wizard = True
        elif provider != "Google Translate (Free)" and not model:
            need_wizard = True
        elif not lang_name:
            need_wizard = True

        if need_wizard and is_interactive():
            new_quest_dir, provider, api_key, model, lang_name, lang_code = await run_setup_wizard(config)
            quest_dirs = find_all_quest_dirs(new_quest_dir)
            if config.provider == "Mixed Providers":
                api_keys = []
                for prov in config.api_keys_pool:
                    api_keys.extend(config.api_keys_pool[prov])
            else:
                api_keys = config.get_api_keys()
        else:
            if not provider:
                provider = config.provider
            if not model and provider != "Google Translate (Free)":
                model = config.model
            if not lang_name:
                lang_name, lang_code = config.resolve_language(config.target_lang)

        if provider == "Mixed Providers":
            concurrency = max(config.concurrency, len(api_keys), 5)
        else:
            concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency, parsed.resource_pack)
    else:
        quest_dir = normalize_path(parsed.dir)
        quest_dirs = find_all_quest_dirs(quest_dir)
        if not quest_dirs:
            logging.getLogger("snbt_localizer.cli").error(f"No quest directories found in {quest_dir}")
            return 1
        provider = config.provider
        if config.provider == "Mixed Providers":
            api_keys = []
            for prov in config.api_keys_pool:
                api_keys.extend(config.api_keys_pool[prov])
        else:
            api_keys = config.get_api_keys()
        model = config.model
        lang_name, lang_code = config.resolve_language(config.target_lang)
        if provider == "Mixed Providers":
            concurrency = max(config.concurrency, len(api_keys), 5)
        else:
            concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dirs, concurrency, parsed.resource_pack)

def main() -> None:
    try:
        if os.name == "nt":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mineai.snbt-tr.localizer.1.0")
            except:
                pass
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.getLogger("snbt_localizer.cli").error("[SIGINT] Получен сигнал прерывания. Безопасная остановка (Graceful Shutdown)...")
        sys.exit(130)
    except Exception as e:
        logging.getLogger("snbt_localizer.cli").exception("Unexpected error")
        sys.exit(1)

if __name__ == "__main__":
    main()
