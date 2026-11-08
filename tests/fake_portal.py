"""Portal Calista falso para los tests de protocolo (T025).

Un único servidor hace de Keycloak, de pasarela OIDC (``acceso.ista.es``) y de GesCon,
con las mismas redirecciones, cookies y respuestas que el portal real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import secrets

from aiohttp import web

from .conftest import fixture_bytes

USERNAME = "abonado@example.com"
PASSWORD = "s3cret"
REALM = "/realms/GESCON-PORTAL-ES-APP-Abonado"
AUTH_PATH = f"{REALM}/protocol/openid-connect/auth"
AUTH_QUERY = (
    "?client_id=abonado-service&response_type=code&scope=openid"
    "&redirect_uri=x&state=y&prompt=login&max_age=0"
)
INTERNAL_REDIRECT = (
    "https://lmad02istaapp4.gescon.ista.invalid:8443/GesCon/RedirectToKeycloak.do"
    "?metodo=reconectToKeycloak&tipoUsuario=abonado"
)
SECOND_ID = "SegundaVivienda0000000B"
SECOND_ADDRESS = "CL-Calle OTRA 9 1 A MADRID (Madrid)"


@dataclass
class FakePortalState:
    base_url: str = ""
    #: la próxima petición de credenciales pide una acción (cambiar contraseña…)
    require_action: bool = False
    #: la próxima página de datos responde como sesión caducada
    expire_next: int = 0
    #: estado HTTP para simular la sesión caducada (302 al host interno o 500)
    expire_status: int = 302
    #: la página de aterrizaje del login redirige al host interno (sesión rechazada)
    expire_landing: int = 0
    #: la cuenta tiene una segunda vivienda
    two_dwellings: bool = False
    logins: int = 0
    logouts: int = 0
    sessions: set[str] = field(default_factory=set)
    #: (método, ruta con query, formulario) de las peticiones a GesCon
    requests: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    active_dwelling: str = "AbonadoTest0000000000A"
    #: sesiones que han mostrado «Mis recibos» (la exportación usa esa lista)
    bills_listed: set[str] = field(default_factory=set)
    #: la exportación CSV devuelve una página HTML (formato inesperado)
    export_broken: bool = False

    @property
    def auth_url(self) -> str:
        return f"{self.base_url}{AUTH_PATH}{AUTH_QUERY}"


def _html(data: bytes, status: int = 200) -> web.Response:
    return web.Response(body=data, status=status, content_type="text/html", charset="UTF-8")


def _with_second_dwelling(page: bytes, state: FakePortalState) -> bytes:
    if not state.two_dwellings:
        return page
    option = f'<option value="{SECOND_ID}">{SECOND_ADDRESS}</option></select>'.encode()
    page = page.replace(b"</option></select>", b"</option>" + option, 1)
    if state.active_dwelling == SECOND_ID:
        page = page.replace(b"12345678", b"87654321")
    return page


def build_app(state: FakePortalState) -> web.Application:
    def login_page(error: bool = False) -> web.Response:
        name = "keycloak_login_error.html" if error else "keycloak_login.html"
        action = (
            f"{state.base_url}{REALM}/login-actions/authenticate"
            "?session_code=abc&amp;execution=e1&amp;client_id=abonado-service&amp;tab_id=t1"
        )
        return _html(fixture_bytes(name).replace(b"__ACTION__", action.encode()))

    async def auth(request: web.Request) -> web.Response:
        assert request.query["prompt"] == "login"
        response = login_page()
        response.set_cookie("AUTH_SESSION_ID", "kc-auth", path=REALM)
        return response

    async def authenticate(request: web.Request) -> web.Response:
        assert request.cookies.get("AUTH_SESSION_ID") == "kc-auth", "falta la cookie de Keycloak"
        assert request.query["session_code"] == "abc"
        form = await request.post()
        if state.require_action:
            return _html(b"<html><head><title>Actualizar contrase\xc3\xb1a</title></head></html>")
        if form.get("username") != USERNAME or form.get("password") != PASSWORD:
            return login_page(error=True)
        response = web.HTTPFound(
            f"{state.base_url}/auth/callback/abonado?state=https%3A%2F%2Fx&code=c0de"
        )
        response.set_cookie("KEYCLOAK_IDENTITY", "kc-id", path=REALM)
        raise response

    async def callback(request: web.Request) -> web.Response:
        assert request.query["code"] == "c0de"
        response = web.HTTPSeeOther(f"{state.base_url}/GesCon/AuthHandler.do?ticket=t-1")
        response.set_cookie("KCSESSID", "gw", path="/auth")
        raise response

    async def auth_handler(request: web.Request) -> web.Response:
        assert request.cookies.get("KCSESSID") is None, "cookie de otra ruta enviada"
        session = secrets.token_hex(8)
        state.sessions.add(session)
        state.logins += 1
        state.active_dwelling = "AbonadoTest0000000000A"
        response = web.HTTPFound("/GesCon/GestionOficinaVirtual.do?metodo=loginAbonado&ticket=t-2")
        response.set_cookie("JSESSIONID", session, path="/GesCon")
        raise response

    def authenticated(request: web.Request, data_page: bool = True) -> web.Response | None:
        if request.cookies.get("JSESSIONID") not in state.sessions:
            raise web.HTTPFound(INTERNAL_REDIRECT)
        if not data_page:
            if state.expire_landing:
                state.expire_landing -= 1
                raise web.HTTPFound(INTERNAL_REDIRECT)
            return None
        if state.expire_next:
            state.expire_next -= 1
            if state.expire_status == 500:
                return web.Response(status=500, text="Error")
            raise web.HTTPFound(INTERNAL_REDIRECT)
        return None

    async def office(request: web.Request) -> web.Response:
        metodo = request.query.get("metodo")
        form = dict(await request.post()) if request.method == "POST" else {}
        state.requests.append(
            (request.method, request.path_qs, {k: str(v) for k, v in form.items()})
        )
        if metodo == "logOutAbonado":
            state.logouts += 1
            state.sessions.discard(request.cookies.get("JSESSIONID", ""))
            raise web.HTTPFound("/GesCon/RedirectToKeycloak.do?metodo=reconectToKeycloak")
        if (error := authenticated(request, data_page=metodo != "loginAbonado")) is not None:
            return error
        if metodo == "loginAbonado":
            state.bills_listed.add(request.cookies["JSESSIONID"])
            return _html(_with_second_dwelling(fixture_bytes("landing.html"), state))
        if metodo == "cambioAbonado":
            assert request.method == "POST"
            assert request.query["metodoDestino"] == "preCargaLecturasRadio"
            assert form.get("metodo") == "preCargaLecturasRadio"
            state.active_dwelling = request.query["param"]
            return _html(_with_second_dwelling(fixture_bytes("radio.html"), state))
        raise web.HTTPNotFound

    async def fincas(request: web.Request) -> web.Response:
        form = dict(await request.post()) if request.method == "POST" else {}
        state.requests.append(
            (request.method, request.path_qs, {k: str(v) for k, v in form.items()})
        )
        if (error := authenticated(request)) is not None:
            return error
        if request.method == "GET" and request.query.get("metodo") == "preCargaLecturasRadio":
            return _html(_with_second_dwelling(fixture_bytes("radio.html"), state))
        if request.method == "POST" and form.get("metodo") == "listadoLecturasRadio":
            assert form["idFinca"] == "1000"
            assert form["validacion"] == "true"
            return _html(_with_second_dwelling(fixture_bytes("radio_range.html"), state))
        raise web.HTTPNotFound

    async def bills(request: web.Request) -> web.Response:
        state.requests.append((request.method, request.path_qs, {}))
        if (error := authenticated(request)) is not None:
            return error
        state.bills_listed.add(request.cookies["JSESSIONID"])
        return _html(_with_second_dwelling(fixture_bytes("bills.html"), state))

    async def bills_export(request: web.Request) -> web.Response:
        state.requests.append((request.method, request.path_qs, {}))
        if (error := authenticated(request)) is not None:
            return error
        assert request.query["d-148657-e"] == "1"
        assert request.query["6578706f7274"] == "1"
        if request.cookies["JSESSIONID"] not in state.bills_listed:
            return web.Response(status=500, text="Error")
        if state.export_broken:
            return _html(b"<html><body>Error</body></html>")
        return web.Response(
            body=fixture_bytes("bills.csv"), content_type="text/csv", charset="UTF-8"
        )

    app = web.Application()
    app.router.add_get(AUTH_PATH, auth)
    app.router.add_post(f"{REALM}/login-actions/authenticate", authenticate)
    app.router.add_get("/auth/callback/abonado", callback)
    app.router.add_get("/GesCon/AuthHandler.do", auth_handler)
    app.router.add_route("*", "/GesCon/GestionOficinaVirtual.do", office)
    app.router.add_route("*", "/GesCon/GestionFincas.do", fincas)
    app.router.add_get("/GesCon/GestionFacturacionBuscar.do", bills)
    app.router.add_get("/GesCon/GestionFacturacion.do", bills_export)
    return app
