# SNBT AI Localizer

English | [Русский](README_RU.md)

Advanced asynchronous translator for Minecraft FTB Quests files (`.snbt`) with support for multiple local and cloud translation engines.

## Installation

### Recommended Methods
| Platform       | Command                          |
|----------------|----------------------------------|
| Arch Linux AUR | `yay -S snbt-tr`                 |
| Flatpak        | `flatpak install org.mineai.snbt-tr` |
| pipx           | `pipx install snbt-tr`           |
| PyPI           | `pip install snbt-tr`            |

### Manual Installation
```bash
git clone https://github.com/your-repo/snbt-ai-localizer.git
cd snbt-ai-localizer
pip install -r requirements.txt
```

## Usage

### Launch Methods
- `snbt-tr` - Launches the interactive CLI setup wizard
- `snbt-tr --gui` - Launches the PyQt6 GUI as a fallback console wrapper
- `snbt-tr -d /path/to/quests` - Unattended batch execution

### Examples
```bash
# List available models for Groq
snbt-tr --list-models -p groq

# Translate quests directory using Groq with API key
snbt-tr -d /path/to/quests -p groq -k YOUR_API_KEY

# Translate using Mixed Provider mode
snbt-tr --mix -d /path/to/quests

# Clear translation cache
snbt-tr --clear-cache

# Scan for Minecraft instances
snbt-tr --fastdir
```

## Features

### Asynchronous Processing
- Non-blocking I/O with `asyncio` and `httpx.AsyncClient`
- Configurable concurrency (1-10 threads)
- Adaptive chunking (5 items for Ollama, 15 for cloud providers)
- Automatic delays between chunks to prevent rate limiting

### Fault Tolerance
- Round-Robin multi-key pool with automatic load balancing
- Invalid keys (401/403) are permanently removed from the pool
- Rate-limited keys (429) enter a dynamic exponential backoff starting at 0.2s and doubling on each consecutive failure
- Fallback to single-item translation on chunk failure
- Mixed Provider Mode continues working even if some providers fail

### Smart Caching
- SQLite-based cache with thread-safe locking
- Per-language tables to prevent cross-contamination
- Pluralization Guard to avoid duplicate API calls for similar phrases
- Real-time persistence between chunks

### Minecraft Formatting Protection
- Hardcoded regex shielding for namespace tags, UUIDs, and entity IDs
- Temporary placeholder substitution during translation
- Preserves all Minecraft-specific formatting codes

## Supported Providers

| Provider               | Default Model                     | Free Tier |
|------------------------|-----------------------------------|-----------|
| Groq Cloud (Fast)     | llama-3.3-70b-versatile          | Yes       |
| NVIDIA NIM            | nvidia/nemotron-4-340b-instruct   | Yes       |
| OpenRouter (Cloud AI) | google/gemma-4-31b:free          | Yes       |
| Google Gemini (Free API) | models/gemini-3.1-flash-lite   | Yes       |
| Sambanova             | DeepSeek-V3.1                     | No        |
| OpenAI                | gpt-4o-mini                       | No        |
| Mistral AI            | mistral-large-latest             | No        |
| Ollama (Local / Free) | qwen2.5:7b                       | Yes       |
| Google Translate (Free)| N/A                              | Yes       |

## License
MIT License - see [LICENSE](LICENSE) for details.
