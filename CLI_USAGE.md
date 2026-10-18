# SNBT Localizer — CLI

```
snbt-tr [options]
```

Without flags in a terminal the CLI opens the interactive wizard (instance → provider → key → model → language).
Without a terminal (desktop launcher) it opens the GUI. Settings are shared with the GUI (QSettings `MineAI/SNBT-Localizer`).
Output is colored via `rich`; `--no-color` or `NO_COLOR=1` gives plain text.

## General
| Flag | Description |
|------|-------------|
| `-h, --help` | Help |
| `--version` | Print version |
| `--gui` | Launch the GUI |
| `--debug` | Debug logs in the console (file log: `~/.snbt_localizer/logs/app.log`) |
| `--no-color` | Plain output |
| `-y, --yes` | Assume yes for confirmations |

## Translation
| Flag | Description |
|------|-------------|
| `-p, --provider` | Provider alias (table below) |
| `-m, --model` | Model; `key\model` pairs are accepted in `-k` for Mixed |
| `-k, --key` | API key(s), comma-separated (fallback: env, saved pool) |
| `-l, --lang` | Language: `ru`, `uk`, `ru_ru` or `Russian` |
| `-d, --dir` | Modpack / quests dir or instance name |
| `-c, --context` | Custom translation context |
| `--policy` | `complement` / `overwrite` / `skip` |
| `--mix` | Mixed Providers: all saved key pools |
| `--fastdir, --fd` | Pick an instance and translate with saved settings |
| `-r, --resource-pack` | Resource Pack mode for KubeJS lang files |
| `--dry-run` | Show the files that would be translated; never writes settings |
| `--no-titles / --no-subs / --no-desc` | Skip titles / subtitles / descriptions (GUI checkboxes) |

## Advanced
| Flag | Description |
|------|-------------|
| `--concurrency N` | Parallel files 1-10 |
| `--batch-size N`, `--min-batch-size N` | Strings per request / minimum before failing |
| `--max-concurrent-requests N` | Max concurrent API requests |
| `--temperature T` | 0.0-2.0 |
| `--base-url URL` | Base URL for Custom / Ollama |
| `--utility-provider`, `--utility-model` | Model for the glossary pre-scan |

## Quality audit (QA)
| Flag | Description |
|------|-------------|
| `--qa / --no-qa` | Enable / disable the judge pass for this run (not saved) |
| `--qa-provider`, `--qa-model` | Judge provider / model for this run |

Judges and jury threshold are configured in the GUI (Settings → QA) and are used by the CLI as-is.

## Tools
| Flag | Description |
|------|-------------|
| `--list-models` | Models of the provider |
| `--verify-keys` | Test keys (+ QA judges), show balance |
| `--cache stats` | Translation memory size |
| `--cache list [--modpack M] [--limit N]` | Browse records |
| `--cache search --search TEXT` | Search originals / translations |
| `--cache autofix` | Repair broken records |
| `--cache heal` | Find wrong-script translations and re-translate them |
| `--cache clear`, `--clear-cache` | Clear the cache (asks unless `-y`) |

## Provider aliases
`google`, `gemini`, `ollama`, `groq`, `openrouter`, `nvidia`/`nim`, `sambanova`, `opencode`, `openai`, `mistral`,
`anthropic`/`claude`, `cohere`, `local`/`custom`, `crusoe`, `runinfra`, `shisa`, `corvex`, `mixed`/`mix`.

## Languages
`ru`, `uk`, `en`, `es`, `zh`, `zh-tw`, `de`, `fr`, `pt`, `ja`, `ko`.

## Examples
```bash
snbt-tr                                   # wizard
snbt-tr --fd                              # pick instance, saved settings
snbt-tr -d "Vortex 1.1.2b" -p groq -m llama-3.3-70b-versatile -l uk
snbt-tr --mix -d ~/modpack -k "gsk_...,nvapi-...\meta/llama-3.3-70b-instruct"
snbt-tr --fd --dry-run --no-desc
snbt-tr -p corvex --verify-keys
snbt-tr --cache search --search "Iron Ingot"
snbt-tr --cache heal
```

## Exit codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid argument, path, keys or translation error |
| 130 | Interrupted (Ctrl+C) |
