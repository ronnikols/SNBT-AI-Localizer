# SNBT AI Localizer — Technical Overview

SNBT AI Localizer is an advanced asynchronous translator for Minecraft FTB Quests files (`.snbt`). It supports multiple local and cloud translation engines with a focus on reliability, fault tolerance, and Minecraft-specific formatting preservation.

## Repository Structure

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point with argument parsing, setup wizards, and batch translation orchestration |
| `gui.py` | PyQt6 GUI implementation with dual-tab interface (Workspace and Translation Memory) |
| `core.py` | Core translation logic: TranslationCache (SQLite), UnifiedTranslator, SNBTManager, and formatting protection |
| `config.py` | Configuration management: ConfigManager for settings, API keys, and provider defaults |
| `tests/` | Test suite with 43 tests covering GUI, CLI, caching, and translation logic |

## Packaging and Distribution

| Platform | Package Name | Install Command |
|----------|--------------|-----------------|
| Arch Linux AUR | `snbt-tr` | `yay -S snbt-tr` |
| Flatpak | `org.mineai.snbt-tr` | `flatpak install org.mineai.snbt-tr` |
| pipx | `snbt-tr` | `pipx install snbt-tr` |
| PyPI | `snbt-tr` | `pip install snbt-tr` |

## Architecture

### Dual-Tab GUI (PyQt6)
- **Workspace Tab**:
  - Provider/model selection with live auto-suggest via QCompleter
  - Multi-key pool management (up to 10 keys) with QTextEdit
  - Custom context input for translation
  - Batch processing controls (Start/Pause/Stop)
  - Real-time progress tracking with QProgressBar
  - Live logging output to QTextEdit
- **Translation Memory Tab**:
  - SQLite cache visualization via QTableWidget
  - Search with 300ms debounce using QTimer
  - Language and modpack filtering via QComboBox
  - Paginated table view (500 entries/page)
  - Inline editing and bulk operations
  - Bidirectional language synchronization with Workspace tab

### Core Components

#### TranslationCache (SQLite + WAL)
- **Thread-Safe Design**: Uses `threading.Lock` for all operations
- **WAL Mode**: Enables concurrent reads/writes (`PRAGMA journal_mode=WAL`)
- **Schema**:
  - Per-language tables (`cache_{lang_code}`)
  - Columns: `orig` (PRIMARY KEY), `trans`, `modpack`, `created_at`
  - Indexes: `idx_cache_{lang_code}_modpack` for fast filtering
- **Sanitization**:
  - Automatic cleanup of nested dictionaries in SNBT via `_sanitize_mapping`
  - Protection against malformed JSON in API responses
- **Pluralization Guard**:
  - Fuzzy matching (90% similarity threshold) via difflib.SequenceMatcher
  - Number-aware comparison (preserves numeric IDs)
  - Tail pattern preservation (punctuation, formatting codes)

#### UnifiedTranslator
- **Multi-Provider Support**: 9 providers with auto-detection via `detect_provider`
- **Key Pool Management**:
  - Round-Robin rotation with `key_index`
  - Exponential backoff for rate-limited keys (0.2s to 64s) stored in `key_backoff`
  - Permanent removal of invalid keys (401/403) from `mixed_pool`
- **Binary Split Fallback**:
  - Recursive chunk splitting on parse errors via `_translate_indexed`
  - Single-item fallback as last resort
- **Mixed Provider Mode**:
  - Auto-detection from key prefixes (`gsk_`, `nvapi-`, etc.) via `resolve_mixed_pool`
  - Per-key model specification (format: `key\model`)
  - Cross-provider load balancing

#### SNBTManager
- **File Processing**:
  - Automatic detection of localization files (`{lang}.snbt`)
  - Backup creation (`.bak` files) for in-place translation
  - Policy support: Complement, Overwrite, Skip
- **Modpack Isolation**:
  - Optional `modpack` parameter for cache segmentation
  - Preserves modpack context in translations
- **Formatting Protection**:
  - Regex patterns for tags (`#namespace:path`), UUIDs, entity IDs
  - Placeholder substitution during translation
  - Exact restoration post-translation

## Supported Providers

| Provider | Default Model | Free Tier | Base URL |
|----------|----------------|-----------|----------|
| Groq Cloud (Fast) | llama-3.3-70b-versatile | Yes | `https://api.groq.com/openai/v1` |
| NVIDIA NIM | nvidia/nemotron-4-340b-instruct | Yes | `https://integrate.api.nvidia.com/v1` |
| OpenRouter (Cloud AI) | google/gemma-4-31b:free | Yes | `https://openrouter.ai/api/v1` |
| Google Gemini (Free API) | models/gemini-3.1-flash-lite | Yes | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Sambanova | DeepSeek-V3.1 | No | `https://api.sambanova.ai/v1` |
| OpenAI | gpt-4o-mini | No | `https://api.openai.com/v1` |
| Mistral AI | mistral-large-latest | No | `https://api.mistral.ai/v1` |
| Ollama (Local / Free) | qwen2.5:7b | Yes | `http://localhost:11434/v1` |
| Google Translate (Free) | N/A | Yes | `https://translate.googleapis.com` |

## CLI Reference

### Global Flags
| Short | Long | Description |
|-------|------|-------------|
| `--gui` | Launch PyQt6 GUI with dual-tab interface |
| `--mix` | Enable Mixed Provider mode |
| `--clear-cache` | Clear translation cache |
| `--fastdir` | Scan for Minecraft instances |

### Translation Flags
| Short | Long | Description |
|-------|------|-------------|
| `-p` | `--provider` | Provider alias (9 supported) |
| `-m` | `--model` | Model name (auto-falls back to provider default) |
| `-k` | `--key` | API key(s) (comma-separated) |
| `-l` | `--lang` | Target language (default: `ru`) |
| `-d` | `--dir` | Quests directory path |
| `-c` | `--context` | Custom translation context |
| | `--policy` | Existing files policy: `complement`, `overwrite`, `skip` |
| | `--concurrency` | Parallel threads (1-10) |
| | `--batch-size` | Items per API request (1-500) |

## Performance Characteristics
- **Concurrency**: 1-10 parallel threads (configurable)
- **Chunking**:
  - Ollama: 5 items/chunk (local inference)
  - Cloud: Configurable (default: 50)
- **Rate Limiting**:
  - Automatic 3s delay between chunks (non-Ollama)
  - Exponential backoff for 429 errors (0.2s to 64s)
- **Caching**:
  - SQLite WAL mode for concurrent access
  - Real-time persistence between chunks
  - Per-language and per-modpack isolation
