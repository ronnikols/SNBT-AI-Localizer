import os
import sys
import re
import asyncio
import time
import logging
import weakref
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLineEdit, 
                             QTextEdit, QLabel, QComboBox, QListView, QCheckBox, 
                             QCompleter, QStyleFactory, QProgressBar, QMessageBox,
                             QSpinBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
                             QTabWidget, QHeaderView)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt, QStringListModel, QObject, QTimer, pyqtSlot
from PyQt6.QtGui import QPalette, QColor, QKeySequence, QShortcut
import httpx
from core import SNBTManager, EXCLUDED_DIRS, AbortException, parse_target_lang, TranslationCache, UnifiedTranslator, is_valid_custom_instance, PROVIDER_DEFAULTS
from config import ConfigManager

def find_all_quest_dirs(instance_path: Path) -> list[Path]:
    """Find all quests directories within an instance path."""
    quest_dirs = []
    MAX_DEPTH = 3

    # Standard locations
    standard_paths = [
        instance_path / "config" / "ftbquests" / "quests",
        instance_path / "minecraft" / "config" / "ftbquests" / "quests",
    ]
    for cp in standard_paths:
        if cp.exists() and cp.is_dir():
            quest_dirs.append(cp)

    # Recursive scan for other locations
    def scan(base: Path, depth: int = 0):
        if depth > MAX_DEPTH:
            return
        try:
            with os.scandir(base) as it:
                for entry in it:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name.startswith('.'):
                        continue
                    path = Path(entry.path)
                    if path.name == "quests" and path.parent.name == "ftbquests":
                        if path not in quest_dirs:
                            quest_dirs.append(path)
                    if depth < MAX_DEPTH:
                        scan(path, depth + 1)
        except (PermissionError, Exception):
            return

    scan(instance_path)
    if not quest_dirs and is_valid_custom_instance(instance_path):
        quest_dirs.append(instance_path)
    return quest_dirs

class QtLogSignaler(QObject):
    log_signal = pyqtSignal(str, int)

class QtLoggingHandler(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.signaler = QtLogSignaler()
        self.text_edit_ref = weakref.ref(text_edit)
        self.signaler.log_signal.connect(self._append_to_text_edit)
        self.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))

    def _append_to_text_edit(self, msg, level):
        text_edit = self.text_edit_ref()
        if text_edit is not None:
            text_edit.append(msg)

    def emit(self, record):
        if record.levelno >= logging.INFO:
            msg = self.format(record)
            self.signaler.log_signal.emit(msg, record.levelno)

STYLE_SHEET = """
QMainWindow {
    background-color: #111216;
}
QLabel {
    font-weight: 600;
    color: #9ba1b0;
    margin-bottom: 2px;
}
QLineEdit {
    background-color: #171920;
    border: 1px solid #2b2f3d;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f2f4f8;
}
QLineEdit:focus {
    border: 1px solid #4a8df8;
}
QLineEdit:disabled {
    background-color: #14151a;
    color: #4b5263;
    border: 1px solid #1c1e24;
}
QListView {
    background-color: #171920;
    border: 1px solid #2b2f3d;
    color: #f2f4f8;
}
QTextEdit {
    background-color: #0b0c10;
    border: 1px solid #1c1e24;
    border-radius: 6px;
    font-family: 'Fira Code', 'Consolas', 'Courier New', monospace;
    color: #a0a8b6;
    padding: 10px;
}
QProgressBar {
    background-color: #171920;
    border: 1px solid #2b2f3d;
    border-radius: 6px;
    text-align: center;
    color: #f2f4f8;
    font-weight: bold;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #306fcb;
    border-radius: 5px;
}

QPushButton {
    background-color: #1a1c23;
    border: 1px solid #2b2f3d;
    border-radius: 6px;
    padding: 10px 16px;
    color: #e3e6ed;
    font-weight: 600;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #232731;
    border: 1px solid #4a8df8;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #171920;
    border: 1px solid #306fcb;
}
QPushButton:disabled {
    background-color: #14151a;
    color: #4b5263;
    border: 1px solid #1c1e24;
}
QPushButton#btn_run {
    background-color: #111e38;
    border: 1px solid #306fcb;
    color: #38bdf8;
}
QPushButton#btn_run:hover {
    background-color: #306fcb;
    border: 1px solid #4a8df8;
    color: #ffffff;
}
QPushButton#btn_run:pressed {
    background-color: #1d4ed8;
    border: 1px solid #1d4ed8;
}
QPushButton#btn_show_key {
    max-width: 60px;
    font-size: 16px;
    padding: 6px 12px;
}
"""

def load_key_from_env_or_file(provider, env_cache=None):
    if "Gemini" in provider:
        var_name = "GEMINI_API_KEY"
        val = os.getenv(var_name)
        if val:
            return val
        if env_cache is not None and var_name in env_cache:
            return env_cache[var_name]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value(var_name.lower(), "")
        return str(saved_val) if saved_val else ""
    elif "Groq" in provider:
        var_name = "GROQ_API_KEY"
        val = os.getenv(var_name)
        if val:
            return val
        if env_cache is not None and var_name in env_cache:
            return env_cache[var_name]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value(var_name.lower(), "")
        return str(saved_val) if saved_val else ""
    elif "OpenRouter" in provider:
        var_name = "OPENROUTER_API_KEY"
        val = os.getenv(var_name)
        if val:
            return val
        if env_cache is not None and var_name in env_cache:
            return env_cache[var_name]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value(var_name.lower(), "")
        return str(saved_val) if saved_val else ""
    elif "NVIDIA NIM" in provider:
        val = os.getenv("NVIDIA_API_KEY")
        if val:
            return val
        if env_cache is not None and "NVIDIA_API_KEY" in env_cache:
            return env_cache["NVIDIA_API_KEY"]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value("nvidia_api_key", "")
        if saved_val:
            return str(saved_val)
                
        val = os.getenv("NVIDIA_NIM_API_KEY")
        if val:
            return val
        if env_cache is not None and "NVIDIA_NIM_API_KEY" in env_cache:
            return env_cache["NVIDIA_NIM_API_KEY"]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value("nvidia_nim_api_key", "")
        return str(saved_val) if saved_val is not None else ""
    elif "Sambanova" in provider:
        val = os.getenv("SAMBANOVA_API_KEY")
        if val:
            return val
        if env_cache is not None and "SAMBANOVA_API_KEY" in env_cache:
            return env_cache["SAMBANOVA_API_KEY"]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value("sambanova_api_key", "")
        return str(saved_val) if saved_val is not None else ""
    elif "OpenAI" in provider:
        var_name = "OPENAI_API_KEY"
        val = os.getenv(var_name)
        if val:
            return val
        if env_cache is not None and var_name in env_cache:
            return env_cache[var_name]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value(var_name.lower(), "")
        return str(saved_val) if saved_val else ""
    elif "Mistral" in provider:
        var_name = "MISTRAL_API_KEY"
        val = os.getenv(var_name)
        if val:
            return val
        if env_cache is not None and var_name in env_cache:
            return env_cache[var_name]
        settings = QSettings("MineAI", "SNBT-Localizer")
        saved_val = settings.value(var_name.lower(), "")
        return str(saved_val) if saved_val else ""
    else:
        return ""

def detect_instances() -> tuple[dict, dict]:
    detected = {}
    quest_dirs_mapping = {}
    home = Path.home()
    MAX_DEPTH = 3

    paths = []
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        localappdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        userprofile = Path(os.environ.get("USERPROFILE", home))

        paths.append((appdata / "PrismLauncher/instances", "Prism Launcher"))
        paths.append((appdata / "ElyPrismLauncher/instances", "ElyPrismLauncher"))
        paths.append((appdata / "MultiMC/instances", "MultiMC"))
        paths.append((localappdata / "ModrinthApp/profiles", "Modrinth App"))
        paths.append((userprofile / "curseforge/minecraft/Instances", "CurseForge"))
        paths.append((appdata / ".minecraft", "TLauncher/Vanilla"))
    else:
        paths.append((home / ".local/share/PrismLauncher/instances", "Prism Launcher"))
        paths.append((home / ".local/share/ElyPrismLauncher/instances", "ElyPrismLauncher"))
        paths.append((home / ".local/share/MultiMC/instances", "MultiMC"))
        paths.append((home / ".local/share/modrinthapp/profiles", "Modrinth App"))
        paths.append((home / "Documents/CurseForge/Minecraft/Instances", "CurseForge"))
        paths.append((home / ".var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances", "Prism Launcher (Flatpak)"))
        paths.append((home / ".minecraft", "TLauncher/Vanilla"))

    def get_quest_title(quests_dir: Path, fallback: str) -> str:
        data_file = quests_dir / "data.snbt"
        if data_file.exists():
            try:
                content = data_file.read_text("utf-8")
                match = re.search(r'title:\s*"([^"]+)"', content)
                if match:
                    return match.group(1)
            except Exception:
                pass
        return fallback

    for base_path, launcher_name in paths:
        if not base_path.exists():
            continue

        if launcher_name != "TLauncher/Vanilla":
            try:
                with os.scandir(base_path) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                            instance_path = Path(entry.path)
                            quest_dirs = find_all_quest_dirs(instance_path)
                            if quest_dirs:
                                title = get_quest_title(quest_dirs[0], instance_path.name)
                                title = re.sub(r'&[0-9a-fA-Fk-orK-OR]', '', title)
                                display_name = f"{title} [{instance_path.name}] ({launcher_name})"
                                if len(quest_dirs) > 1:
                                    display_name += " [Multiple Folders]"
                                detected[display_name] = instance_path
                                quest_dirs_mapping[instance_path] = quest_dirs
            except Exception:
                pass
        else:
            cp = base_path / "config" / "ftbquests" / "quests"
            if cp.exists() and cp.is_dir():
                title = get_quest_title(cp, "Active Pack")
                title = re.sub(r'&[0-9a-fA-Fk-orK-OR]', '', title)
                display_name = f"{title} (TLauncher/Vanilla)"
                detected[display_name] = base_path
                quest_dirs_mapping[base_path] = [cp]

            versions_path = base_path / "versions"
            if versions_path.exists() and versions_path.is_dir():
                try:
                    with os.scandir(versions_path) as it:
                        for entry in it:
                            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                                instance_path = Path(entry.path)
                                quest_dirs = find_all_quest_dirs(instance_path)
                                if quest_dirs:
                                    title = get_quest_title(quest_dirs[0], instance_path.name)
                                    title = re.sub(r'&[0-9a-fA-Fk-orK-OR]', '', title)
                                    display_name = f"{title} [{instance_path.name}] (TLauncher Version)"
                                    if len(quest_dirs) > 1:
                                        display_name += " [Multiple Folders]"
                                    detected[display_name] = instance_path
                                    quest_dirs_mapping[instance_path] = quest_dirs
                except Exception:
                    pass
    return detected, quest_dirs_mapping

class TranslationMemoryTab(QWidget):
    language_changed = pyqtSignal(str)

    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.db_path = cache.db_path
        self.pending_updates = {}
        self.pending_deletions = set()
        self.offset = 0
        self.limit = 500
        self.search_timer = QTimer()
        self.search_timer.setInterval(300)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_search)
        self.setup_ui()
        self._load_data()
        self.refresh_modpack_filter()

    def setup_ui(self):
        layout = QVBoxLayout()
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by original or translation...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)

        self.lang_filter = QComboBox()
        self.lang_filter.addItems([
            "Russian (ru_ru)", "Spanish (es_es)", "Chinese Simplified (zh_cn)",
            "Chinese Traditional (zh_tw)", "German (de_de)", "French (fr_fr)",
            "Portuguese (pt_br)", "Japanese (ja_jp)", "Korean (ko_kr)"
        ])
        self.lang_filter.currentTextChanged.connect(self._on_lang_filter_changed)
        search_layout.addWidget(self.lang_filter)

        self.modpack_filter = QComboBox()
        self.modpack_filter.addItem("All Modpacks")
        self.modpack_filter.currentTextChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self.modpack_filter)

        layout.addLayout(search_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Original", "Translation", "Modpack", "Added"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)

        layout.addWidget(self.table)

        button_layout = QHBoxLayout()
        self.load_more_btn = QPushButton("Load More")
        self.load_more_btn.clicked.connect(self._on_load_more)
        button_layout.addWidget(self.load_more_btn)

        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.clicked.connect(self._on_delete_selected)
        button_layout.addWidget(self.delete_selected_btn)

        self.save_changes_btn = QPushButton("Save Changes")
        self.save_changes_btn.clicked.connect(self._on_save_changes)
        button_layout.addWidget(self.save_changes_btn)

        self.clear_cache_btn = QPushButton("Clear Cache")
        self.clear_cache_btn.clicked.connect(self._on_clear_cache)
        button_layout.addWidget(self.clear_cache_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _on_search_changed(self):
        self.search_timer.start()

    def _on_filter_changed(self):
        self.offset = 0
        self._load_data()

    def _perform_search(self):
        self.offset = 0
        self._load_data()

    def _load_data(self):
        self.load_more_btn.setEnabled(False)
        search_term = self.search_input.text()
        modpack = self.modpack_filter.currentText()
        modpack_filter = modpack if modpack != "All Modpacks" else None
        records = self.cache.get_all_records(search_term, self.limit, self.offset, modpack_filter)
        self._populate_table(records, append=(self.offset > 0))
        self.load_more_btn.setEnabled(len(records) == self.limit)

    def _populate_table(self, records, append=False):
        self.table.blockSignals(True)
        if not append:
            self.table.setRowCount(0)
            self.pending_updates.clear()
            self.pending_deletions.clear()

        for orig, trans, modpack, created_at in records:
            row = self.table.rowCount()
            self.table.insertRow(row)

            orig_item = QTableWidgetItem(orig)
            orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, orig_item)

            trans_item = QTableWidgetItem(trans)
            self.table.setItem(row, 1, trans_item)

            modpack_item = QTableWidgetItem(modpack if modpack else "Global")
            modpack_item.setFlags(modpack_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, modpack_item)

            created_item = QTableWidgetItem(created_at if created_at else "")
            created_item.setFlags(created_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, created_item)
        self.table.blockSignals(False)

    def _on_item_changed(self, item):
        if item.column() == 1:
            row = item.row()
            orig_item = self.table.item(row, 0)
            if orig_item:
                orig_text = orig_item.text()
                self.pending_updates[orig_text] = item.text()

    def _on_delete_selected(self):
        selected_items = self.table.selectedItems()
        selected_rows = sorted(list(set(item.row() for item in selected_items)), reverse=True)
        for row in selected_rows:
            orig_item = self.table.item(row, 0)
            if orig_item:
                orig_text = orig_item.text()
                self.pending_deletions.add(orig_text)
                if orig_text in self.pending_updates:
                    del self.pending_updates[orig_text]
            self.table.removeRow(row)

    def _on_save_changes(self):
        if self.pending_updates:
            self.cache.update_records(self.pending_updates)
            self.pending_updates.clear()
        if self.pending_deletions:
            self.cache.delete_records(list(self.pending_deletions))
            self.pending_deletions.clear()
        self._load_data()

    def _on_load_more(self):
        self.offset += self.limit
        self._load_data()

    def _confirm_clear_cache(self):
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Are you sure you want to clear the translation cache?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes

    def _on_clear_cache(self):
        if self._confirm_clear_cache():
            try:
                self.cache.clear()
                self.offset = 0
                self.pending_updates.clear()
                self.pending_deletions.clear()
                self._load_data()
                self.refresh_modpack_filter()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cache clear error: {e}")

    def _on_lang_filter_changed(self, lang_text):
        lang_name, lang_code = parse_target_lang(lang_text)
        self.set_language_code(lang_code)
        self.language_changed.emit(lang_text)

    def set_language_code(self, lang_code):
        self.cache.close()
        self.cache = TranslationCache(db_path=self.db_path, target_lang_code=lang_code)
        self.offset = 0
        self.refresh_modpack_filter()
        self._load_data()

    def refresh_modpack_filter(self):
        self.modpack_filter.blockSignals(True)
        self.modpack_filter.clear()
        self.modpack_filter.addItem("All Modpacks")
        modpacks = self.cache.get_unique_modpacks()
        self.modpack_filter.addItems(modpacks)
        self.modpack_filter.blockSignals(False)

class ModelLoader(QThread):
    loaded = pyqtSignal(list, str, int, str)
    def __init__(self, provider, api_key=None, loader_id=0):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.loader_id = loader_id

    def run(self):
        asyncio.run(self.fetch())

    async def fetch(self):
        models = []
        error_msg = ""
        try:
            async with httpx.AsyncClient() as client:
                if "OpenRouter" in self.provider:
                    resp = await client.get("https://openrouter.ai/api/v1/models", timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"OpenRouter API error {resp.status_code}: Invalid or missing API key"
                elif "Groq" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Groq API error {resp.status_code}: Invalid or missing API key"
                elif "Gemini" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://generativelanguage.googleapis.com/v1beta/openai/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Gemini API error {resp.status_code}: Invalid or missing API key"
                elif "Ollama" in self.provider:
                    resp = await client.get("http://localhost:11434/v1/models", timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Ollama API error {resp.status_code}: Authentication required"
                elif "NVIDIA NIM" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://integrate.api.nvidia.com/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"NVIDIA NIM API error {resp.status_code}: Invalid or missing API key"
                elif "Sambanova" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://api.sambanova.ai/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Sambanova API error {resp.status_code}: Invalid or missing API key"
                elif "OpenAI" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://api.openai.com/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"OpenAI API error {resp.status_code}: Invalid or missing API key"
                elif "Mistral" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://api.mistral.ai/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Mistral API error {resp.status_code}: Invalid or missing API key"
                elif "Anthropic" in self.provider and self.api_key:
                    headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
                    resp = await client.get("https://api.anthropic.com/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Anthropic API error {resp.status_code}: Invalid or missing API key"
                elif "Cohere" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get("https://api.cohere.ai/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("models", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Cohere API error {resp.status_code}: Invalid or missing API key"
        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
        self.loaded.emit(models, error_msg, self.loader_id, self.provider)

class KeyVerifierWorker(QThread):
    verification_complete = pyqtSignal(dict)

    def __init__(self, keys, provider, model, translator):
        super().__init__()
        self.keys = keys
        self.provider = provider
        self.model = model
        self.translator = translator

    def run(self):
        results = {}
        for key in self.keys:
            status = asyncio.run(self.translator.ping_key(key, self.provider, self.model))
            results[key] = status
        self.verification_complete.emit(results)

class Worker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal()
    progress_batch = pyqtSignal(int, int)
    chunk_progress = pyqtSignal(int, int, int, int)
    lines_translated = pyqtSignal(int, int)
    progress_state = pyqtSignal(int, int, str, int, int, float)

    def __init__(self, files, keys, provider, model, t_titles, t_subs, t_desc, custom_context="", policy="Complement (Дополнить)", target_lang="Russian (ru_ru)", concurrency=3, mixed_pool=None, batch_size=50, min_batch_size=1, max_concurrent_requests=10, modpack=None, custom_base_url=None):
        super().__init__()
        self.files = files
        self.keys = keys
        self.provider = provider
        self.model = model
        self.t_titles = t_titles
        self.t_subs = t_subs
        self.t_desc = t_desc
        self.custom_context = custom_context
        self.policy = policy
        self.target_lang = target_lang
        self.concurrency = concurrency
        self.mixed_pool = mixed_pool
        self.batch_size = batch_size
        self.min_batch_size = min_batch_size
        self.max_concurrent_requests = max_concurrent_requests
        self.modpack = modpack
        self.custom_base_url = custom_base_url
        self.is_aborted = False
        self.is_paused = False
        self._total_strings = 0
        self._completed_strings = 0
        self._ema_speed = None
        self._files_last_time = {}
        self._files_last_strings = {}

    def run(self):
        try:
            asyncio.run(self.process())
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            logging.getLogger("snbt_localizer.gui").error(f"Unexpected error: {e}")
        finally:
            self.done.emit()

    async def check_status(self):
        while self.is_paused:
            await asyncio.sleep(0.1)
        if self.is_aborted:
            raise AbortException()

    def handle_batch_progress(self, idx, total_files, filename, chunk_idx, total_chunks, strings_done=0):
        duration = time.time() - self._files_last_time.get(idx, time.time())
        strings_in_batch = strings_done - self._files_last_strings.get(idx, 0)

        if duration > 0 and strings_in_batch > 0:
            current_speed = duration / strings_in_batch
            if self._ema_speed is None:
                self._ema_speed = current_speed
            else:
                self._ema_speed = (0.2 * current_speed) + (0.8 * self._ema_speed)
            self._ema_speed = max(self._ema_speed, 0.05)

        self._completed_strings += strings_in_batch
        remaining_strings = max(0, self._total_strings - self._completed_strings)
        eta_seconds = remaining_strings * self._ema_speed if self._ema_speed is not None else 0

        self.progress_state.emit(idx, total_files, filename, self._completed_strings, self._total_strings, eta_seconds)
        self._files_last_time[idx] = time.time()
        self._files_last_strings[idx] = strings_done

        self.chunk_progress.emit(idx, total_files, chunk_idx, total_chunks)

    async def process(self):
        if not self.files:
            self.log.emit("No files to process.")
            return

        target_lang_name, target_lang_code = parse_target_lang(self.target_lang)
        first_key = self.keys[0] if self.keys else ""
        m = SNBTManager(
            first_key,
            self.provider,
            self.model,
            self.custom_context,
            target_lang_name,
            target_lang_code,
            concurrency_limit=self.concurrency,
            mixed_pool=self.mixed_pool,
            batch_size=self.batch_size,
            min_batch_size=self.min_batch_size,
            max_concurrent_requests=self.max_concurrent_requests,
            modpack=self.modpack,
            custom_base_url=self.custom_base_url
        )

        total_lines = 0
        for f in self.files:
            total_lines += m.count_translatable_strings(f, self.t_titles, self.t_subs, self.t_desc)

        self._total_strings = total_lines
        self._completed_strings = 0
        self._ema_speed = None
        self._files_last_time = {}
        self._files_last_strings = {}

        total_files = len(self.files)
        completed_count = 0
        completed_lines = 0
        self.progress_batch.emit(0, total_files)

        sem = asyncio.Semaphore(self.concurrency)
        lock = asyncio.Lock()
        batch_start = time.time()

        async def process_one(idx, f):
            nonlocal completed_lines, completed_count
            async with sem:
                await self.check_status()
                self.log.emit(f"Processing: {f.name}")
                logging.getLogger("snbt_localizer.gui").info(f"Processing: {f.name}")
                file_total_strings = m.count_translatable_strings(f, self.t_titles, self.t_subs, self.t_desc)
                file_start = time.time()
                self._files_last_time[idx] = time.time()
                self._files_last_strings[idx] = 0
                m.is_aborted = self.is_aborted
                lines_processed = await m.process_file(
                    f, self.t_titles, self.t_subs, self.t_desc,
                    lambda x: self.log.emit(str(x)),
                    self.check_status,
                    self.policy,
                    progress_callback=lambda chunk_idx, total_chunks, strings_done=0, file_total=0: self.handle_batch_progress(idx, total_files, f.name, chunk_idx, total_chunks, strings_done)
                )
                accounted = self._files_last_strings.get(idx, 0)
                unaccounted = file_total_strings - accounted
                if unaccounted > 0:
                    self._completed_strings += unaccounted
                    self._files_last_strings[idx] = file_total_strings
                remaining_strings = max(0, self._total_strings - self._completed_strings)
                eta_seconds = remaining_strings * self._ema_speed if self._ema_speed is not None else 0
                self.progress_state.emit(idx, total_files, f.name, self._completed_strings, self._total_strings, eta_seconds)
                file_elapsed = time.time() - file_start
                self.log.emit(f"Done: {f.name} (took {file_elapsed:.1f}s)")
                logging.getLogger("snbt_localizer.gui").info(f"Done: {f.name} (took {file_elapsed:.1f}s)")
                async with lock:
                    completed_count += 1
                    self.progress_batch.emit(completed_count, total_files)

        try:
            tasks = [asyncio.create_task(process_one(idx, f)) for idx, f in enumerate(self.files)]
            await asyncio.gather(*tasks)
            self.progress_batch.emit(total_files, total_files)

            batch_elapsed = time.time() - batch_start
            mins = int(batch_elapsed // 60)
            secs = int(batch_elapsed % 60)
            if mins > 0:
                self.log.emit(f"Batch completed in {mins}m {secs}s.")
            else:
                self.log.emit(f"Batch completed in {secs}s.")
        except AbortException:
            self.log.emit("Translation process was aborted by user.")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            m.close()

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SNBT AI Localizer")
        self.resize(750, 680)
        self.setStyleSheet(STYLE_SHEET)
        
        self._is_initializing = True
        self.last_valid_index = 0
        self._key_validation_cache = {}
        self._translation_finished = False
        self.running_loaders = []
        self.current_loader_id = 0
        self.settings = QSettings("MineAI", "SNBT-Localizer")
        self.instance_quest_dirs = {}
        self.env_cache = self._load_env_cache()
        self.config = ConfigManager()
        self.config.prune_invalid_paths()
        self._is_updating_models = False
        self.current_provider = "RESERVED_INIT_STATE"
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._perform_debounced_save)
        self._pending_save_provider = None
        self.custom_base_url = ""
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(STYLE_SHEET)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        workspace_tab = QWidget()
        workspace_layout = QVBoxLayout()
        workspace_layout.setSpacing(12)
        workspace_layout.setContentsMargins(16, 16, 16, 16)

        selectors_layout = QHBoxLayout()
        selectors_layout.setSpacing(12)

        provider_layout = QVBoxLayout()
        provider_label = QLabel("API Provider")
        self.provider_box = QComboBox()
        self.provider_box.setView(QListView())
        self.provider_box.addItems([
            "Google Translate (Free)",
            "Google Gemini (Free API)",
            "Ollama (Local / Free)",
            "Groq Cloud (Fast)",
            "OpenRouter (Cloud AI)",
            "NVIDIA NIM",
            "Sambanova",
            "OpenAI",
            "Mistral AI",
            "Anthropic (Claude)",
            "Cohere",
            "Local LLM / Custom",
            "Mixed Providers"
        ])
        self.provider_box.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_box)
        selectors_layout.addLayout(provider_layout)

        model_layout = QVBoxLayout()
        model_label = QLabel("AI Model (Live Auto-suggest)")
        self.model_box = QComboBox()
        self.model_box.setView(QListView())
        self.model_box.setEditable(True)
        self.model_box.currentTextChanged.connect(self.on_model_changed)
        self.loader = None

        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.popup().setStyleSheet(STYLE_SHEET)
        self.model_box.setCompleter(self.completer)

        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_box)
        selectors_layout.addLayout(model_layout)

        workspace_layout.addLayout(selectors_layout)

        key_layout = QVBoxLayout()
        self.key_label = QLabel("API Access Keys (one per line, max 10)")

        self.btn_toggle_keys = QPushButton("▼ API Keys Pool")
        self.btn_toggle_keys.setCheckable(True)
        self.btn_toggle_keys.setObjectName("btn_show_key")
        self.btn_toggle_keys.setMinimumWidth(160)
        self.btn_toggle_keys.setStyleSheet("padding: 6px;")
        self.btn_toggle_keys.clicked.connect(self.toggle_key_pool)

        self.key_pool_edit = QTextEdit()
        self.key_pool_edit.setPlaceholderText("Enter up to 10 API keys, one per line")
        self.key_pool_edit.setMaximumHeight(120)
        self.key_pool_edit.setVisible(False)
        self.key_pool_edit.textChanged.connect(self.key_pool_changed)

        self.btn_test_keys = QPushButton("Test Keys")
        self.btn_test_keys.clicked.connect(self.verify_keys)
        self.lbl_key_status = QLabel("Pool Status: Unchecked")

        key_layout.addWidget(self.key_label)
        key_layout.addWidget(self.btn_toggle_keys)
        key_layout.addWidget(self.key_pool_edit)
        key_layout.addWidget(self.btn_test_keys)
        key_layout.addWidget(self.lbl_key_status)

        self.custom_url_label = QLabel("Custom API Base URL (for Local LLM):")
        self.custom_base_url_edit = QLineEdit()
        self.custom_base_url_edit.setPlaceholderText("e.g. http://localhost:8080/v1")
        self.custom_base_url_edit.setVisible(False)
        self.custom_url_label.setVisible(False)
        self.custom_base_url_edit.textChanged.connect(lambda: self.save_timer.start(500))

        key_layout.addWidget(self.custom_url_label)
        key_layout.addWidget(self.custom_base_url_edit)
        workspace_layout.addLayout(key_layout)

        context_layout = QVBoxLayout()
        context_label = QLabel("Custom Translation Context / Modpack Description")
        self.context_in = QLineEdit(placeholderText="e.g. Medieval RPG modpack with magic, technology, and dragons")
        self.context_in.setText(self.settings.value("custom_context", ""))
        context_layout.addWidget(context_label)
        context_layout.addWidget(self.context_in)
        workspace_layout.addLayout(context_layout)

        lang_layout = QVBoxLayout()
        lang_label = QLabel("Target Language (Format: Name (code))")
        self.lang_box = QComboBox()
        self.lang_box.setView(QListView())
        self.lang_box.setEditable(True)
        self.lang_box.addItems([
            "Russian (ru_ru)",
            "Spanish (es_es)",
            "Chinese Simplified (zh_cn)",
            "Chinese Traditional (zh_tw)",
            "German (de_de)",
            "French (fr_fr)",
            "Portuguese (pt_br)",
            "Japanese (ja_jp)",
            "Korean (ko_kr)"
        ])
        self.lang_box.setCurrentText(self.settings.value("target_lang", "Russian (ru_ru)"))
        self.lang_box.currentTextChanged.connect(self.on_lang_box_changed)
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_box)
        workspace_layout.addLayout(lang_layout)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        concurrency_layout = QVBoxLayout()
        concurrency_label = QLabel("Threads:")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        self.concurrency_spin.setValue(int(self.settings.value("concurrency_limit", 2)))
        self.concurrency_spin.valueChanged.connect(lambda: self.save_timer.start(500))
        concurrency_layout.addWidget(concurrency_label)
        concurrency_layout.addWidget(self.concurrency_spin)
        settings_row.addLayout(concurrency_layout)

        batch_layout = QVBoxLayout()
        batch_label = QLabel("Batch Size:")
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 500)
        self.batch_spin.setValue(int(self.settings.value("batch_size", 50)))
        self.batch_spin.valueChanged.connect(lambda: self.save_timer.start(500))
        batch_layout.addWidget(batch_label)
        batch_layout.addWidget(self.batch_spin)
        settings_row.addLayout(batch_layout)

        min_batch_layout = QVBoxLayout()
        min_batch_label = QLabel("Min Batch Size:")
        self.min_batch_spin = QSpinBox()
        self.min_batch_spin.setRange(1, 50)
        self.min_batch_spin.setValue(int(self.settings.value("min_batch_size", 1)))
        self.min_batch_spin.valueChanged.connect(lambda: self.save_timer.start(500))
        min_batch_layout.addWidget(min_batch_label)
        min_batch_layout.addWidget(self.min_batch_spin)
        settings_row.addLayout(min_batch_layout)

        max_requests_layout = QVBoxLayout()
        max_requests_label = QLabel("Max API Requests:")
        self.max_requests_spin = QSpinBox()
        self.max_requests_spin.setRange(1, 100)
        self.max_requests_spin.setValue(int(self.settings.value("max_concurrent_requests", 10)))
        self.max_requests_spin.valueChanged.connect(lambda: self.save_timer.start(500))
        max_requests_layout.addWidget(max_requests_label)
        max_requests_layout.addWidget(self.max_requests_spin)
        settings_row.addLayout(max_requests_layout)

        settings_row.addStretch()
        workspace_layout.addLayout(settings_row)

        policy_layout = QVBoxLayout()
        policy_label = QLabel("Existing Localized Files Policy")
        self.policy_box = QComboBox()
        self.policy_box.setView(QListView())
        self.policy_box.addItems([
            "Complement",
            "Full Overwrite",
            "Skip / Nothing"
        ])
        self.policy_box.setCurrentText(self.settings.value("policy", "Complement"))
        policy_layout.addWidget(policy_label)
        policy_layout.addWidget(self.policy_box)
        workspace_layout.addLayout(policy_layout)

        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(20)
        self.cb_titles = QCheckBox("Translate Titles")
        self.cb_titles.setChecked(True)
        self.cb_subs = QCheckBox("Translate Subtitles")
        self.cb_subs.setChecked(True)
        self.cb_desc = QCheckBox("Translate Descriptions")
        self.cb_desc.setChecked(True)
        filters_layout.addWidget(self.cb_titles)
        filters_layout.addWidget(self.cb_subs)
        filters_layout.addWidget(self.cb_desc)
        workspace_layout.addLayout(filters_layout)

        dir_layout = QVBoxLayout()
        dir_label = QLabel("Target Modpack / Directory")
        self.dir_box = QComboBox()
        self.dir_box.setView(QListView())
        self.dir_box.currentIndexChanged.connect(self.dir_box_changed)

        self.lbl_file_count = QLabel("")
        self.lbl_file_count.setStyleSheet("color: #4a8df8; font-weight: normal; margin-top: 5px; margin-bottom: 5px; font-size: 11px;")

        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_box)
        dir_layout.addWidget(self.lbl_file_count)
        workspace_layout.addLayout(dir_layout)

        self.pb_batch = QProgressBar()
        self.pb_batch.setFormat("Total Progress: %v / %m files")
        self.pb_batch.setValue(0)
        workspace_layout.addWidget(self.pb_batch)

        self.out = QTextEdit(readOnly=True)
        workspace_layout.addWidget(self.out)

        control_layout = QHBoxLayout()
        self.btn_run = QPushButton("Start Batch Translation")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self.start)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.clicked.connect(self.pause)
        self.btn_pause.setEnabled(False)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)

        self.btn_clear = QPushButton("Clear Log")
        self.btn_clear.clicked.connect(self.out.clear)

        control_layout.addWidget(self.btn_run)
        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_clear)
        workspace_layout.addLayout(control_layout)

        workspace_tab.setLayout(workspace_layout)
        self.tabs.addTab(workspace_tab, "Workspace")

        saved_lang = self.settings.value("target_lang", "Russian (ru_ru)")
        lang_name, lang_code = parse_target_lang(saved_lang)
        self.translation_memory_tab = TranslationMemoryTab(TranslationCache(target_lang_code=lang_code))
        self.translation_memory_tab.language_changed.connect(self.on_tm_language_changed)
        self.tabs.addTab(self.translation_memory_tab, "Translation Memory")

        self.setCentralWidget(self.tabs)
        saved_geometry = self.settings.value("geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        self.load_saved_settings()
        self.populate_instances()
        self.current_provider = "INIT_STATE"
        self._is_initializing = False
        self.on_provider_changed(self.provider_box.currentText())
        self.log_cache_stats()

        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.shortcut_copy.activated.connect(self.copy_logs)

        gui_logger = logging.getLogger("snbt_localizer")
        gui_logger.setLevel(logging.DEBUG)
        gui_logger.handlers.clear()
        gui_handler = QtLoggingHandler(self.out)
        gui_handler.setLevel(logging.INFO)
        gui_logger.addHandler(gui_handler)
        gui_logger.propagate = False

    def on_lang_box_changed(self, lang_text):
        if self._is_initializing:
            return
        if not hasattr(self, 'translation_memory_tab'):
            return
        self.translation_memory_tab.lang_filter.blockSignals(True)
        self.translation_memory_tab.lang_filter.setCurrentText(lang_text)
        self.translation_memory_tab.lang_filter.blockSignals(False)
        lang_name, lang_code = parse_target_lang(lang_text)
        self.translation_memory_tab.set_language_code(lang_code)
        self.save_timer.start(500)

    def on_tm_language_changed(self, lang_text):
        if self._is_initializing:
            return
        self.lang_box.blockSignals(True)
        self.lang_box.setCurrentText(lang_text)
        self.lang_box.blockSignals(False)
        self.save_timer.start(500)

    def _on_tab_changed(self, index):
        if index == 1:
            self.translation_memory_tab.lang_filter.blockSignals(True)
            self.translation_memory_tab.lang_filter.setCurrentText(self.lang_box.currentText())
            self.translation_memory_tab.lang_filter.blockSignals(False)
            lang_name, lang_code = parse_target_lang(self.lang_box.currentText())
            self.translation_memory_tab.set_language_code(lang_code)
            self.translation_memory_tab.refresh_modpack_filter()
            self.translation_memory_tab._load_data()

    def _load_env_cache(self):
        cache = {}
        try:
            env_path = Path(".env")
            if env_path.exists():
                for line in env_path.read_text("utf-8").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        cache[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
        return cache

    def load_saved_settings(self):
        self.provider_box.blockSignals(True)
        self.dir_box.blockSignals(True)

        saved_provider = self.config.provider
        idx_p = self.provider_box.findText(saved_provider)
        if idx_p != -1:
            self.provider_box.setCurrentIndex(idx_p)

        self.cb_titles.setChecked(self.settings.value("cb_titles", "true") == "true")
        self.cb_subs.setChecked(self.settings.value("cb_subs", "true") == "true")
        self.cb_desc.setChecked(self.settings.value("cb_desc", "true") == "true")

        saved_model = self.config.model or ""
        if saved_model in ["", "Loading live models...", "None (Free Engine)"]:
            self.config.model = None
            self.saved_model = ""
        else:
            self.saved_model = saved_model

        saved_policy = self.settings.value("policy", "Complement")
        if saved_policy in ["Complement (Дополнить)", "Full Overwrite (Перезаписать)", "Skip / Nothing (Пропустить)"]:
            mapping = {
                "Complement (Дополнить)": "Complement",
                "Full Overwrite (Перезаписать)": "Full Overwrite",
                "Skip / Nothing (Пропустить)": "Skip / Nothing"
            }
            self.policy_box.setCurrentText(mapping.get(saved_policy, "Complement"))
        else:
            self.policy_box.setCurrentText(saved_policy)

        provider = self.config.provider
        saved_keys = self.config.get_api_keys(provider)
        if saved_keys:
            self.key_pool_edit.setPlainText("\n".join(saved_keys))

        self.custom_base_url_edit.setText(self.settings.value("custom_base_url", ""))
        self.custom_base_url = self.custom_base_url_edit.text()

        self.concurrency_spin.setValue(self.config.concurrency)
        self.batch_spin.setValue(self.config.batch_size)
        self.min_batch_spin.setValue(self.config.min_batch_size)
        self.max_requests_spin.setValue(self.config.max_concurrent_requests)

        self.provider_box.blockSignals(False)
        self.dir_box.blockSignals(False)

    def save_current_settings(self, provider_to_save: str = None):
        if self._is_updating_models and provider_to_save is None:
            return
        provider = provider_to_save or self.config.provider

        if provider_to_save is None:
            self.config.provider = self.provider_box.currentText()

        model_text = self.model_box.currentText()
        if model_text and model_text not in ["", "Loading live models...", "None (Free Engine)", "Defined per key in pool"]:
            self.config.model = model_text
            self.settings.setValue(f"model_{provider}", model_text)
        else:
            self.config.model = None

        self.settings.setValue("cb_titles", "true" if self.cb_titles.isChecked() else "false")
        self.settings.setValue("cb_subs", "true" if self.cb_subs.isChecked() else "false")
        self.settings.setValue("cb_desc", "true" if self.cb_desc.isChecked() else "false")

        self.config.custom_context = self.context_in.text().strip()
        self.config.target_lang = self.lang_box.currentText()

        policy_text = self.policy_box.currentText()
        self.config.policy = policy_text
        self.settings.setValue("policy", policy_text)

        self.custom_base_url = self.custom_base_url_edit.text()
        self.settings.setValue("custom_base_url", self.custom_base_url)

        if provider not in ("Google Translate (Free)", "Ollama (Local / Free)"):
            keys_text = self.key_pool_edit.toPlainText().strip()
            keys = [k.strip() for k in keys_text.splitlines() if k.strip()]
            self.config.set_api_keys(provider, keys)
        self.config.concurrency = self.concurrency_spin.value()
        self.config.batch_size = self.batch_spin.value()
        self.config.min_batch_size = self.min_batch_spin.value()
        self.config.max_concurrent_requests = self.max_requests_spin.value()
        self.config.save_to_settings()

    def populate_instances(self):
        self.dir_box.currentIndexChanged.disconnect()

        self.detected_instances, self.instance_quest_dirs = detect_instances()
        self.dir_box.clear()

        for custom_path in self.config.custom_instances_paths:
            p = Path(custom_path)
            if is_valid_custom_instance(p) and p not in self.detected_instances.values():
                name = f"{p.name} [Custom]"
                self.detected_instances[name] = p
                quest_dirs = find_all_quest_dirs(p)
                if quest_dirs:
                    self.instance_quest_dirs[p] = quest_dirs

        for name in sorted(self.detected_instances.keys()):
            self.dir_box.addItem(name, str(self.detected_instances[name]))
            
        self.dir_box.addItem("Select Folder Manually...", "MANUAL")
        
        last_path = self.settings.value("last_path", "")
        if last_path:
            found = False
            for i in range(self.dir_box.count()):
                if self.dir_box.itemData(i) == last_path:
                    self.dir_box.setCurrentIndex(i)
                    self.last_valid_index = i
                    found = True
                    break
            if not found:
                custom_name = f"Custom: {Path(last_path).name}"
                self.dir_box.insertItem(0, custom_name, last_path)
                self.dir_box.setCurrentIndex(0)
                self.last_valid_index = 0
        else:
            self.dir_box.setCurrentIndex(0)
            self.last_valid_index = 0
            
        self.dir_box.currentIndexChanged.connect(self.dir_box_changed)
        
        self.update_run_status()

    def dir_box_changed(self, index):
        if index < 0:
            return
        data = self.dir_box.itemData(index)
        
        if data == "MANUAL":
            self.dir_box.currentIndexChanged.disconnect()
            start_dir = self.settings.value("last_path", "")
            d = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
            
            if d:
                path_obj = Path(d)
                custom_name = f"{path_obj.name} [Custom]"

                quest_dirs = self.instance_quest_dirs.get(path_obj)
                if not quest_dirs:
                    quest_dirs = find_all_quest_dirs(path_obj)

                all_files = []
                if quest_dirs:
                    for qd in quest_dirs:
                        files = [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
                        all_files.extend(files)

                if is_valid_custom_instance(path_obj) and all_files:
                    self.config.add_custom_path(str(path_obj))
                    if quest_dirs:
                        self.instance_quest_dirs[path_obj] = quest_dirs

                exists_idx = -1
                for i in range(self.dir_box.count()):
                    if self.dir_box.itemData(i) == d:
                        exists_idx = i
                        break

                if exists_idx != -1:
                    self.dir_box.setCurrentIndex(exists_idx)
                    self.last_valid_index = exists_idx
                else:
                    self.dir_box.insertItem(0, custom_name, d)
                    self.dir_box.setCurrentIndex(0)
                    self.last_valid_index = 0

                self.settings.setValue("last_path", d)
                logging.getLogger("snbt_localizer.gui").info(f"Custom folder selected: {d}")

                # Populate quest_dirs for custom path
                path_obj = Path(d)
                quest_dirs = find_all_quest_dirs(path_obj)
                if quest_dirs:
                    self.instance_quest_dirs[path_obj] = quest_dirs
            else:
                self.dir_box.setCurrentIndex(self.last_valid_index)
                
            self.dir_box.currentIndexChanged.connect(self.dir_box_changed)
        else:
            self.last_valid_index = index
            self.settings.setValue("last_path", data)
            logging.getLogger("snbt_localizer.gui").info(f"Selected modpack path: {data}")
            
        self.update_run_status()

    def is_model_valid(self):
        model_text = self.model_box.currentText()
        provider = self.provider_box.currentText()
        if "Google Translate" in provider and model_text == "None (Free Engine)":
            return True
        return bool(model_text and model_text not in ["", "Loading live models...", "None (Free Engine)"])

    def update_run_status(self):
        path_str = self.dir_box.itemData(self.dir_box.currentIndex())
        has_files = False
        if path_str and path_str != "MANUAL" and os.path.exists(path_str):
            path = Path(path_str)
            quest_dirs = self.instance_quest_dirs.get(path)
            if not quest_dirs:
                quest_dirs = find_all_quest_dirs(path)

            all_files = []
            if quest_dirs:
                for qd in quest_dirs:
                    files = [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
                    all_files.extend(files)

            count = len(all_files)
            if count > 0:
                self.lbl_file_count.setText(f"✓ Detected: {count} quest files (.snbt)")
                has_files = True
                self.pb_batch.setRange(0, count)
                self.pb_batch.setValue(0)
            else:
                self.lbl_file_count.setText("⚠ Warning: No quest files (.snbt) found in this directory")
                self.pb_batch.setRange(0, 100)
                self.pb_batch.setValue(0)
        else:
            self.lbl_file_count.setText("")
            self.pb_batch.setRange(0, 100)
            self.pb_batch.setValue(0)

        self.btn_run.setEnabled(has_files and self.is_model_valid())

    def update_batch_progress(self, cur, tot):
        tot = max(1, tot)
        if hasattr(self, 'files_progress') and cur > 0:
            self.files_progress[cur - 1] = 1.0

    def update_chunk_progress(self, file_idx, total_files, chunk_idx, total_chunks):
        if hasattr(self, 'files_progress'):
            if total_chunks > 0:
                self.files_progress[file_idx] = chunk_idx / total_chunks
            else:
                self.files_progress[file_idx] = 0.0

    def update_lines_progress(self, completed: int, total: int):
        pass

    def update_progress_state(self, current_file_idx, total_files, current_file_name, completed_strings, total_strings, eta_seconds):
        if getattr(self, '_translation_finished', False):
            return
        self.pb_batch.setRange(0, 100)
        if total_strings > 0:
            progress_percent = int((completed_strings / total_strings) * 100)
            self.pb_batch.setValue(progress_percent)
            self.pb_batch.setFormat(f"File {current_file_idx}/{total_files}: {current_file_name} | Strings {completed_strings}/{total_strings} | ETA: {self.format_eta(eta_seconds)}")
        else:
            self.pb_batch.setValue(0)
            self.pb_batch.setFormat("Processing...")

    def format_eta(self, eta_seconds):
        if eta_seconds <= 0 or eta_seconds is None:
            return "--:--"
        minutes = int(eta_seconds // 60)
        seconds = int(eta_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _perform_debounced_save(self):
        provider = self._pending_save_provider
        self._pending_save_provider = None
        self.save_current_settings(provider_to_save=provider)

    def copy_logs(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.out.toPlainText())
        logging.getLogger("snbt_localizer.gui").info("--- Log content copied to clipboard ---")

    def log_cache_stats(self):
        try:
            size_mb, count = self.translation_memory_tab.cache.get_stats()
            logging.getLogger("snbt_localizer.gui").info(f"Cache stats: {size_mb:.2f} MB, {count} entries")
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Cache stats error: {e}")


    def toggle_key_pool(self, checked):
        if checked:
            self.key_pool_edit.setVisible(True)
            self.btn_toggle_keys.setText("▲ Hide Keys")
        else:
            self.key_pool_edit.setVisible(False)
            self.btn_toggle_keys.setText("▼ API Keys Pool")

    def verify_keys(self):
        provider = self.provider_box.currentText()
        model = self.model_box.currentText()
        keys_text = self.key_pool_edit.toPlainText().strip()
        keys = [k.strip() for k in keys_text.splitlines() if k.strip()]

        if provider in ("Google Translate (Free)", "Ollama (Local / Free)", "Local LLM / Custom"):
            results = {k: "Active" for k in keys} if keys else {}
            self.on_verification_complete(results)
            return

        if not keys:
            self.lbl_key_status.setText("Pool Status: No keys to verify")
            return

        self.lbl_key_status.setText("Pool Status: Verifying keys...")
        self.btn_test_keys.setEnabled(False)

        custom_url = self.custom_base_url_edit.text() if provider in ("Local LLM / Custom", "Ollama (Local / Free)") else None
        translator = UnifiedTranslator(keys, provider, model, custom_base_url=custom_url)
        self.verifier = KeyVerifierWorker(keys, provider, model, translator)
        self.verifier.verification_complete.connect(self.on_verification_complete)
        self.verifier.start()

    def on_verification_complete(self, results):
        self.btn_test_keys.setEnabled(True)
        active_count = sum(1 for status in results.values() if status == "Active")
        total = len(results)
        self._key_validation_cache.update(results)
        self.lbl_key_status.setText(f"Pool Status: {active_count}/{total} active")

    def key_pool_changed(self):
        self.save_timer.start(500)

    def on_model_changed(self, text):
        if not self._is_updating_models:
            self.save_timer.start(500)

    def on_provider_changed(self, new_provider: str):
        if new_provider == self.current_provider and not getattr(self, '_is_initializing', False):
            return

        if self.current_provider != "INIT_STATE" and self.current_provider != new_provider:
            self.save_current_settings(provider_to_save=self.current_provider)

        self.save_timer.stop()

        self.current_provider = new_provider
        self.config.provider = new_provider

        self.provider_box.blockSignals(True)
        self.key_pool_edit.blockSignals(True)
        self.model_box.blockSignals(True)
        self._is_updating_models = True

        if new_provider == "Google Translate (Free)":
            self.key_pool_edit.clear()
            self.key_pool_edit.setEnabled(False)
            self.key_pool_edit.setPlaceholderText("No key required for free Google Translate")
            self.btn_toggle_keys.setEnabled(False)
            self.custom_base_url_edit.setVisible(False)
            self.custom_url_label.setVisible(False)
        elif "Ollama" in new_provider:
            self.key_pool_edit.clear()
            self.key_pool_edit.setEnabled(False)
            self.key_pool_edit.setPlaceholderText("No key required for local Ollama")
            self.btn_toggle_keys.setEnabled(False)
            self.custom_base_url_edit.setVisible(True)
            self.custom_url_label.setVisible(True)
        elif new_provider == "Local LLM / Custom":
            self.key_pool_edit.setEnabled(True)
            self.key_pool_edit.setPlaceholderText("Enter up to 10 API keys, one per line")
            self.btn_toggle_keys.setEnabled(True)
            saved_keys = self.config.get_api_keys(new_provider)
            if saved_keys:
                self.key_pool_edit.setPlainText("\n".join(saved_keys))
            else:
                self.key_pool_edit.clear()
            self.custom_base_url_edit.setVisible(True)
            self.custom_url_label.setVisible(True)
        else:
            self.key_pool_edit.setEnabled(True)
            self.key_pool_edit.setPlaceholderText("Enter up to 10 API keys, one per line")
            self.btn_toggle_keys.setEnabled(True)
            saved_keys = self.config.get_api_keys(new_provider)
            if saved_keys:
                self.key_pool_edit.setPlainText("\n".join(saved_keys))
            else:
                k = load_key_from_env_or_file(new_provider, self.env_cache)
                self.key_pool_edit.setPlainText(k if k else "")
            self.custom_base_url_edit.setVisible(False)
            self.custom_url_label.setVisible(False)

        self._is_updating_models = False
        self.key_pool_edit.blockSignals(False)
        self.model_box.blockSignals(False)
        self.provider_box.blockSignals(False)

        self.update_models()

    def update_models(self):
        provider = self.provider_box.currentText()
        self.model_box.blockSignals(True)
        self._is_updating_models = True

        if "Google Translate" in provider:
            self.model_box.clear()
            self.model_box.addItem("None (Free Engine)")
            self.model_box.setCurrentIndex(0)
            self.model_box.setEnabled(False)
            self.completer.setModel(QStringListModel(["None (Free Engine)"]))
        elif provider == "Mixed Providers":
            self.model_box.clear()
            self.model_box.addItem("Defined per key in pool")
            self.model_box.setCurrentIndex(0)
            self.model_box.setEnabled(False)
            self.completer.setModel(QStringListModel(["Defined per key in pool"]))
        elif "Ollama" in provider:
            self.model_box.setEnabled(True)
            self._trigger_loader(provider, "")
        elif provider == "Local LLM / Custom":
            self.model_box.setEnabled(True)
            self.model_box.clear()
            self.model_box.setEditable(True)
            self.completer.setModel(QStringListModel([]))
        else:
            self.model_box.setEnabled(True)

            keys_text = self.key_pool_edit.toPlainText().strip()
            keys = [k.strip() for k in keys_text.splitlines() if k.strip()]
            if not keys:
                self.model_box.clear()
                self.model_box.addItem("Enter API Key to load models")
                self.completer.setModel(QStringListModel(["Enter API Key to load models"]))
                self.model_box.blockSignals(False)
                self._is_updating_models = False
                self.update_run_status()
                logging.getLogger("snbt_localizer.gui").warning("API Key is empty")
                return

            self._trigger_loader(provider, keys[0])

        self.model_box.blockSignals(False)
        self._is_updating_models = False
        self.update_run_status()

    def _trigger_loader(self, provider, key):
        self.model_box.blockSignals(True)
        self.model_box.clear()
        self.model_box.addItem("Loading live models...")
        self.completer.setModel(QStringListModel(["Loading live models..."]))
        self.model_box.blockSignals(False)
        
        for loader in self.running_loaders:
            if loader.isRunning():
                loader.quit()
                loader.wait(1000)
        self.running_loaders.clear()
        
        self.current_loader_id += 1
        loader_id = self.current_loader_id
        
        self.loader = ModelLoader(provider, key, loader_id)
        self.loader.loaded.connect(self.on_models_loaded)
        self.loader.start()
        self.running_loaders.append(self.loader)

    def on_models_loaded(self, models, error_msg="", loader_id=0, loader_provider=""):
        if loader_provider and loader_provider != self.provider_box.currentText():
            return
        self.model_box.blockSignals(True)
        self.model_box.clear()
        provider = self.provider_box.currentText()
        filtered_models = []
        if models:
            for m in models:
                m_low = m.lower()
                if not any(x in m_low for x in ["whisper", "tts", "stablediffusion", "dall-e", "embed", "moderation", "davinci", "babbage", "curie", "ada", "guard", "shield", "rerank", "classify", "classifier", "nli", "sentiment", "bert"]):
                    filtered_models.append(m)
        
        if filtered_models:
            self.model_box.addItems(filtered_models)
            self.completer.setModel(QStringListModel(filtered_models))
        else:
            if "Groq" in provider:
                fallbacks = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "mixtral-8x7b-32768"]
            elif "Gemini" in provider:
                fallbacks = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash"]
            elif "Ollama" in provider:
                fallbacks = ["qwen2.5:7b", "llama3.2", "llama3"]
            elif "NVIDIA NIM" in provider:
                fallbacks = [
                    "nvidia/nemotron-4-340b-instruct",
                    "nvidia/nemotron-3-ultra",
                    "nvidia/nemotron-3-super-120b-a12b",
                    "nvidia/nemotron-3-nano-30b-a3b",
                    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                    "meta/llama-3.1-70b-instruct",
                    "google/gemma-2-27b-it",
                    "meta/llama-3.1-8b-instruct"
                ]
            elif "OpenAI" in provider:
                fallbacks = ["gpt-4o-mini", "gpt-4o"]
            elif "Mistral" in provider:
                fallbacks = ["mistral-large-latest", "open-mistral-nemo"]
            elif "Anthropic" in provider:
                fallbacks = ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307", "claude-3-sonnet-20240229"]
            elif "Cohere" in provider:
                fallbacks = ["command-r-plus", "command-r", "command"]
            else:
                fallbacks = [
                    "google/gemma-4-31b:free",
                    "openai/gpt-oss-120b:free",
                    "poolside/laguna-m.1:free",
                    "nvidia/nemotron-3-super:free",
                    "meta-llama/llama-3.3-70b-instruct:free",
                    "meta-llama/llama-3.1-8b-instruct:free",
                    "qwen/qwen3-coder:free"
                ]
            self.model_box.addItems(fallbacks)
            self.completer.setModel(QStringListModel(fallbacks))

        if error_msg:
            logging.getLogger("snbt_localizer.gui").error(f"Error: {error_msg}")

        if self.model_box.count() > 0:
            saved_model = self.settings.value(f"model_{provider}", "")
            index = self.model_box.findText(saved_model)
            if index >= 0:
                self.model_box.setCurrentIndex(index)
            else:
                self.model_box.setCurrentIndex(0)
                self.settings.setValue(f"model_{provider}", self.model_box.currentText())
            self.config.model = self.model_box.currentText()

        self.update_run_status()
        self.model_box.blockSignals(False)
        self._is_updating_models = False

    def choose_dir(self):
        pass

    def pause(self):
        if not hasattr(self, 'w') or self.w is None:
            return
        if self.w.is_paused:
            self.w.is_paused = False
            self.btn_pause.setText("Pause")
        else:
            self.w.is_paused = True
            self.btn_pause.setText("Resume")

    def stop(self):
        if not hasattr(self, 'w') or self.w is None:
            return
        self.w.is_aborted = True
        self.w.is_paused = False
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)

    def start(self):
        self._translation_finished = False
        if hasattr(self, 'w') and self.w.isRunning():
            return

        self.save_timer.start(500)
        prov = self.config.provider
        policy = self.config.policy
        
        raw_keys = self.key_pool_edit.toPlainText().strip().splitlines()
        keys = [k.strip() for k in raw_keys if k.strip()]
        seen = set()
        unique_keys = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique_keys.append(k)
        unique_keys = unique_keys[:10]
        
        if "Skip" in policy or "Пропустить" in policy:
            unique_keys = ["SKIP"]
        
        mixed_pool = None
        if prov == "Mixed Providers":
            pairs = []
            for entry in unique_keys:
                if "\\" in entry:
                    parts = entry.split("\\", 1)
                    pairs.append({"key": parts[0].strip(), "model": parts[1].strip() if parts[1].strip() else None})
                else:
                    pairs.append({"key": entry, "model": None})
            
            saved_keys_by_provider = {}
            saved_models_by_provider = {}
            default_models_by_provider = {}
            for p in ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI", "Anthropic (Claude)", "Cohere", "Google Translate (Free)", "Ollama (Local / Free)", "Local LLM / Custom"]:
                saved_keys_by_provider[p] = self.config.get_api_keys(p)
                saved_models_by_provider[p] = self.settings.value(f"model_{p}", "")
                default_models_by_provider[p] = PROVIDER_DEFAULTS.get(p, "")
            
            from core import resolve_mixed_pool
            mixed_pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
            
            if not mixed_pool:
                logging.getLogger("snbt_localizer.gui").error("Error: No API keys available for Mixed Providers. Add keys or configure other providers first.")
                return
            
            unique_keys = [item["api_key"] for item in mixed_pool]
        
        if unique_keys:
            first_key = unique_keys[0]
            if first_key in self._key_validation_cache and self._key_validation_cache[first_key] == "Invalid":
                QMessageBox.warning(self, "Invalid API Key", "The first API key in your pool is known to be invalid. Please check your keys.")
                return

        if "Google Translate" not in prov and "Ollama" not in prov and not unique_keys:
            logging.getLogger("snbt_localizer.gui").error("Error: Enter at least one API Key.")
            return
            
        self.btn_run.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

        self.provider_box.setEnabled(False)
        self.model_box.setEnabled(False)
        self.key_pool_edit.setEnabled(False)
        self.btn_toggle_keys.setEnabled(False)
        self.dir_box.setEnabled(False)
        self.context_in.setEnabled(False)
        self.lang_box.setEnabled(False)
        self.policy_box.setEnabled(False)
        self.tabs.setTabEnabled(1, False)
        
        model = self.model_box.currentText() or ""
        t_titles = self.cb_titles.isChecked()
        t_subs = self.cb_subs.isChecked()
        t_desc = self.cb_desc.isChecked()
        custom_context = self.context_in.text().strip()
        policy = self.policy_box.currentText()
        target_lang = self.lang_box.currentText()

        dir_path = self.dir_box.itemData(self.dir_box.currentIndex())
        if dir_path == "MANUAL":
            logging.getLogger("snbt_localizer.gui").error("Error: Please select a valid directory first.")
            return

        dir_path_obj = Path(dir_path)
        quest_dirs = self.instance_quest_dirs.get(dir_path_obj)
        if not quest_dirs:
            quest_dirs = find_all_quest_dirs(dir_path_obj)
            if not quest_dirs:
                logging.getLogger("snbt_localizer.gui").error(f"Error: No quest directories found in {dir_path}")
                return

        all_files = []
        for qd in quest_dirs:
            files = [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            all_files.extend(files)

        modpack_name = dir_path_obj.name if dir_path != "MANUAL" else "Global"

        target_lang_name, target_lang_code = parse_target_lang(target_lang)
        concurrency = self.config.concurrency
        first_key = unique_keys[0] if unique_keys else ""
        custom_url = self.custom_base_url_edit.text() if prov in ("Local LLM / Custom", "Ollama (Local / Free)") else None
        m = SNBTManager(
            first_key, prov, model, custom_context, target_lang_name, target_lang_code,
            concurrency_limit=concurrency, mixed_pool=mixed_pool, modpack=modpack_name,
            batch_size=self.batch_spin.value(), min_batch_size=self.min_batch_spin.value(),
            max_concurrent_requests=self.max_requests_spin.value(), custom_base_url=custom_url
        )
        
        lang_pattern = re.compile(r'^[a-z]{2}_[a-z]{2}\.snbt$', re.IGNORECASE)
        loc_files = [p for p in all_files if lang_pattern.match(p.name)]
        chapter_files = [p for p in all_files if not lang_pattern.match(p.name)]
        
        files = []
        if loc_files:
            source_file = None
            for p in loc_files:
                if "en_us" in p.name.lower():
                    source_file = p
                    break
            if not source_file:
                for p in loc_files:
                    if target_lang_code not in p.name.lower():
                        source_file = p
                        break
            if source_file:
                files.append(source_file)
                logging.getLogger("snbt_localizer.gui").info(f"Localization source file resolved: {source_file.name}")
                
        files.extend(chapter_files)
        
        self.pb_batch.setRange(0, len(files))
        self.pb_batch.setValue(0)
        self.files_progress = {}
        logging.getLogger("snbt_localizer.gui").info(f"Starting localization. Active Provider: {prov}, Active Model: {model or 'N/A'}, Keys in Pool: {len(unique_keys)}")

        custom_url = self.custom_base_url_edit.text() if prov in ("Local LLM / Custom", "Ollama (Local / Free)") else None
        self.w = Worker(files, unique_keys, prov, model, t_titles, t_subs, t_desc, custom_context, policy, target_lang, concurrency, mixed_pool, self.batch_spin.value(), self.min_batch_spin.value(), self.max_requests_spin.value(), modpack=modpack_name, custom_base_url=custom_url)
        self.w.is_aborted = False
        self.w.is_paused = False
        self.w.log.connect(self.out.append)
        self.w.progress_batch.connect(self.update_batch_progress)
        self.w.chunk_progress.connect(self.update_chunk_progress)
        self.w.lines_translated.connect(self.update_lines_progress)
        self.w.progress_state.connect(self.update_progress_state)
        self.w.done.connect(self.on_worker_done)
        self.w.start()

    def on_worker_done(self):
        self._translation_finished = True
        self.pb_batch.setRange(0, 100)
        self.pb_batch.setValue(100)
        self.pb_batch.setFormat("Translation Finished! 100% Completed")
        self.btn_run.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self.btn_stop.setEnabled(False)

        self.provider_box.setEnabled(True)
        self.model_box.setEnabled(True)
        self.key_pool_edit.setEnabled(True)
        self.btn_toggle_keys.setEnabled(True)
        self.dir_box.setEnabled(True)
        self.context_in.setEnabled(True)
        self.lang_box.setEnabled(True)
        self.policy_box.setEnabled(True)
        self.tabs.setTabEnabled(1, True)
        self.translation_memory_tab.refresh_modpack_filter()
        self.translation_memory_tab._load_data()
        if getattr(self, '_close_pending', False):
            self.close()

    def closeEvent(self, event):
        if hasattr(self, 'w') and self.w.isRunning():
            reply = QMessageBox.question(self, "Выход", "Идет перевод. Прервать и выйти?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.w.is_aborted = True
                self._close_pending = True
            event.ignore()
        else:
            self.save_current_settings()
            self.settings.setValue("geometry", self.saveGeometry())
            event.accept()

def main():
    import os
    from logging.handlers import RotatingFileHandler
    root_logger = logging.getLogger("snbt_localizer")
    if not root_logger.handlers:
        root_logger.setLevel(logging.DEBUG)
        log_dir = os.path.expanduser("~/.snbt_localizer/logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
        root_logger.addHandler(file_handler)
        root_logger.propagate = False
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor("#111216"))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor("#e3e6ed"))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#171920"))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#111216"))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#171920"))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e3e6ed"))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor("#f2f4f8"))

    dark_palette.setColor(QPalette.ColorRole.Button, QColor("#171920"))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e3e6ed"))

    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor("white"))
    dark_palette.setColor(QPalette.ColorRole.Link, QColor("#4a8df8"))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor("#306fcb"))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))

    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#4b5263"))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#4b5263"))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#4b5263"))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#14151a"))

    app.setPalette(dark_palette)

    ex = App()
    ex.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
