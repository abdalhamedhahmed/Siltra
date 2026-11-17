"""
Slitra - Coil Slitting Optimizer v4.1.1
ZAT AL-EMAD FACTORY
"""

APP_NAME = "Slitra"
APP_VERSION = "4.1.1"
FACTORY_NAME = "ZAT AL-EMAD FACTORY"

# Developer / publisher info
DEVELOPER_NAME = "Abdalhamed H. Ahmed"
DEVELOPER_URL = "https://github.com/abdalhamedhahmed/Siltra"
COPYRIGHT_YEAR = "2026"
COPYRIGHT_HOLDER = "Abdalhamed H. Ahmed"

# Auto-update check
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/abdalhamedhahmed/Siltra/main/latest_version.txt"
UPDATE_CHECK_INTERVAL_HOURS = 24

# Calculation parameters
DEFAULT_MIN_SCRAP = 0
DEFAULT_MAX_SCRAP = 30
DEFAULT_AT_LEAST_ONCE = True

# UI strings
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"
HEADER_TITLE = f"{APP_NAME} v{APP_VERSION}"
COIL_SIZES_HEADER = "Available Strip Sizes"
COIL_LIMITS_HEADER = "Coil Limits"

# Report/Export strings
PDF_TITLE = f"{APP_NAME} Report"
EXCEL_TITLE = f"{APP_NAME} Export"
LOG_HEADER = f"{APP_NAME} - {FACTORY_NAME}"

# Feature flags
ORDER_MODE_ENABLED = True
PRESET_COMPATIBILITY = True

# Maximum number of coils supported (technical safety only; practically no limit)
MAX_COILS = 100000

# History settings
HISTORY_KEEP = 20
HISTORY_MAX_BYTES = 1024 * 1024 * 1024