#!/usr/bin/env bash
# SNBT-AI-Localizer Uninstaller

DESKTOP_FILE="$HOME/.local/share/applications/snbt-ai-localizer.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/snbt-ai-localizer.svg"

echo "Uninstalling SNBT AI Localizer shortcuts..."

rm -f "$DESKTOP_FILE"
rm -f "$ICON_FILE"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "SUCCESS: Shortcuts and system integrations have been removed cleanly."
