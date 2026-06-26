# SNBT Localizer - AI Development Guide

## Project Mission & Stack
High-quality, production-grade Minecraft SNBT quest localizer. Tech stack: Python 3.10+, PyQt6, httpx, aiofiles, sqlite3.

## Architecture Map
- core.py: Core translation logic, SNBT processing, caching
- gui.py: PyQt6-based graphical user interface
- main.py: CLI entrypoint (snbt-tr) with argument parsing

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
