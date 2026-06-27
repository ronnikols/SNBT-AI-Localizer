import os
import sys
import asyncio
import httpx
import logging
from pathlib import Path
from typing import List, Optional, Dict
from core import SNBTManager, EXCLUDED_DIRS, parse_target_lang, TranslationCache, UnifiedTranslator
from config import ConfigManager, PROVIDER_ALIASES, PROVIDER_DEFAULTS, PROVIDER_ENDPOINTS, LANG_ALIASES, ENV_KEY_MAP, SETTINGS_KEY_MAP
try:
    from PyQt6.QtCore import QSettings
except ImportError:
    QSettings = None

def setup_logging(debug=False):
    """Configure logging for the CLI application."""
    root_logger = logging.getLogger("snbt_localizer")
    root_logger.setLevel(logging.DEBUG)  # capture all levels; handlers filter

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler("snbt_localizer.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(console_format)
    root_logger.addHandler(file_handler)

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

def load_cli_setting(key: str, default: str = "") -> str:
    settings = get_cli_settings()
    if settings:
        val = settings.value(key, default)
        return str(val) if val else default
    return default

async def run_setup_wizard() -> tuple[Path, str, str | None, str | None, str, str]:
    print("\n=== SNBT AI Localizer - Setup Wizard ===\n")

    print("Step 1: Select modpack instance")
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
        print("No modpack instances with FTB Quests found.")
        custom_path = input("Enter path to modpack manually: ").strip()
        if not custom_path:
            die("No path provided")
        quest_dir = normalize_path(custom_path)
    else:
        last_instance = load_cli_setting("cli_last_instance", "")
        default_idx = 0
        if last_instance:
            for i, (_, path, _) in enumerate(instances):
                if path == last_instance:
                    instances.insert(0, instances.pop(i))
                    default_idx = 0
                    break

        print("Found instances:")
        for i, (name, path, launcher) in enumerate(instances):
            marker = " (last used)" if i == 0 and last_instance else ""
            print(f"  {i + 1}) {name} [{launcher}]{marker}")
        print(f"  {len(instances) + 1}) Enter path manually...")

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
                    save_cli_setting("cli_last_instance", str(quest_dir))
                    break
            except ValueError:
                pass
            print("Invalid choice")

    print(f"\nSelected: {quest_dir}\n")

    print("Step 2: Select translation provider")
    providers = list(dict.fromkeys(PROVIDER_ALIASES.values()))
    last_provider = load_cli_setting("cli_last_provider", "")
    default_idx = 0
    if last_provider and last_provider in providers:
        default_idx = providers.index(last_provider)

    print("Available providers:")
    for i, p in enumerate(providers):
        marker = " (last used)" if i == default_idx else ""
        print(f"  {i + 1}) {p}{marker}")

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
        print("Invalid choice")

    print(f"\nSelected: {provider}\n")

    print("Step 3: API Key")
    api_key = None
    if provider not in ("Google Translate (Free)", "Ollama (Local / Free)"):
        env_key = load_key_from_env_or_settings(provider)
        if env_key:
            masked = "*" * (len(env_key) - 4) + env_key[-4:] if len(env_key) > 4 else "****"
            print(f"API key detected in system. Press Enter to use it or enter a new one:")
            user_key = input(f"Use saved key [{masked}]: ").strip()
            if user_key:
                api_key = user_key
                settings_key = SETTINGS_KEY_MAP.get(provider)
                if settings_key:
                    save_cli_setting(settings_key, api_key)
            else:
                api_key = env_key
        else:
            while True:
                api_key = input("API Key: ").strip()
                if api_key:
                    settings_key = SETTINGS_KEY_MAP.get(provider)
                    if settings_key:
                        save_cli_setting(settings_key, api_key)
                    break
                print("API Key cannot be empty")

    print(f"\nStep 4: Model and Language")
    model = None
    if provider != "Google Translate (Free)":
        models = await fetch_models(provider, api_key)
        if "gemini" in provider.lower() or "google" in provider.lower():
            for i in range(len(models)):
                if "gemini-3.1-flash-lite" in models[i] and not models[i].endswith(" [RECOMMENDED]"):
                    models[i] = models[i] + " [RECOMMENDED]"
        last_model = load_cli_setting("cli_last_model", "")
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
            print("Available models:")
            for i, m in enumerate(models):
                base = m.replace(" [RECOMMENDED]", "")
                marker = " (last used)" if i == 0 and base == last_model else ""
                print(f"  {i + 1}) {m}{marker}")
            
            choice = input(f"Choice [1]: ").strip()
            choice = choice or "1"
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    model = models[idx]
                    model = model.replace(" [RECOMMENDED]", "")
                    save_cli_setting("cli_last_model", model)
                    break
            except ValueError:
                if choice.lower() == "all":
                    models = list(all_models)
                    continue
                filtered = [m for m in all_models if choice.lower() in m.lower()]
                if filtered:
                    models = filtered
                    continue
                print("Invalid choice")
    else:
        model = None

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

    print("Available languages:")
    for i, (alias, (name, code)) in enumerate(langs):
        marker = " (last used)" if i == default_idx else ""
        print(f"  {i + 1}) {name} ({code}){marker}")

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
        print("Invalid choice")

    print(f"\nSelected: {lang_name} ({lang_code})\n")
    print("Starting translation...\n")

    return quest_dir, provider, api_key, model, lang_name, lang_code

def die(msg: str, code: int = 1) -> None:
    try:
        logging.getLogger("snbt_localizer.cli").error(msg)
    except Exception:
        sys.stderr.write(f"ERROR: {msg}\n")
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
    if api_key and provider != "Ollama (Local / Free)":
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
    except Exception:
        pass
    return []

def select_provider_interactive() -> str:
    providers = list(dict.fromkeys(PROVIDER_ALIASES.values()))
    print("Select provider:")
    for i, p in enumerate(providers, 1):
        print(f"  {i}) {p}")
    while True:
        choice = input("Choice [1]: ").strip()
        choice = choice or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                return providers[idx]
        except ValueError:
            pass
        print("Invalid choice")

def select_model_interactive(models: list[str], provider: str) -> str:
    if not models:
        default = PROVIDER_DEFAULTS.get(provider)
        if default:
            return default
        die("No models available and no default for provider")
    print("Select model:")
    for i, m in enumerate(models[:20], 1):
        print(f"  {i}) {m}")
    if len(models) > 20:
        print(f"  ... and {len(models) - 20} more")
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
        print("Invalid choice")

def select_language_interactive() -> tuple[str, str]:
    langs = list(LANG_ALIASES.items())
    print("Select language:")
    for i, (alias, (name, code)) in enumerate(langs, 1):
        print(f"  {i}) {name} ({code})")
    while True:
        choice = input("Choice [1]: ").strip()
        choice = choice or "1"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(langs):
                return langs[idx][1]
        except ValueError:
            pass
        print("Invalid choice")

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

def cmd_fastdir() -> Path | None:
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
        logging.getLogger("snbt_localizer.cli").warning("No modpack instances with FTB Quests found.")
        return None

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

    while True:
        choice = input(f"Choice [{default_idx + 1}]: ").strip()
        choice = choice or str(default_idx + 1)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(instances):
                quest_dir = Path(instances[idx][1])
                save_cli_setting("cli_last_instance", str(quest_dir))
                return quest_dir
        except ValueError:
            pass
        print("Invalid choice")

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

async def run_translation(config: ConfigManager, provider: str, model: str | None, api_keys: List[str], lang_name: str, lang_code: str, quest_dir: Path, concurrency: Optional[int] = None) -> int:
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
    first_key = api_keys[0] if api_keys else ""
    m = SNBTManager(first_key, provider, model or "", config.custom_context, lang_name, lang_code, concurrency_limit=limit)

    mixed_pool = None
    if provider == "Mixed Providers":
        pairs = parse_key_model_pairs(api_keys)
        saved_keys_by_provider = {}
        saved_models_by_provider = {}
        default_models_by_provider = {}
        for p in ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)"]:
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
        
        api_keys = [item["api_key"] for item in mixed_pool]
    
    m.translator = UnifiedTranslator(api_keys, provider, model or "", config.custom_context, lang_name, lang_code, mixed_pool=mixed_pool)
    target_dir = m.find_quests_dir(quest_dir)
    files = [p for p in target_dir.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
    if not files:
        logging.getLogger("snbt_localizer.cli").warning("No .snbt files found")
        return 0
    total_files = len(files)
    logging.getLogger("snbt_localizer.cli").info(
        f"Starting localization. Active Provider: {provider}, Active Model: {model or 'N/A'}, Keys in Pool: {len(api_keys)}"
    )
    logging.getLogger("snbt_localizer.cli").info(f"Found {total_files} files")
    policy = resolve_policy(config.policy)
    current_file_idx = 0
    current_chunk_progress = 0.0

    def log_with_bar(msg):
        nonlocal first_file
        sys.stdout.write('\r\033[K')
        if not first_file:
            sys.stdout.write('\033[F\033[K')
        else:
            first_file = False
        print(msg)
        overall = current_file_idx + current_chunk_progress
        render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")

    def file_progress_callback(chunk_idx, total_chunks):
        nonlocal current_chunk_progress
        if total_chunks > 0:
            current_chunk_progress = chunk_idx / total_chunks
        else:
            current_chunk_progress = 0.0
        overall = current_file_idx + current_chunk_progress
        render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")

    first_file = True
    for idx, f in enumerate(files):
        current_file_idx = idx
        current_chunk_progress = 0.0
        log_with_bar(f"Processing: {f.name}")
        await m.process_file(f, True, True, True, log_with_bar, None, policy, progress_callback=file_progress_callback)
        current_chunk_progress = 1.0
        overall = current_file_idx + current_chunk_progress
        render_cli_progress(overall, total_files, prefix="Progress", suffix="Complete")
        sys.stdout.write('\n')
        sys.stdout.flush()
    sys.stdout.write('\n')
    sys.stdout.flush()
    logging.getLogger("snbt_localizer.cli").info("Finished.")
    return 0

async def main_async() -> int:
    config = ConfigManager()
    parsed = config.parse_cli_args()
    setup_logging(debug=parsed.debug)
    cli_logger = logging.getLogger("snbt_localizer.cli")
    
    if len(sys.argv) == 1:
        quest_dir, provider, api_key, model, lang_name, lang_code = await run_setup_wizard()
        config.provider = provider
        config.model = model
        config.target_lang = lang_code
        config.quest_dir = quest_dir
        config.custom_context = ""
        config.policy = "Complement (Дополнить)"
        config.set_api_keys(provider, [api_key] if api_key else [])
        config.save_to_settings()
        api_keys = config.get_api_keys()
        concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dir, concurrency)
    
    if parsed.clear_cache:
        if is_interactive():
            confirm = input("Are you sure you want to clear the entire translation cache? (y/n) [n]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cancelled.")
                return 0
        cache = TranslationCache()
        cache.clear_all()
        logging.getLogger("snbt_localizer.cli").info("Translation cache cleared successfully.")
        return 0

    if parsed.fastdir:
        quest_dir = cmd_fastdir()
        if quest_dir is None:
            logging.getLogger("snbt_localizer.cli").warning("No instance selected. Exiting.")
            return 1

        provider = config.provider
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
            quest_dir, provider, api_key, model, lang_name, lang_code = await run_setup_wizard()
            config.provider = provider
            config.model = model
            config.target_lang = lang_code
            config.quest_dir = quest_dir
            config.custom_context = ""
            config.policy = "Complement (Дополнить)"
            config.set_api_keys(provider, [api_key] if api_key else [])
            config.save_to_settings()
        else:
            if not provider:
                provider = config.provider
            if not api_keys:
                api_keys = config.get_api_keys()
            if not model and provider != "Google Translate (Free)":
                model = config.model
            if not lang_name:
                lang_name, lang_code = config.resolve_language(config.target_lang)

        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dir)
    else:
        quest_dir = normalize_path(parsed.dir)
        provider = config.provider
        api_keys = config.get_api_keys()
        model = config.model
        lang_name, lang_code = config.resolve_language(config.target_lang)
        concurrency = max(1, min(config.concurrency, 10))
        return await run_translation(config, provider, model, api_keys, lang_name, lang_code, quest_dir, concurrency)

def main() -> None:
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[SIGINT] Получен сигнал прерывания. Безопасная остановка (Graceful Shutdown)...")
        sys.exit(130)
    except Exception as e:
        logging.getLogger("snbt_localizer.cli").exception("Unexpected error")
        sys.exit(1)

if __name__ == "__main__":
    main()
