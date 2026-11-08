"""Cliente del portal Calista de ista España (ver contracts/calista-http.md).

Cada cliente guarda sus propias cookies (Keycloak, pasarela OIDC y GesCon) en un
``CookieJar`` independiente de la sesión HTTP, que puede ser compartida y sin cookies.
Las redirecciones se siguen a mano: así se guardan las cookies de cada salto y se detecta
la redirección a un host interno que el portal usa cuando la sesión no es válida.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
from typing import Final

import aiohttp
from yarl import URL

from .exceptions import (
    AuthActionRequired,
    CalistaError,
    CannotConnect,
    InvalidAuth,
    ParseError,
    SessionExpired,
)
from .html import Element, decode_html, parse_html
from .models import Bill, CalistaData, Dwelling
from .parser import (
    RadioPage,
    is_portal_page,
    login_error_message,
    login_form_action,
    parse_bills,
    parse_bills_csv,
    parse_header,
    parse_radio_page,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_AUTH_URL: Final = (
    "https://login.ista.com/realms/GESCON-PORTAL-ES-APP-Abonado/protocol/openid-connect/auth"
    "?client_id=abonado-service&response_type=code&scope=openid"
    "&redirect_uri=https%3A%2F%2Facceso.ista.es%2Fauth%2Fcallback%2Fabonado"
    "&state=https%3A%2F%2Foficina.ista.es%2FGesCon%2FAuthHandler.do"
    "&prompt=login&max_age=0"
)
DEFAULT_PORTAL_URL: Final = "https://oficina.ista.es"

PATH_RADIO: Final = "/GesCon/GestionFincas.do"
PATH_RADIO_DEFAULT: Final = "/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio"
PATH_BILLS: Final = "/GesCon/GestionFacturacionBuscar.do?metodo=buscarRecibos"
#: exportación CSV (displaytag) de la lista de recibos mostrada en la sesión: todo el
#: historial en una sola petición (spec 004)
PATH_BILLS_CSV: Final = (
    "/GesCon/GestionFacturacion.do?d-148657-e=1&metodo=listadoRecibos"
    "&metodo=buscarRecibos&6578706f7274=1"
)
PATH_OFFICE: Final = "/GesCon/GestionOficinaVirtual.do"
PATH_LOGOUT: Final = "/GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado"

#: días que muestra «Mis lecturas Radio» sin indicar fechas
DEFAULT_WINDOW_DAYS: Final = 15
MAX_REDIRECTS: Final = 10
REQUEST_TIMEOUT: Final = 30
#: un año de lecturas son ~1,2 MB de HTML
HISTORY_TIMEOUT: Final = 120

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


def _as_url(value: str | URL) -> URL:
    return value if isinstance(value, URL) else URL(value, encoded=True)


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


class CalistaClient:
    """Acceso de solo lectura a la oficina virtual de un abonado."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        auth_url: str = DEFAULT_AUTH_URL,
        portal_url: str = DEFAULT_PORTAL_URL,
        unsafe_cookies: bool = False,
    ) -> None:
        self._session = session
        self.username = username
        self._password = password
        self._auth_url = _as_url(auth_url)
        self._portal = URL(portal_url.rstrip("/"))
        #: cookies propias (``unsafe`` solo para tests contra 127.0.0.1)
        self._jar = aiohttp.CookieJar(unsafe=unsafe_cookies)
        self._lock = asyncio.Lock()

    # --- HTTP ---------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: URL,
        *,
        data: dict[str, str] | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> tuple[int, URL, str | None, bytes]:
        try:
            async with self._session.request(
                method,
                url,
                data=data,
                allow_redirects=False,
                cookies=self._jar.filter_cookies(url),
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                body = await resp.read()
                self._jar.update_cookies(resp.cookies, resp.url)
                _LOGGER.debug(
                    "%s %s%s → %s (%d B)", method, url.host, url.path, resp.status, len(body)
                )
                return resp.status, resp.url, resp.headers.get("Location"), body
        except TimeoutError as err:
            raise CannotConnect(f"Tiempo agotado contactando con {url.host}") from err
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Error de red con {url.host}: {type(err).__name__}") from err

    async def _follow(
        self, status: int, url: URL, location: str | None, body: bytes
    ) -> tuple[int, URL, bytes]:
        """Sigue redirecciones con ``GET`` guardando las cookies de cada salto."""
        hops = 0
        while status in _REDIRECT_CODES:
            if not location or hops >= MAX_REDIRECTS:
                raise CannotConnect("Redirecciones inesperadas durante el login")
            if "RedirectToKeycloak" in location:
                # GesCon no reconoce la sesión (suele apuntar a un host interno)
                raise SessionExpired("El portal ha rechazado la sesión durante el login")
            target = URL(location, encoded=True)
            next_url = target if target.is_absolute() else url.join(target)
            status, url, location, body = await self._request("GET", next_url)
            hops += 1
        return status, url, body

    async def _portal_page(
        self,
        path: str | URL,
        *,
        data: dict[str, str] | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ) -> Element:
        """Página autenticada de GesCon. Sesión no válida → ``SessionExpired``."""
        url = path if isinstance(path, URL) else URL(f"{self._portal}{path}", encoded=True)
        status, _, _, body = await self._request(
            "POST" if data is not None else "GET", url, data=data, timeout=timeout
        )
        if status in _REDIRECT_CODES or status in (401, 500):
            raise SessionExpired(f"HTTP {status} en {url.path}")
        if status != 200:
            raise CannotConnect(f"HTTP {status} en {url.path}")
        doc = parse_html(decode_html(body))
        if not is_portal_page(doc):
            if login_form_action(doc):
                raise SessionExpired(f"Login pedido en {url.path}")
            raise ParseError(f"Respuesta inesperada en {url.path}")
        return doc

    async def _portal_export(self, path: str) -> str:
        """Exportación de texto (CSV) autenticada. Sesión no válida → ``SessionExpired``."""
        url = URL(f"{self._portal}{path}", encoded=True)
        status, _, _, body = await self._request("GET", url)
        if status in _REDIRECT_CODES or status in (401, 500):
            raise SessionExpired(f"HTTP {status} en la exportación {url.path}")
        if status != 200:
            raise CannotConnect(f"HTTP {status} en la exportación {url.path}")
        text = decode_html(body)
        if "<html" in text[:1000].lower():
            raise ParseError(f"La exportación {url.path} no es CSV")
        return text

    async def _async_read_bills(self, fallback: list[Bill]) -> list[Bill]:
        """Historial completo de recibos (CSV); si no se puede, la primera página."""
        try:
            bills = parse_bills_csv(await self._portal_export(PATH_BILLS_CSV))
        except ParseError as err:
            _LOGGER.debug("Sin exportación de recibos (%s); se usa la primera página", err)
            return fallback
        return bills or fallback

    # --- sesión -------------------------------------------------------------------

    async def async_login(self) -> Element:
        """Inicia sesión y devuelve la página de aterrizaje («Mis recibos»)."""
        self._jar.clear()
        status, url, location, body = await self._request("GET", self._auth_url)
        status, url, body = await self._follow(status, url, location, body)
        doc = parse_html(decode_html(body))
        action = login_form_action(doc)
        if status != 200 or not action:
            raise CannotConnect(
                f"La página de login de ista no responde como se esperaba ({status})"
            )

        target = URL(action, encoded=True)
        status, url, location, body = await self._request(
            "POST",
            target if target.is_absolute() else url.join(target),
            data={"username": self.username, "password": self._password},
        )
        if status == 200:
            doc = parse_html(decode_html(body))
            if login_form_action(doc):
                raise InvalidAuth(login_error_message(doc) or "Credenciales no válidas")
            title = doc.find("title")
            raise AuthActionRequired(
                "El portal pide una acción antes de entrar"
                + (f": {title.text()}" if title is not None and title.text() else "")
            )
        if status not in _REDIRECT_CODES:
            raise CannotConnect(f"HTTP {status} al enviar las credenciales")

        status, url, body = await self._follow(status, url, location, body)
        doc = parse_html(decode_html(body))
        if status != 200 or url.host != self._portal.host or not is_portal_page(doc):
            if login_form_action(doc):
                raise InvalidAuth(login_error_message(doc) or "Credenciales no válidas")
            raise CannotConnect(f"El portal no ha abierto la sesión ({status})")
        _LOGGER.debug("Sesión iniciada en el portal")
        return doc

    async def async_logout(self) -> None:
        """Cierra la sesión (best effort) y olvida las cookies."""
        try:
            await self._request("GET", URL(f"{self._portal}{PATH_LOGOUT}", encoded=True))
        except CalistaError as err:
            _LOGGER.debug("Logout fallido (se ignora): %s", err)
        finally:
            self._jar.clear()

    # --- lectura ------------------------------------------------------------------

    async def async_get_data(self, history_start: date | None = None) -> CalistaData:
        """Lee todas las viviendas. ``history_start`` pide lecturas desde esa fecha.

        Abre y cierra su propia sesión. Si la sesión cae a mitad de ciclo, lo repite una
        vez con un login nuevo.
        """
        async with self._lock:
            try:
                return await self._async_read_all(history_start)
            except SessionExpired as err:
                _LOGGER.debug("Sesión no válida durante la lectura (%s); se repite", err)
                return await self._async_read_all(history_start)

    async def _async_read_all(self, history_start: date | None) -> CalistaData:
        landing = await self.async_login()
        try:
            header = parse_header(landing)
            data = CalistaData()
            if len(header.dwellings) <= 1:
                radio = await self._async_read_radio(
                    await self._portal_page(PATH_RADIO_DEFAULT), history_start
                )
                # la exportación usa la lista de recibos de la página de aterrizaje
                bills = await self._async_read_bills(parse_bills(landing))
                data.dwellings.append(
                    Dwelling(
                        id=header.active_id or radio.header.active_id,
                        number=radio.header.number or header.number,
                        address=radio.header.address or header.address,
                        meters=radio.meters,
                        bills=bills,
                    )
                )
                data.window_start, data.window_end = radio.window_start, radio.window_end
                return data
            # Varias viviendas: se recorre cada abonado como hace el selector de la web
            for dwelling_id, address in header.dwellings:
                switch_url = URL(f"{self._portal}{PATH_OFFICE}").with_query(
                    metodo="cambioAbonado", param=dwelling_id, metodoDestino="preCargaLecturasRadio"
                )
                radio = await self._async_read_radio(
                    await self._portal_page(switch_url, data={"metodo": "preCargaLecturasRadio"}),
                    history_start,
                )
                bills = await self._async_read_bills(
                    parse_bills(await self._portal_page(PATH_BILLS))
                )
                data.dwellings.append(
                    Dwelling(
                        id=dwelling_id,
                        number=radio.header.number,
                        address=address,
                        meters=radio.meters,
                        bills=bills,
                    )
                )
                data.window_start, data.window_end = radio.window_start, radio.window_end
            return data
        finally:
            await self.async_logout()

    async def _async_read_radio(self, doc: Element, history_start: date | None) -> RadioPage:
        """Página de lecturas radio y, si hace falta más histórico, el rango pedido."""
        page = parse_radio_page(doc)
        if (
            history_start is None
            or page.id_finca is None
            or (page.window_start is not None and history_start >= page.window_start)
        ):
            return page
        end = page.window_end or date.today()
        _LOGGER.debug("Pidiendo lecturas desde %s hasta %s", history_start, end)
        ranged = parse_radio_page(
            await self._portal_page(
                PATH_RADIO,
                data={
                    "metodo": "listadoLecturasRadio",
                    "idFinca": page.id_finca,
                    "idAbonado": "",
                    "validacion": "true",
                    "fechaDesdeRadio": _fmt(history_start),
                    "fechaHastaRadio": _fmt(end),
                },
                timeout=HISTORY_TIMEOUT,
            )
        )
        if ranged.header.number is None:
            ranged.header = page.header
        return ranged


def default_window_start(today: date | None = None) -> date:
    """Primer día que devuelve «Mis lecturas Radio» sin fechas."""
    return (today or date.today()) - timedelta(days=DEFAULT_WINDOW_DAYS)
