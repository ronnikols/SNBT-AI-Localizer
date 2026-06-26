# SNBT Localizer — CLI Usage

## Synopsis
```
python main.py [options]
```

## Options
| Flag | Argument | Description |
|------|----------|-------------|
| `-p`, `--provider` | ALIAS | Provider: `google`, `gemini`, `groq`, `openrouter`, `nvidia`, `nim` |
| `-m`, `--model` | NAME | Model name (default: provider default) |
| `-k`, `--key` | KEY | API key (fallback: env var, QSettings) |
| `-l`, `--lang` | CODE | Target language (default: `ru`) |
| `-d`, `--dir` | PATH | Quests directory (default: `.`, supports `~`) |
| `-c`, `--context` | TEXT | Custom translation context |
| `--list-models` | | List models for provider and exit |
| `-h`, `--help` | | Show help |

## Provider Aliases
| Alias | Full Name |
|-------|-----------|
| `google` | Google Translate (Free) |
| `gemini` | Google Gemini (Free API) |
| `ollama` | Ollama (Local / Free) |
| `groq` | Groq Cloud (Fast) |
| `openrouter` | OpenRouter (Cloud AI) |
| `nvidia`, `nim` | NVIDIA NIM |

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

## Examples

### List models
```bash
python main.py --provider nim --list-models
```

### Non-interactive (CI/CD)
```bash
python main.py -d ~/modpack -p groq -m llama-3.3-70b-versatile -k $GROQ_KEY -l ru
```

### Interactive (TTY)
```bash
python main.py -d ~/modpack
# Prompts for provider, key, model, language
```

### With custom context
```bash
python main.py -d ./quests -p gemini -c "Medieval fantasy modpack with magic and dragons" -l en
```

## Exit Codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Missing/invalid argument, auth error, path error |
| 2 | Network/API error |
| 3 | Translation/processing error |
| 130 | Interrupted (Ctrl+C) |
