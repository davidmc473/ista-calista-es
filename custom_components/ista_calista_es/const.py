"""Constantes de la integración ista Calista (España)."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ista_calista_es"
MANUFACTURER: Final = "ista"
PORTAL_URL: Final = "https://oficina.ista.es/GesCon/"
#: zona horaria del portal: las fechas de lectura son días naturales en España peninsular
PORTAL_TIMEZONE: Final = "Europe/Madrid"

CONF_UPDATE_INTERVAL: Final = "update_interval_hours"
CONF_IMPORT_STATISTICS: Final = "import_statistics"
CONF_HISTORY_DAYS: Final = "history_days"

DEFAULT_UPDATE_INTERVAL: Final = 6
MIN_UPDATE_INTERVAL: Final = 1
MAX_UPDATE_INTERVAL: Final = 24
DEFAULT_IMPORT_STATISTICS: Final = True
DEFAULT_HISTORY_DAYS: Final = 365
MAX_HISTORY_DAYS: Final = 1095

PLATFORMS: Final = [Platform.SENSOR]
