"""Acceso al portal Calista de ista España.

Sin dependencias de Home Assistant (constitución IV): solo ``aiohttp`` y la librería
estándar.
"""

from __future__ import annotations

from .client import (
    DEFAULT_AUTH_URL,
    DEFAULT_PORTAL_URL,
    DEFAULT_WINDOW_DAYS,
    CalistaClient,
    default_window_start,
)
from .exceptions import (
    AuthActionRequired,
    CalistaError,
    CannotConnect,
    InvalidAuth,
    ParseError,
    SessionExpired,
)
from .models import (
    Bill,
    CalistaData,
    Consumption,
    Dwelling,
    Meter,
    MeterKind,
    Reading,
    consumption_delta,
)

__all__ = [
    "DEFAULT_AUTH_URL",
    "DEFAULT_PORTAL_URL",
    "DEFAULT_WINDOW_DAYS",
    "AuthActionRequired",
    "Bill",
    "CalistaClient",
    "CalistaData",
    "CalistaError",
    "CannotConnect",
    "Consumption",
    "Dwelling",
    "InvalidAuth",
    "Meter",
    "MeterKind",
    "ParseError",
    "Reading",
    "SessionExpired",
    "consumption_delta",
    "default_window_start",
]
