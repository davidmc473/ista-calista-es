"""Tests del coste en estadísticas (spec 004) y del evento «Nuevo recibo» (spec 005)."""

from __future__ import annotations

from datetime import date
from functools import partial

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_metadata
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ista_calista_es.api import Bill, MeterKind
from custom_components.ista_calista_es.const import CONF_IMPORT_STATISTICS, DOMAIN
from custom_components.ista_calista_es.statistics import cost_statistic_id

from .common import entity_id, refresh, setup, stats_rows
from .conftest import NUMBER, FakeClient

HEATING = cost_statistic_id(NUMBER, MeterKind.HEAT_COST_ALLOCATOR)
HOT_WATER = cost_statistic_id(NUMBER, MeterKind.HOT_WATER)
HEATING_LABEL = "Radio Distribuidor de Costes de Calefacción"


def _add_bill(client: FakeClient, bill: Bill) -> None:
    for data in (client.default, client.ranged):
        data.dwellings[0].bills.insert(0, bill)


# --- spec 004: coste ----------------------------------------------------------------


async def test_cost_statistics_first_import(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await setup(hass, config_entry)
    bills = mock_client.default.dwellings[0].bills
    heating_days = {b.date for b in bills if b.kind is MeterKind.HEAT_COST_ALLOCATOR}
    water_days = {b.date for b in bills if b.kind is MeterKind.HOT_WATER}
    assert len(heating_days) + len(water_days) == 34  # un recibo por tipo y día

    heating = await stats_rows(hass, HEATING)
    assert len(heating) == len(heating_days)
    assert heating[-1]["sum"] == pytest.approx(337.83)
    assert heating[-1]["state"] == pytest.approx(17.11)
    water = await stats_rows(hass, HOT_WATER)
    assert len(water) == len(water_days)
    assert water[-1]["sum"] == 0.0

    metadata = await get_instance(hass).async_add_executor_job(
        partial(get_metadata, hass, statistic_ids={HEATING, HOT_WATER})
    )
    assert metadata[HEATING][1]["unit_of_measurement"] == "EUR"
    assert metadata[HEATING][1]["name"] == "ista · Coste calefacción"
    assert metadata[HOT_WATER][1]["name"] == "ista · Coste agua caliente"
    assert metadata[HEATING][1]["source"] == DOMAIN


async def test_cost_statistics_incremental_and_correction(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await setup(hass, config_entry)
    _add_bill(
        mock_client, Bill(date(2026, 10, 31), HEATING_LABEL, MeterKind.HEAT_COST_ALLOCATOR, 9.5)
    )
    await refresh(hass, config_entry)
    heating = await stats_rows(hass, HEATING)
    before = len(heating)
    assert heating[-1]["sum"] == pytest.approx(337.83 + 9.5)

    # recibo con fecha anterior a la última fila (corrección): se recalcula la serie
    _add_bill(
        mock_client, Bill(date(2024, 1, 15), HEATING_LABEL, MeterKind.HEAT_COST_ALLOCATOR, 5.0)
    )
    await refresh(hass, config_entry)
    heating = await stats_rows(hass, HEATING)
    assert len(heating) == before + 1
    assert heating[-1]["sum"] == pytest.approx(337.83 + 9.5 + 5.0)


async def test_cost_statistics_disabled(hass: HomeAssistant, mock_client: FakeClient) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abonado@example.com",
        title="ista Calista (abonado@example.com)",
        data={"username": "abonado@example.com", "password": "x"},
        options={CONF_IMPORT_STATISTICS: False},
    )
    entry.add_to_hass(hass)
    await setup(hass, entry)
    assert await stats_rows(hass, HEATING) == []


async def test_last_bill_uses_full_history(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await setup(hass, config_entry)
    _add_bill(
        mock_client, Bill(date(2026, 10, 31), HEATING_LABEL, MeterKind.HEAT_COST_ALLOCATOR, 9.5)
    )
    await refresh(hass, config_entry)
    state = hass.states.get(entity_id(hass, f"{NUMBER}_last_bill_heat_cost_allocator"))
    assert state.state == "9.5"
    assert state.attributes["date"] == "2026-10-31"


# --- spec 005: evento ---------------------------------------------------------------


def _capture(hass: HomeAssistant, event_entity: str) -> list:
    states: list = []

    @callback
    def _changed(event: Event) -> None:
        states.append(event.data["new_state"])

    async_track_state_change_event(hass, [event_entity], _changed)
    return states


async def test_no_events_for_existing_bills(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await setup(hass, config_entry)
    state = hass.states.get(entity_id(hass, f"{NUMBER}_new_bill", "event"))
    assert state.state == STATE_UNKNOWN
    assert state.attributes["event_types"] == ["new_bill"]


async def test_event_per_new_bill(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, hass_storage
) -> None:
    await setup(hass, config_entry)
    event_entity = entity_id(hass, f"{NUMBER}_new_bill", "event")
    states = _capture(hass, event_entity)

    _add_bill(mock_client, Bill(date(2026, 10, 31), "Agua caliente", MeterKind.HOT_WATER, 0.0))
    _add_bill(
        mock_client, Bill(date(2026, 10, 31), HEATING_LABEL, MeterKind.HEAT_COST_ALLOCATOR, 9.5)
    )
    await refresh(hass, config_entry)

    fired = [s for s in states if s.attributes.get("event_type") == "new_bill"]
    assert len(fired) == 2
    assert {(s.attributes["kind"], s.attributes["amount"]) for s in fired} == {
        ("hot_water", 0.0),
        ("heat_cost_allocator", 9.5),
    }
    last = hass.states.get(event_entity)
    assert last.attributes["date"] == "2026-10-31"
    assert last.attributes["currency"] == "EUR"
    assert last.attributes["type"] in ("Agua caliente", HEATING_LABEL)

    # sin recibos nuevos no hay más eventos, tampoco tras recargar la integración
    states.clear()
    await refresh(hass, config_entry)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not [
        s for s in states if s is not None and s.state != last.state and s.state != "unavailable"
    ]
    assert hass.states.get(event_entity).state == last.state

    # al eliminar la entrada se borra el registro de recibos vistos
    key = f"{DOMAIN}.{config_entry.entry_id}.bills"
    assert key in hass_storage
    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_late_old_bill_does_not_fire(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await setup(hass, config_entry)
    states = _capture(hass, entity_id(hass, f"{NUMBER}_new_bill", "event"))
    _add_bill(
        mock_client, Bill(date(2024, 1, 15), HEATING_LABEL, MeterKind.HEAT_COST_ALLOCATOR, 5.0)
    )
    await refresh(hass, config_entry)
    assert not [s for s in states if s.attributes.get("event_type") == "new_bill"]
