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
                             QTabWidget, QHeaderView, QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, QSettings, Qt, QStringListModel, QObject, QTimer, pyqtSlot
from PyQt6.QtGui import QPalette, QColor, QKeySequence, QShortcut
import httpx
from core import SNBTManager, EXCLUDED_DIRS, AbortException, parse_target_lang, TranslationCache, UnifiedTranslator, is_valid_custom_instance, PROVIDER_DEFAULTS, detect_kubejs_mode, JSONManager
from config import ConfigManager

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
        "lang_ko_kr": "Korean (ko_kr)"
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
        "lang_ko_kr": "Корейский (ko_kr)"
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
        "lang_ko_kr": "Coreano (ko_kr)"
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
        "lang_ko_kr": "Koreanisch (ko_kr)"
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
        "lang_ko_kr": "Coréen (ko_kr)"
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
        "lang_ko_kr": "Coreano (ko_kr)"
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
        "lang_ko_kr": "韩语 (ko_kr)"
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

        settings_row.addStretch()
        settings_layout.addLayout(settings_row)
        self.layout.addWidget(settings_frame)

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
        self.resource_pack_desc.setStyleSheet("font-size: 11px; color: #64748b; border: none; margin-left: 20px;")
        ui_settings_layout.addWidget(self.resource_pack_desc)
        self.layout.addWidget(ui_settings_frame)
        self.layout.addStretch()

    def _on_rp_mode_toggled(self, checked):
        self.config.resource_pack_mode = checked
        self.config.save_to_settings()

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

    def __init__(self, files, keys, provider, model, t_titles, t_subs, t_desc, custom_context="", policy="Complement (Дополнить)", target_lang="Russian (ru_ru)", concurrency=3, mixed_pool=None, batch_size=50, min_batch_size=1, max_concurrent_requests=10, modpack=None, custom_base_url=None, translator=None, cache=None, resource_pack_mode=False):
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
        self.translator = translator
        self.cache = cache
        self.resource_pack_mode = resource_pack_mode
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
            from core import JSONManager, parse_target_lang

            snbt_files = [f for f in self.files if str(f).endswith('.snbt')]
            json_files = [f for f in self.files if str(f).endswith('en_us.json')]

            self.is_snbt_mode = bool(snbt_files)
            self.is_json_mode = bool(json_files)

            if snbt_files:
                self.log.emit("Starting Quest translation (SNBT)...")
                original_files = self.files
                self.files = snbt_files
                asyncio.run(self.process())
                self.files = original_files

            if json_files:
                self.log.emit("Starting Language translation (JSON)...")
                _, target_lang_code = parse_target_lang(self.target_lang)
                processed_dirs = set()
                for json_file in json_files:
                    json_path = Path(json_file)
                    lang_dir = json_path.parent
                    base_dir = lang_dir.parent
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
                        progress_callback=json_progress
                    )
                    asyncio.run(manager.process(
                        log_callback=self.log.emit,
                        check_status=self.check_status
                    ))
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            logging.getLogger("snbt_localizer.gui").error(f"Unexpected error: {e}")
        finally:
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

class JSONWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal()
    progress_batch = pyqtSignal(int, int)

    def __init__(self, base_dir, target_lang_code, translator, cache, modpack, policy, concurrency, batch_size, min_batch_size, max_concurrent_requests, resource_pack_mode=False):
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
        self.is_aborted = False
        self.is_paused = False

    async def check_status(self):
        while self.is_paused:
            await asyncio.sleep(0.1)
        if self.is_aborted:
            raise AbortException()

    def run(self):
        try:
            asyncio.run(self.process())
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}")
            logging.getLogger("snbt_localizer.gui").error(f"Unexpected error: {e}")
        finally:
            self.done.emit()

    async def process(self):
        from core import JSONManager
        manager = JSONManager(
            self.base_dir,
            self.target_lang_code,
            self.translator,
            self.cache,
            self.modpack,
            self.policy,
            resource_pack_mode=self.resource_pack_mode,
            progress_callback=lambda cur, tot: self.progress_batch.emit(cur, tot)
        )
        await manager.process(
            log_callback=self.log.emit,
            check_status=self.check_status
        )

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

        test_keys_layout = QHBoxLayout()
        test_keys_layout.addStretch()
        self.btn_test_keys = QPushButton("Test Keys")
        self.btn_test_keys.setFixedWidth(200)
        self.btn_test_keys.setFixedHeight(32)
        self.btn_test_keys.clicked.connect(self.verify_keys)
        test_keys_layout.addWidget(self.btn_test_keys)
        test_keys_layout.addStretch()

        self.lbl_key_status = QLabel("Pool Status: Unchecked")

        key_layout.addWidget(self.key_label)
        key_layout.addWidget(self.btn_toggle_keys)
        key_layout.addWidget(self.key_pool_edit)
        key_layout.addLayout(test_keys_layout)
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
            "Korean (ko_kr)"
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
        self.policy_box.setCurrentText(self.settings.value("policy", "Complement"))
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

        self.settings_tab = SettingsTab(self.config, parent=self)
        self.settings_tab.ui_lang_combo.currentIndexChanged.connect(self.on_ui_language_changed)
        self.tabs.addTab(self.settings_tab, "Settings")

        self.credits_tab = CreditsTab()
        self.tabs.addTab(self.credits_tab, "Credits")

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
        self.retranslate_ui()

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

        self.settings_tab.concurrency_spin.setValue(self.config.concurrency)
        self.settings_tab.batch_spin.setValue(self.config.batch_size)
        self.settings_tab.min_batch_spin.setValue(self.config.min_batch_size)
        self.settings_tab.max_requests_spin.setValue(self.config.max_concurrent_requests)

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

        if provider not in ("Google Translate (Free)", "Ollama (Local / Free)"):
            keys_text = self.key_pool_edit.toPlainText().strip()
            keys = [k.strip() for k in keys_text.splitlines() if k.strip()]
            self.config.set_api_keys(provider, keys)
        self.config.concurrency = self.settings_tab.concurrency_spin.value()
        self.config.batch_size = self.settings_tab.batch_spin.value()
        self.config.min_batch_size = self.settings_tab.min_batch_spin.value()
        self.config.max_concurrent_requests = self.settings_tab.max_requests_spin.value()
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
            _, modpack_name = self._resolve_instance_root(path)

            snbt_files = [p for p in path.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            json_files = [p for p in path.rglob("**/lang/en_us.json") if not any(x in p.parts for x in EXCLUDED_DIRS)]

            snbt_count = len(snbt_files)
            json_count = len(json_files)

            if snbt_count > 0 and json_count > 0:
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | Detected: {snbt_count} quest files (.snbt) & {json_count} JSON lang files")
                has_files = True
                self.pb_batch.setRange(0, snbt_count + json_count)
                self.pb_batch.setValue(0)
            elif snbt_count > 0:
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | Detected: {snbt_count} quest files (.snbt)")
                has_files = True
                self.pb_batch.setRange(0, snbt_count)
                self.pb_batch.setValue(0)
            elif json_count > 0:
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | JSON Translation Mode Active")
                has_files = True
                self.pb_batch.setRange(0, json_count)
                self.pb_batch.setValue(0)
            else:
                self.lbl_file_count.setText(f"Modpack: {modpack_name} | ⚠ Warning: No quest files (.snbt) or JSON lang files found")
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
        if "JSON" in current_file_name or "strings" in current_file_name:
            self.pb_batch.setRange(0, total_strings)
            self.pb_batch.setValue(completed_strings)
            self.pb_batch.setFormat(f"{current_file_name}: %v / %m strings")
        else:
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
        self.setWindowTitle(locale["window_title"])

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
        self.lang_box.addItems([
            locale["lang_ru_ru"],
            locale["lang_es_es"],
            locale["lang_zh_cn"],
            locale["lang_zh_tw"],
            locale["lang_de_de"],
            locale["lang_fr_fr"],
            locale["lang_pt_br"],
            locale["lang_ja_jp"],
            locale["lang_ko_kr"]
        ])
        self.policy_label.setText(locale["policy_label"])
        self.policy_box.clear()
        self.policy_box.addItems([
            locale["policy_complement"],
            locale["policy_overwrite"],
            locale["policy_skip"]
        ])
        self.target_lang_label.setText(locale["target_lang_label"])
        self.dir_label.setText(locale["target_dir_label"])
        self.dir_box.setItemText(self.dir_box.count() - 1, locale["target_dir_label"])
        self.btn_run.setText(locale["start_translation"])
        self.btn_pause.setText(locale["pause"])
        self.btn_stop.setText(locale["stop"])
        self.btn_clear.setText(locale["clear_log"])
        self.pb_batch.setFormat(locale["pool_status_unchecked"])

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

        dir_path = self.dir_box.itemData(self.dir_box.currentIndex())
        if dir_path == "MANUAL":
            logging.getLogger("snbt_localizer.gui").error("Error: Please select a valid directory first.")
            return

        dir_path_obj = Path(dir_path)
        _, modpack_name = self._resolve_instance_root(dir_path_obj)
        quest_dirs = [dir_path_obj]
        if not quest_dirs:
            quest_dirs = find_all_quest_dirs(dir_path_obj)
            if not quest_dirs:
                logging.getLogger("snbt_localizer.gui").error(f"Error: No quest directories found in {dir_path}")
                return


        all_files = []
        for qd in quest_dirs:
            snbt_files = [p for p in qd.rglob("*.snbt") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            json_files = [p for p in qd.rglob("**/lang/en_us.json") if not any(x in p.parts for x in EXCLUDED_DIRS)]
            all_files.extend(snbt_files)
            all_files.extend(json_files)


        target_lang_name, target_lang_code = parse_target_lang(target_lang)
        concurrency = self.config.concurrency
        first_key = unique_keys[0] if unique_keys else ""
        custom_url = self.custom_base_url_edit.text() if prov in ("Local LLM / Custom", "Ollama (Local / Free)") else None
        m = SNBTManager(
            first_key, prov, model, custom_context, target_lang_name, target_lang_code,
            concurrency_limit=concurrency, mixed_pool=mixed_pool, modpack=modpack_name,
            batch_size=self.settings_tab.batch_spin.value(), min_batch_size=self.settings_tab.min_batch_spin.value(),
            max_concurrent_requests=self.settings_tab.max_requests_spin.value(), custom_base_url=custom_url
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
        self.w = Worker(files, unique_keys, prov, model, t_titles, t_subs, t_desc, custom_context, policy, target_lang, concurrency, mixed_pool, self.settings_tab.batch_spin.value(), self.settings_tab.min_batch_spin.value(), self.settings_tab.max_requests_spin.value(), modpack=modpack_name, custom_base_url=custom_url, translator=translator, cache=cache, resource_pack_mode=self.config.resource_pack_mode)
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
            self.out.append("Quest and JSON translation completed. In Minecraft, run '/ftbquests reload' or restart the game to apply changes.")
        elif getattr(self.w, 'is_json_mode', False):
            self.out.append("JSON translation completed. In Minecraft, run '/ftbquests reload' or restart the game to apply changes.")
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
