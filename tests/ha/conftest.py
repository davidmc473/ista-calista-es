"""Fixtures de Home Assistant: cliente simulado y entrada de configuración."""

from __future__ import annotations

from collections.abc import Iterator
import copy
from datetime import date
from unittest.mock import patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ista_calista_es.api import CalistaData, Dwelling
from custom_components.ista_calista_es.api.parser import parse_bills, parse_radio_page
from custom_components.ista_calista_es.const import DOMAIN

from ..conftest import fixture_doc

USERNAME = "abonado@example.com"
ENTRY_DATA = {CONF_USERNAME: USERNAME, CONF_PASSWORD: "s3cret"}
NUMBER = "12345678"
WATER = "900000009"
HALL = "900000008"
BATH = "900000004"
BEDROOM = "900000001"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock, enable_custom_integrations: None
) -> Iterator[None]:
    """La integración depende del recorder: todos los tests lo levantan en memoria."""
    yield


def build_data(page_name: str) -> CalistaData:
    page = parse_radio_page(fixture_doc(page_name))
    return CalistaData(
        dwellings=[
            Dwelling(
                id="AbonadoTest0000000000A",
                number=NUMBER,
                address="CL-Calle FALSA 1 2 B MADRID (Madrid)",
                meters=page.meters,
                bills=parse_bills(fixture_doc("landing.html")),
            )
        ],
        window_start=page.window_start,
        window_end=page.window_end,
    )


class FakeClient:
    """Cliente en memoria: ventana por defecto o rango según ``history_start``."""

    def __init__(self) -> None:
        self.default = build_data("radio.html")
        self.ranged = build_data("radio_range.html")
        self.error: Exception | None = None
        self.calls: list[date | None] = []

    async def async_get_data(self, history_start: date | None = None) -> CalistaData:
        self.calls.append(history_start)
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.ranged if history_start is not None else self.default)


@pytest.fixture
def mock_client() -> Iterator[FakeClient]:
    client = FakeClient()
    with patch("custom_components.ista_calista_es.CalistaClient", return_value=client):
        yield client


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=USERNAME,
        title=f"ista Calista ({USERNAME})",
        data=dict(ENTRY_DATA),
    )
    entry.add_to_hass(hass)
    return entry
