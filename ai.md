# SNBT AI Localizer

SNBT AI Localizer is an advanced asynchronous translator for Minecraft FTB Quests files (`.snbt`). It supports multiple local and cloud translation engines with a focus on reliability, fault tolerance, and Minecraft-specific formatting preservation.

## Packaging and Distribution

| Platform       | Package Name          | Install Command                          |
|----------------|------------------------|------------------------------------------|
| Arch Linux AUR | `snbt-tr`             | `yay -S snbt-tr`                         |
| Flatpak        | `org.mineai.snbt-tr`  | `flatpak install org.mineai.snbt-tr`    |
| pipx           | `snbt-tr`             | `pipx install snbt-tr`                   |
| PyPI           | `snbt-tr`             | `pip install snbt-tr`                    |
| Windows EXE    | Standalone            | Download from releases                   |

## CLI Reference

The primary entry point is the `snbt-tr` command.

### Global Flags

| Short | Long            | Description                                                                                     | Default       |
|-------|-----------------|-------------------------------------------------------------------------------------------------|---------------|
| `-h`  | `--help`        | Show this help message and exit                                                                | N/A           |
|       | `--gui`         | Launch Graphical User Interface (GUI)                                                          | False         |
|       | `--debug`       | Enable debug logging to console                                                                | False         |
|       | `--mix`         | Enable Mixed Provider mode using QSettings key pool                                           | False         |

### Translation Configuration

| Short | Long         | Description                                                                                     | Default       |
|-------|--------------|-------------------------------------------------------------------------------------------------|---------------|
| `-p`  | `--provider` | Provider alias (google, gemini, groq, openrouter, nvidia, nim, sambanova, openai, mistral)       | N/A           |
| `-m`  | `--model`    | Model name (default: provider default)                                                          | N/A           |
| `-k`  | `--key`      | API key(s), comma-separated (env/QSettings fallback)                                          | N/A           |
| `-l`  | `--lang`     | Language code (default: ru)                                                                     | ru            |
| `-d`  | `--dir`      | Path to quests directory (default: current directory)                                          | .             |
| `-c`  | `--context`  | Custom translation context                                                                    | ""            |
|       | `--policy`   | Existing files policy: complement, overwrite, skip (default: complement)                        | complement    |
|       | `--concurrency` | Number of parallel translation threads (1-10, default: 3)                                   | 3             |

### Utility Commands

| Short | Long            | Description                                                                                     |
|-------|-----------------|-------------------------------------------------------------------------------------------------|
|       | `--list-models` | List available models for provider and exit                                                    |
|       | `--fastdir`     | Scan launcher paths for instances and exit (alias: `--fd`)                                     |
|       | `--clear-cache` | Clear translation cache and exit (alias: `--clear`)                                            |

## Core Architecture

### Asynchronous Engine
- Built on `asyncio` with `httpx.AsyncClient` for non-blocking I/O
- Configurable concurrency (1-10 threads) with adaptive chunking:
  - 5 items per chunk for Ollama (local)
  - 15 items per chunk for cloud providers
- Automatic 3-second delay between chunks for non-Ollama providers to prevent rate limiting

### Round-Robin Multi-Key Pool
- Cyclic key rotation with automatic load balancing
- Invalid keys (HTTP 401/403) are permanently removed from the pool during operation
- Rate-limited keys (HTTP 429) enter a dynamic exponential backoff starting at 0.2s and doubling on each consecutive failure
- Mixed Provider Mode: Auto-detects provider from key prefix and uses saved defaults

### SQLite Cache with Pluralization Guard
- Thread-safe SQLite database (`cache.sqlite`) with per-language tables
- Exact-match lookup with O(1) primary key search
- Batch persistence via `executemany` for atomic updates
- Pluralization Guard: Prevents duplicate API calls for similar phrases by normalizing variations

### Minecraft Tag Protection
- Hardcoded regex shielding for:
  - Namespace tags (`#c:ender_pearl_dusts`, `#forge:ingots`)
  - UUIDs (`[0-9a-f]{8}-[0-9a-f]{4}-...`)
  - Entity IDs (`minecraft:diamond_sword`)
- Temporary placeholder substitution (`__TAG_N__`) during translation, restored post-processing

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
