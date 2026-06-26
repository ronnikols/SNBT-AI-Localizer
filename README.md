# SNBT AI Localizer

**English** | [Русский](README.ru.md)

An advanced, asynchronous packet localizer for Minecraft FTB Quests files (`.snbt`). Built with a modern, Wayland-ready PyQt6 interface and powered by multiple local and cloud translation engines.

### How to Launch

1. Open your terminal in the project directory.
2. Activate your virtual environment and run the application:
   ./.venv/bin/python gui.py

### Key Features

- **Multi-Provider Support**: Translate using local LLMs via **Ollama** (e.g., Gemma 2, Qwen 2.5), **Groq Cloud**, **OpenRouter**, **Google Gemini**, or completely free **Google Translate**.
- **Minecraft Tag Protection**: Programmatic shielding of technical Minecraft tags (e.g., `#c:ender_pearl_dusts` or `#forge:ingots`) and formatting codes (`&c`, `&r`) so they never get translated or corrupted.
- **Smart Comparison & Backups**: Treats `.snbt.bak` files as pristine English baselines, enabling smart incremental translations (Complement policy) and clean resets (Overwrite policy) without Cyrillic translation loops.
- **Local SQLite Caching**: Save translations in real-time to avoid duplicate API requests and lower costs.
- **Wayland/Hyprland Ready**: Styled with PyQt6 Fusion engine and native palettes, completely bypassing system icon issues.
