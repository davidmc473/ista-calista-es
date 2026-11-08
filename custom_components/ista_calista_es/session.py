"""Sesión HTTP compartida por la integración."""

from __future__ import annotations

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import DOMAIN

DATA_SESSION = f"{DOMAIN}_http_session"


@callback
def async_get_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Sesión sin cookie jar: cada cliente lleva sus propias cookies (una por cuenta).

    Se reutiliza entre entradas y flujos de configuración; Home Assistant la cierra al
    detenerse (no debe cerrarse a mano).
    """
    session: aiohttp.ClientSession | None = hass.data.get(DATA_SESSION)
    if session is None or session.closed:
        session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
        hass.data[DATA_SESSION] = session
    return session
