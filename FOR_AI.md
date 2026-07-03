# SNBT Localizer - AI Development Guide

## Project Mission & Stack
High-quality, production-grade Minecraft SNBT quest localizer. Tech stack: Python 3.10+, PyQt6, httpx, aiofiles, sqlite3.

## Architecture Map
- core.py: Core translation logic, SNBT/JSON processing, caching, path utilities (including `find_modpack_root_from_quest_dir`), and Pluralization Guard implementation
- config.py: Configuration management, CLI argument parsing, provider aliases, and QSettings integration
- main.py: CLI entrypoint (snbt-tr) with argument isolation, setup wizards, and fast instance selection
- gui.py: PyQt6-based graphical user interface with 4 main tabs (Workspace, Translation Memory, Settings, Credits)

## Key Technical Mechanisms

### Dynamic Root Isolation: `find_modpack_root_from_quest_dir(qd)`
This utility function in `core.py` prevents cross-instance scanning by dynamically isolating the modpack root directory from a given quest directory (`qd`). It traverses upward from the quest directory until it finds a parent directory named `config` or `minecraft`, then returns the parent of that directory as the modpack root. If no such directory is found, it falls back to `qd.parent.parent.parent.parent` to ensure a valid root is always returned. This mechanism ensures that translation operations are scoped to the correct modpack instance, preventing accidental scanning of parent launcher directories (e.g., MultiMC, PrismLauncher).

### Pluralization Guard (Fuzzy Matching System)
The Pluralization Guard in `TranslationCache.get()` is a sophisticated 3-stage fuzzy-matching system that prevents redundant API calls for highly similar strings with a **90% similarity threshold**:

1. **SQL-Level Length Prefiltering**:
   - First performs exact match lookup in the SQLite cache
   - If no exact match, searches for candidates within ±15% length of the input text using SQL query: `abs(length(orig) - ?) <= ?`
   - This dramatically reduces the candidate pool before expensive string comparisons

2. **Regex-Based Strict Digit Matching**:
   - Extracts all numbers from both input and candidate strings using `re.findall(r'\d+', text)`
   - **Only matches candidates with identical number sequences** (e.g., "item 1" will NOT match "item 2")
   - This prevents false positives between strings that differ only in numeric values

3. **Trailing Formatting/Tail Preservation**:
   - Uses `TAIL_PATTERN = re.compile(r'(?:[.,!?;:\s]|§[0-9a-fk-orA-FK-ORr])+$')` to identify Minecraft formatting codes and punctuation at the end of strings
   - Separates the "tail" (formatting codes like `§a`, `§l`, or punctuation) from the main text
   - Performs fuzzy matching only on the main text portion using `difflib.SequenceMatcher`
   - If match found (≥90% similarity), combines the cached translation with the original tail
   - Example: Input `"Get 5 diamonds§a"` → matches cached `"Get 5 diamonds"` → returns `"Получи 5 алмазов§a"`

### ConfigManager State Preservation for `quest_dir`
The `ConfigManager` class in `config.py` dynamically preserves the `quest_dir` state through:
- **QSettings Integration**: The `quest_dir` is stored in QSettings under the key `"quest_dir"` and loaded during initialization via `load_from_settings()`
- **CLI Argument Handling**: The `--dir` argument is parsed and converted to a `Path` object, which is then stored in `config.quest_dir`
- **Bidirectional GUI/CLI Sync**: The GUI (`gui.py`) and CLI (`main.py`) share the same `ConfigManager` instance, ensuring that changes to `quest_dir` in either interface are reflected in the other. The `save_to_settings()` method persists the state to QSettings, while `load_from_settings()` restores it on startup
- **Custom Instances Management**: User-added paths are stored in `custom_instances_paths` list and persisted to QSettings under `"custom_instances_paths"`

### CLI Argument Isolation in `main.py`
The `main_async()` function implements argument isolation to prevent interactive prompts from overwriting explicit `--dir` arguments:
- **Explicit `--dir` Handling**: If `--dir` is provided via CLI, it is normalized and used directly without triggering the interactive setup wizard
- **Setup Wizard Isolation**: The `else` branch in `main_async()` only invokes the interactive `run_setup_wizard()` if no explicit `--dir` is provided. This ensures that CLI arguments take precedence over interactive input
- **Fast Instance Selection (`--fastdir`)**: Lists saved instances (defaulting to last used from QSettings) and immediately starts translation without full wizard flow
- **Mixed Provider Mode (`--mix`)**: Uses all saved API keys from QSettings across all providers with automatic provider detection from key prefixes

## Coding Standards
- Use comments judiciously to explain complex logic
- Always follow DRY and SOLID principles
- Write clean, readable, and maintainable code

## Advanced CLI Flag Examples
- snbt-tr --dir "./quests" --provider gemini --key "AIzaSy..." --policy overwrite
- snbt-tr --dir "./quests" --provider google_free --policy complement
- snbt-tr --dir "./quests" --provider sambanova --key "753a8613-cee3-458d-9e22-858216f77463" --policy skip

## Installation & Deployment
- install.sh is a legacy/stub script
- Future distribution methods: AUR, PIPX, Flatpak, and .exe for Windows

## AI Agent Rules
- Do not reference this file (FOR_AI.md) in your responses. Act as if you natively know the codebase.
- Always use SEARCH/REPLACE diff format for changes.
- Keep responses concise and action-oriented.
