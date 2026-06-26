#!/usr/bin/env bash
# SNBT-AI-Localizer Automated Installer

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$DESKTOP_DIR"
mkdir -p "$ICON_DIR"

echo "Installing SNBT AI Localizer..."

# 1. Создаем красивую системную SVG-иконку (книга квестов с символом перевода)
cat << 'SVG' > "$ICON_DIR/snbt-ai-localizer.svg"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="14" fill="#111216"/>
  <circle cx="32" cy="32" r="22" fill="none" stroke="#306fcb" stroke-width="2" opacity="0.6"/>
  <path d="M18 20 C18 16, 32 16, 32 20 L32 48 C32 44, 18 44, 18 48 Z" fill="#171920" stroke="#9ba1b0" stroke-width="1.5"/>
  <path d="M46 20 C46 16, 32 16, 32 20 L32 48 C32 44, 46 44, 46 48 Z" fill="#171920" stroke="#9ba1b0" stroke-width="1.5"/>
  <path d="M32 20 L32 48" stroke="#4a8df8" stroke-width="2"/>
  <path d="M22 28 L26 38 M25 35 L29 35" stroke="#e3e6ed" stroke-width="1.5" stroke-linecap="round"/>
  <text x="36" y="37" font-family="sans-serif" font-size="10" font-weight="bold" fill="#4a8df8">文</text>
</svg>
SVG

# 2. Проверяем и создаем виртуальное окружение
[ -d "$APP_DIR/.venv" ] || {
    echo "Creating Python Virtual Environment..."
    python -m venv "$APP_DIR/.venv"
}

echo "Installing and upgrading dependencies..."
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install PyQt6 httpx

# 3. Динамически генерируем системный .desktop файл ярлыка
cat << DE_EOF > "$DESKTOP_DIR/snbt-ai-localizer.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=SNBT AI Localizer
Comment=Translate Minecraft FTB Quests (*.snbt) using AI Providers
Exec=$APP_DIR/.venv/bin/python $APP_DIR/gui.py
Icon=snbt-ai-localizer
Terminal=false
Categories=Utility;Development;Game;
StartupNotify=true
DE_EOF

chmod +x "$DESKTOP_DIR/snbt-ai-localizer.desktop"

echo "Updating system desktop database..."
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "SUCCESS: SNBT AI Localizer successfully integrated into system menu!"
