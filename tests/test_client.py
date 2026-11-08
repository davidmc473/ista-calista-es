"""Tests de protocolo contra el portal falso (T024, T025, FR-001…FR-009)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import aiohttp
import pytest

from custom_components.ista_calista_es.api import (
    AuthActionRequired,
    CalistaClient,
    CannotConnect,
    InvalidAuth,
    MeterKind,
    SessionExpired,
)

from .fake_portal import PASSWORD, SECOND_ID, USERNAME, FakePortalState


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    # Igual que en HA: sesión compartida sin cookies; el cliente lleva las suyas
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as http:
        yield http


def _client(
    session: aiohttp.ClientSession, state: FakePortalState, password: str = PASSWORD
) -> CalistaClient:
    return CalistaClient(
        session,
        USERNAME,
        password,
        auth_url=state.auth_url,
        portal_url=state.base_url,
        unsafe_cookies=True,
    )


async def test_full_cycle(fake_portal, session) -> None:
    state, _ = fake_portal
    data = await _client(session, state).async_get_data()

    assert state.logins == 1
    assert state.logouts == 1
    assert state.sessions == set()  # sesión cerrada
    assert (data.window_start, data.window_end) == (date(2026, 10, 24), date(2026, 11, 8))
    assert len(data.dwellings) == 1
    dwelling = data.dwellings[0]
    assert dwelling.number == "12345678"
    assert dwelling.id == "AbonadoTest0000000000A"
    assert len(dwelling.meters) == 9
    assert {b.kind for b in dwelling.bills} == {MeterKind.HOT_WATER, MeterKind.HEAT_COST_ALLOCATOR}
    # solo la página de lecturas (los recibos vienen en la de aterrizaje) y el logout
    paths = [path for _, path, _ in state.requests]
    assert paths == [
        "/GesCon/GestionOficinaVirtual.do?metodo=loginAbonado&ticket=t-2",
        "/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio",
        "/GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado",
    ]


async def test_history_range(fake_portal, session) -> None:
    state, _ = fake_portal
    data = await _client(session, state).async_get_data(history_start=date(2026, 9, 2))
    post = [form for method, _, form in state.requests if method == "POST"]
    assert post == [
        {
            "metodo": "listadoLecturasRadio",
            "idFinca": "1000",
            "idAbonado": "",
            "validacion": "true",
            "fechaDesdeRadio": "02/09/2026",
            "fechaHastaRadio": "08/11/2026",
        }
    ]
    assert data.window_start == date(2026, 9, 2)
    assert len(data.dwellings[0].meters[0].readings) == 64


async def test_history_inside_default_window_does_not_post(fake_portal, session) -> None:
    state, _ = fake_portal
    await _client(session, state).async_get_data(history_start=date(2026, 10, 30))
    assert not [r for r in state.requests if r[0] == "POST"]


async def test_invalid_auth(fake_portal, session) -> None:
    state, _ = fake_portal
    with pytest.raises(InvalidAuth, match="incorrectas"):
        await _client(session, state, password="mala").async_get_data()
    assert state.logins == 0


async def test_auth_action_required(fake_portal, session) -> None:
    state, _ = fake_portal
    state.require_action = True
    with pytest.raises(AuthActionRequired, match="Actualizar contraseña"):
        await _client(session, state).async_get_data()


@pytest.mark.parametrize("status", [302, 500])
async def test_session_expired_mid_cycle_is_retried_once(fake_portal, session, status) -> None:
    state, _ = fake_portal
    state.expire_next, state.expire_status = 1, status
    data = await _client(session, state).async_get_data()
    assert len(data.meters) == 9
    assert state.logins == 2


async def test_session_rejected_on_landing_is_retried(fake_portal, session) -> None:
    state, _ = fake_portal
    state.expire_landing = 1  # 302 a RedirectToKeycloak en un host interno: no se sigue
    data = await _client(session, state).async_get_data()
    assert len(data.meters) == 9
    assert state.logins == 2


async def test_session_expired_twice_fails(fake_portal, session) -> None:
    state, _ = fake_portal
    state.expire_next = 2
    with pytest.raises(SessionExpired):
        await _client(session, state).async_get_data()
    assert state.logouts == 2  # siempre se cierra la sesión


async def test_cannot_connect(session) -> None:
    client = CalistaClient(
        session,
        USERNAME,
        PASSWORD,
        auth_url="http://127.0.0.1:9/realms/x/auth",
        portal_url="http://127.0.0.1:9",
    )
    with pytest.raises(CannotConnect):
        await client.async_get_data()


async def test_two_dwellings(fake_portal, session) -> None:
    state, _ = fake_portal
    state.two_dwellings = True
    data = await _client(session, state).async_get_data()
    assert [d.id for d in data.dwellings] == ["AbonadoTest0000000000A", SECOND_ID]
    assert [d.number for d in data.dwellings] == ["12345678", "87654321"]
    assert data.dwellings[1].address == "CL-Calle OTRA 9 1 A MADRID (Madrid)"
    assert all(len(d.meters) == 9 and d.bills for d in data.dwellings)
    switches = [path for method, path, _ in state.requests if "cambioAbonado" in path]
    assert len(switches) == 2
    assert f"param={SECOND_ID}" in switches[1]


async def test_clients_do_not_share_cookies(fake_portal, session) -> None:
    state, _ = fake_portal
    first, second = _client(session, state), _client(session, state)
    await first.async_login()
    # el segundo cliente no hereda la sesión del primero
    with pytest.raises(SessionExpired):
        await second._portal_page("/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio")
    await first.async_logout()
