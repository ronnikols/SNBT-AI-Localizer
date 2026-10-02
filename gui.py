import os
import sys
import ctypes
import re
import json
import asyncio
import random
import time
import logging
import weakref
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLineEdit, 
                             QTextEdit, QLabel, QComboBox, QListView, QCheckBox, 
                             QCompleter, QStyleFactory, QProgressBar, QMessageBox,
                             QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
                             QTabWidget, QHeaderView, QFrame, QScrollArea)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt, QStringListModel, QObject, QTimer, QUrl
from PyQt6.QtGui import QPalette, QColor, QKeySequence, QShortcut, QIcon, QDesktopServices, QPainter
import httpx
from core import SNBTManager, EXCLUDED_DIRS, AbortException, parse_target_lang, TranslationCache, UnifiedTranslator, is_valid_custom_instance, PROVIDER_DEFAULTS, JSONManager, get_resource_path, get_base_url, detect_provider, test_key_with_question, fetch_provider_balance, TEST_QUESTIONS, REASONING_EFFORT_LEVELS, parse_model_effort, set_temperature, reset_request_timeout
from config import ConfigManager, APP_VERSION

LOCALES = {
    "en": {
        "window_title": "SNBT AI Localizer",
        "workspace_tab": "Workspace",
        "translation_memory_tab": "Translation Memory",
        "settings_tab": "Settings",
        "credits_tab": "Credits",
        "api_provider": "API Provider",
        "ai_model": "AI Model (Live Auto-suggest)",
        "api_keys_label": "API Access Keys (one per line, max 10)",
        "show_keys": "▼ API Keys Pool",
        "hide_keys": "▲ Hide Keys",
        "test_keys": "Test Keys",
        "pool_status_unchecked": "Pool Status: Unchecked",
        "pool_status_verifying": "Pool Status: Verifying keys...",
        "pool_status_active": "Pool Status: {} active",
        "custom_url_label": "Custom API Base URL (for Local LLM):",
        "custom_url_placeholder": "e.g. http://localhost:8080/v1",
        "context_label": "Custom Translation Context / Modpack Description",
        "context_placeholder": "e.g. Medieval RPG modpack with magic, technology, and dragons",
        "target_lang_label": "Target Language (Format: Name (code))",
        "policy_label": "Existing Localized Files Policy",
        "policy_complement": "complement",
        "policy_overwrite": "overwrite",
        "policy_skip": "skip",
        "translate_titles": "Translate Titles",
        "translate_subs": "Translate Subtitles",
        "translate_desc": "Translate Descriptions",
        "target_dir_label": "Target Modpack / Directory",
        "start_translation": "Start Batch Translation",
        "pause": "Pause",
        "resume": "Resume",
        "stop": "Stop",
        "clear_log": "Clear Log",
        "settings_threads": "Threads:",
        "settings_batch_size": "Batch Size:",
        "settings_min_batch_size": "Min Batch Size:",
        "settings_max_requests": "Max API Requests:",
        "settings_ui_language": "UI Language",
        "settings_resource_pack_mode": "Resource Pack Mode (Isolate JSONs)",
        "settings_resource_pack_desc": "Saves KubeJS/JSON translations into a clean standalone Resource Pack. WARNING: Some modpacks (like KubeJS in ATM9) ignore resource packs for script translations. If translations don't load in-game, disable this mode to translate directly in-place.",
        "tm_search_placeholder": "Search by original or translation...",
        "tm_all_modpacks": "All Modpacks",
        "tm_original": "Original",
        "tm_translation": "Translation",
        "tm_modpack": "Modpack",
        "tm_added": "Added",
        "tm_load_more": "Load More",
        "tm_delete_selected": "Delete Selected",
        "tm_save_changes": "Save Changes",
        "tm_clear_cache": "Clear Cache",
        "tm_clear_cache_confirm": "Are you sure you want to clear the translation cache?",
        "lang_english": "English",
        "lang_russian": "Русский",
        "lang_ru_ru": "Russian (ru_ru)",
        "lang_es_es": "Spanish (es_es)",
        "lang_zh_cn": "Chinese Simplified (zh_cn)",
        "lang_zh_tw": "Chinese Traditional (zh_tw)",
        "lang_de_de": "German (de_de)",
        "lang_fr_fr": "French (fr_fr)",
        "lang_pt_br": "Portuguese (pt_br)",
        "lang_ja_jp": "Japanese (ja_jp)",
        "lang_ko_kr": "Korean (ko_kr)",
        "lang_uk_ua": "Ukrainian (uk_ua)"
    },
    "ru": {
        "window_title": "SNBT AI Локализатор",
        "workspace_tab": "Рабочая область",
        "translation_memory_tab": "Память переводов",
        "settings_tab": "Настройки",
        "credits_tab": "Благодарности",
        "api_provider": "Провайдер API",
        "ai_model": "AI Модель (живая автоподстановка)",
        "api_keys_label": "Ключи API (по одному на строку, максимум 10)",
        "show_keys": "▼ Пул ключей API",
        "hide_keys": "▲ Скрыть ключи",
        "test_keys": "Проверить ключи",
        "pool_status_unchecked": "Статус пула: Не проверено",
        "pool_status_verifying": "Статус пула: Проверка ключей...",
        "pool_status_active": "Статус пула: {} активных",
        "custom_url_label": "Пользовательский базовый URL API (для локальной LLM):",
        "custom_url_placeholder": "например http://localhost:8080/v1",
        "context_label": "Пользовательский контекст перевода / Описание модпака",
        "context_placeholder": "например Средневековый RPG модпак с магией, технологиями и драконами",
        "target_lang_label": "Целевой язык (Формат: Название (код))",
        "policy_label": "Политика для существующих локализованных файлов",
        "policy_complement": "дополнить",
        "policy_overwrite": "перезаписать",
        "policy_skip": "пропустить",
        "translate_titles": "Переводить заголовки",
        "translate_subs": "Переводить субтитры",
        "translate_desc": "Переводить описания",
        "target_dir_label": "Целевой модпак / Директория",
        "start_translation": "Начать пакетный перевод",
        "pause": "Пауза",
        "resume": "Продолжить",
        "stop": "Стоп",
        "clear_log": "Очистить лог",
        "settings_threads": "Потоки:",
        "settings_batch_size": "Размер пакета:",
        "settings_min_batch_size": "Минимальный размер пакета:",
        "settings_max_requests": "Максимум API запросов:",
        "settings_ui_language": "Язык интерфейса",
        "settings_resource_pack_mode": "Режим ресурс-пака (Изоляция JSON)",
        "settings_resource_pack_desc": "Сохраняет переводы KubeJS/JSON в отдельный ресурс-пак. ВНИМАНИЕ: Некоторые сборки (например, KubeJS в ATM9) игнорируют переводы из ресурс-паков. Если перевод не работает в игре, отключите этот режим для прямого перевода на диск.",
        "tm_search_placeholder": "Поиск по оригиналу или переводу...",
        "tm_all_modpacks": "Все модпаки",
        "tm_original": "Оригинал",
        "tm_translation": "Перевод",
        "tm_modpack": "Модпак",
        "tm_added": "Добавлено",
        "tm_load_more": "Загрузить ещё",
        "tm_delete_selected": "Удалить выбранные",
        "tm_save_changes": "Сохранить изменения",
        "tm_clear_cache": "Очистить кэш",
        "tm_clear_cache_confirm": "Вы уверены, что хотите очистить кэш переводов?",
        "lang_english": "English",
        "lang_russian": "Русский",
        "lang_ru_ru": "Русский (ru_ru)",
        "lang_es_es": "Испанский (es_es)",
        "lang_zh_cn": "Китайский упрощённый (zh_cn)",
        "lang_zh_tw": "Китайский традиционный (zh_tw)",
        "lang_de_de": "Немецкий (de_de)",
        "lang_fr_fr": "Французский (fr_fr)",
        "lang_pt_br": "Португальский (pt_br)",
        "lang_ja_jp": "Японский (ja_jp)",
        "lang_ko_kr": "Корейский (ko_kr)",
        "lang_uk_ua": "Украинский (uk_ua)"
    },
    "es": {
        "window_title": "Localizador de IA SNBT",
        "workspace_tab": "Área de trabajo",
        "translation_memory_tab": "Memoria de traducción",
        "settings_tab": "Configuración",
        "credits_tab": "Créditos",
        "api_provider": "Proveedor de API",
        "ai_model": "Modelo de IA (Sugerencia en vivo)",
        "api_keys_label": "Claves de API (una por línea, máximo 10)",
        "show_keys": "▼ Grupo de claves API",
        "hide_keys": "▲ Ocultar claves",
        "test_keys": "Probar claves",
        "pool_status_unchecked": "Estado del grupo: Sin verificar",
        "pool_status_verifying": "Estado del grupo: Verificando claves...",
        "pool_status_active": "Estado del grupo: {} activas",
        "custom_url_label": "URL base de API personalizada (para LLM local):",
        "custom_url_placeholder": "ej. http://localhost:8080/v1",
        "context_label": "Contexto de traducción personalizado / Descripción del modpack",
        "context_placeholder": "ej. Modpack RPG medieval con magia, tecnología y dragones",
        "target_lang_label": "Idioma de destino (Formato: Nombre (código))",
        "policy_label": "Política para archivos localizados existentes",
        "policy_complement": "complementar",
        "policy_overwrite": "sobrescribir",
        "policy_skip": "omitir",
        "translate_titles": "Traducir títulos",
        "translate_subs": "Traducir subtítulos",
        "translate_desc": "Traducir descripciones",
        "target_dir_label": "Modpack / Directorio de destino",
        "start_translation": "Iniciar traducción por lotes",
        "pause": "Pausa",
        "resume": "Reanudar",
        "stop": "Detener",
        "clear_log": "Limpiar registro",
        "settings_threads": "Hilos:",
        "settings_batch_size": "Tamaño del lote:",
        "settings_min_batch_size": "Tamaño mínimo del lote:",
        "settings_max_requests": "Máximo de solicitudes API:",
        "settings_ui_language": "Idioma de la interfaz",
        "settings_resource_pack_mode": "Modo paquete de recursos (Aislar JSONs)",
        "settings_resource_pack_desc": "Guarda las traducciones KubeJS/JSON en un paquete de recursos independiente. ADVERTENCIA: Algunos modpacks (como KubeJS en ATM9) ignoran los paquetes de recursos para traducciones de scripts. Si las traducciones no se cargan en el juego, desactive este modo para traducir directamente en el lugar.",
        "tm_search_placeholder": "Buscar por original o traducción...",
        "tm_all_modpacks": "Todos los modpacks",
        "tm_original": "Original",
        "tm_translation": "Traducción",
        "tm_modpack": "Modpack",
        "tm_added": "Añadido",
        "tm_load_more": "Cargar más",
        "tm_delete_selected": "Eliminar seleccionados",
        "tm_save_changes": "Guardar cambios",
        "tm_clear_cache": "Limpiar caché",
        "tm_clear_cache_confirm": "¿Estás seguro de que quieres limpiar la caché de traducción?",
        "lang_english": "English",
        "lang_russian": "Русский",
        "lang_ru_ru": "Ruso (ru_ru)",
        "lang_es_es": "Español (es_es)",
        "lang_zh_cn": "Chino simplificado (zh_cn)",
        "lang_zh_tw": "Chino tradicional (zh_tw)",
        "lang_de_de": "Alemán (de_de)",
        "lang_fr_fr": "Francés (fr_fr)",
        "lang_pt_br": "Portugués (pt_br)",
        "lang_ja_jp": "Japonés (ja_jp)",
        "lang_ko_kr": "Coreano (ko_kr)",
        "lang_uk_ua": "Ucraniano (uk_ua)"
    },
    "de": {
        "window_title": "SNBT KI-Lokalisierer",
        "workspace_tab": "Arbeitsbereich",
        "translation_memory_tab": "Übersetzungsspeicher",
        "settings_tab": "Einstellungen",
        "credits_tab": "Danksagungen",
        "api_provider": "API-Anbieter",
        "ai_model": "KI-Modell (Live-Vorschlag)",
        "api_keys_label": "API-Zugriffsschlüssel (einer pro Zeile, max. 10)",
        "show_keys": "▼ API-Schlüssel-Pool",
        "hide_keys": "▲ Schlüssel ausblenden",
        "test_keys": "Schlüssel testen",
        "pool_status_unchecked": "Pool-Status: Nicht geprüft",
        "pool_status_verifying": "Pool-Status: Schlüssel werden überprüft...",
        "pool_status_active": "Pool-Status: {} aktiv",
        "custom_url_label": "Benutzerdefinierte API-Basis-URL (für lokale LLM):",
        "custom_url_placeholder": "z.B. http://localhost:8080/v1",
        "context_label": "Benutzerdefinierter Übersetzungskontext / Modpack-Beschreibung",
        "context_placeholder": "z.B. Mittelalterliches RPG-Modpack mit Magie, Technologie und Drachen",
        "target_lang_label": "Zielsprache (Format: Name (Code))",
        "policy_label": "Richtlinie für bestehende lokalisierte Dateien",
        "policy_complement": "ergänzen",
        "policy_overwrite": "überschreiben",
        "policy_skip": "überspringen",
        "translate_titles": "Titel übersetzen",
        "translate_subs": "Untertitel übersetzen",
        "translate_desc": "Beschreibungen übersetzen",
        "target_dir_label": "Ziel-Modpack / Verzeichnis",
        "start_translation": "Stapelübersetzung starten",
        "pause": "Pause",
        "resume": "Fortsetzen",
        "stop": "Stoppen",
        "clear_log": "Protokoll löschen",
        "settings_threads": "Threads:",
        "settings_batch_size": "Stapelgröße:",
        "settings_min_batch_size": "Minimale Stapelgröße:",
        "settings_max_requests": "Max. API-Anfragen:",
        "settings_ui_language": "UI-Sprache",
        "settings_resource_pack_mode": "Ressourcenpaket-Modus (JSONs isolieren)",
        "settings_resource_pack_desc": "Speichert KubeJS/JSON-Übersetzungen in einem sauberen eigenständigen Ressourcenpaket. WARNUNG: Einige Modpacks (wie KubeJS in ATM9) ignorieren Ressourcenpakete für Skriptübersetzungen. Wenn Übersetzungen im Spiel nicht geladen werden, deaktivieren Sie diesen Modus, um direkt vor Ort zu übersetzen.",
        "tm_search_placeholder": "Suche nach Original oder Übersetzung...",
        "tm_all_modpacks": "Alle Modpacks",
        "tm_original": "Original",
        "tm_translation": "Übersetzung",
        "tm_modpack": "Modpack",
        "tm_added": "Hinzugefügt",
        "tm_load_more": "Mehr laden",
        "tm_delete_selected": "Ausgewählte löschen",
        "tm_save_changes": "Änderungen speichern",
        "tm_clear_cache": "Cache leeren",
        "tm_clear_cache_confirm": "Sind Sie sicher, dass Sie den Übersetzungscache leeren möchten?",
        "lang_english": "English",
        "lang_russian": "Russisch",
        "lang_ru_ru": "Russisch (ru_ru)",
        "lang_es_es": "Spanisch (es_es)",
        "lang_zh_cn": "Chinesisch (vereinfacht) (zh_cn)",
        "lang_zh_tw": "Chinesisch (traditionell) (zh_tw)",
        "lang_de_de": "Deutsch (de_de)",
        "lang_fr_fr": "Französisch (fr_fr)",
        "lang_pt_br": "Portugiesisch (BR) (pt_br)",
        "lang_ja_jp": "Japanisch (ja_jp)",
        "lang_ko_kr": "Koreanisch (ko_kr)",
        "lang_uk_ua": "Ukrainisch (uk_ua)"
    },
    "fr": {
        "window_title": "Localisateur IA SNBT",
        "workspace_tab": "Espace de travail",
        "translation_memory_tab": "Mémoire de traduction",
        "settings_tab": "Paramètres",
        "credits_tab": "Crédits",
        "api_provider": "Fournisseur d'API",
        "ai_model": "Modèle IA (Suggestion en direct)",
        "api_keys_label": "Clés d'accès API (une par ligne, max 10)",
        "show_keys": "▼ Pool de clés API",
        "hide_keys": "▲ Masquer les clés",
        "test_keys": "Tester les clés",
        "pool_status_unchecked": "Statut du pool : Non vérifié",
        "pool_status_verifying": "Statut du pool : Vérification des clés...",
        "pool_status_active": "Statut du pool : {} actif(s)",
        "custom_url_label": "URL de base API personnalisée (pour LLM locale) :",
        "custom_url_placeholder": "ex. http://localhost:8080/v1",
        "context_label": "Contexte de traduction personnalisé / Description du modpack",
        "context_placeholder": "ex. Modpack RPG médiéval avec magie, technologie et dragons",
        "target_lang_label": "Langue cible (Format : Nom (code))",
        "policy_label": "Politique pour les fichiers déjà localisés",
        "policy_complement": "compléter",
        "policy_overwrite": "écraser",
        "policy_skip": "ignorer",
        "translate_titles": "Traduire les titres",
        "translate_subs": "Traduire les sous-titres",
        "translate_desc": "Traduire les descriptions",
        "target_dir_label": "Modpack / Répertoire cible",
        "start_translation": "Démarrer la traduction par lots",
        "pause": "Pause",
        "resume": "Reprendre",
        "stop": "Arrêter",
        "clear_log": "Effacer le journal",
        "settings_threads": "Threads :",
        "settings_batch_size": "Taille du lot :",
        "settings_min_batch_size": "Taille minimale du lot :",
        "settings_max_requests": "Requêtes API max :",
        "settings_ui_language": "Langue de l'interface",
        "settings_resource_pack_mode": "Mode pack de ressources (Isoler les JSON)",
        "settings_resource_pack_desc": "Enregistre les traductions KubeJS/JSON dans un pack de ressources autonome propre. ATTENTION : Certains modpacks (comme KubeJS dans ATM9) ignorent les packs de ressources pour les traductions de scripts. Si les traductions ne se chargent pas en jeu, désactivez ce mode pour traduire directement sur place.",
        "tm_search_placeholder": "Rechercher par original ou traduction...",
        "tm_all_modpacks": "Tous les modpacks",
        "tm_original": "Original",
        "tm_translation": "Traduction",
        "tm_modpack": "Modpack",
        "tm_added": "Ajouté",
        "tm_load_more": "Charger plus",
        "tm_delete_selected": "Supprimer la sélection",
        "tm_save_changes": "Enregistrer les modifications",
        "tm_clear_cache": "Effacer le cache",
        "tm_clear_cache_confirm": "Êtes-vous sûr de vouloir effacer le cache de traduction ?",
        "lang_english": "English",
        "lang_russian": "Russe",
        "lang_ru_ru": "Russe (ru_ru)",
        "lang_es_es": "Espagnol (es_es)",
        "lang_zh_cn": "Chinois simplifié (zh_cn)",
        "lang_zh_tw": "Chinois traditionnel (zh_tw)",
        "lang_de_de": "Allemand (de_de)",
        "lang_fr_fr": "Français (fr_fr)",
        "lang_pt_br": "Portugais (BR) (pt_br)",
        "lang_ja_jp": "Japonais (ja_jp)",
        "lang_ko_kr": "Coréen (ko_kr)",
        "lang_uk_ua": "Ukrainien (uk_ua)"
    },
    "pt_br": {
        "window_title": "Localizador de IA SNBT",
        "workspace_tab": "Área de trabalho",
        "translation_memory_tab": "Memória de tradução",
        "settings_tab": "Configurações",
        "credits_tab": "Créditos",
        "api_provider": "Provedor de API",
        "ai_model": "Modelo de IA (Sugestão ao vivo)",
        "api_keys_label": "Chaves de acesso à API (uma por linha, máximo 10)",
        "show_keys": "▼ Pool de chaves de API",
        "hide_keys": "▲ Ocultar chaves",
        "test_keys": "Testar chaves",
        "pool_status_unchecked": "Status do pool: Não verificado",
        "pool_status_verifying": "Status do pool: Verificando chaves...",
        "pool_status_active": "Status do pool: {} ativo(s)",
        "custom_url_label": "URL base da API personalizada (para LLM local):",
        "custom_url_placeholder": "ex. http://localhost:8080/v1",
        "context_label": "Contexto de tradução personalizado / Descrição do modpack",
        "context_placeholder": "ex. Modpack RPG medieval com magia, tecnologia e dragões",
        "target_lang_label": "Idioma de destino (Formato: Nome (código))",
        "policy_label": "Política para arquivos já localizados",
        "policy_complement": "complementar",
        "policy_overwrite": "sobrescrever",
        "policy_skip": "pular",
        "translate_titles": "Traduzir títulos",
        "translate_subs": "Traduzir legendas",
        "translate_desc": "Traduzir descrições",
        "target_dir_label": "Modpack / Diretório de destino",
        "start_translation": "Iniciar tradução em lote",
        "pause": "Pausar",
        "resume": "Retomar",
        "stop": "Parar",
        "clear_log": "Limpar registro",
        "settings_threads": "Threads:",
        "settings_batch_size": "Tamanho do lote:",
        "settings_min_batch_size": "Tamanho mínimo do lote:",
        "settings_max_requests": "Máximo de solicitações de API:",
        "settings_ui_language": "Idioma da interface",
        "settings_resource_pack_mode": "Modo pacote de recursos (Isolar JSONs)",
        "settings_resource_pack_desc": "Salva traduções KubeJS/JSON em um pacote de recursos autônomo limpo. AVISO: Alguns modpacks (como KubeJS no ATM9) ignoram pacotes de recursos para traduções de scripts. Se as traduções não carregarem no jogo, desative este modo para traduzir diretamente no local.",
        "tm_search_placeholder": "Pesquisar por original ou tradução...",
        "tm_all_modpacks": "Todos os modpacks",
        "tm_original": "Original",
        "tm_translation": "Tradução",
        "tm_modpack": "Modpack",
        "tm_added": "Adicionado",
        "tm_load_more": "Carregar mais",
        "tm_delete_selected": "Excluir selecionados",
        "tm_save_changes": "Salvar alterações",
        "tm_clear_cache": "Limpar cache",
        "tm_clear_cache_confirm": "Tem certeza de que deseja limpar o cache de tradução?",
        "lang_english": "English",
        "lang_russian": "Russo",
        "lang_ru_ru": "Russo (ru_ru)",
        "lang_es_es": "Espanhol (es_es)",
        "lang_zh_cn": "Chinês simplificado (zh_cn)",
        "lang_zh_tw": "Chinês tradicional (zh_tw)",
        "lang_de_de": "Alemão (de_de)",
        "lang_fr_fr": "Francês (fr_fr)",
        "lang_pt_br": "Português (BR) (pt_br)",
        "lang_ja_jp": "Japonês (ja_jp)",
        "lang_ko_kr": "Coreano (ko_kr)",
        "lang_uk_ua": "Ucraniano (uk_ua)"
    },
    "zh_cn": {
        "window_title": "SNBT AI 本地化工具",
        "workspace_tab": "工作区",
        "translation_memory_tab": "翻译内存",
        "settings_tab": "设置",
        "credits_tab": "鸣谢",
        "api_provider": "API 提供商",
        "ai_model": "AI 模型（实时建议）",
        "api_keys_label": "API 访问密钥（每行一个，最多10个）",
        "show_keys": "▼ API 密钥池",
        "hide_keys": "▲ 隐藏密钥",
        "test_keys": "测试密钥",
        "pool_status_unchecked": "池状态：未检查",
        "pool_status_verifying": "池状态：正在验证密钥...",
        "pool_status_active": "池状态：{} 个活跃",
        "custom_url_label": "自定义 API 基础 URL（用于本地 LLM）：",
        "custom_url_placeholder": "例如 http://localhost:8080/v1",
        "context_label": "自定义翻译上下文 / 模组包描述",
        "context_placeholder": "例如 中世纪 RPG 模组包，包含魔法、科技和龙",
        "target_lang_label": "目标语言（格式：名称（代码））",
        "policy_label": "现有本地化文件策略",
        "policy_complement": "补充",
        "policy_overwrite": "覆盖",
        "policy_skip": "跳过",
        "translate_titles": "翻译标题",
        "translate_subs": "翻译字幕",
        "translate_desc": "翻译描述",
        "target_dir_label": "目标模组包 / 目录",
        "start_translation": "开始批量翻译",
        "pause": "暂停",
        "resume": "继续",
        "stop": "停止",
        "clear_log": "清除日志",
        "settings_threads": "线程：",
        "settings_batch_size": "批次大小：",
        "settings_min_batch_size": "最小批次大小：",
        "settings_max_requests": "最大 API 请求数：",
        "settings_ui_language": "界面语言",
        "settings_resource_pack_mode": "资源包模式（隔离 JSON）",
        "settings_resource_pack_desc": "将 KubeJS/JSON 翻译保存到干净独立的资源包中。警告：某些模组包（如 ATM9 中的 KubeJS）会忽略资源包中的脚本翻译。如果翻译在游戏中无法加载，请禁用此模式以直接进行原地翻译。",
        "tm_search_placeholder": "按原文或翻译搜索...",
        "tm_all_modpacks": "所有模组包",
        "tm_original": "原文",
        "tm_translation": "翻译",
        "tm_modpack": "模组包",
        "tm_added": "已添加",
        "tm_load_more": "加载更多",
        "tm_delete_selected": "删除选中项",
        "tm_save_changes": "保存更改",
        "tm_clear_cache": "清除缓存",
        "tm_clear_cache_confirm": "您确定要清除翻译缓存吗？",
        "lang_english": "English",
        "lang_russian": "俄语",
        "lang_ru_ru": "俄语 (ru_ru)",
        "lang_es_es": "西班牙语 (es_es)",
        "lang_zh_cn": "简体中文 (zh_cn)",
        "lang_zh_tw": "繁体中文 (zh_tw)",
        "lang_de_de": "德语 (de_de)",
        "lang_fr_fr": "法语 (fr_fr)",
        "lang_pt_br": "巴西葡萄牙语 (pt_br)",
        "lang_ja_jp": "日语 (ja_jp)",
        "lang_ko_kr": "韩语 (ko_kr)",
        "lang_uk_ua": "乌克兰语 (uk_ua)"
    }
}

def get_locale():
    settings = QSettings("MineAI", "SNBT-Localizer")
    lang = settings.value("ui_language", "English")
    lang_map = {
        "English": "en", "Русский": "ru", "Español": "es",
        "Deutsch": "de", "Français": "fr", "Português (BR)": "pt_br",
        "简体中文": "zh_cn"
    }
    code = lang_map.get(lang, "en")
    base = LOCALES.get("en", {}).copy()
    base.update(LOCALES.get(code, {}))
    return base

def has_kubejs_lang(instance_path: Path) -> bool:
    for kubejs_dir in (instance_path / "kubejs", instance_path / "minecraft" / "kubejs"):
        if not kubejs_dir.is_dir():
            continue
        try:
            for lang_dir in kubejs_dir.rglob("lang"):
                if lang_dir.is_dir() and (lang_dir / "en_us.json").is_file():
                    return True
        except (PermissionError, OSError):
            continue
    return False

def find_all_quest_dirs(instance_path: Path) -> list[Path]:
    quest_dirs = []
    MAX_DEPTH = 3

    standard_paths = [
        instance_path / "config" / "ftbquests" / "quests",
        instance_path / "minecraft" / "config" / "ftbquests" / "quests",
    ]
    for cp in standard_paths:
        if cp.exists() and cp.is_dir():
            quest_dirs.append(cp)

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
    if not quest_dirs and has_kubejs_lang(instance_path):
        quest_dirs.append(instance_path)
    return quest_dirs

async def run_with_abort_watchdog(coro, is_aborted, log=None):
    task = asyncio.create_task(coro)
    while not task.done():
        if is_aborted():
            if log:
                log("Stop requested: cancelling in-flight requests...")
            task.cancel()
            break
        await asyncio.sleep(0.25)
    return await task

_ACTIVE_QTHREADS = set()

def _track_qthread(thread):
    """Keep a strong reference to a running QThread until it finishes.

    Without this, a QThread whose Python wrapper gets garbage-collected while
    the C++ thread is still running aborts the whole process
    ("QThread: Destroyed while thread is still running").
    """
    _ACTIVE_QTHREADS.add(thread)
    try:
        thread.finished.connect(lambda t=thread: _ACTIVE_QTHREADS.discard(t))
    except RuntimeError:
        _ACTIVE_QTHREADS.discard(thread)
    return thread

class QtLogSignaler(QObject):
    log_signal = pyqtSignal(str, int)

class QtLoggingHandler(logging.Handler):
    def __init__(self, text_edit, full_log_sink=None):
        super().__init__()
        self.signaler = QtLogSignaler()
        self.text_edit_ref = weakref.ref(text_edit)
        self.full_log_sink = full_log_sink
        self.signaler.log_signal.connect(self._append_to_text_edit)
        self.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))

    def _append_to_text_edit(self, msg, level):
        text_edit = self.text_edit_ref()
        # Keep the shadow buffer complete even when the on-screen view trims
        if self.full_log_sink is not None:
            try:
                self.full_log_sink(msg)
                return
            except Exception:
                pass
        if text_edit is not None and not text_edit.signalsBlocked():
            try:
                text_edit.append(msg)
            except RuntimeError:
                pass

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

class InstanceScanner(QThread):
    """Background scan of launcher instances - keeps the GUI thread free."""
    instances_scanned = pyqtSignal(object, object)

    def run(self):
        try:
            detected, quest_dirs_mapping = detect_instances()
            self.instances_scanned.emit(detected, quest_dirs_mapping)
        except Exception:
            self.instances_scanned.emit({}, {})

class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()

    def run(self):
        try:
            asyncio.run(self._check_updates())
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Update check failed: {e}")

    async def _check_updates(self):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get("https://api.github.com/repos/ronnikols/SNBT-AI-Localizer/releases/latest", follow_redirects=True)
                response.raise_for_status()
                data = response.json()
                remote_version = data.get("tag_name", "v0.0.0")
                if remote_version.startswith("v"):
                    remote_version = remote_version[1:]
                current_version = APP_VERSION
                if current_version.startswith("v"):
                    current_version = current_version[1:]

                if self._compare_versions(remote_version, current_version) > 0:
                    current_exe_name = Path(sys.executable).name
                    asset_url = ""
                    for asset in data.get("assets", []):
                        if asset.get("name") == current_exe_name:
                            asset_url = asset.get("browser_download_url", "")
                            break
                    if asset_url:
                        self.update_available.emit(remote_version, asset_url)
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Update check error: {e}")

    def _compare_versions(self, v1, v2):
        v1_parts = list(map(int, v1.split('.')))
        v2_parts = list(map(int, v2.split('.')))
        for i in range(max(len(v1_parts), len(v2_parts))):
            part1 = v1_parts[i] if i < len(v1_parts) else 0
            part2 = v2_parts[i] if i < len(v2_parts) else 0
            if part1 > part2:
                return 1
            elif part1 < part2:
                return -1
        return 0

class CreditsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedWidth(450)
        card.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(15)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("SNBT AI Localizer")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #f2f4f8; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        description = QLabel("Advanced asynchronous translator for Minecraft FTB Quests and KubeJS files.")
        description.setStyleSheet("font-size: 13px; color: #9ba1b0; border: none;")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(description)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #2d2d30; max-height: 1px; border: none;")
        card_layout.addWidget(line)

        links_layout = QHBoxLayout()
        links_layout.setSpacing(30)

        github_label = QLabel('<a href="https://github.com/ronnikols/SNBT-AI-Localizer" style="color: #4a8df8; text-decoration: none; font-weight: bold;">GitHub</a>')
        github_label.setOpenExternalLinks(True)
        github_label.setStyleSheet("border: none; font-size: 14px;")
        github_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links_layout.addWidget(github_label)

        telegram_label = QLabel('<a href="https://t.me/ronnikols" style="color: #4a8df8; text-decoration: none; font-weight: bold;">Telegram</a>')
        telegram_label.setOpenExternalLinks(True)
        telegram_label.setStyleSheet("border: none; font-size: 14px;")
        telegram_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links_layout.addWidget(telegram_label)

        card_layout.addLayout(links_layout)
        main_layout.addWidget(card)

def _sanitize_judge_key(key: str, origin: str = "") -> str:
    """ТЗ-v4 A1: judge-row API keys pass the central core sanitizer at
    save time; a rejected key becomes empty (= provider pool)."""
    try:
        from core import sanitize_api_key
        cleaned = sanitize_api_key(key, origin=f"judge {origin}" if origin else "judge")
        return cleaned
    except Exception:
        return str(key or "").strip()


class SettingsTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings = QSettings("MineAI", "SNBT-Localizer")
        self.setup_ui()
        self.setLayout(self.layout)
        self._load_settings()

    def _load_settings(self):
        self.context_in.setText(self.settings.value("custom_context", ""))
        self.concurrency_spin.setValue(int(self.settings.value("concurrency_limit", 2)))
        self.batch_spin.setValue(int(self.settings.value("batch_size", 50)))
        self.min_batch_spin.setValue(int(self.settings.value("min_batch_size", 1)))
        self.max_requests_spin.setValue(int(self.settings.value("max_concurrent_requests", 10)))
        self.cb_titles.setChecked(self.settings.value("cb_titles", "true") == "true")
        self.cb_subs.setChecked(self.settings.value("cb_subs", "true") == "true")
        self.cb_desc.setChecked(self.settings.value("cb_desc", "true") == "true")
        # Utility model (glossary pre-scan): empty = same as main
        saved_up = self.settings.value("utility_provider", "") or ""
        idx = self.utility_provider_combo.findData(saved_up)
        self.utility_provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._utility_saved_model = self.settings.value("utility_model", "") or ""
        # _on_utility_provider_changed fires via setCurrentIndex above when a
        # non-default provider was saved; the model text is restored after
        # the list loads (see _on_utility_models_loaded).
        # QA audit phase: judge #1 (provider + model) is restored in setup_ui
        # by _judges_load_from_config — row 0 of the judges table.

    def setup_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setSpacing(12)
        self.layout.setContentsMargins(16, 16, 16, 16)

        context_frame = QFrame(self)
        context_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        context_layout = QVBoxLayout(context_frame)
        context_layout.setContentsMargins(12, 12, 12, 12)
        context_layout.setSpacing(8)

        self.context_label = QLabel("Custom Translation Context / Modpack Description")
        self.context_in = QLineEdit()
        self.context_in.setPlaceholderText("e.g. Medieval RPG modpack with magic, technology, and dragons")
        context_layout.addWidget(self.context_label)
        context_layout.addWidget(self.context_in)
        self.layout.addWidget(context_frame)

        settings_frame = QFrame(self)
        settings_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(12)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        concurrency_layout = QVBoxLayout()
        self.concurrency_label = QLabel("Threads:")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        concurrency_layout.addWidget(self.concurrency_label)
        concurrency_layout.addWidget(self.concurrency_spin)
        settings_row.addLayout(concurrency_layout)

        batch_layout = QVBoxLayout()
        self.batch_label = QLabel("Batch Size:")
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 500)
        batch_layout.addWidget(self.batch_label)
        batch_layout.addWidget(self.batch_spin)
        settings_row.addLayout(batch_layout)

        min_batch_layout = QVBoxLayout()
        self.min_batch_label = QLabel("Min Batch Size:")
        self.min_batch_spin = QSpinBox()
        self.min_batch_spin.setRange(1, 50)
        min_batch_layout.addWidget(self.min_batch_label)
        min_batch_layout.addWidget(self.min_batch_spin)
        settings_row.addLayout(min_batch_layout)

        max_requests_layout = QVBoxLayout()
        self.max_requests_label = QLabel("Max API Requests:")
        self.max_requests_spin = QSpinBox()
        self.max_requests_spin.setRange(1, 100)
        max_requests_layout.addWidget(self.max_requests_label)
        max_requests_layout.addWidget(self.max_requests_spin)
        settings_row.addLayout(max_requests_layout)

        temp_layout = QVBoxLayout()
        self.temperature_label = QLabel("Temperature:")
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setValue(0.1)
        temp_layout.addWidget(self.temperature_label)
        temp_layout.addWidget(self.temperature_spin)
        settings_row.addLayout(temp_layout)

        settings_row.addStretch()
        settings_layout.addLayout(settings_row)
        self.layout.addWidget(settings_frame)

        # Utility model for the modpack glossary pre-scan. Both fields empty
        # (default) = use the main provider/model; the pre-scan sends 1-2
        # tiny batches of recurring mod terms and pins their translations
        # for the main run (Curio → артефакт, Solidifier → Затвердитель).
        utility_frame = QFrame(self)
        utility_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        utility_layout = QVBoxLayout(utility_frame)
        utility_layout.setContentsMargins(12, 12, 12, 12)
        utility_layout.setSpacing(8)

        utility_label = QLabel("Glossary Utility Model (empty = same as main):")
        utility_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        utility_layout.addWidget(utility_label)

        utility_row = QHBoxLayout()
        utility_row.setSpacing(12)
        self.utility_provider_combo = QComboBox()
        self.utility_provider_combo.setView(QListView())
        self.utility_provider_combo.setEditable(False)
        self.utility_provider_combo.addItem("Same as main (default)", "")
        from config import ConfigManager
        for p in ConfigManager.AVAILABLE_PROVIDERS:
            self.utility_provider_combo.addItem(p, p)
        self.utility_provider_combo.setToolTip(
            "Provider used ONLY for the glossary pre-scan (translating recurring mod terms).\n"
            "Keys are taken from this provider's pool on the main screen.\n"
            "If the pool is empty, falls back to the main provider."
        )
        self.utility_provider_combo.currentIndexChanged.connect(self._on_utility_provider_changed)
        utility_row.addWidget(self.utility_provider_combo)

        # Utility model: same UX as the main model box — editable combo with
        # a live-loaded model list, a completion popup and the "/level" hint.
        self.utility_model_box = QComboBox()
        self.utility_model_box.setView(QListView())
        self.utility_model_box.setEditable(True)
        self.utility_model_box.setEnabled(False)
        self.utility_model_box.setToolTip(
            "Model for the glossary pre-scan. A fast/cheap model is enough.\n"
            'Type "/" after a model id for a reasoning level (e.g. zai-org/GLM-5.3-Flash/low).'
        )
        self.utility_completer = QCompleter(self)
        self.utility_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.utility_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.utility_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.utility_completer.popup().setStyleSheet(STYLE_SHEET)
        self.utility_model_box.setLineEdit(GhostSuffixLineEdit())
        self.utility_model_box.setCompleter(self.utility_completer)
        # Hard dark styling for every state (enabled/disabled/placeholder):
        # without this the Fusion palette can render black text.
        self.utility_model_box.setStyleSheet(
            "QComboBox { background-color: #171920; border: 1px solid #2b2f3d;"
            " border-radius: 6px; padding: 6px 10px; color: #f2f4f8; }"
            "QComboBox:disabled { background-color: #14151a; color: #4b5263; }"
            "QComboBox QLineEdit { background-color: transparent; color: #f2f4f8; border: none; padding: 0; }"
            "QLineEdit:disabled { background-color: transparent; color: #4b5263; border: none; }"
        )
        self.utility_provider_combo.setStyleSheet(
            "QComboBox { background-color: #171920; border: 1px solid #2b2f3d;"
            " border-radius: 6px; padding: 6px 10px; color: #f2f4f8; }"
            "QComboBox:disabled { background-color: #14151a; color: #4b5263; }"
            "QComboBox QAbstractItemView { background-color: #171920; color: #f2f4f8;"
            " selection-background-color: #306fcb; selection-color: #ffffff; }"
        )
        self.utility_model_box.lineEdit().textEdited.connect(self._on_utility_model_text_edited)
        self._utility_orig_completer_model = None
        utility_row.addWidget(self.utility_model_box, 1)
        utility_layout.addLayout(utility_row)
        utility_hint = QLabel('After the model you can type "/" for a reasoning level (e.g. gpt-5/low)')
        utility_hint.setStyleSheet("font-size: 11px; color: #64748b; border: none; margin-left: 2px;")
        utility_hint.setToolTip('Type "/" after a model id to pick a reasoning level:\n'
                                '/off /minimal /low /medium /high /xhigh /max /default\n'
                                'Controls how much the model "thinks" before answering —\n'
                                'lower levels are faster and cheaper.')
        utility_layout.addWidget(utility_hint)
        self.layout.addWidget(utility_frame)

        # --- QA audit phase frame ------------------------------------------
        qa_frame = QFrame(self)
        qa_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        qa_layout = QVBoxLayout(qa_frame)
        qa_layout.setContentsMargins(12, 12, 12, 12)
        qa_layout.setSpacing(8)

        qa_title = QLabel("QA Audit (Post-Translation Scan)")
        qa_title.setStyleSheet("font-weight: bold; color: #f2f4f8; border: none;")
        qa_layout.addWidget(qa_title)

        qa_top_row = QHBoxLayout()
        qa_top_row.setSpacing(10)
        self.cb_qa_enabled = QCheckBox("Enable QA scan after translation")
        self.cb_qa_enabled.setChecked(self.config.qa_enabled)
        qa_top_row.addWidget(self.cb_qa_enabled)
        qa_top_row.addStretch()
        qa_layout.addLayout(qa_top_row)

        # (ТЗ-Жюри UX) The separate auditor provider/model rows are gone:
        # judge #1 row in the table below IS the QA picker — same provider
        # combo, same live model list, same '/' effort hints per row.

        self.cb_qa_update_glossary = QCheckBox("Update modpack glossary from scan results")
        self.cb_qa_update_glossary.setChecked(self.config.qa_update_glossary)
        self.cb_qa_update_glossary.setEnabled(self.cb_qa_enabled.isChecked())
        self.cb_qa_update_glossary.setStyleSheet("color: #f2f4f8;")
        qa_layout.addWidget(self.cb_qa_update_glossary)

        qa_batch_row = QHBoxLayout()
        qa_batch_label = QLabel("QA batch size")
        qa_batch_label.setStyleSheet("color: #b8bfcc; border: none;")
        self.qa_batch_spin = QSpinBox()
        self.qa_batch_spin.setRange(10, 200)
        self.qa_batch_spin.setSingleStep(10)
        self.qa_batch_spin.setValue(self.config.qa_batch_size)
        self.qa_batch_spin.setEnabled(self.cb_qa_enabled.isChecked())
        self.qa_batch_spin.setToolTip(
            "Number of translated pairs sent to the auditor model per request.\n"
            "Bigger batches = fewer requests but slower answers.\n"
            "Batches are scanned in parallel, one per API key.")
        self.qa_batch_spin.setStyleSheet(
            "QSpinBox { background-color: #171920; color: #e8ecf1; border: 1px solid #2d2d30; "
            "border-radius: 4px; padding: 4px 6px; font-size: 12px; min-width: 60px; }")
        qa_batch_row.addWidget(qa_batch_label)
        qa_batch_row.addWidget(self.qa_batch_spin)
        qa_batch_row.addStretch()
        qa_layout.addLayout(qa_batch_row)

        qa_temp_row = QHBoxLayout()
        qa_temp_label = QLabel("QA temperature")
        qa_temp_label.setStyleSheet("color: #b8bfcc; border: none;")
        self.qa_temp_spin = QDoubleSpinBox()
        self.qa_temp_spin.setRange(0.0, 2.0)
        self.qa_temp_spin.setSingleStep(0.1)
        self.qa_temp_spin.setDecimals(2)
        self.qa_temp_spin.setValue(self.config.qa_temperature)
        self.qa_temp_spin.setEnabled(self.cb_qa_enabled.isChecked())
        self.qa_temp_spin.setToolTip(
            "Sampling temperature for the QA auditor model.\n"
            "0.0 = fully deterministic audit (recommended).\n"
            "Higher values make the auditor more varied / less strict.")
        self.qa_temp_spin.setStyleSheet(
            "QDoubleSpinBox { background-color: #171920; color: #e8ecf1; border: 1px solid #2d2d30; "
            "border-radius: 4px; padding: 4px 6px; font-size: 12px; min-width: 60px; }")
        qa_temp_row.addWidget(qa_temp_label)
        qa_temp_row.addWidget(self.qa_temp_spin)
        qa_temp_row.addStretch()
        qa_layout.addLayout(qa_temp_row)

        qa_ds_row = QHBoxLayout()
        self.cb_qa_dataset = QCheckBox("Collect QA dataset (training records)")
        self.cb_qa_dataset.setChecked(self.config.qa_dataset)
        self.cb_qa_dataset.setEnabled(self.cb_qa_enabled.isChecked())
        self.cb_qa_dataset.setToolTip(
            "Passively record every audited pair (source / machine translation / final / verdicts / action)\n"
            "into ~/.snbt-tr/datasets/<pack>/<run>.jsonl — training data for the future decision model.\n"
            "The run is never affected: a write failure only disables the dataset.")
        self.cb_qa_dataset.setStyleSheet("color: #b8bfcc; border: none;")
        qa_ds_row.addWidget(self.cb_qa_dataset)

        self.cb_qa_vcache = QCheckBox("Verdict cache (skip re-audit of clean lines)")
        self.cb_qa_vcache.setChecked(self.config.qa_verdict_cache)
        self.cb_qa_vcache.setEnabled(self.cb_qa_enabled.isChecked())
        self.cb_qa_vcache.setToolTip(
            "Hashes every (source, translation) pair with the QA config. Clean\n"
            "pairs skip the LLM re-audit on the next run; change a line — it is\n"
            "audited again automatically.")
        self.cb_qa_vcache.setStyleSheet("color: #b8bfcc; border: none;")
        qa_ds_row.addWidget(self.cb_qa_vcache)
        qa_ds_row.addStretch()
        qa_layout.addLayout(qa_ds_row)

        # --- ТЗ-Жюри: jury threshold + judges table --------------------
        self.jury_threshold_spin = QSpinBox()
        self.jury_threshold_spin.setRange(1, 4)
        self.jury_threshold_spin.setValue(int(getattr(self.config, "qa_jury_threshold", 2) or 2))
        self.jury_threshold_spin.setEnabled(self.cb_qa_enabled.isChecked())
        self.jury_threshold_spin.setToolTip(
            "Consensus threshold: how many judges must flag a pair before it goes to phase 2.\n"
            "Pairs flagged by fewer judges (but at least one) are disputed → the foreman "
            "re-examines them (phase 2.5).")
        self.jury_threshold_spin.setStyleSheet(
            "QSpinBox { background-color: #2d2d33; color: #f2f4f8; border: 1px solid #3a3a42;"
            " border-radius: 4px; padding: 3px 6px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        jury_row = QHBoxLayout()
        jury_label = QLabel("Consensus threshold (judges)")
        jury_label.setStyleSheet("color: #b8bfcc; border: none;")
        jury_row.addWidget(jury_label)
        jury_row.addWidget(self.jury_threshold_spin)
        jury_row.addStretch()
        qa_layout.addLayout(jury_row)

        jury_hint_top = QLabel(
            "Judges (1..4). Judge #1 = the primary QA auditor and foreman — edit its provider/model "
            "right in the table (live model list; type '/' after the id for a reasoning level). "
            "Add extra judges to vote on every flagged pair; a pair is applied only on consensus.")
        jury_hint_top.setStyleSheet("font-size: 11px; color: #64748b; border: none;")
        jury_hint_top.setWordWrap(True)
        qa_layout.addWidget(jury_hint_top)

        self.judges_table = QTableWidget(0, 8)
        self.judges_table.setHorizontalHeaderLabels(
            ["Enabled", "Name", "Provider", "Base URL", "API key", "Model", "Temperature", "Test"])
        _jt_hdr = self.judges_table.horizontalHeader()
        _jt_hdr.setStretchLastSection(False)
        self.judges_table.setColumnWidth(0, 46)
        self.judges_table.setColumnWidth(1, 100)
        self.judges_table.setColumnWidth(2, 165)
        self.judges_table.setColumnWidth(3, 110)
        self.judges_table.setColumnWidth(4, 90)
        self.judges_table.setColumnWidth(6, 78)
        self.judges_table.setColumnWidth(7, 86)
        _jt_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        _jt_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        _jt_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.judges_table.verticalHeader().setVisible(False)
        self.judges_table.setAlternatingRowColors(True)
        self.judges_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.judges_table.setStyleSheet(
            "QTableWidget { background-color: #1e1e24; alternate-background-color: #232329;"
            " border: 1px solid #2d2d30; border-radius: 6px; gridline-color: #2d2d30; }"
            "QHeaderView::section { background-color: #2d2d33; color: #b8bfcc; padding: 4px;"
            " border: none; }"
            "QCheckBox { color: #f2f4f8; }")
        self.judges_table.setMinimumHeight(190)
        self._judge_loaders = {}
        self._judge_orig_cmodel = {}
        self._judges_load_from_config()
        qa_layout.addWidget(self.judges_table)

        jury_btn_row = QHBoxLayout()
        self.btn_judge_add = QPushButton("Add judge")
        self.btn_judge_add.setEnabled(self.cb_qa_enabled.isChecked())
        self.btn_judge_add.clicked.connect(lambda: self._judges_add_row())
        self.btn_judge_del = QPushButton("Remove selected judge")
        self.btn_judge_del.setEnabled(self.cb_qa_enabled.isChecked())
        self.btn_judge_del.clicked.connect(self._judges_del_selected)
        jury_btn_row.addWidget(self.btn_judge_add)
        jury_btn_row.addWidget(self.btn_judge_del)
        jury_btn_row.addStretch()
        qa_layout.addLayout(jury_btn_row)

        jury_hint = QLabel(
            "Judge #1 is always the primary and the foreman (its effort is raised one step for "
            "disputed pairs). Extra judges: leave the API key empty to use that provider's key pool "
            "from the main screen. In any Model field type '/' after the id for a reasoning level "
            "(e.g. gpt-5/low). A dead judge's votes are excluded automatically, the run continues.")
        jury_hint.setStyleSheet("font-size: 11px; color: #64748b; border: none;")
        jury_hint.setWordWrap(True)
        qa_layout.addWidget(jury_hint)
        # --- end ТЗ-Жюри widgets ---------------------------------------

        qa_hint = QLabel("A second model re-reads every translated pair before writing ru_ru: hard errors are retranslated, safe terminology fixes are applied, glossary terms are learned. Skips silently if no keys or unsupported provider.")
        qa_hint.setStyleSheet("font-size: 11px; color: #64748b; border: none;")
        qa_hint.setWordWrap(True)
        qa_layout.addWidget(qa_hint)

        self.cb_qa_enabled.toggled.connect(self._on_qa_enabled_toggled)
        self.layout.addWidget(qa_frame)

        filters_frame = QFrame(self)
        filters_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        filters_layout = QVBoxLayout(filters_frame)
        filters_layout.setContentsMargins(12, 12, 12, 12)
        filters_layout.setSpacing(8)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(20)
        self.cb_titles = QCheckBox("Translate Titles")
        self.cb_titles.setChecked(True)
        self.cb_subs = QCheckBox("Translate Subtitles")
        self.cb_subs.setChecked(True)
        self.cb_desc = QCheckBox("Translate Descriptions")
        self.cb_desc.setChecked(True)
        filters_row.addWidget(self.cb_titles)
        filters_row.addWidget(self.cb_subs)
        filters_row.addWidget(self.cb_desc)
        filters_row.addStretch()
        filters_layout.addLayout(filters_row)
        self.layout.addWidget(filters_frame)

        ui_settings_frame = QFrame(self)
        ui_settings_frame.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #2d2d30; border-radius: 8px; }")
        ui_settings_layout = QVBoxLayout(ui_settings_frame)
        ui_settings_layout.setContentsMargins(12, 12, 12, 12)
        ui_settings_layout.setSpacing(8)

        lang_layout = QHBoxLayout()
        self.ui_lang_label = QLabel("UI Language")
        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.addItems(["English", "Русский", "Español", "Deutsch", "Français", "Português (BR)", "简体中文"])
        saved_lang = self.settings.value("ui_language", "English")
        idx = self.ui_lang_combo.findText(saved_lang)
        if idx >= 0:
            self.ui_lang_combo.setCurrentIndex(idx)
        lang_layout.addWidget(self.ui_lang_label)
        lang_layout.addWidget(self.ui_lang_combo)
        lang_layout.addStretch()
        ui_settings_layout.addLayout(lang_layout)

        line_ui = QFrame()
        line_ui.setFrameShape(QFrame.Shape.HLine)
        line_ui.setStyleSheet("background-color: #2d2d30; max-height: 1px; border: none;")
        ui_settings_layout.addWidget(line_ui)

        self.cb_resource_pack = QCheckBox("Resource Pack Mode (Isolate JSONs)")
        self.cb_resource_pack.setEnabled(True)
        self.cb_resource_pack.setChecked(self.config.resource_pack_mode)
        self.cb_resource_pack.toggled.connect(self._on_rp_mode_toggled)
        ui_settings_layout.addWidget(self.cb_resource_pack)

        self.resource_pack_desc = QLabel("Saves KubeJS/JSON translations into a clean standalone Resource Pack. WARNING: Some modpacks (like KubeJS in ATM9) ignore resource packs for script translations. If translations don't load in-game, disable this mode to translate directly in-place.")
        self.resource_pack_desc.setWordWrap(True)
        self.resource_pack_desc.setStyleSheet("font-size: 11px; color: #64748b; border: none; margin-left: 20px;")
        ui_settings_layout.addWidget(self.resource_pack_desc)
        self.layout.addWidget(ui_settings_frame)
        self.layout.addStretch()

    def _on_rp_mode_toggled(self, checked):
        self.config.resource_pack_mode = checked
        self.config.save_to_settings()

    # --- Utility model (glossary pre-scan) ---------------------------
    def _utility_keys_for(self, provider: str):
        """Keys for the utility provider's model list: its own pool."""
        return self.config.get_api_keys(provider) if provider else []

    def _on_utility_provider_changed(self, index):
        provider = self.utility_provider_combo.currentData() or ""
        if getattr(self, "_utility_loader", None):
            self._utility_loader.cancelled = True
        self.utility_model_box.blockSignals(True)
        self.utility_model_box.clear()
        if not provider or "Google Translate" in provider or provider == "Mixed Providers":
            self.utility_model_box.setEnabled(False)
            self.utility_completer.setModel(QStringListModel([]))
            ph = ("Utility model (same as main)" if not provider
                  else ("Not needed (free engine)" if "Google Translate" in provider
                        else "Defined per key in pool"))
            self.utility_model_box.setPlaceholderText(ph)
            self.utility_model_box.lineEdit().setPlaceholderText(ph)
        else:
            self.utility_model_box.setEnabled(True)
            ph = "Utility model (empty = same as main)"
            self.utility_model_box.setPlaceholderText(ph)
            self.utility_model_box.lineEdit().setPlaceholderText(ph)
            self.utility_model_box.addItem("Loading live models...")
            self.utility_completer.setModel(QStringListModel(["Loading live models..."]))
            keys = self._utility_keys_for(provider)
            key = keys[0] if keys else None
            loader = _track_qthread(ModelLoader(provider, key, 0, None))
            self._utility_loader = loader
            loader.loaded.connect(self._on_utility_models_loaded)
            loader.finished.connect(lambda l=loader: self._cleanup_utility_loader(l))
            loader.start()

    def _cleanup_utility_loader(self, loader):
        if getattr(self, "_utility_loader", None) is loader:
            self._utility_loader = None

    # --- QA audit phase -----------------------------------------------------
    def _judge_item_text(self, r, c):
        it = self.judges_table.item(r, c)
        return (it.text() or "").strip() if it else ""

    def _judge_row_of_combo(self, combo):
        for r in range(self.judges_table.rowCount()):
            if self.judges_table.cellWidget(r, 2) is combo:
                return r
        return -1

    def _judge_row_of_lineedit(self, w):
        for r in range(self.judges_table.rowCount()):
            box = self.judges_table.cellWidget(r, 5)
            if box is not None and box.lineEdit() is w:
                return r
        return -1

    def _judges_load_from_config(self):
        """Rebuild the judges table: row 0 = the primary QA auditor
        (config.qa_provider / config.qa_model), rows 1..3 = extra judges
        from config.qa_judges."""
        self.judges_table.setRowCount(0)
        self._judge_loaders = {}
        self._judge_orig_cmodel = {}
        # Primary row's own overrides persisted under qa_judge1 (dict):
        # api_key / base_url / temperature — empty means "pool defaults".
        j1 = {}
        raw1 = getattr(self.config, "qa_judge1", "") or ""
        if isinstance(raw1, str) and raw1.strip():
            try:
                parsed = json.loads(raw1)
                if isinstance(parsed, dict):
                    j1 = parsed
            except (ValueError, TypeError):
                j1 = {}
        elif isinstance(raw1, dict):
            j1 = raw1
        self._judges_add_row(
            primary=True,
            provider=(getattr(self.config, "qa_provider", "") or "").strip(),
            model=(getattr(self.config, "qa_model", "") or "").strip(),
            base_url=str(j1.get("base_url") or ""),
            api_key=str(j1.get("api_key") or ""),
            temperature=j1.get("temperature"))
        raw = getattr(self.config, "qa_judges", "") or ""
        judges = []
        if isinstance(raw, str) and raw.strip():
            try:
                judges = json.loads(raw)
            except (ValueError, TypeError):
                judges = []
        elif isinstance(raw, list):
            judges = raw
        for j in (judges or [])[:3]:
            if not isinstance(j, dict):
                continue
            self._judges_add_row(
                enabled=bool(j.get("enabled", True)),
                name=str(j.get("name") or ""),
                provider=str(j.get("provider") or ""),
                base_url=str(j.get("base_url") or ""),
                api_key=str(j.get("api_key") or ""),
                model=str(j.get("model") or ""),
                temperature=j.get("temperature"))
        if self.cb_qa_enabled.isChecked():
            for r in range(self.judges_table.rowCount()):
                self._judge_reload_models(r)

    def _judges_add_row(self, enabled=True, name="", provider="",
                        base_url="", api_key="", model="", temperature=None,
                        primary=False):
        """Append one judge row. Row 0 (primary) edits the QA provider and
        model; its keys/base URL come from the main screen pools, so those
        cells stay read-only."""
        t = self.judges_table
        if t.rowCount() >= 4:
            return
        r = t.rowCount()
        t.insertRow(r)
        cb = QCheckBox()
        cb.setChecked(True if primary else bool(enabled))
        if primary:
            cb.setEnabled(False)
            cb.setToolTip("Judge #1 = primary auditor + foreman — always on while QA is enabled.")
        t.setCellWidget(r, 0, cb)
        name_item = QTableWidgetItem("j1 (primary QA model)" if primary
                                      else (name or f"j{r + 1}"))
        # All cells are editable now — the primary judge is just row 0,
        # not a locked summary of the main screen (user request: every
        # field must accept input).
        name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
        if primary:
            name_item.setToolTip("Judge #1 is built from this row's provider/model.")
        t.setItem(r, 1, name_item)
        # Provider combo: real provider list instead of raw text editing.
        prov_combo = QComboBox()
        prov_combo.setView(QListView())
        prov_combo.setEditable(False)
        from config import ConfigManager as _CM
        prov_combo.addItem("Same as utility (default)", "")
        for p in _CM.AVAILABLE_PROVIDERS:
            prov_combo.addItem(p, p)
        idx = prov_combo.findData(provider)
        prov_combo.setCurrentIndex(idx if idx >= 0 else 0)
        prov_combo.setStyleSheet(
            "QComboBox { background-color: #171920; border: 1px solid #2b2f3d;"
            " border-radius: 6px; padding: 4px 8px; color: #f2f4f8; }"
            "QComboBox:disabled { background-color: #14151a; color: #4b5263; }"
            "QComboBox QAbstractItemView { background-color: #171920; color: #f2f4f8;"
            " selection-background-color: #306fcb; selection-color: #ffffff; }")
        prov_combo.setToolTip(
            "Provider for this judge's audit requests.\n"
            "Keys: an empty API key takes this provider's pool from the main screen.")
        t.setCellWidget(r, 2, prov_combo)
        prov_combo.currentIndexChanged.connect(
            lambda _=None, c=prov_combo: self._judge_provider_changed(self._judge_row_of_combo(c)))
        # Base URL / API key cells — editable for every judge (row 0 too);
        # empty = take this provider's pool from the main screen.
        url_item = QTableWidgetItem(base_url or "")
        key_item = QTableWidgetItem(api_key or "")
        url_item.setFlags(url_item.flags() | Qt.ItemFlag.ItemIsEditable)
        key_item.setFlags(key_item.flags() | Qt.ItemFlag.ItemIsEditable)
        if primary:
            url_item.setToolTip("Empty = provider base URL; override here if needed.")
            key_item.setToolTip("Empty = this provider's key pool from the main screen.")
        else:
            key_item.setToolTip("Empty = use this provider's key pool from the main screen.")
        t.setItem(r, 3, url_item)
        t.setItem(r, 4, key_item)
        # Model combo: editable, ghost '/effort' suffix, live list per row.
        model_box = QComboBox()
        model_box.setEditable(True)
        model_box.setEnabled(self.cb_qa_enabled.isChecked())
        model_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        model_box.setLineEdit(GhostSuffixLineEdit("/low"))
        model_box.lineEdit().setPlaceholderText(
            "QA model (empty = same as utility)" if primary else "Model id")
        model_box.setStyleSheet(
            "QComboBox { background-color: #171920; border: 1px solid #2b2f3d;"
            " border-radius: 6px; padding: 4px 8px; color: #f2f4f8; }"
            "QComboBox:disabled { background-color: #14151a; color: #4b5263; }"
            "QComboBox QLineEdit { background-color: transparent; color: #f2f4f8; border: none; padding: 0; }"
            "QLineEdit:disabled { background-color: transparent; color: #4b5263; border: none; }")
        _comp = QCompleter(self)
        _comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        _comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        _comp.setFilterMode(Qt.MatchFlag.MatchContains)
        _comp.popup().setStyleSheet(STYLE_SHEET)
        model_box.setCompleter(_comp)
        if model:
            model_box.setCurrentText(model)
        model_box.lineEdit().textEdited.connect(
            lambda text, w=model_box.lineEdit(): self._on_judge_model_text_edited(
                self._judge_row_of_lineedit(w), text))
        t.setCellWidget(r, 5, model_box)
        # Temperature cell — editable for every judge; empty = the QA
        # temperature spin for row 0, None for extras.
        temp_val = temperature if isinstance(temperature, (int, float)) else ""
        titem = QTableWidgetItem("" if temp_val == "" else str(temp_val))
        titem.setFlags(titem.flags() | Qt.ItemFlag.ItemIsEditable)
        if primary:
            titem.setToolTip("Empty = the QA temperature setting above.")
        t.setItem(r, 6, titem)
        # ТЗ-v4 A4: per-row Test button — verifies this judge's key+model
        # (its own key, else the provider pool) with one test question.
        btn = QPushButton("Test")
        btn.setFixedHeight(24)
        btn.setEnabled(self.cb_qa_enabled.isChecked())
        btn.setToolTip("Verify this judge's key(s) and model with a test question.\n"
                       "An empty API key tests the provider's whole key pool.")
        btn.setStyleSheet(
            "QPushButton { background-color: #26304a; border: 1px solid #3b4a6b;"
            " border-radius: 6px; padding: 2px 8px; color: #dbe4f3; font-size: 11px; }"
            "QPushButton:disabled { background-color: #14151a; color: #4b5263; }")
        btn.clicked.connect(lambda _=False, b=btn: self._judge_test_row(b))
        t.setCellWidget(r, 7, btn)

    def _judge_test_row(self, btn):
        """ТЗ-v4 A4: test ONE judge row (its key or the provider pool)."""
        t = self.judges_table
        row = None
        for r in range(t.rowCount()):
            if t.cellWidget(r, 7) is btn:
                row = r
                break
        if row is None:
            return
        # Snapshot the row's settings BEFORE starting the worker (the user
        # may edit the row while the test runs).
        spec = self._judge_row_spec(row)
        if spec is None:
            btn.setText("…")
            btn.setToolTip("Nothing to test: set a model for this judge first.")
            return
        keys, provider, model, tag = spec
        specs = [(k, provider, model) for k in keys]
        if getattr(self, "_judge_test_workers", None) is None:
            self._judge_test_workers = {}
        old = self._judge_test_workers.get(row)
        if old is not None:
            old.cancelled = True
            old.quit()
        btn.setText("…")
        btn.setEnabled(False)
        worker = JudgeTestWorker(row, specs)
        self._judge_test_workers[row] = worker
        _track_qthread(worker)
        worker.finished_row.connect(self._on_judge_test_done)
        worker.start()

    def _judge_row_spec(self, row, require_enabled=False):
        """(keys, provider, model, tag) snapshot for the Test button; None
        when the row has no model to test (or is disabled and the caller
        only wants enabled rows)."""
        t = self.judges_table
        if row < 0 or row >= t.rowCount():
            return None
        cb = t.cellWidget(row, 0)
        if require_enabled and cb is not None and not cb.isChecked():
            return None
        prov_combo = t.cellWidget(row, 2)
        provider = ((prov_combo.currentData() or "") if prov_combo is not None else "").strip()
        if row == 0:
            model = self.judge1_model()
        else:
            box = t.cellWidget(row, 5)
            model = ((box.currentText() or "").strip() if box is not None
                     else self._judge_item_text(row, 5))
        if not model or model in ("Loading live models...", "Enter model name manually"):
            return None
        api_key = self._judge_item_text(row, 4)
        keys = [api_key] if api_key else self._judge_keys_for(provider)
        keys = [k for k in keys if k]
        if not keys:
            return None
        tag = "j1" if row == 0 else (self._judge_item_text(row, 1) or f"j{row + 1}")
        return keys, provider, model, tag

    def _on_judge_test_done(self, row, results):
        """Test button result: OK/FAIL label + tooltip with per-key details."""
        t = self.judges_table
        btn = t.cellWidget(row, 7)
        if btn is None:
            return
        btn.setEnabled(self.cb_qa_enabled.isChecked())
        btn.setText("Test")
        if not results:
            btn.setToolTip("No answer — the test failed to run (see app.log).")
            return
        ok = sum(1 for status, _ in results.values() if status == "Active")
        total = len(results)
        if ok == total:
            btn.setText("✓ OK")
            btn.setStyleSheet(
                "QPushButton { background-color: #1d3a29; border: 1px solid #2e6b45;"
                " border-radius: 6px; padding: 2px 8px; color: #a4e8bf; font-size: 11px; }"
                "QPushButton:disabled { background-color: #14151a; color: #4b5263; }")
        else:
            btn.setText(f"✗ {ok}/{total}")
            btn.setStyleSheet(
                "QPushButton { background-color: #3a1d1d; border: 1px solid #6b2e2e;"
                " border-radius: 6px; padding: 2px 8px; color: #e8a4a4; font-size: 11px; }"
                "QPushButton:disabled { background-color: #14151a; color: #4b5263; }")
        tag = ("j1" if row == 0 else (self._judge_item_text(row, 1) or f"j{row + 1}"))
        tip_lines = [f"Judge {tag} test results:"]
        for i, (key, (status, answer)) in enumerate(results.items(), 1):
            short = f"...{key[-4:]}" if len(key) > 8 else key
            line = f"[{i}] {short}: {status}"
            if answer:
                line += f" — {answer[:70]}"
            tip_lines.append(line)
        btn.setToolTip("\n".join(tip_lines))

    def _judges_del_selected(self):
        """Remove selected extra judges (row 0 = primary, never removed)."""
        rows = sorted({i.row() for i in self.judges_table.selectedIndexes()}, reverse=True)
        for r in rows:
            if r <= 0:
                continue
            self.judges_table.removeRow(r)
        # Rows shifted: cancel stale loaders and reset per-row caches.
        for loader in list(getattr(self, "_judge_loaders", {}).values()):
            loader.cancelled = True
        self._judge_loaders = {}
        self._judge_orig_cmodel = {}
        # ТЗ-v4 A4: rows shifted — cancel all in-flight row tests too (a
        # finished_row signal would otherwise land on the wrong button).
        for worker in list(getattr(self, "_judge_test_workers", {}).values()):
            worker.cancelled = True
            worker.quit()
        self._judge_test_workers = {}

    def _judges_collect(self):
        """Extra judges (rows 1..3) as dicts for config.qa_judges. Row 0 is
        the primary QA model — synced separately into config.qa_provider /
        config.qa_model via judge1_provider() / judge1_model()."""
        out = []
        for r in range(1, self.judges_table.rowCount()):
            prov = self.judges_table.cellWidget(r, 2)
            box = self.judges_table.cellWidget(r, 5)
            cb = self.judges_table.cellWidget(r, 0)
            model = (box.currentText() or "").strip() if box is not None else self._judge_item_text(r, 5)
            if not model or model in ("Loading live models...", "Enter model name manually"):
                continue
            temp_raw = self._judge_item_text(r, 6)
            try:
                temp = float(temp_raw) if temp_raw not in ("", "None") else None
            except ValueError:
                temp = None
            api_key = self._judge_item_text(r, 4)
            if api_key:
                api_key = _sanitize_judge_key(api_key, f"row {r}")
            out.append({
                "name": self._judge_item_text(r, 1) or f"j{r + 1}",
                "provider": (prov.currentData() or "") if prov is not None else self._judge_item_text(r, 2),
                "base_url": self._judge_item_text(r, 3),
                "api_key": api_key,
                "model": model,
                "temperature": temp,
                "enabled": bool(cb.isChecked()) if cb is not None else True,
            })
        return out[:3]

    def judge1_provider(self):
        """Judge #1 provider (row 0 of the table) for the main sync."""
        prov = self.judges_table.cellWidget(0, 2)
        return ((prov.currentData() or "") if prov is not None else "").strip()

    def judge1_model(self):
        """Judge #1 model text (row 0 of the table) for the main sync."""
        box = self.judges_table.cellWidget(0, 5)
        text = ((box.currentText() or "") if box is not None else "").strip()
        if text in ("Loading live models...", "Enter model name manually"):
            return ""
        return text

    def judge1_overrides(self):
        """Judge #1 row overrides: api_key / base_url / temperature.
        Only non-empty values are stored; empty = pool defaults.
        The API key passes the central sanitizer (ТЗ-v4 A1)."""
        out = {}
        api_key = self._judge_item_text(0, 4)
        if api_key:
            api_key = _sanitize_judge_key(api_key, "judge1")
        if api_key:
            out["api_key"] = api_key
        base_url = self._judge_item_text(0, 3)
        if base_url:
            out["base_url"] = base_url
        temp_raw = self._judge_item_text(0, 6)
        if temp_raw not in ("", "None"):
            try:
                out["temperature"] = float(temp_raw)
            except ValueError:
                pass
        return out

    def _on_qa_enabled_toggled(self, checked):
        self.cb_qa_update_glossary.setEnabled(checked)
        self.qa_batch_spin.setEnabled(checked)
        self.qa_temp_spin.setEnabled(checked)
        self.cb_qa_dataset.setEnabled(checked)
        self.cb_qa_vcache.setEnabled(checked)
        self.jury_threshold_spin.setEnabled(checked)
        self.btn_judge_add.setEnabled(checked)
        self.btn_judge_del.setEnabled(checked)
        self.judges_table.setEnabled(checked)
        # Grey the model boxes while off, restore live lists when on.
        for r in range(self.judges_table.rowCount()):
            self._judge_reload_models(r)
        # save immediately so the choice survives a crash/close
        self.config.qa_enabled = checked
        self.config.save_to_settings()

    def _judge_keys_for(self, provider, api_key=""):
        """Key for this row's model list: its own key, else the provider pool."""
        if api_key:
            return [api_key]
        return self.config.get_api_keys(provider) if provider else []

    def _judge_test_specs(self):
        """(key, provider, model, tag) specs for the Test Keys button.

        Same resolution a real QA run uses (core.parse_qa_judges): the row's
        own API key first, else that provider's pool from the main screen.
        Disabled rows and rows without a model are skipped; keys that only
        differ by an effort suffix are not re-tested (same key+model).
        """
        specs = []
        for r in range(self.judges_table.rowCount()):
            spec = self._judge_row_spec(r, require_enabled=True)
            if spec is None:
                continue
            keys, provider, model, tag = spec
            for k in keys:
                specs.append((k, provider, model, tag))
        return specs

    def _judge_provider_changed(self, row):
        self._judge_reload_models(row)

    def _judge_reload_models(self, row):
        """Refresh one row's model combo for its provider: grey it out for
        utility/free/per-key providers, load the live model list otherwise
        (the row's own key first, else the provider pool)."""
        t = self.judges_table
        if row < 0 or row >= t.rowCount():
            return
        prov_combo = t.cellWidget(row, 2)
        box = t.cellWidget(row, 5)
        if prov_combo is None or box is None:
            return
        provider = prov_combo.currentData() or ""
        api_key = self._judge_item_text(row, 4)
        base_url = self._judge_item_text(row, 3)
        old = self._judge_loaders.get(row)
        if old is not None:
            old.cancelled = True
            self._judge_loaders.pop(row, None)
        box.blockSignals(True)
        keep = (box.currentText() or "").strip()
        box.clear()
        if not provider or "Google Translate" in provider or provider == "Mixed Providers":
            # Same as utility / free engine / per-key pool: no model list.
            box.setEnabled(False)
            ph = ("Model (same as utility)" if not provider
                  else ("Not needed (free engine)" if "Google Translate" in provider
                        else "Defined per key in pool"))
            box.setPlaceholderText(ph)
            box.lineEdit().setPlaceholderText(ph)
            comp = box.completer()
            if comp is not None:
                comp.setModel(QStringListModel([]))
        elif not self.cb_qa_enabled.isChecked():
            box.setEnabled(False)
        else:
            box.setEnabled(True)
            ph = "QA model (empty = same as utility)" if row == 0 else "Model id"
            box.setPlaceholderText(ph)
            box.lineEdit().setPlaceholderText(ph)
            keys = self._judge_keys_for(provider, api_key)
            key = keys[0] if keys else None
            loader = _track_qthread(ModelLoader(provider, key, 0, base_url or None))
            self._judge_loaders[row] = loader
            loader.loaded.connect(
                lambda models, err="", lid=0, lp="", r=row, l=loader:
                    self._on_judge_models_loaded(r, l, models, err, lid, lp))
            loader.finished.connect(lambda l=loader, r=row: self._judge_cleanup_loader(r, l))
            loader.start()
        if keep:
            box.setCurrentText(keep)
        box.blockSignals(False)

    def _judge_cleanup_loader(self, row, loader):
        if self._judge_loaders.get(row) is loader:
            self._judge_loaders.pop(row, None)

    def _on_judge_models_loaded(self, row, loader, models, error_msg="",
                                loader_id=0, loader_provider=""):
        if self._judge_loaders.get(row) is not loader:
            return  # stale loader: row deleted or provider changed meanwhile
        t = self.judges_table
        if row >= t.rowCount():
            return
        box = t.cellWidget(row, 5)
        if box is None:
            return
        box.blockSignals(True)
        keep = (box.currentText() or "").strip()
        box.clear()
        filtered = []
        if models:
            for m in models:
                m_low = m.lower()
                if not any(x in m_low for x in ["whisper", "tts", "stablediffusion", "dall-e", "embed", "moderation", "davinci", "babbage", "curie", "ada", "guard", "shield", "rerank", "classify", "classifier", "nli", "sentiment", "bert"]):
                    filtered.append(m)
        if filtered:
            box.addItems(filtered)
            comp = box.completer()
            if comp is not None:
                comp.setModel(QStringListModel(filtered))
        else:
            box.addItem("Enter model name manually")
        if keep:
            box.setCurrentText(keep)
        box.blockSignals(False)

    def _on_judge_model_text_edited(self, row, text):
        """Same live '/' hint as the main model box, per judge row."""
        t = self.judges_table
        if row < 0 or row >= t.rowCount():
            return
        box = t.cellWidget(row, 5)
        comp = box.completer() if box is not None else None
        if comp is None:
            return
        base, _, tail = text.rpartition("/")
        tail_l = tail.strip().lower()
        is_level_typing = bool(base.strip()) and (tail_l == "" or any(l.startswith(tail_l) for l in REASONING_EFFORT_LEVELS))
        if is_level_typing:
            if row not in self._judge_orig_cmodel:
                self._judge_orig_cmodel[row] = comp.model()
            comp.setModel(QStringListModel([f"{base.strip()}/{l}" for l in REASONING_EFFORT_LEVELS]))
            comp.setCompletionPrefix(text)
            comp.complete()
        elif row in self._judge_orig_cmodel:
            comp.setModel(self._judge_orig_cmodel.pop(row))

    def _on_utility_model_text_edited(self, text):
        """Same live hint as the main model box: typing "model/" swaps the
        completer to reasoning-level suggestions, anything else restores the
        normal model list."""
        base, _, tail = text.rpartition("/")
        tail_l = tail.strip().lower()
        is_level_typing = bool(base.strip()) and (tail_l == "" or any(l.startswith(tail_l) for l in REASONING_EFFORT_LEVELS))
        if is_level_typing:
            if self._utility_orig_completer_model is None:
                self._utility_orig_completer_model = self.utility_completer.model()
            self.utility_completer.setModel(QStringListModel([f"{base.strip()}/{l}" for l in REASONING_EFFORT_LEVELS]))
            self.utility_completer.setCompletionPrefix(text)
            self.utility_completer.complete()
        elif self._utility_orig_completer_model is not None:
            self.utility_completer.setModel(self._utility_orig_completer_model)
            self._utility_orig_completer_model = None

    def _on_utility_models_loaded(self, models, error_msg="", loader_id=0, loader_provider=""):
        if getattr(self, "_utility_loader", None) is None:
            return
        provider = self.utility_provider_combo.currentData() or ""
        if loader_provider and provider and loader_provider != provider:
            return
        self.utility_model_box.blockSignals(True)
        self.utility_model_box.clear()
        filtered = []
        if models:
            for m in models:
                m_low = m.lower()
                if not any(x in m_low for x in ["whisper", "tts", "stablediffusion", "dall-e", "embed", "moderation", "davinci", "babbage", "curie", "ada", "guard", "shield", "rerank", "classify", "classifier", "nli", "sentiment", "bert"]):
                    filtered.append(m)
        if filtered:
            self.utility_model_box.addItems(filtered)
            self.utility_completer.setModel(QStringListModel(filtered))
        else:
            self.utility_model_box.addItem("Enter model name manually")
            self.utility_completer.setModel(QStringListModel([]))
        # restore the saved model choice now that the list is loaded
        saved = getattr(self, "_utility_saved_model", "") or ""
        if saved:
            self.utility_model_box.setCurrentText(saved)
        self.utility_model_box.blockSignals(False)


class CacheHealerWorker(QThread):
    """Auto-Fix healer: re-translates garbage cache entries (wrong-language
    text, CJK leaks, mixed-alphabet words) with the ACTIVE provider/model."""

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # done, total
    finished_heal = pyqtSignal(int, int, list)  # healed, failed, reasons

    def __init__(self, violations, provider, model, keys, custom_context, target_lang_name, target_lang_code, custom_base_url=None, temperature=0.1, batch_size=50, modpack=None, parent=None):
        super().__init__(parent)
        self.violations = violations  # list of (orig, trans, reason, modpack)
        self.provider = provider
        self.model = model
        self.keys = keys
        self.custom_context = custom_context
        self.target_lang_name = target_lang_name
        self.target_lang_code = target_lang_code
        self.custom_base_url = custom_base_url
        self.temperature = temperature
        self.batch_size = batch_size
        self.modpack = modpack
        self.cache = TranslationCache(target_lang_code=target_lang_code)
        self.is_aborted = False

    def run(self):
        healed, failed = 0, 0
        reasons_seen = []
        try:
            from core import set_temperature, get_target_script, script_violation_reason, UnifiedTranslator
            set_temperature(self.temperature)
            script = get_target_script(self.target_lang_code)
            translator = UnifiedTranslator(
                self.keys, self.provider, self.model,
                self.custom_context, self.target_lang_name,
                self.target_lang_code, batch_size=self.batch_size,
                custom_base_url=self.custom_base_url,
            )
            total = len(self.violations)
            done = 0
            for i in range(0, total, self.batch_size):
                if self.is_aborted:
                    break
                chunk = self.violations[i:i + self.batch_size]
                texts = [v[0] for v in chunk]
                try:
                    results = asyncio.run(translator.translate(
                        texts, self.log.emit, None, self.custom_context))
                except Exception as e:
                    self.log.emit(f"Auto-Fix heal: batch failed: {e}")
                    results = None
                if results is None or len(results) != len(chunk):
                    failed += len(chunk)
                    done += len(chunk)
                    self.progress.emit(done, total)
                    continue
                updates = {}
                for (orig, bad_trans, reason, mp), new_trans in zip(chunk, results):
                    if not isinstance(new_trans, str) or not new_trans:
                        failed += 1
                        continue
                    if new_trans == orig and reason != 'not_target_lang':
                        # LLM returned the source unchanged: keep the old
                        # translation rather than poisoning with identity
                        failed += 1
                        continue
                    if script_violation_reason(new_trans, script):
                        # LLM produced garbage again - keep the old value
                        failed += 1
                        reasons_seen.append(reason)
                        continue
                    updates[orig] = new_trans
                    healed += 1
                if updates:
                    self.cache.update_records(updates)
                done += len(chunk)
                self.progress.emit(done, total)
        except Exception as e:
            self.log.emit(f"Auto-Fix heal error: {e}")
        finally:
            self.cache.close()
            self.finished_heal.emit(healed, failed, reasons_seen)


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
            "Portuguese (pt_br)", "Japanese (ja_jp)", "Korean (ko_kr)",
            "Ukrainian (uk_ua)"
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

        self.autofix_btn = QPushButton("Auto-Fix")
        self.autofix_btn.clicked.connect(self._on_autofix_cache)
        button_layout.addWidget(self.autofix_btn)

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

    def _on_autofix_cache(self):
        # Stage 1: repair broken technical syntax (placeholders/macros/links)
        try:
            fixed = self.cache.autofix_records()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Auto-fix error: {e}")
            return

        # Stage 2: find garbage translations (wrong language / CJK leaks /
        # mixed-alphabet words) and offer to re-translate them with the
        # ACTIVE provider/model from the workspace tab
        try:
            from core import get_target_script
            lang_text = self.lang_filter.currentText()
            _, lang_code = parse_target_lang(lang_text)
            script = get_target_script(lang_code)
            violations = self.cache.find_script_violations(script)
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Auto-fix scan failed: {repr(e)}")
            violations = []

        if not violations:
            self.offset = 0
            self.pending_updates.clear()
            self.pending_deletions.clear()
            self._load_data()
            if fixed:
                QMessageBox.information(self, "Auto-Fix", f"Repaired {fixed} cached translation(s). Cache is clean - no wrong-language garbage found.")
            else:
                QMessageBox.information(self, "Auto-Fix", "Cache is clean - no broken placeholders, no wrong-language garbage found.")
            return

        reason_names = {
            'garbage_chars': 'replacement/zero-width characters',
            'cjk_symbols': 'CJK symbols leaked into non-CJK text',
            'mixed_script': 'words mixing two alphabets (e.g. "Лимитite")',
            'not_target_lang': 'text is >=90% not in the target language',
        }
        summary_lines = [f"  {reason_names.get(r, r)}: {sum(1 for v in violations if v[2] == r)}" for r in dict.fromkeys(v[2] for v in violations)]
        total = len(violations)

        reply = QMessageBox.question(
            self,
            "Auto-Fix: garbage translations found",
            (f"Found {total} cached translation(s) that look like garbage:\n\n"
             + "\n".join(summary_lines)
             + f"\n\nRe-translate all {total} with your ACTIVE provider/model?"
                "\n(The old values will be replaced only when the new translation is clean.)"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        mw = getattr(self, 'main_window', None)
        if mw is None:
            QMessageBox.warning(self, "Auto-Fix", "Main window is not available - cannot heal the cache.")
            return

        prov = mw.config.provider
        model = mw.model_box.currentText() or ""
        custom_context = mw.settings_tab.context_in.text().strip()
        custom_url = mw.custom_base_url_edit.text() if prov in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)") else None
        temperature = mw.settings_tab.temperature_spin.value()
        batch_size = mw.settings_tab.batch_spin.value()
        keys = [k.strip() for k in mw.key_pool_edit.toPlainText().strip().splitlines() if k.strip()]

        if prov not in ("Google Translate (Free)", "Ollama (Local / Free)") and not keys:
            QMessageBox.warning(self, "Auto-Fix", "No API keys in the pool. Add keys on the Workspace tab first.")
            return
        if prov != "Google Translate (Free)" and not mw.is_model_valid():
            QMessageBox.warning(self, "Auto-Fix", "Please select a valid model on the Workspace tab first.")
            return

        lang_name, lang_code = parse_target_lang(self.lang_filter.currentText())

        self.autofix_btn.setEnabled(False)
        self.healer = _track_qthread(CacheHealerWorker(
            violations, prov, model, keys, custom_context,
            lang_name, lang_code, custom_base_url=custom_url,
            temperature=temperature, batch_size=batch_size,
        ))
        self.healer.log.connect(self._append_heal_log)
        self.healer.progress.connect(self._on_heal_progress)
        self.healer.finished_heal.connect(self._on_heal_finished)
        self.healer.start()

    def _append_heal_log(self, msg):
        logging.getLogger("snbt_localizer.gui").info(msg)

    def _on_heal_progress(self, done, total):
        self.autofix_btn.setText(f"Healing {done}/{total}...")

    def _on_heal_finished(self, healed, failed, reasons):
        self.autofix_btn.setEnabled(True)
        self.autofix_btn.setText("Auto-Fix")
        self.offset = 0
        self.pending_updates.clear()
        self.pending_deletions.clear()
        self._load_data()
        if failed:
            QMessageBox.warning(self, "Auto-Fix",
                                f"Healed {healed} translation(s); {failed} could not be healed (LLM returned the same garbage or empty text - those entries keep their old values).")
        else:
            QMessageBox.information(self, "Auto-Fix", f"Healed {healed} translation(s).")

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
    def __init__(self, provider, api_key=None, loader_id=0, custom_base_url=None):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.loader_id = loader_id
        self.custom_base_url = custom_base_url
        self.cancelled = False

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
                    ollama_base = (self.custom_base_url or "http://localhost:11434").rstrip('/')
                    resp = await client.get(f"{ollama_base}/v1/models", timeout=12.0)
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
                    resp = await client.get("https://api.cohere.com/v1/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m.get("name") or m.get("id") if isinstance(m, dict) else m for m in data.get("models", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Cohere API error {resp.status_code}: Invalid or missing API key"
                elif "OpenCode" in self.provider:
                    url = f"{get_base_url('OpenCode')}/models"
                    headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                    resp = await client.get(url, headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"OpenCode API error {resp.status_code}: Invalid or missing API key"
                elif "Crusoe" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get(f"{get_base_url('Crusoe Cloud')}/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"Crusoe API error {resp.status_code}: Invalid or missing API key"
                elif "RunInfra" in self.provider and self.api_key:
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    resp = await client.get(f"{get_base_url('RunInfra')}/models", headers=headers, timeout=12.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        models = [m["id"] for m in data.get("data", [])]
                    elif resp.status_code in (401, 403):
                        error_msg = f"RunInfra API error {resp.status_code}: Invalid or missing API key"
        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
        if not self.cancelled:
            self.loaded.emit(models, error_msg, self.loader_id, self.provider)

class JudgeTestWorker(QThread):
    """ТЗ-v4 A4: verify ONE judge row's key+model with a test question.

    Runs the same resolution a real QA run uses (the row's own API key,
    else the provider's pool) — each pool key gets its own verdict so an
    empty-key judge shows which pool keys are alive. Emits (row, results)
    where results maps key -> (status, answer).
    """
    finished_row = pyqtSignal(int, dict)

    def __init__(self, row, specs):
        super().__init__()
        self.row = row
        self.specs = specs  # [(key, provider, model), ...]
        self.cancelled = False

    def run(self):
        question = random.choice(TEST_QUESTIONS)
        results = {}
        try:
            for key, provider, model in self.specs:
                if self.cancelled:
                    return
                status, answer = asyncio.run(test_key_with_question(provider, key, model, question))
                if status == "Model Paused":
                    answer = (answer or "model paused on provider side")[:80]
                results[key] = (status, answer or "")
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Judge key test failed: {repr(e)}")
        if self.cancelled:
            return
        self.finished_row.emit(self.row, results)


class KeyVerifierWorker(QThread):
    verification_complete = pyqtSignal(dict, dict, str)

    def __init__(self, specs, show_provider=False, judge_specs=None):
        super().__init__()
        self.specs = specs
        self.judge_specs = judge_specs or []
        self.cancelled = False
        self.show_provider = show_provider

    def run(self):
        question = random.choice(TEST_QUESTIONS)
        results = {}
        answers = {}
        try:
            for key, provider, model in self.specs:
                if self.cancelled:
                    break
                status, answer = asyncio.run(test_key_with_question(provider, key, model, question))
                if status == "Model Paused":
                    # answer carries the provider's pause message; keep it short
                    answer = (answer or "model paused on provider side")[:80]
                if self.show_provider and provider != "Mixed Providers":
                    answer = f"[{provider}] {answer}" if answer else f"[{provider}]"
                if status == "Active":
                    balance = asyncio.run(fetch_provider_balance(provider, key))
                    if balance:
                        answer = f"{answer} | Balance: {balance}" if answer else f"Balance: {balance}"
                results[key] = status
                answers[key] = answer
            # Jury keys (j1..jN from the judges table): verified with each
            # judge's own model; the tag is shown instead of the key.
            self.judge_results = {}
            for key, provider, model, tag in self.judge_specs:
                if self.cancelled:
                    break
                status, answer = asyncio.run(test_key_with_question(provider, key, model, question))
                if status == "Model Paused":
                    answer = (answer or "model paused on provider side")[:80]
                if status == "Active":
                    balance = asyncio.run(fetch_provider_balance(provider, key))
                    if balance:
                        answer = f"{answer} | Balance: {balance}" if answer else f"Balance: {balance}"
                self.judge_results[tag] = (status, answer or "")
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Key verification failed: {repr(e)}")
        finally:
            # Always emit: otherwise the Test Keys button stays disabled forever
            self.verification_complete.emit(results, answers, question)

class Worker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal()
    progress_batch = pyqtSignal(int, int)
    chunk_progress = pyqtSignal(int, int, int, int)
    lines_translated = pyqtSignal(int, int)
    progress_state = pyqtSignal(int, int, str, int, int, float)

    def __init__(self, files, keys, provider, model, t_titles, t_subs, t_desc, custom_context="", policy="Complement (Дополнить)", target_lang="Russian (ru_ru)", concurrency=3, mixed_pool=None, batch_size=50, min_batch_size=1, max_concurrent_requests=10, temperature=0.1, modpack=None, custom_base_url=None, translator=None, cache=None, resource_pack_mode=False, prescan_params=None, qa_params=None):
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
        self.temperature = temperature
        self.modpack = modpack
        self.custom_base_url = custom_base_url
        self.translator = translator
        self.cache = cache
        self.resource_pack_mode = resource_pack_mode
        self.prescan_params = prescan_params
        self.qa_params = qa_params
        self.is_aborted = False
        self.is_paused = False
        self._total_strings = 0
        self._completed_strings = 0
        self._ema_speed = None
        self._files_last_time = {}
        self._files_last_strings = {}

    def run(self):
        try:
            from pathlib import Path
            from core import JSONManager, parse_target_lang, set_temperature

            # ТЗ-v4.5 fix: the QA scope belongs to the WHOLE run — the SNBT
            # batch AND the JSON/JSON5 phase below (and a JSON-only pack, where
            # Worker.process never runs). Opening it in process() left the
            # scope unopened for JSON-only packs and, worse, a nested
            # qa_run_open() there returned False and overwrote the owner flag,
            # so nothing ever closed the scope.
            from core import qa_run_open
            self._owns_qa_scope = qa_run_open()

            # Apply the GUI temperature setting to every provider payload.
            set_temperature(self.temperature)

            # --- Modpack glossary pre-scan (in Worker thread: own event loop) ---
            # GUI thread runs inside asyncio.run(main_async()) from cli.py --gui,
            # so asyncio.run() is illegal there. Here in the QThread it is fine.
            # Best-effort: a failed pre-scan never blocks the translation itself.
            if self.prescan_params and self.translator is not None:
                try:
                    from core import ensure_modpack_glossary
                    pp = self.prescan_params
                    self.log.emit("Glossary pre-scan: extracting recurring mod terms...")
                    glossary = asyncio.run(ensure_modpack_glossary(
                        pp["texts"],
                        pp["root"],
                        pp["keys"],
                        pp["provider"],
                        pp["model"],
                        pp["lang_name"],
                        mixed_pool=pp.get("mixed_pool"),
                        custom_base_url=pp.get("custom_base_url"),
                        logger=self.log.emit,
                        check_status=None,
                    ))
                    if glossary.terms:
                        self.translator.modpack_glossary_terms = glossary.terms
                        self.log.emit(f"Modpack glossary active: {len(glossary.terms)} terms pinned.")
                except Exception as e:
                    self.log.emit(f"Glossary pre-scan skipped: {e}")

            snbt_files = [f for f in self.files if str(f).endswith('.snbt') and not Path(f).is_dir()]
            json_files = [f for f in self.files if str(f).endswith('en_us.json')]
            # FTB Quests 26.x sentinel: directories named lang/en_us with .json5
            json5_dirs = [f for f in self.files if Path(f).is_dir() and Path(f).name == "en_us"]

            self.is_snbt_mode = bool(snbt_files)
            self.is_json_mode = bool(json_files or json5_dirs)

            if snbt_files:
                self.log.emit("Starting Quest translation (SNBT)...")
                original_files = self.files
                self.files = snbt_files
                asyncio.run(run_with_abort_watchdog(self.process(), lambda: self.is_aborted, self.log.emit))
                self.files = original_files

            # skip policy: SNBT files were skipped by design, JSON files must not
            # be sent to a "SKIP"-keyed translator either (it would 401 and
            # poison files with untranslated text)
            skip_mode = any(k == "SKIP" for k in (self.keys or []))
            json_targets = [(Path(f).parent.parent, "JSON") for f in json_files]
            # lang/en_us directory → JSONManager scans it as a lang dir itself
            json_targets += [(Path(f).parent.parent, "JSON5") for f in json5_dirs]
            if json_targets and not self.is_aborted and not skip_mode:
                self.log.emit("Starting Language translation (JSON)...")
                _, target_lang_code = parse_target_lang(self.target_lang)
                processed_dirs = set()
                for base_dir, kind in json_targets:
                    if base_dir in processed_dirs:
                        continue
                    processed_dirs.add(base_dir)
                    def json_progress(processed, total):
                        self.progress_state.emit(0, 0, "Translating KubeJS JSON strings", processed, total, 0)
                        self.progress_batch.emit(processed, total)

                    manager = JSONManager(
                        base_dir,
                        target_lang_code,
                        self.translator,
                        self.cache,
                        self.modpack,
                        self.policy,
                        resource_pack_mode=self.resource_pack_mode,
                        progress_callback=json_progress,
                        batch_size=self.batch_size,
                        min_batch_size=self.min_batch_size,
                        qa_params=self.qa_params
                    )
                    asyncio.run(run_with_abort_watchdog(manager.process(
                        log_callback=self.log.emit,
                        check_status=self.check_status
                    ), lambda: self.is_aborted, self.log.emit))
        except asyncio.CancelledError:
            self.log.emit("Translation process was aborted by user.")
            logging.getLogger("snbt_localizer.gui").warning("Translation aborted: in-flight requests cancelled.")
        except AbortException as e:
            self.log.emit(str(e) if str(e) else "Translation process was aborted by user.")
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            logging.getLogger("snbt_localizer.gui").error(f"Unexpected error: {e}")
        finally:
            # ТЗ-v4 C8/C9: ONE run-wide [QA] total + jury line for the whole
            # run — the SNBT batch AND every JSON/JSON5 lang dir. This is the
            # only place the GUI closes the scope (ТЗ-v4.5 fix).
            try:
                from core import qa_run_close
                qa_run_close(getattr(self, "_owns_qa_scope", False),
                             logger=lambda msg: (
                                 self.log.emit(msg),
                                 logging.getLogger("snbt_localizer.core").info(msg)))
            except Exception:
                pass
            if self.cache:
                self.cache.close()
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

        reset_request_timeout()
        # ТЗ-health: one batch run = one health window (stats + benching).
        # ТЗ-v4.5 fix: the QA scope is owned by Worker.run (it spans the JSON
        # phase too) — this method must NOT open or close one.
        from core import health_reset, health_mark_start
        health_reset()
        health_mark_start()
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
            translator=self.translator,
            batch_size=self.batch_size,
            min_batch_size=self.min_batch_size,
            max_concurrent_requests=self.max_concurrent_requests,
            modpack=self.modpack,
            custom_base_url=self.custom_base_url,
            qa_params=self.qa_params
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
                file_total_strings = m.count_translatable_strings(f, self.t_titles, self.t_subs, self.t_desc)
                file_start = time.time()
                self._files_last_time[idx] = time.time()
                self._files_last_strings[idx] = 0
                await m.process_file(
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
        except AbortException as e:
            self.log.emit(str(e) if str(e) else "Translation process was aborted by user.")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            from core import close_shared_httpx_clients
            try:
                # ТЗ-health п.4: per-key [POOL] stats into the GUI console
                # and app.log at the end of the SNBT batch.
                # ТЗ-v4.5 fix: the QA scope stays OPEN across the JSON phase —
                # Worker.run closes it once, after every phase is done.
                from core import health_summary_lines
                for line in health_summary_lines():
                    self.log.emit(line)
                    logging.getLogger("snbt_localizer.core").info(line)
            except Exception:
                pass
            try:
                await close_shared_httpx_clients()
            except Exception:
                pass
            m.close()

class JSONWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal()
    progress_batch = pyqtSignal(int, int)

    def __init__(self, base_dir, target_lang_code, translator, cache, modpack, policy, concurrency, batch_size, min_batch_size, max_concurrent_requests, resource_pack_mode=False, qa_params=None):
        super().__init__()
        self.base_dir = base_dir
        self.target_lang_code = target_lang_code
        self.translator = translator
        self.cache = cache
        self.modpack = modpack
        self.policy = policy
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.min_batch_size = min_batch_size
        self.max_concurrent_requests = max_concurrent_requests
        self.resource_pack_mode = resource_pack_mode
        # ТЗ-v4.5 fix: process() reads self.qa_params (it forwards the audit
        # config to JSONManager); the constructor never stored it, so any
        # caller hit AttributeError on the first run.
        self.qa_params = qa_params
        self.is_aborted = False
        self.is_paused = False

    async def check_status(self):
        while self.is_paused:
            await asyncio.sleep(0.1)
        if self.is_aborted:
            raise AbortException()

    def run(self):
        try:
            asyncio.run(run_with_abort_watchdog(self.process(), lambda: self.is_aborted, self.log.emit))
        except asyncio.CancelledError:
            self.log.emit("Translation process was aborted by user.")
        except AbortException as e:
            self.log.emit(str(e) if str(e) else "Translation process was aborted by user.")
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            logging.getLogger("snbt_localizer.gui").error(f"Unexpected error: {e}")
        finally:
            self.done.emit()

    async def process(self):
        manager = JSONManager(
            self.base_dir,
            self.target_lang_code,
            self.translator,
            self.cache,
            self.modpack,
            self.policy,
            resource_pack_mode=self.resource_pack_mode,
            progress_callback=lambda cur, tot: self.progress_batch.emit(cur, tot),
            batch_size=self.batch_size,
            min_batch_size=self.min_batch_size,
            qa_params=self.qa_params
        )
        await manager.process(
            log_callback=self.log.emit,
            check_status=self.check_status
        )

class GhostSuffixLineEdit(QLineEdit):
    """Editable combo line edit that paints a translucent suffix hint.

    When the typed model id has no reasoning-effort suffix yet, a
    semi-transparent "/low" is painted right after the text — an IDE-style
    ghost suggesting the optional "model/level" syntax.
    """
    GHOST = "/low"

    def _ghost_visible(self) -> bool:
        text = self.text().strip()
        if not text or text in ("Loading live models...", "None (Free Engine)", "Defined per key in pool"):
            return False
        base, _, tail = text.rpartition("/")
        if base.strip() and tail.strip().lower() in REASONING_EFFORT_LEVELS:
            return False  # suffix already typed
        return True

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._ghost_visible():
            return
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.displayText())
        margins = self.textMargins()
        x = margins.left() + 8 + text_w
        ghost_w = fm.horizontalAdvance(self.GHOST)
        if x + ghost_w > self.width() - margins.right() - 6:
            return  # not enough room left in the field
        p = QPainter(self)
        p.setPen(QColor(160, 165, 180, 110))
        p.setFont(self.font())
        y = (self.height() - fm.height()) // 2 + fm.ascent()
        p.drawText(int(x), int(y), self.GHOST)


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SNBT AI Localizer v{APP_VERSION}")
        icon_path = os.path.normpath(get_resource_path("resources/logo.png"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(750, 680)
        self.setStyleSheet(STYLE_SHEET)
        
        self._is_initializing = True
        self._is_syncing_language = False
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
        self.model_reload_timer = QTimer(self)
        self.model_reload_timer.setSingleShot(True)
        self.model_reload_timer.timeout.connect(self.update_models)
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
            "OpenCode",
            "Mistral AI",
            "Anthropic (Claude)",
            "Cohere",
            "Crusoe Cloud",
            "RunInfra",
            "Custom (OpenAI-compatible)",
            "Mixed Providers"
        ])
        self.provider_box.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_box)
        selectors_layout.addLayout(provider_layout)

        model_layout = QVBoxLayout()
        model_label = QLabel('AI Model — after the model you can type "/" for a reasoning level (e.g. gpt-5/low)')
        model_label.setToolTip('Type "/" after a model id to pick a reasoning level:\n'
                               '/off /minimal /low /medium /high /xhigh /max /default\n'
                               'Controls how much the model "thinks" before answering —\n'
                               'lower levels are faster and cheaper.')
        self.model_box = QComboBox()
        self.model_box.setView(QListView())
        self.model_box.setEditable(True)
        self.model_box.currentTextChanged.connect(self.on_model_changed)
        self.model_box.setToolTip(model_label.toolTip())
        self.loader = None

        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.popup().setStyleSheet(STYLE_SHEET)
        # Reasoning-effort hints: when the user types '/' after a model id,
        # offer the supported levels (e.g. "zai-org/GLM-5.3/low").
        self._all_models = []
        self._orig_completer_model = None
        # IDE-style translucent "/low" ghost painted inside the model field
        # until a reasoning suffix is typed. setLineEdit first: the combo's
        # setCompleter binds to the current line edit.
        self.model_box.setLineEdit(GhostSuffixLineEdit())
        self.model_box.setCompleter(self.completer)
        self.model_box.lineEdit().textEdited.connect(self._on_model_text_edited)

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

        test_keys_layout = QHBoxLayout()
        test_keys_layout.addStretch()
        self.btn_test_keys = QPushButton("Test Keys")
        self.btn_test_keys.setFixedWidth(200)
        self.btn_test_keys.setFixedHeight(32)
        self.btn_test_keys.clicked.connect(self.verify_keys)
        test_keys_layout.addWidget(self.btn_test_keys)
        test_keys_layout.addStretch()

        self.lbl_key_status = QLabel("Pool Status: Unchecked")
        self.lbl_key_status.setWordWrap(True)

        key_layout.addWidget(self.key_label)
        key_layout.addWidget(self.btn_toggle_keys)
        key_layout.addWidget(self.key_pool_edit)
        key_layout.addLayout(test_keys_layout)
        key_layout.addWidget(self.lbl_key_status)

        self.custom_url_label = QLabel("Custom API Base URL:")
        self.custom_base_url_edit = QLineEdit()
        self.custom_base_url_edit.setPlaceholderText("e.g. http://localhost:8080/v1")
        self.custom_base_url_edit.setVisible(False)
        self.custom_url_label.setVisible(False)
        self.custom_base_url_edit.textChanged.connect(lambda: self.save_timer.start(500))

        key_layout.addWidget(self.custom_url_label)
        key_layout.addWidget(self.custom_base_url_edit)
        workspace_layout.addLayout(key_layout)

        lang_layout = QVBoxLayout()
        self.target_lang_label = QLabel("Target Language (Format: Name (code))")
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
            "Korean (ko_kr)",
            "Ukrainian (uk_ua)"
        ])
        self.lang_box.setCurrentText(self.settings.value("target_lang", "Russian (ru_ru)"))
        self.lang_box.currentTextChanged.connect(self.on_lang_box_changed)
        lang_layout.addWidget(self.target_lang_label)
        lang_layout.addWidget(self.lang_box)
        workspace_layout.addLayout(lang_layout)

        policy_layout = QVBoxLayout()
        self.policy_label = QLabel("Existing Localized Files Policy")
        self.policy_box = QComboBox()
        self.policy_box.setView(QListView())
        self.policy_box.addItems([
            "complement",
            "overwrite",
            "skip"
        ])
        self.policy_box.setCurrentText(self.settings.value("policy", "complement"))
        self.policy_box.currentTextChanged.connect(lambda *_: self.save_timer.start(500))
        policy_layout.addWidget(self.policy_label)
        policy_layout.addWidget(self.policy_box)
        workspace_layout.addLayout(policy_layout)

        dir_layout = QVBoxLayout()
        self.dir_label = QLabel("Target Modpack / Directory")
        self.dir_box = QComboBox()
        self.dir_box.setView(QListView())
        self.dir_box.currentIndexChanged.connect(self.dir_box_changed)

        self.lbl_file_count = QLabel("")
        self.lbl_file_count.setStyleSheet("color: #4a8df8; font-weight: normal; margin-top: 5px; margin-bottom: 5px; font-size: 11px;")

        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_box)
        dir_layout.addWidget(self.lbl_file_count)
        workspace_layout.addLayout(dir_layout)

        self.pb_batch = QProgressBar()
        self.pb_batch.setFormat("Total Progress: %v / %m files")
        self.pb_batch.setValue(0)
        workspace_layout.addWidget(self.pb_batch)

        self.out = QTextEdit(readOnly=True)
        # Unbounded log growth slows the widget down and leaks memory on long runs
        self.out.document().setMaximumBlockCount(5000)
        # Shadow buffer with the FULL untruncated text of every log line:
        # the on-screen view stays compact, but Ctrl+Shift+C copies this, complete
        self._full_log = []
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
        self.btn_clear.clicked.connect(self._clear_log)

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
        # Let the Auto-Fix healer pick up the active provider/model/keys
        self.translation_memory_tab.main_window = self
        self.tabs.addTab(self.translation_memory_tab, "Translation Memory")

        self.settings_tab = SettingsTab(self.config, parent=self)
        self.settings_tab.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)
        # The Settings page keeps growing (QA, dataset, jury); a scroll area
        # guarantees every row keeps its natural height — nothing squeezes
        # or overlaps regardless of window size.
        settings_scroll = QScrollArea()
        settings_scroll.setWidget(self.settings_tab)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tabs.addTab(settings_scroll, "Settings")

        self.credits_tab = CreditsTab()
        self.tabs.addTab(self.credits_tab, "Credits")

        self.setCentralWidget(self.tabs)
        saved_geometry = self.settings.value("geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        self._has_files = False
        self.load_saved_settings()
        self._start_instance_scan()
        self.current_provider = "INIT_STATE"
        self._is_initializing = False
        self.on_provider_changed(self.provider_box.currentText())
        self.log_cache_stats()

        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self.shortcut_copy.activated.connect(self.copy_logs)

        gui_logger = logging.getLogger("snbt_localizer")
        gui_logger.setLevel(logging.DEBUG)
        # Do NOT clear handlers here: main() attached the RotatingFileHandler
        # (app.log) - clearing it kills file logging for the whole session
        gui_handler = QtLoggingHandler(self.out, full_log_sink=self._append_log)
        gui_handler.setLevel(logging.INFO)
        gui_logger.addHandler(gui_handler)
        gui_logger.propagate = False
        self.retranslate_ui()

        if (not os.environ.get('SNBT_TR_SKIP_UPDATE_CHECK', '').lower() in ('1', 'true', 'yes') and
            os.environ.get('QT_QPA_PLATFORM', '') != 'offscreen'):
            self.update_checker = _track_qthread(UpdateChecker())
            self.update_checker.update_available.connect(self.on_update_available)
            self.update_checker.start()

    def on_update_available(self, new_version, asset_url):
        msg = f"New version v{new_version} is available! Download from GitHub releases."
        reply = QMessageBox.question(
            self,
            "Update Available",
            msg,
            QMessageBox.StandardButton.Ok
        )
        if reply == QMessageBox.StandardButton.Ok:
            QDesktopServices.openUrl(QUrl("https://github.com/ronnikols/SNBT-AI-Localizer/releases"))


    def on_lang_box_changed(self, lang_text):
        if self._is_initializing or self._is_syncing_language:
            return
        if not hasattr(self, 'translation_memory_tab'):
            return
        lang_name, lang_code = parse_target_lang(lang_text)
        # Recreating the SQLite cache is expensive and spawns one table per
        # code: only do it for complete plausible codes (ru_ru, pt-br...),
        # never for per-keystroke fragments like "r" or "russ"
        if not re.fullmatch(r'[a-z]{2}[-_][a-z]{2}', lang_code or ''):
            return
        self._is_syncing_language = True
        try:
            self.translation_memory_tab.lang_filter.blockSignals(True)
            self.translation_memory_tab.lang_filter.setCurrentText(lang_text)
            self.translation_memory_tab.lang_filter.blockSignals(False)
            self.translation_memory_tab.set_language_code(lang_code)
            self.save_timer.start(500)
        finally:
            self._is_syncing_language = False

    def on_tm_language_changed(self, lang_text):
        if self._is_initializing or self._is_syncing_language:
            return
        self._is_syncing_language = True
        try:
            self.lang_box.blockSignals(True)
            self.lang_box.setCurrentText(lang_text)
            self.lang_box.blockSignals(False)
            self.save_timer.start(500)
        finally:
            self._is_syncing_language = False

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

        saved_model = self.config.model or ""
        if saved_model in ["", "Loading live models...", "None (Free Engine)"]:
            self.config.model = None
            self.saved_model = ""
        else:
            self.saved_model = saved_model

        saved_policy = self.settings.value("policy", "complement")
        if saved_policy in ["complement", "overwrite", "skip"]:
            self.policy_box.setCurrentText(saved_policy)
        else:
            self.policy_box.setCurrentText("complement")

        provider = self.config.provider
        saved_keys = self.config.get_api_keys(provider)
        if saved_keys:
            self.key_pool_edit.setPlainText("\n".join(saved_keys))

        self.custom_base_url_edit.setText(self.settings.value("custom_base_url", ""))
        self.custom_base_url = self.custom_base_url_edit.text()

        # Загружаем сохраненную модель для текущего провайдера
        provider_model = self.settings.value(f"model_{provider}", "")
        if provider_model and provider_model not in ["", "Loading live models...", "None (Free Engine)"]:
            self.model_box.setCurrentText(provider_model)
            self.config.model = provider_model

        self.settings_tab.concurrency_spin.setValue(self.config.concurrency)
        self.settings_tab.batch_spin.setValue(self.config.batch_size)
        self.settings_tab.min_batch_spin.setValue(self.config.min_batch_size)
        self.settings_tab.max_requests_spin.setValue(self.config.max_concurrent_requests)
        if getattr(self.config, "temperature", None) is not None:
            self.settings_tab.temperature_spin.setValue(float(self.config.temperature))

        self.provider_box.blockSignals(False)
        self.dir_box.blockSignals(False)

    def save_current_settings(self, provider_to_save: str = None, force: bool = False):
        if self._is_updating_models and provider_to_save is None and not force:
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

        self.settings.setValue("cb_titles", "true" if self.settings_tab.cb_titles.isChecked() else "false")
        self.settings.setValue("cb_subs", "true" if self.settings_tab.cb_subs.isChecked() else "false")
        self.settings.setValue("cb_desc", "true" if self.settings_tab.cb_desc.isChecked() else "false")

        self.config.custom_context = self.settings_tab.context_in.text().strip()
        self.config.target_lang = self.lang_box.currentText()

        policy_text = self.policy_box.currentText()
        self.config.policy = policy_text
        self.settings.setValue("policy", policy_text)

        self.custom_base_url = self.custom_base_url_edit.text()
        self.settings.setValue("custom_base_url", self.custom_base_url)
        self.config.custom_base_url = self.custom_base_url

        if provider not in ("Google Translate (Free)", "Ollama (Local / Free)"):
            keys_text = self.key_pool_edit.toPlainText().strip()
            keys = [k.strip() for k in keys_text.splitlines() if k.strip()]
            self.config.set_api_keys(provider, keys)
        self.config.concurrency = self.settings_tab.concurrency_spin.value()
        self.config.batch_size = self.settings_tab.batch_spin.value()
        self.config.min_batch_size = self.settings_tab.min_batch_spin.value()
        self.config.max_concurrent_requests = self.settings_tab.max_requests_spin.value()
        self.config.temperature = self.settings_tab.temperature_spin.value()
        self.settings.setValue("temperature", self.settings_tab.temperature_spin.value())
        # Utility model (glossary pre-scan)
        utility_provider = self.settings_tab.utility_provider_combo.currentData() or ""
        utility_model = self.settings_tab.utility_model_box.currentText().strip()
        if utility_model in ("Loading live models...", "Enter model name manually"):
            utility_model = ""
        if utility_provider and utility_provider == self.config.provider and not utility_model:
            # explicitly "same as main": store empty (default semantics)
            utility_provider, utility_model = "", ""
        self.config.utility_provider = utility_provider
        self.config.utility_model = utility_model
        self.settings.setValue("utility_provider", utility_provider)
        self.settings.setValue("utility_model", utility_model)
        # QA audit phase
        qa_provider = self.settings_tab.judge1_provider()
        qa_model = self.settings_tab.judge1_model()
        self.config.qa_provider = qa_provider
        self.config.qa_model = qa_model
        # Judge #1 row overrides (api_key / base_url / temperature):
        # empty cells = pool defaults — stored as a small JSON dict.
        j1_overrides = self.settings_tab.judge1_overrides()
        self.config.qa_judge1 = json.dumps(j1_overrides, ensure_ascii=False)
        self.config.qa_enabled = self.settings_tab.cb_qa_enabled.isChecked()
        self.config.qa_update_glossary = self.settings_tab.cb_qa_update_glossary.isChecked()
        self.config.qa_batch_size = self.settings_tab.qa_batch_spin.value()
        self.config.qa_temperature = self.settings_tab.qa_temp_spin.value()
        self.config.qa_dataset = self.settings_tab.cb_qa_dataset.isChecked()
        self.config.qa_verdict_cache = self.settings_tab.cb_qa_vcache.isChecked()
        self.config.qa_judges = json.dumps(self.settings_tab._judges_collect(), ensure_ascii=False)
        self.config.qa_jury_threshold = int(self.settings_tab.jury_threshold_spin.value())
        self.settings.setValue("qa_provider", qa_provider)
        self.settings.setValue("qa_model", qa_model)
        self.config.save_to_settings()

    def _disconnect_dir_box(self):
        """Safe disconnect: no TypeError when the signal is not connected."""
        try:
            self.dir_box.currentIndexChanged.disconnect()
        except TypeError:
            pass

    def _start_instance_scan(self):
        """Scan launcher instances off the GUI thread, then populate the combo."""
        self._disconnect_dir_box()
        self.dir_box.clear()
        self.dir_box.addItem("Scanning for instances...", "SCANNING")
        self.instance_scanner = _track_qthread(InstanceScanner())
        # Bound method: Qt auto-disconnects when this QObject is destroyed,
        # so a scan finishing after teardown cannot touch a deleted App
        self.instance_scanner.instances_scanned.connect(self._on_instances_scanned)
        self.instance_scanner.start()

    def _on_instances_scanned(self, detected_instances, quest_dirs_mapping):
        try:
            self.populate_instances(detected_instances, quest_dirs_mapping)
        except RuntimeError:
            # C++ side of the App is gone (test teardown / re-entrant close)
            pass

    def populate_instances(self, detected_instances=None, quest_dirs_mapping=None):
        self._disconnect_dir_box()

        if detected_instances is None:
            detected_instances, quest_dirs_mapping = detect_instances()
        self.detected_instances = detected_instances
        self.instance_quest_dirs = quest_dirs_mapping
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
        self._has_files = False
        if path_str and path_str != "MANUAL" and os.path.exists(path_str):
            path = Path(path_str)
            _, modpack_name = self._resolve_instance_root(path)

            snbt_files = [p for p in path.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            json_files = [p for p in path.rglob("**/lang/en_us.json") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            # FTB Quests 26.x: lang/en_us/ is a directory of .json5 lang files
            json5_dirs = [p for p in path.rglob("lang/en_us") if p.is_dir() and any(p.glob("*.json5")) and not any(x in p.parts for x in EXCLUDED_DIRS)]

            snbt_count = len(snbt_files)
            json_count = len(json_files)
            json5_count = len(json5_dirs)

            if snbt_count > 0 or json_count > 0 or json5_count > 0:
                parts = []
                if snbt_count > 0:
                    parts.append(f"{snbt_count} quest files (.snbt)")
                if json_count > 0:
                    parts.append(f"{json_count} JSON lang files")
                if json5_count > 0:
                    parts.append(f"{json5_count} FTB Quests 26.x lang directories (.json5)")
                has_files = True
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | Detected: {' & '.join(parts)}")
                self.pb_batch.setRange(0, snbt_count + json_count + json5_count)
                self.pb_batch.setValue(0)
            else:
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | ⚠ Warning: No quest files (.snbt) or JSON lang files found")
                self.pb_batch.setRange(0, 100)
                self.pb_batch.setValue(0)
        else:
            self.lbl_file_count.setText("")
            self.pb_batch.setRange(0, 100)
            self.pb_batch.setValue(0)

        self._has_files = has_files
        self.btn_run.setEnabled(has_files and self.is_model_valid())

    def update_batch_progress(self, cur, tot):
        """A whole file finished (SNBT) or JSON strings advanced (JSON mode)."""
        if getattr(self, '_progress_mode', 'snbt') == 'json':
            # JSONManager reports strings here; the string progress is already
            # driven by progress_state, so just mark the bar.
            return
        if hasattr(self, 'files_progress') and cur > 0:
            self.files_progress[cur - 1] = 1.0
        self._refresh_progress_bar()

    def update_chunk_progress(self, file_idx, total_files, chunk_idx, total_chunks):
        if not hasattr(self, 'files_progress'):
            self.files_progress = {}
        if total_chunks > 0:
            self.files_progress[file_idx] = min(1.0, chunk_idx / total_chunks)
        else:
            self.files_progress[file_idx] = 0.0
        self._refresh_progress_bar()

    def update_lines_progress(self, completed: int, total: int):
        pass

    def update_progress_state(self, current_file_idx, total_files, current_file_name, completed_strings, total_strings, eta_seconds):
        if getattr(self, '_translation_finished', False):
            return
        if "JSON" in current_file_name or "strings" in current_file_name:
            # JSON phase: a plain string bar, independent of the SNBT files.
            self._progress_mode = 'json'
            self.pb_batch.setRange(0, 100)
            if total_strings > 0:
                self.pb_batch.setValue(int((completed_strings / total_strings) * 100))
                self.pb_batch.setFormat(
                    f"JSON strings: {completed_strings}/{total_strings} "
                    f"({int((completed_strings / total_strings) * 100)}%)")
            else:
                self.pb_batch.setValue(0)
                self.pb_batch.setFormat("Translating JSON strings...")
            return
        self._progress_mode = 'snbt'
        if total_files:
            self._progress_total_files = total_files
        self._progress_total_strings = total_strings
        self._progress_done_strings = completed_strings
        self._progress_eta = eta_seconds
        self._progress_current = current_file_name
        self._refresh_progress_bar()

    def _refresh_progress_bar(self):
        """One consistent overall bar for the SNBT phase.

        Driven by STRINGS done / strings total, not by file count: a modpack
        has many tiny quest files and a few huge ones, so "one file done =
        equal share" sent the bar to the end while only 10% of the strings
        were translated. Chunk-level string counts make it move during the
        network work too. Files are only a fallback when no string total is
        known yet.
        """
        if getattr(self, '_translation_finished', False):
            return
        total_files = max(1, getattr(self, '_progress_total_files', 0))
        fp = getattr(self, 'files_progress', {}) or {}
        done_files = 0
        file_frac = 0.0
        for i in range(total_files):
            f = max(0.0, min(1.0, fp.get(i, 0.0)))
            file_frac += f
            if f >= 1.0:
                done_files += 1
        total_str = getattr(self, '_progress_total_strings', 0) or 0
        done_str = getattr(self, '_progress_done_strings', 0) or 0
        self.pb_batch.setRange(0, 1000)
        if total_str > 0:
            # Never let a miscount read as "400/200": show at most what the
            # denominator promises, even if a sink over-reported.
            done_str = min(done_str, total_str)
            frac = done_str / total_str
        else:
            frac = file_frac / total_files
        self.pb_batch.setValue(int(frac * 1000))
        eta = getattr(self, '_progress_eta', 0)
        parts = [f"Files {done_files}/{total_files}"]
        if total_str > 0:
            parts.append(f"Strings {done_str}/{total_str}")
        cur = getattr(self, '_progress_current', '')
        if cur:
            parts.append(cur)
        if eta and eta > 0:
            parts.append(f"ETA {self.format_eta(eta)}")
        self.pb_batch.setFormat(" | ".join(parts))

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

    def _append_log(self, msg):
        """Store the full line in the shadow buffer; show a compact view on screen."""
        self._full_log.append(msg)
        # Visual truncation only: long translated strings would flood the widget
        if len(msg) > 160:
            self.out.append(msg[:157] + "...")
        else:
            self.out.append(msg)

    def _clear_log(self):
        self._full_log.clear()
        self.out.clear()

    def copy_logs(self):
        clipboard = QApplication.clipboard()
        # Full untruncated log: on-screen lines are visually trimmed, the buffer never is
        clipboard.setText("\n".join(self._full_log))
        logging.getLogger("snbt_localizer.gui").info("--- Log content copied to clipboard ---")

    def _resolve_instance_root(self, path: Path) -> tuple[Path, str]:
        curr = path.resolve()
        while curr != curr.parent:
            if (curr / "minecraft").is_dir() or (curr / "instance.cfg").is_file():
                return curr, curr.name
            if (curr / "config").is_dir() or (curr / "mods").is_dir() or (curr / "kubejs").is_dir():
                return curr, curr.name
            if curr.name == "minecraft":
                return curr.parent, curr.parent.name
            curr = curr.parent
        return path, path.name

    def log_cache_stats(self):
        try:
            size_mb, count = self.translation_memory_tab.cache.get_stats()
            logging.getLogger("snbt_localizer.gui").info(f"Cache stats: {size_mb:.2f} MB, {count} entries")
        except Exception as e:
            logging.getLogger("snbt_localizer.gui").error(f"Cache stats error: {e}")

    def on_ui_language_changed(self, index):
        lang = self.settings_tab.ui_lang_combo.currentText()
        self.settings.setValue("ui_language", lang)
        self.retranslate_ui()

    def retranslate_ui(self):
        locale = get_locale()
        self.setWindowTitle(f"{locale['window_title']} v{APP_VERSION}")

        self.tabs.setTabText(0, locale["workspace_tab"])
        self.tabs.setTabText(1, locale["translation_memory_tab"])
        self.tabs.setTabText(2, locale["settings_tab"])
        self.tabs.setTabText(3, locale["credits_tab"])

        self.provider_box.blockSignals(True)
        self.model_box.blockSignals(True)
        self.lang_box.blockSignals(True)
        self.policy_box.blockSignals(True)
        self.key_label.setText(locale["api_keys_label"])
        self.btn_toggle_keys.setText(locale["hide_keys"] if self.key_pool_edit.isVisible() else locale["show_keys"])
        self.btn_test_keys.setText(locale["test_keys"])
        self.lbl_key_status.setText(locale["pool_status_unchecked"])
        self.custom_url_label.setText(locale["custom_url_label"])
        self.custom_base_url_edit.setPlaceholderText(locale["custom_url_placeholder"])
        self.lang_box.clear()
        saved_lang = self.lang_box.currentText()
        self.lang_box.addItems([
            locale["lang_ru_ru"],
            locale["lang_es_es"],
            locale["lang_zh_cn"],
            locale["lang_zh_tw"],
            locale["lang_de_de"],
            locale["lang_fr_fr"],
            locale["lang_pt_br"],
            locale["lang_ja_jp"],
            locale["lang_ko_kr"],
            locale["lang_uk_ua"]
        ])
        if saved_lang:
            # Keep the user's selection: clear+addItems resets currentIndex to 0
            self.lang_box.setCurrentText(saved_lang)
        self.policy_label.setText(locale["policy_label"])
        saved_policy = self.policy_box.currentText()
        self.policy_box.clear()
        self.policy_box.addItems([
            locale["policy_complement"],
            locale["policy_overwrite"],
            locale["policy_skip"]
        ])
        if saved_policy:
            self.policy_box.setCurrentText(saved_policy)
        self.target_lang_label.setText(locale["target_lang_label"])
        self.dir_label.setText(locale["target_dir_label"])
        self.dir_box.setItemText(self.dir_box.count() - 1, locale["target_dir_label"])
        self.btn_run.setText(locale["start_translation"])
        self.btn_pause.setText(locale["pause"])
        self.btn_stop.setText(locale["stop"])
        self.btn_clear.setText(locale["clear_log"])

        self.provider_box.blockSignals(False)
        self.model_box.blockSignals(False)
        self.lang_box.blockSignals(False)
        self.policy_box.blockSignals(False)

        self.settings_tab.context_label.setText(locale["context_label"])
        self.settings_tab.context_in.setPlaceholderText(locale["context_placeholder"])
        self.settings_tab.concurrency_label.setText(locale["settings_threads"])
        self.settings_tab.batch_label.setText(locale["settings_batch_size"])
        self.settings_tab.min_batch_label.setText(locale["settings_min_batch_size"])
        self.settings_tab.max_requests_label.setText(locale["settings_max_requests"])
        self.settings_tab.cb_titles.setText(locale["translate_titles"])
        self.settings_tab.cb_subs.setText(locale["translate_subs"])
        self.settings_tab.cb_desc.setText(locale["translate_desc"])
        self.settings_tab.ui_lang_label.setText(locale["settings_ui_language"])
        self.settings_tab.cb_resource_pack.setText(locale["settings_resource_pack_mode"])
        self.settings_tab.resource_pack_desc.setText(locale.get("settings_resource_pack_desc", ""))

        self.translation_memory_tab.search_input.setPlaceholderText(locale["tm_search_placeholder"])
        self.translation_memory_tab.modpack_filter.setItemText(0, locale["tm_all_modpacks"])
        self.translation_memory_tab.table.setHorizontalHeaderLabels([
            locale["tm_original"],
            locale["tm_translation"],
            locale["tm_modpack"],
            locale["tm_added"]
        ])
        self.translation_memory_tab.load_more_btn.setText(locale["tm_load_more"])
        self.translation_memory_tab.delete_selected_btn.setText(locale["tm_delete_selected"])
        self.translation_memory_tab.save_changes_btn.setText(locale["tm_save_changes"])
        self.translation_memory_tab.clear_cache_btn.setText(locale["tm_clear_cache"])

        self.credits_tab.setWindowTitle(locale["window_title"])


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

        if provider in ("Google Translate (Free)", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"):
            results = {k: "Active" for k in keys} if keys else {}
            self.on_verification_complete(results, {}, "")
            return

        if not keys and provider != "Mixed Providers":
            self.lbl_key_status.setText("Pool Status: No keys to verify")
            return

        # Mixed mode with an empty manual pool: resolve saved provider keys so
        # the Test Keys button still works (a real run collects them the same way)
        if provider == "Mixed Providers" and not keys:
            has_saved = any(self.config.get_api_keys(p) for p in [
                "Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova",
                "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI", "Anthropic (Claude)",
                "Cohere", "OpenCode", "Crusoe Cloud", "RunInfra",
                "Google Translate (Free)", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"
            ])
            if not has_saved:
                self.lbl_key_status.setText("Pool Status: No keys to verify")
                return

        self.lbl_key_status.setText("Pool Status: Verifying keys...")
        self.btn_test_keys.setEnabled(False)

        # Cancel any verification still in flight before starting a new one
        if getattr(self, 'verifier', None) is not None and self.verifier.isRunning():
            self.verifier.cancelled = True

        model = self.model_box.currentText()
        if provider == "Mixed Providers":
            # Resolve the pool exactly like a real run would: manual entries
            # (key or key\model) first, then all keys saved under each provider.
            # This way prefix-less keys (e.g. Crusoe 82-char keys) map to the
            # provider they are saved under instead of falling back to OpenAI.
            pairs = []
            for entry in keys:
                if "\\" in entry:
                    parts = entry.split("\\", 1)
                    pairs.append({"key": parts[0].strip(), "model": parts[1].strip() if parts[1].strip() else None})
                else:
                    pairs.append({"key": entry, "model": None})
            saved_keys_by_provider = {}
            saved_models_by_provider = {}
            default_models_by_provider = {}
            for p in ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI", "Anthropic (Claude)", "Cohere", "OpenCode", "Crusoe Cloud", "RunInfra", "Google Translate (Free)", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"]:
                saved_keys_by_provider[p] = self.config.get_api_keys(p)
                saved_models_by_provider[p] = self.settings.value(f"model_{p}", "")
                default_models_by_provider[p] = PROVIDER_DEFAULTS.get(p, "")
            from core import resolve_mixed_pool
            mixed_pool = resolve_mixed_pool(pairs, saved_keys_by_provider, saved_models_by_provider, default_models_by_provider)
            specs = [(item["api_key"], item["provider"], item["model"]) for item in mixed_pool]
            # Manual entries that no provider claims (unknown prefix AND not
            # saved under any provider) would be silently dropped by
            # resolve_mixed_pool - show them as Invalid instead so the user sees
            # something is wrong with the format.
            if pairs:
                resolved_keys = {item["api_key"] for item in mixed_pool}
                saved_all = {k for ks in saved_keys_by_provider.values() for k in ks}
                for pair in pairs:
                    k = pair["key"]
                    if k and k not in resolved_keys and k not in saved_all and not detect_provider(k):
                        specs.append((k, "Mixed Providers", "Unknown format"))
        else:
            if not model or model in ("Loading live models...", "Enter API Key to load models", "Defined per key in pool", "None (Free Engine)"):
                model = PROVIDER_DEFAULTS.get(provider, "")
            specs = [(k, provider, model) for k in keys]

        if not specs:
            self.lbl_key_status.setText("Pool Status: No keys to verify")
            return

        # Test Keys covers the jury too: j1..jN from the judges table are
        # verified with their own models after the main pool. A key+model
        # pair already covered by the main pool is not re-asked.
        judge_specs = []
        if getattr(self, "settings_tab", None) is not None:
            seen = {(k, m) for k, p, m in specs}
            for k, p, m, tag in self.settings_tab._judge_test_specs():
                if (k, m) in seen:
                    continue
                seen.add((k, m))
                judge_specs.append((k, p, m, tag))

        self.verifier = _track_qthread(KeyVerifierWorker(specs, judge_specs=judge_specs))
        self.verifier.verification_complete.connect(self.on_verification_complete)
        self.verifier.start()

    def on_verification_complete(self, results, answers=None, question=""):
        self.btn_test_keys.setEnabled(True)
        active_count = sum(1 for status in results.values() if status == "Active")
        total = len(results)
        self._key_validation_cache.update(results)
        text = f"Pool Status: {active_count}/{total} active"
        if answers:
            parts = []
            for i, key in enumerate(results.keys(), 1):
                answer = answers.get(key, "")
                if answer:
                    parts.append(f"[{i}] {answer}")
                else:
                    status = results.get(key, "")
                    parts.append(f"[{i}] ({status})" if status and status != "Active" else f"[{i}] —")
            text += f'\nQ: "{question}" → ' + "  ".join(parts)
        # Jury verdict line: each judge's key verified with its own model
        # (tags j1..jN come from the judges table).
        judge_results = getattr(self.verifier, "judge_results", None) if getattr(self, "verifier", None) else None
        if judge_results:
            parts = []
            ok_count = 0
            for tag, (status, answer) in judge_results.items():
                if status == "Active":
                    ok_count += 1
                    parts.append(f"[{tag}] {'OK' + (' ' + answer if answer else '')}")
                else:
                    parts.append(f"[{tag}] ({status})")
            text += f"\nJudges: {ok_count}/{len(judge_results)} active → " + "  ".join(parts)
        self.lbl_key_status.setText(text)

    def key_pool_changed(self):
        self.save_timer.start(500)
        prov = self.provider_box.currentText()
        if prov not in ("Google Translate (Free)", "Mixed Providers", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"):
            self.model_reload_timer.start(600)

    def _on_model_text_edited(self, text):
        """Live hint for the reasoning-effort suffix.

        Typing "model/" (the last segment being an effort level or a prefix
        of one) swaps the completer to level suggestions like
        "model/low", "model/medium"... Any other text restores the normal
        model list.
        """
        base, _, tail = text.rpartition("/")
        tail_l = tail.strip().lower()
        is_level_typing = bool(base.strip()) and (tail_l == "" or any(l.startswith(tail_l) for l in REASONING_EFFORT_LEVELS))
        if is_level_typing:
            if self._orig_completer_model is None:
                self._orig_completer_model = self.completer.model()
            self.completer.setModel(QStringListModel([f"{base.strip()}/{l}" for l in REASONING_EFFORT_LEVELS]))
            self.completer.setCompletionPrefix(text)
            self.completer.complete()
        elif self._orig_completer_model is not None:
            self.completer.setModel(self._orig_completer_model)
            self._orig_completer_model = None

    def on_model_changed(self, text):
        if not self._is_updating_models:
            self.save_timer.start(500)
        # Model text does not change which files exist: reuse the cached scan
        # result instead of re-running two full rglob scans per keystroke
        self.btn_run.setEnabled(getattr(self, '_has_files', False) and self.is_model_valid())

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
        elif new_provider == "Custom (OpenAI-compatible)":
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
            # Загружаем сохраненные ключи из настроек, если их нет в config
            if not saved_keys:
                settings_keys = self.settings.value(f"api_keys_pool_{new_provider}", "")
                if settings_keys:
                    self.key_pool_edit.setPlainText(settings_keys)
            # Загружаем сохраненную модель для кастомного провайдера
            saved_model = self.settings.value(f"model_{new_provider}", "")
            if saved_model and saved_model not in ["", "Loading live models...", "None (Free Engine)"]:
                self.model_box.setCurrentText(saved_model)
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
            self._trigger_loader(provider, "", self.custom_base_url_edit.text().strip() or None)
        elif provider == "Custom (OpenAI-compatible)":
            self.model_box.setEnabled(True)
            self.model_box.setEditable(True)
            self.model_box.clear()
            self.model_box.setPlaceholderText("Enter custom model name (e.g. llama3.2:70b)")
            self.completer.setModel(QStringListModel([]))
            # Загружаем сохраненную модель
            saved_model = self.settings.value(f"model_{provider}", "")
            if saved_model and saved_model not in ["", "Loading live models...", "None (Free Engine)"]:
                self.model_box.setCurrentText(saved_model)
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

    def _trigger_loader(self, provider, key, custom_base_url=None):
        self.model_box.blockSignals(True)
        self.model_box.clear()
        self.model_box.addItem("Loading live models...")
        self.completer.setModel(QStringListModel(["Loading live models..."]))
        self.model_box.blockSignals(False)

        # Cooperative cancel: quit() is a no-op for threads without a Qt event
        # loop and wait() blocks the GUI thread; a cancelled loader simply
        # drops its result. Keep references until finished so GC never
        # destroys a running QThread.
        for loader in self.running_loaders:
            loader.cancelled = True

        self.current_loader_id += 1
        loader_id = self.current_loader_id

        loader = _track_qthread(ModelLoader(provider, key, loader_id, custom_base_url))
        self.loader = loader
        loader.loaded.connect(self.on_models_loaded)
        loader.finished.connect(lambda l=loader: self._cleanup_loader(l))
        loader.start()
        self.running_loaders.append(loader)

    def _cleanup_loader(self, loader):
        if loader in self.running_loaders:
            self.running_loaders.remove(loader)

    def on_models_loaded(self, models, error_msg="", loader_id=0, loader_provider=""):
        if loader_provider and loader_provider != self.provider_box.currentText():
            return
        # A newer loader may have been started meanwhile: drop stale results
        if loader_id and loader_id != self.current_loader_id:
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
            self._all_models = filtered_models
            self._orig_completer_model = None
        else:
            if "Groq" in provider:
                fallbacks = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "allam-2-7b"]
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
            self._all_models = fallbacks
            self._orig_completer_model = None

        if error_msg:
            logging.getLogger("snbt_localizer.gui").error(f"Error: {error_msg}")

        if self.model_box.count() > 0:
            saved_model = self.settings.value(f"model_{provider}", "")
            index = self.model_box.findText(saved_model)
            if index >= 0:
                self.model_box.setCurrentIndex(index)
            else:
                # Saved value may carry a reasoning-effort suffix
                # ("zai-org/GLM-5.3/low") that has no combobox entry: set
                # it as edit text as long as the base model exists.
                base, effort = parse_model_effort(saved_model)
                base_index = self.model_box.findText(base) if effort else -1
                if base_index >= 0:
                    self.model_box.setCurrentIndex(base_index)
                    self.model_box.setEditText(saved_model)
                    self.config.model = saved_model
                else:
                    # The saved model's base is not in the (fallback) list:
                    # keep the saved value instead of overwriting it with the
                    # placeholder item — this used to wipe saved models and
                    # their reasoning-effort suffixes on every restart for
                    # providers with no keys loaded.
                    self.model_box.setCurrentIndex(0)
                    self.model_box.setEditText(saved_model)
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
            # Resume: apply live settings FIRST (keys/model/temperature/
            # batches/QA edited while paused), then release the pause flag
            # and re-lock the live-editable widgets.
            try:
                self._apply_live_settings()
            except Exception as e:
                self._append_log(f"Live-update failed: {repr(e)[:150]} — continuing with the previous settings.")
            self.w.is_paused = False
            self.btn_pause.setText("Pause")
            self._set_live_edit_enabled(False)
        else:
            self.w.is_paused = True
            self.btn_pause.setText("Resume")
            self._set_live_edit_enabled(True)
            self._append_log("Paused — you can edit the API key pool, model, temperature, batch sizes and QA settings; press Resume to apply them.")

    def _set_live_edit_enabled(self, enabled: bool):
        """Enable/disable the widgets that can be changed during a pause.

        Structure-defining widgets (provider, language, directory, policy,
        titles/subs/desc checkboxes, concurrency, context) stay locked for
        the whole run. In skip-mode the key pool/model are pointless — the
        run translates nothing — so they stay locked too.
        """
        skip_mode = any(k == "SKIP" for k in (getattr(self.w, 'keys', None) or []))
        pool_editable = enabled and not skip_mode
        self.key_pool_edit.setEnabled(pool_editable)
        self.model_box.setEnabled(pool_editable)
        self.tabs.setTabEnabled(1, enabled)
        # batch/min/max were disabled individually in start(); temperature
        # and the QA frame are inside the Settings tab and become available
        # simply by enabling the tab itself.
        self.settings_tab.batch_spin.setEnabled(enabled)
        self.settings_tab.min_batch_spin.setEnabled(enabled)
        self.settings_tab.max_requests_spin.setEnabled(enabled)

    def _apply_live_settings(self):
        """Mutate the RUNNING worker with the settings edited while paused.

        Everything is applied on the live objects the workers already hold
        references to: translator.mixed_pool (the actual rotation pool),
        the worker's snapshot fields (used by managers created later) and
        the shared qa_params dict (mutated in place, in original batch
        order). In-flight requests finish on the old settings — the new
        ones apply from the next request/manager/QA file.
        """
        w = self.w
        prov = getattr(w, 'provider', '')
        # Sync config from the widgets first so the QA cascade reads the
        # values the user just edited (force: skip the model-update guard).
        try:
            self.save_current_settings(force=True)
        except Exception:
            pass

        log_parts = []
        skip_mode = any(k == "SKIP" for k in (getattr(w, 'keys', None) or []))
        tr = getattr(w, 'translator', None)

        # --- key pool + model (rotation pool is mixed_pool, not api_keys) ---
        if not skip_mode and tr is not None:
            raw_keys = self.key_pool_edit.toPlainText().strip().splitlines()
            keys = [k.strip() for k in raw_keys if k.strip()]
            seen = set()
            unique_keys = []
            for k in keys:
                if k not in seen:
                    seen.add(k)
                    unique_keys.append(k)
            unique_keys = unique_keys[:10]

            needs_keys = prov not in ("Google Translate (Free)", "Ollama (Local / Free)")
            model_text = self.model_box.currentText() or ""

            if prov == "Mixed Providers":
                pairs = []
                for entry in unique_keys:
                    if "\\" in entry:
                        parts = entry.split("\\", 1)
                        pairs.append({"key": parts[0].strip(),
                                      "model": parts[1].strip() if parts[1].strip() else None})
                    else:
                        pairs.append({"key": entry, "model": None})
                saved_keys_by_provider = {}
                saved_models_by_provider = {}
                default_models_by_provider = {}
                for p in ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI", "Anthropic (Claude)", "Cohere", "OpenCode", "Crusoe Cloud", "RunInfra", "Google Translate (Free)", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"]:
                    saved_keys_by_provider[p] = self.config.get_api_keys(p)
                    saved_models_by_provider[p] = self.settings.value(f"model_{p}", "")
                    default_models_by_provider[p] = PROVIDER_DEFAULTS.get(p, "")
                from core import resolve_mixed_pool
                mp = resolve_mixed_pool(pairs, saved_keys_by_provider,
                                        saved_models_by_provider, default_models_by_provider)
                if mp:
                    tr.mixed_pool = mp
                    tr.api_keys = [item["api_key"] for item in mp]
                    log_parts.append(f"mixed pool {len(mp)} key(s)")
                else:
                    self._append_log("Live-update: Mixed pool resolved to nothing — kept the old pool.")
            elif unique_keys or not needs_keys:
                new_model = model_text if (model_text and model_text not in
                                           ("", "Loading live models...", "None (Free Engine)")) else tr.model
                base = get_base_url(prov)
                new_pool = [{"provider": prov, "api_key": k, "model": new_model,
                             "base_url": base} for k in unique_keys]
                if not new_pool and prov == "Ollama (Local / Free)":
                    new_pool = [{"provider": prov, "api_key": "", "model": new_model,
                                 "base_url": base}]
                tr.mixed_pool = new_pool
                tr.api_keys = list(unique_keys)
                if unique_keys:
                    tr.api_key = unique_keys[0]
                    log_parts.append(f"keys {len(unique_keys)} (...{unique_keys[0][-4:]})")
                if new_model != getattr(tr, 'model', None):
                    tr.model = new_model
                    log_parts.append(f"model {new_model}")
            elif needs_keys:
                self._append_log("Live-update: the key pool is empty — kept the old keys.")

        # --- temperature (global; applies to every next request) ---
        new_temp = float(self.settings_tab.temperature_spin.value())
        set_temperature(new_temp)
        w.temperature = new_temp
        if tr is not None:
            log_parts.append(f"temperature {new_temp}")

        # --- batch sizes (worker snapshot + translator thresholds; the
        #     currently running manager keeps its own snapshot) ---
        b = int(self.settings_tab.batch_spin.value())
        mb = int(self.settings_tab.min_batch_spin.value())
        mr = int(self.settings_tab.max_requests_spin.value())
        w.batch_size, w.min_batch_size, w.max_concurrent_requests = b, mb, mr
        if tr is not None:
            tr.batch_size, tr.min_batch_size = b, mb
        log_parts.append(f"batch {b} (min {mb}, max-req {mr})")

        # --- QA params: same dict the managers already reference ---
        qp = getattr(w, 'qa_params', None)
        if qp is not None:
            if not self.config.qa_enabled:
                # Turning QA off mid-run: empty keys make each QA phase skip
                # itself instantly ("no live API keys") without touching the
                # running translation. Turning it back on re-fills the keys.
                qp["keys"] = []
                log_parts.append("QA off")
            else:
                qa_provider = self.config.qa_provider or self.config.utility_provider or prov
                # ТЗ-v4.2 4.1/4.3: the audit has NO private key pool any more —
                # it runs on the provider pool, exactly like the translation
                # workerpool. Only a judge's PERSONAL key is carried along,
                # and even that one is ADDED to the pool, never replacing it.
                qa_keys = []
                extra_qa_keys = []
                # Judge #1 row overrides apply on resume too.
                raw_j1 = getattr(self.config, "qa_judge1", "") or ""
                j1_over = {}
                if isinstance(raw_j1, str) and raw_j1.strip():
                    try:
                        parsed = json.loads(raw_j1)
                        if isinstance(parsed, dict):
                            j1_over = parsed
                    except (ValueError, TypeError):
                        j1_over = {}
                elif isinstance(raw_j1, dict):
                    j1_over = raw_j1
                if j1_over.get("api_key"):
                    extra_qa_keys.append(str(j1_over["api_key"]))
                qa_model = self.config.qa_model or self.config.utility_model or (self.model_box.currentText() or "")
                qp["keys"] = qa_keys
                qp["extra_keys"] = extra_qa_keys
                qp["provider"] = qa_provider
                qp["model"] = qa_model
                qp["batch_size"] = int(self.settings_tab.qa_batch_spin.value())
                qp["temperature"] = float(self.settings_tab.qa_temp_spin.value())
                qp["update_glossary"] = bool(self.settings_tab.cb_qa_update_glossary.isChecked())
                qp["custom_base_url"] = (self.custom_base_url_edit.text()
                                         if qa_provider in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)")
                                         else None)
                if j1_over.get("base_url"):
                    qp["custom_base_url"] = str(j1_over["base_url"])
                qp["qa_temperature_override"] = (float(j1_over["temperature"])
                                                 if isinstance(j1_over.get("temperature"), (int, float))
                                                 else None)
                log_parts.append(f"QA {qa_model or '(default)'} shared pool"
                                 + (f" +{len(extra_qa_keys)} personal key(s)" if extra_qa_keys else ""))

        if log_parts:
            self._append_log("[Live-update] applied on resume: " + ", ".join(log_parts))

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
        policy = self.policy_box.currentText()
        
        raw_keys = self.key_pool_edit.toPlainText().strip().splitlines()
        keys = [k.strip() for k in raw_keys if k.strip()]
        seen = set()
        unique_keys = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                unique_keys.append(k)
        unique_keys = unique_keys[:10]
        
        if policy.lower().strip() == "skip":
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
            for p in ["Groq Cloud (Fast)", "NVIDIA NIM", "Google Gemini (Free API)", "Sambanova", "OpenRouter (Cloud AI)", "OpenAI", "Mistral AI", "Anthropic (Claude)", "Cohere", "OpenCode", "Crusoe Cloud", "RunInfra", "Google Translate (Free)", "Ollama (Local / Free)", "Custom (OpenAI-compatible)"]:
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

        # Validate model
        if prov != "Google Translate (Free)":
            if not self.is_model_valid():
                QMessageBox.warning(self, "Validation Error", "Please select a valid model.")
                return

        # Validate API keys
        if prov not in ("Google Translate (Free)", "Ollama (Local / Free)") and not unique_keys:
            QMessageBox.warning(self, "Validation Error", "Please enter at least one API Key in the API Keys Pool section.")
            return

        # Validate target directory BEFORE locking the UI: an early return
        # after the disable block would leave the app permanently disabled
        dir_path = self.dir_box.itemData(self.dir_box.currentIndex())
        if dir_path == "MANUAL" or not dir_path:
            QMessageBox.warning(self, "Validation Error", "Please select a valid directory first.")
            return
        dir_path_obj = Path(dir_path)
        _, modpack_name = self._resolve_instance_root(dir_path_obj)
        quest_dirs = self.instance_quest_dirs.get(dir_path_obj) or find_all_quest_dirs(dir_path_obj)
        if not quest_dirs:
            QMessageBox.warning(self, "Validation Error", f"No quest directories found in {dir_path}")
            return

        self.btn_run.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

        self.provider_box.setEnabled(False)
        self.model_box.setEnabled(False)
        self.key_pool_edit.setEnabled(False)
        self.btn_toggle_keys.setEnabled(False)
        self.dir_box.setEnabled(False)
        self.settings_tab.context_in.setEnabled(False)
        self.settings_tab.cb_titles.setEnabled(False)
        self.settings_tab.cb_subs.setEnabled(False)
        self.settings_tab.cb_desc.setEnabled(False)
        self.settings_tab.concurrency_spin.setEnabled(False)
        self.settings_tab.batch_spin.setEnabled(False)
        self.settings_tab.min_batch_spin.setEnabled(False)
        self.settings_tab.max_requests_spin.setEnabled(False)
        self.lang_box.setEnabled(False)
        self.policy_box.setEnabled(False)
        self.tabs.setTabEnabled(1, False)
        
        model = self.model_box.currentText() or ""
        t_titles = self.settings_tab.cb_titles.isChecked()
        t_subs = self.settings_tab.cb_subs.isChecked()
        t_desc = self.settings_tab.cb_desc.isChecked()
        custom_context = self.settings_tab.context_in.text().strip()
        policy = self.policy_box.currentText()
        target_lang = self.lang_box.currentText()

        all_files = []
        for qd in quest_dirs:
            snbt_files = [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            json_files = [p for p in qd.rglob("**/lang/en_us.json") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            # FTB Quests 26.x: lang/en_us/ directory of .json5 files — pass a
            # sentinel path so the JSON phase runs over these dirs too
            json5_dirs = [p for p in qd.rglob("lang/en_us") if p.is_dir() and any(p.glob("*.json5")) and not any(x in p.parts for x in EXCLUDED_DIRS)]
            all_files.extend(snbt_files)
            all_files.extend(json_files)
            all_files.extend(json5_dirs)


        target_lang_name, target_lang_code = parse_target_lang(target_lang)
        concurrency = self.config.concurrency
        custom_url = self.custom_base_url_edit.text() if prov in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)") else None

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
        # Fresh progress state for this run (one consistent bar: see
        # _refresh_progress_bar).
        self._progress_mode = 'snbt'
        self._progress_total_files = len(files)
        self._progress_total_strings = 0
        self._progress_done_strings = 0
        self._progress_eta = 0
        self._progress_current = ""
        logging.getLogger("snbt_localizer.gui").info(f"Starting localization. Active Provider: {prov}, Active Model: {model or 'N/A'}, Keys in Pool: {len(unique_keys)}")

        translator = UnifiedTranslator(
            unique_keys,
            prov,
            model or "",
            custom_context,
            target_lang_name,
            target_lang_code,
            mixed_pool=mixed_pool,
            batch_size=self.settings_tab.batch_spin.value(),
            min_batch_size=self.settings_tab.min_batch_spin.value(),
            max_concurrent_requests=self.settings_tab.max_requests_spin.value(),
            custom_base_url=custom_url
        )
        cache = TranslationCache(target_lang_code=target_lang_code)
        cache.autofix_records()

        # --- Modpack glossary pre-scan ----------------------------------
        # Extract recurring Capitalized terms from the quest strings, then
        # hand them to the Worker thread: it runs the utility model there
        # (asyncio.run is illegal on the GUI thread because cli.py --gui
        # wraps the whole GUI in a running asyncio event loop).
        prescan_params = None
        try:
            from core import (
                find_modpack_root, _find_all_snbt_strings,
            )
            prescan_texts = []
            for qd in quest_dirs:
                for snbt_file in [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]:
                    try:
                        # Mine the ENGLISH original (.snbt.bak) — after the
                        # first in-place run the file itself is translated
                        # and a Russian pre-scan yields 0 candidates.
                        src = snbt_file.with_suffix('.snbt.bak')
                        if not (src.exists() and src.stat().st_size > 0):
                            src = snbt_file
                        content = src.read_text(encoding='utf-8')
                    except OSError:
                        continue
                    for s in _find_all_snbt_strings(content):
                        if s['key'] == 'title' or s['key'].endswith('.title') or s['key'] == 'subtitle' or s['key'].endswith('.quest_subtitle'):
                            v = s['value']
                            if v and len(v) < 250:
                                prescan_texts.append(v)
                for j5 in qd.rglob("lang/en_us/*.json5"):
                    try:
                        raw = j5.read_text(encoding='utf-8')
                        raw = re.sub(r',(\s*[}\]])', r'\1', raw)
                        data = json.loads(raw)
                    except Exception:
                        continue
                    def _walk(node):
                        if isinstance(node, dict):
                            for k, v in node.items():
                                if k in ("title", "subtitle") and isinstance(v, str) and len(v) < 250:
                                    prescan_texts.append(v)
                                else:
                                    _walk(v)
                        elif isinstance(node, list):
                            for it in node:
                                _walk(it)
                    _walk(data)

            if prescan_texts:
                utility_provider = self.config.utility_provider or prov
                utility_model = self.config.utility_model or model
                utility_keys = unique_keys
                utility_mixed = mixed_pool
                if self.config.utility_provider and self.config.utility_provider != "Mixed Providers":
                    pool_keys = self.config.get_api_keys(self.config.utility_provider)
                    if pool_keys:
                        utility_keys = pool_keys
                        utility_mixed = [
                            {"provider": self.config.utility_provider, "api_key": k,
                             "model": utility_model or "", "base_url": get_base_url(self.config.utility_provider)}
                            for k in pool_keys
                        ]
                    else:
                        self._append_log(
                            f"Glossary pre-scan: utility provider '{self.config.utility_provider}' has no keys — using the main provider."
                        )
                prescan_needed = (
                    utility_provider not in ("Google Translate (Free)", "Ollama (Local / Free)")
                    and prov not in ("Google Translate (Free)", "Ollama (Local / Free)")
                )
                if prescan_needed:
                    first_root = find_modpack_root(quest_dirs[0]) if quest_dirs else None
                    if first_root:
                        target_lang_name_, _ = parse_target_lang(target_lang)
                        # Overwrite bypasses the translation cache, but the
                        # modpack glossary stays additive-converged (pin
                        # re-rolls = the old roulette) and the verdict cache is
                        # content-keyed, so it stays valid across overwrite runs.
                        prescan_params = {
                            "texts": prescan_texts,
                            "root": first_root,
                            "keys": utility_keys,
                            "provider": utility_provider,
                            "model": utility_model,
                            "lang_name": target_lang_name_,
                            "mixed_pool": utility_mixed,
                            "custom_base_url": custom_url if self.config.utility_provider in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)") else None,
                        }
        except Exception as e:
            self._append_log(f"Glossary pre-scan skipped: {e}")

        # --- QA phase params (post-translation audit) ------------------
        qa_params = None
        try:
            if self.config.qa_enabled:
                target_lang_name_, _ = parse_target_lang(target_lang)
                # Dedicated QA provider > utility provider > main provider.
                qa_provider = self.config.qa_provider or self.config.utility_provider or prov
                # ТЗ-v4.2 4.1/4.3: no private QA pool — the audit shares the
                # provider pool with the translation workerpool.
                qa_keys = []
                extra_qa_keys = []
                # Auditor model: dedicated QA model (may carry a "/effort"
                # suffix typed in the model field) > utility > main.
                qa_model = self.config.qa_model or self.config.utility_model or model
                qa_custom_url = custom_url if qa_provider in ("Custom (OpenAI-compatible)", "Ollama (Local / Free)") else None
                # Judge #1 row overrides typed in the judges table:
                # its own key / base URL / temperature (empty = pool defaults).
                j1_over = {}
                raw_j1 = getattr(self.config, "qa_judge1", "") or ""
                if isinstance(raw_j1, str) and raw_j1.strip():
                    try:
                        parsed = json.loads(raw_j1)
                        if isinstance(parsed, dict):
                            j1_over = parsed
                    except (ValueError, TypeError):
                        j1_over = {}
                elif isinstance(raw_j1, dict):
                    j1_over = raw_j1
                if j1_over.get("api_key"):
                    # 4.2: personal judge key JOINS the pool (added, not a
                    # replacement) — otherwise the audit serializes on it.
                    extra_qa_keys.append(str(j1_over["api_key"]))
                if j1_over.get("base_url"):
                    qa_custom_url = str(j1_over["base_url"])
                first_root = find_modpack_root(quest_dirs[0]) if quest_dirs else None
                qa_params = {
                    # 4.3: kept empty for backward compatibility — the phase
                    # logs "legacy QA key field ignored" if anything lands here.
                    "keys": qa_keys,
                    "extra_keys": extra_qa_keys,
                    "provider": qa_provider,
                    "model": qa_model,
                    "custom_base_url": qa_custom_url,
                    "qa_temperature_override": (float(j1_over["temperature"])
                                                if isinstance(j1_over.get("temperature"), (int, float))
                                                else None),
                    "update_glossary": bool(self.config.qa_update_glossary),
                    "batch_size": int(self.config.qa_batch_size),
                    "temperature": float(self.config.qa_temperature),
                    "dataset": bool(self.config.qa_dataset),
                    "verdict_cache": bool(self.config.qa_verdict_cache),
                    "judges": json.loads(getattr(self.config, "qa_judges", "[]") or "[]"),
                    "jury_threshold": int(getattr(self.config, "qa_jury_threshold", 2) or 2),
                    "provider_pool": {prov: list(keys) for prov, keys in self.config.api_keys_pool.items()},
                    "modpack_root": first_root,
                    "lang_name": target_lang_name_,
                }
                if any(u in qa_provider for u in ("Google Translate", "Ollama")):
                    self._append_log(f"QA audit: provider '{qa_provider}' is not supported — the QA phase will be skipped.")
        except Exception as e:
            self._append_log(f"QA audit skipped: {e}")

        self.w = _track_qthread(Worker(files, unique_keys, prov, model, t_titles, t_subs, t_desc, custom_context, policy, target_lang, concurrency, mixed_pool, self.settings_tab.batch_spin.value(), self.settings_tab.min_batch_spin.value(), self.settings_tab.max_requests_spin.value(), temperature=self.settings_tab.temperature_spin.value(), modpack=modpack_name, custom_base_url=custom_url, translator=translator, cache=cache, resource_pack_mode=self.config.resource_pack_mode, prescan_params=prescan_params, qa_params=qa_params))
        self.w.is_aborted = False
        self.w.is_paused = False
        self.w.log.connect(self._append_log)
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
        self.settings_tab.context_in.setEnabled(True)
        self.settings_tab.cb_titles.setEnabled(True)
        self.settings_tab.cb_subs.setEnabled(True)
        self.settings_tab.cb_desc.setEnabled(True)
        self.settings_tab.concurrency_spin.setEnabled(True)
        self.settings_tab.batch_spin.setEnabled(True)
        self.settings_tab.min_batch_spin.setEnabled(True)
        self.settings_tab.max_requests_spin.setEnabled(True)
        self.lang_box.setEnabled(True)
        self.policy_box.setEnabled(True)
        self.tabs.setTabEnabled(1, True)
        self.translation_memory_tab.refresh_modpack_filter()
        self.translation_memory_tab._load_data()
        if getattr(self.w, 'is_snbt_mode', False) and getattr(self.w, 'is_json_mode', False):
            self._append_log("Quest and JSON translation completed. In Minecraft, run '/ftbquests reload' or restart the game to apply changes.")
        elif getattr(self.w, 'is_json_mode', False):
            self._append_log("JSON translation completed. In Minecraft, run '/ftbquests reload' or restart the game to apply changes.")
        if getattr(self, '_close_pending', False):
            # Defer close: the worker thread may still be finishing its last
            # instructions and isRunning() would trigger a second dialog
            self._close_pending = False
            QTimer.singleShot(200, self.close)

    def closeEvent(self, event):
        # isinstance guard: a mocked/replaced worker must not be treated as a
        # running translation (QThread API missing on mocks); headless runs
        # cannot answer a modal dialog, so auto-abort there.
        worker_running = (
            isinstance(getattr(self, 'w', None), QThread) and self.w.isRunning()
        )
        if worker_running and not getattr(self, '_close_pending', False):
            if os.environ.get('QT_QPA_PLATFORM', '') == 'offscreen':
                reply = QMessageBox.StandardButton.Yes
            else:
                reply = QMessageBox.question(self, "Выход", "Идет перевод. Прервать и выйти?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._close_pending = True
                self.w.is_aborted = True
                self.w.is_paused = False
                self._cancel_helper_threads()
            event.ignore()
        else:
            self._cancel_helper_threads()
            self.save_current_settings(force=True)
            self.settings.setValue("geometry", self.saveGeometry())
            event.accept()

    def _cancel_helper_threads(self):
        # Cooperatively stop helper threads so they don't get destroyed mid-request
        for loader in list(self.running_loaders):
            loader.cancelled = True
        verifier = getattr(self, 'verifier', None)
        if verifier is not None:
            verifier.cancelled = True
        for loader in list(self.running_loaders):
            loader.wait(2000)

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
    if os.name == 'nt':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('org.mineai.snbt-tr')
        except:
            pass
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.normpath(get_resource_path("resources/logo.png"))))
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
