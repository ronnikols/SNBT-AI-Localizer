<p align="center">
  <img src="resources/logo.png" alt="SNBT AI Localizer Logo" width="200" height="200">
</p> # SNBT AI Localizer

English | [Русский](README_RU.md)

Advanced asynchronous translator for Minecraft FTB Quests files (`.snbt` and the new FTB Quests 26.x `.json5` lang format) with support for multiple local and cloud translation engines, featuring a 4-tab GUI and intelligent SQLite caching system.

## Installation

### Recommended Methods
| Platform       | Command                          |
|----------------|----------------------------------|
| Windows        | `winget install org.mineai.snbt-tr` (Recommended) |
| Arch Linux AUR | `yay -S snbt-tr`                 |
| Flatpak        | `flatpak install org.mineai.snbt-tr` |
| pipx           | `pipx install snbt-tr`           |
| PyPI           | `pip install snbt-tr`            |

### Manual Installation
```bash
git clone https://github.com/ronnikols/SNBT-AI-Localizer.git
cd SNBT-AI-Localizer
pip install -r requirements.txt
```

## Usage

### Launch Methods
- `snbt-tr` - Launches the interactive CLI setup wizard
- `snbt-tr --gui` - Launches the PyQt6 GUI with dual-tab interface
- `snbt-tr [options]` - Unattended batch execution

### Examples
```bash
snbt-tr --list-models -p groq
snbt-tr -d /path/to/quests -p groq -k YOUR_API_KEY
snbt-tr --mix -d /path/to/quests
snbt-tr --clear-cache
snbt-tr --fastdir
```

## Features

### 4-Tab GUI Architecture
- **Workspace Tab**: Primary translation interface with provider/model selection, API key pool management (up to 10 keys), custom context input, target language dropdown, batch processing controls (Start/Pause/Stop), and live logging output
- **Translation Memory Tab**: Visual cache manager with:
  - Real-time search across original and translated text with 300ms debounce
  - Modpack combobox filter for isolating translations by modpack
  - Target language filter synchronized with Workspace tab
  - 4-column QTableWidget (Original, Translation, Modpack, Added) with auto-stretch column width layout
  - Inline editing of translations directly in the table
  - Bulk operations: Load More (pagination), Delete Selected, Save Changes, Clear Cache
  - **Auto-Fix button**: two-stage cache healer — repairs broken technical syntax (`% s` → `%s`, `__TAG _12__` → `__TAG_12__`, markdown links), then scans the whole cache for garbage translations (≥90% wrong-language text, CJK symbol leaks, mixed-alphabet hybrid words like "Лимитite") and re-translates them with your **active provider/model**, validating every LLM answer before writing
- **Settings Tab**: Configuration management for providers, models, API keys, and application settings
- **Credits Tab**: Displays project credits and acknowledgments

### Asynchronous Processing
- Non-blocking I/O with `asyncio` and `httpx.AsyncClient`
- Configurable concurrency (1-10 threads)
- Adaptive chunking:
  - 5 items per chunk for Ollama (local inference)
  - Configurable batch size (default: 50) for cloud providers
- Automatic delays between chunks to prevent rate limiting

### Fault Tolerance
- Round-Robin multi-key pool with automatic load balancing
- Invalid keys (HTTP 401/403) are permanently removed from the pool
- Rate-limited keys (HTTP 429) enter exponential backoff (0.2s to 64s)
- Fallback to single-item translation on chunk failure
- Mixed Provider Mode: Auto-detects provider from key prefix and uses saved defaults
- Binary split fallback for parse errors with recursive chunk splitting

### Smart Caching System
- SQLite-based cache with WAL mode for concurrent access
- Per-language tables (`cache_{lang_code}`) to prevent cross-contamination
- Modpack isolation: Translations can be filtered and managed by modpack
- Thread-safe operations with locking
- Real-time persistence between chunks
- Defensive sanitization: Automatic cleanup of nested dictionaries in SNBT and protection against malformed JSON in responses
- Cache poisoning protection: identity records (translation = original) never count as cache hits
- Cache hits are logged (`Cache: N string(s) from cache`); `overwrite` policy bypasses the cache entirely so every string is re-translated

### FTB Quests 26.x (.json5) Support
- Automatic detection of the new `lang/en_us/*.json5` directory format (FTB Quests 26.x / MC 26.x)
- Per-file translation jobs writing to `lang/ru_ru/<file>.json5`, with `.json5.bak` backups
- List values (quest descriptions) flattened as `key[idx]` and re-assembled after translation
- Complement and overwrite strategies, same as SNBT

### 🛡️ Pluralization Guard
**Prevents redundant API calls for highly similar strings with a 90% similarity threshold**

The Pluralization Guard is a sophisticated fuzzy-matching system that automatically detects and reuses translations for similar phrases, preventing duplicate API calls and saving costs. It works by:

1. **Exact Match Check**: First attempts to find an exact match in the cache
2. **Length Filtering**: Searches for candidates within ±15% length of the input text
3. **Number Preservation**: Ensures strings with different numbers (e.g., "item 1" vs "item 2") are NOT matched
4. **Fuzzy Matching**: Uses `difflib.SequenceMatcher` with a **90% similarity threshold**
5. **Tail Preservation**: Maintains Minecraft formatting codes at the end of strings (e.g., "hello§a" → cached "привет" + "§a")

**Example:**
- Input: `"Get 5 diamonds"` → Cache miss
- Input: `"Get 6 diamonds"` → **Cache hit!** (90%+ similarity, same structure)
- Input: `"Get diamond"` → Cache miss (different number count)
- Input: `"Get 5 diamonds§a"` → **Cache hit!** (matches "Get 5 diamonds" + preserves "§a")

This prevents charging for translations of:
- Plural variations: "apple" → "apples"
- Number variations: "item 1" → "item 2" (if structure matches)
- Minor formatting differences: "text" → "text§a"

### Minecraft Formatting Protection
- Regex shielding for namespace tags (`#c:ender_pearl_dusts`), UUIDs, and entity IDs
- Temporary placeholder substitution (`__TAG_N__`) during translation
- Preserves all Minecraft-specific formatting codes

## Supported Providers

| Provider | Default Model | Free Tier | Notes |
|----------|----------------|-----------|-------|
| Groq Cloud (Fast) | qwen/qwen3.8-27b | Yes | Low-latency inference |
| NVIDIA NIM | nvidia/nemotron-4-340b-instruct | Yes | Enterprise-grade models |
| OpenRouter (Cloud AI) | google/gemma-4-31b:free | Yes | 100+ free models |
| Google Gemini (Free API) | models/gemini-flash-lite-latest | Yes | Google's latest free model |
| Sambanova | DeepSeek-V3.1 | No | High-performance inference |
| OpenAI | gpt-4o-mini | No | Optimized for speed |
| Mistral AI | mistral-large-latest | Yes | Open-source frontier models |
| Anthropic (Claude) | claude-3-5-sonnet-20241022 | No | High-quality responses |
| Cohere | command-r-plus | No | Production-ready |
| OpenCode | deepseek-v4-flash | Yes | OpenCode Zen inference |
| Crusoe Cloud | zai/GLM-5.3-Flash | Yes | OpenAI-compatible serverless inference, $5 free credits |
| RunInfra | glm-5-3-flash | Yes | OpenAI-compatible inference for open models (`rp_` keys, env `RUNINFRA_GATEWAY_KEY`) |
| Ollama (Local / Free) | qwen2.5:7b | Yes | Self-hosted, no API key |
| Google Translate (Free) | N/A | Yes | Traditional MT, no API key |
| Custom (OpenAI-compatible) | (Custom) | Yes | Custom OpenAI-compatible endpoints |

### Key Tester Features
- One-click key verification with a live test question; active keys also show their **account balance** when the provider exposes an API (RunInfra, OpenRouter, OpenCode) or a console hint (Crusoe, Groq, OpenAI, Anthropic, Cohere, Mistral, Sambanova, NVIDIA)
- "Model Paused" status for provider-side model pauses (HTTP 503 `hosted_model_paused`)
- Mixed Providers mode: auto-detects provider from key prefix; unknown-format keys are explicitly marked Invalid instead of being misrouted
- Reasoning effort suffix support: `model/level` syntax (e.g. `zai-org/GLM-5.3-Flash/low`) with per-provider mapping
- Global temperature setting: spinbox in GUI, `--temperature` CLI flag, applied to all LLM providers

## Feedback & Community
For feedback, suggestions, and bug reports, please contact us via:
- **Telegram**: [https://t.me/ronnikols](https://t.me/ronnikols)

## License
MIT License - see [LICENSE](LICENSE) for details. 
