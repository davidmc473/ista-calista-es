"""Configuración común de tests.

Si Home Assistant no está instalado (p. ej. en Windows), se registra un paquete
``custom_components.ista_calista_es`` vacío para poder importar la capa ``api/`` sin
ejecutar el ``__init__`` de la integración; los tests de HA se saltan solos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(ROOT))

try:
    import homeassistant  # noqa: F401

    HAS_HA = True
except ImportError:
    HAS_HA = False
    for _name, _path in (
        ("custom_components", ROOT / "custom_components"),
        ("custom_components.ista_calista_es", ROOT / "custom_components" / "ista_calista_es"),
    ):
        _module = types.ModuleType(_name)
        _module.__path__ = [str(_path)]
        sys.modules.setdefault(_name, _module)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Reparte los tests según el arnés disponible.

    - ``tests/ha`` necesita el plugin de Home Assistant.
    - ``test_client.py`` levanta un portal falso en 127.0.0.1 y el plugin de HA bloquea
      los sockets, así que se ejecuta aparte: ``pytest -p no:homeassistant``.
    """
    ha_plugin = config.pluginmanager.has_plugin("homeassistant")
    if collection_path.name == "ha" and collection_path.is_dir() and not ha_plugin:
        return True
    if collection_path.name == "test_client.py" and ha_plugin:
        return True
    return None


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_doc(name: str):
    from custom_components.ista_calista_es.api.html import decode_html, parse_html

    return parse_html(decode_html(fixture_bytes(name)))


@pytest.fixture
async def fake_portal() -> AsyncIterator[tuple]:
    """Arranca el portal falso; devuelve (estado, url base)."""
    from aiohttp.test_utils import TestServer

    from .fake_portal import FakePortalState, build_app

    state = FakePortalState()
    server = TestServer(build_app(state), host="127.0.0.1")
    await server.start_server()
    state.base_url = f"http://127.0.0.1:{server.port}"
    try:
        yield state, state.base_url
    finally:
        await server.close()
