"""Constantes de la integración ista Calista (España)."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ista_calista_es"
MANUFACTURER: Final = "ista"
PORTAL_URL: Final = "https://oficina.ista.es/GesCon/"
ISSUES_URL: Final = "https://github.com/davidmc473/ista-calista-es/issues"
#: zona horaria del portal: las fechas de lectura son días naturales en España peninsular
PORTAL_TIMEZONE: Final = "Europe/Madrid"

CONF_UPDATE_INTERVAL: Final = "update_interval_hours"
CONF_IMPORT_STATISTICS: Final = "import_statistics"
CONF_HISTORY_DAYS: Final = "history_days"
CONF_STALE_DAYS: Final = "stale_days"

DEFAULT_UPDATE_INTERVAL: Final = 6
MIN_UPDATE_INTERVAL: Final = 1
MAX_UPDATE_INTERVAL: Final = 24
DEFAULT_IMPORT_STATISTICS: Final = True
DEFAULT_HISTORY_DAYS: Final = 365
MAX_HISTORY_DAYS: Final = 1095
#: días sin lectura para considerar que un equipo no transmite (spec 006): el mayor hueco
#: visto en un año fue de 6 días, más ~3 de retraso de publicación
DEFAULT_STALE_DAYS: Final = 10
MIN_STALE_DAYS: Final = 2
MAX_STALE_DAYS: Final = 60

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR]
