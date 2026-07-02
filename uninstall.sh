#!/usr/bin/env bash

DESKTOP_FILE="$HOME/.local/share/applications/snbt-ai-localizer.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/snbt-ai-localizer.svg"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Uninstalling SNBT AI Localizer..."

rm -f "$DESKTOP_FILE"
rm -f "$ICON_FILE"

if [ -d "$APP_DIR/.venv" ]; then
    echo "Removing virtual environment..."
    rm -rf "$APP_DIR/.venv"
fi

CACHE_DIR="$HOME/.snbt_localizer"
if [ -d "$CACHE_DIR" ]; then
    echo "Removing cache and logs..."
    rm -rf "$CACHE_DIR"
fi

if [ -d "$HOME/.config/MineAI" ]; then
    echo "Removing QSettings configuration..."
    rm -rf "$HOME/.config/MineAI"
fi

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "SUCCESS: All files, cache, logs, and settings have been removed cleanly."
