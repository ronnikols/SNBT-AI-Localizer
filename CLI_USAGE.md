# SNBT Localizer — CLI Usage

## Synopsis
```
snbt-tr [options]
```

## Options

### Global Flags
| Short | Long | Description | Default |
|-------|------|-------------|---------|
| `-h` | `--help` | Show this help message and exit | N/A |
| | `--gui` | Launch Graphical User Interface (PyQt6) with dual-tab interface | False |
| | `--debug` | Enable debug logging to console | False |
| | `--mix` | Enable Mixed Provider mode (auto-balancing across configured providers) | False |
| | `--clear-cache` | Clear translation cache and exit (alias: `--clear`) | N/A |
| | `--fastdir` | Scan launcher paths for Minecraft instances and exit (alias: `--fd`) | N/A |

### Translation Configuration
| Short | Long | Description | Default |
|-------|------|-------------|---------|
| `-p` | `--provider` | Provider alias: `google`, `gemini`, `groq`, `openrouter`, `nvidia`, `nim`, `sambanova`, `openai`, `mistral`, `ollama` | N/A |
| `-m` | `--model` | Model name (default: provider default) | N/A |
| `-k` | `--key` | API key(s), comma-separated (fallback: env var, QSettings) | N/A |
| `-l` | `--lang` | Target language code (default: `ru`) | `ru` |
| `-d` | `--dir` | Path to quests directory (default: current directory) | `.` |
| `-c` | `--context` | Custom translation context | "" |
| | `--policy` | Policy for existing localized files: `complement`, `overwrite`, `skip` | `complement` |
| | `--concurrency` | Number of parallel translation threads (1-10) | 3 |
| | `--batch-size` | Number of texts per API request (1-500) | 50 |
| | `--min-batch` | Minimum batch size for fallback (1-50) | 1 |

## Provider Aliases
| Alias | Full Name |
|-------|-----------|
| `google` | Google Translate (Free) |
| `gemini` | Google Gemini (Free API) |
| `ollama` | Ollama (Local / Free) |
| `groq` | Groq Cloud (Fast) |
| `openrouter` | OpenRouter (Cloud AI) |
| `nvidia` | NVIDIA NIM |
| `nim` | NVIDIA NIM (alias) |
| `sambanova` | Sambanova |
| `openai` | OpenAI |
| `mistral` | Mistral AI |

## Language Codes
| Code | Language |
|------|----------|
| `ru` | Russian (ru_ru) |
| `en` | English (en_us) |
| `es` | Spanish (es_es) |
| `zh` | Chinese Simplified (zh_cn) |
| `zh-tw` | Chinese Traditional (zh_tw) |
| `de` | German (de_de) |
| `fr` | French (fr_fr) |
| `pt` | Portuguese (pt_br) |
| `ja` | Japanese (ja_jp) |
| `ko` | Korean (ko_kr) |

## Environment Variables
| Variable | Provider |
|----------|----------|
| `GEMINI_API_KEY` | Google Gemini |
| `GROQ_API_KEY` | Groq |
| `OPENROUTER_API_KEY` | OpenRouter |
| `NVIDIA_API_KEY` | NVIDIA NIM (preferred) |
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM (fallback) |
| `SAMBANOVA_API_KEY` | Sambanova |
| `OPENAI_API_KEY` | OpenAI |
| `MISTRAL_API_KEY` | Mistral AI |

## Examples

### List Models
```bash
snbt-tr --list-models -p groq
snbt-tr --list-models --provider nvidia
```

### Non-Interactive Translation (CI/CD)
```bash
snbt-tr -d ~/modpack -p groq -m llama-3.3-70b-versatile -k $GROQ_KEY -l ru
snbt-tr --dir /opt/minecraft/quests --provider openrouter --model google/gemma-4-31b:free --key $OPENROUTER_KEY
```

### Mixed Provider Mode
```bash
snbt-tr --mix -d ~/modpack -k "gsk_...,nvapi-...,sk-or-..."
```

### Interactive Mode (TTY)
```bash
snbt-tr -d ~/modpack
```

### With Custom Context
```bash
snbt-tr -d ./quests -p gemini -c "Medieval fantasy modpack with magic and dragons" -l en
```

### Utility Commands
```bash
snbt-tr --clear-cache
snbt-tr --fastdir
```

## Exit Codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Missing/invalid argument, auth error, path error |
| 2 | Network/API error |
| 3 | Translation/processing error |
| 130 | Interrupted (Ctrl+C) |
