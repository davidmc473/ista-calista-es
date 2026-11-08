"""Tests de setup, entidades, estadísticas y diagnósticos (T030–T036)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import partial
import json

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    get_metadata,
    statistics_during_period,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.ista_calista_es import async_remove_config_entry_device
from custom_components.ista_calista_es.api import (
    AuthActionRequired,
    CannotConnect,
    InvalidAuth,
    Meter,
    MeterKind,
    Reading,
)
from custom_components.ista_calista_es.const import (
    CONF_HISTORY_DAYS,
    CONF_IMPORT_STATISTICS,
    DOMAIN,
)
from custom_components.ista_calista_es.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ista_calista_es.statistics import statistic_id, statistic_start

from .conftest import BATH, BEDROOM, HALL, NUMBER, WATER, FakeClient


def _device(hass: HomeAssistant, entry: MockConfigEntry, ident: str) -> dr.DeviceEntry:
    devices = dr.async_get(hass).async_get_devices(
        identifiers={(DOMAIN, ident)}, config_entry_id=entry.entry_id
    )
    assert len(devices) == 1, f"dispositivo {ident}: {devices}"
    return devices[0]


def _entity_id(hass: HomeAssistant, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id, f"sensor {unique_id} no registrado"
    return entity_id


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def _stats(hass: HomeAssistant, serial: str) -> list[dict]:
    stat_id = statistic_id(serial)
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(0),
        None,
        {stat_id},
        "hour",
        None,
        {"state", "sum"},
    )
    return result.get(stat_id, [])


async def test_setup_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_devices(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    registry = dr.async_get(hass)
    dwelling = _device(hass, config_entry, f"dwelling_{NUMBER}")
    assert dwelling is not None
    assert dwelling.name == f"Dwelling {NUMBER}"
    assert dwelling.entry_type is dr.DeviceEntryType.SERVICE
    meters = [
        d for d in dr.async_entries_for_config_entry(registry, config_entry.entry_id)
        if d.id != dwelling.id
    ]  # fmt: skip
    assert len(meters) == 9
    assert all(d.via_device_id == dwelling.id for d in meters)
    bedroom = _device(hass, config_entry, BEDROOM)
    assert bedroom.name == "Heat cost allocator Dormitorio 1"
    assert bedroom.manufacturer == "ista"
    assert bedroom.model == "Radio Distribuidor de Costes de Calefacción"
    assert bedroom.serial_number == BEDROOM
    water = _device(hass, config_entry, WATER)
    assert water.name == "Hot water meter"


async def test_meter_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)

    reading = hass.states.get(_entity_id(hass, f"{WATER}_reading"))
    assert reading.state == "19.875"
    assert reading.attributes[ATTR_UNIT_OF_MEASUREMENT] == "m³"
    assert reading.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.WATER
    assert reading.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING

    consumption = hass.states.get(_entity_id(hass, f"{WATER}_last_consumption"))
    assert float(consumption.state) == pytest.approx(0.039)
    assert consumption.attributes["from"] == "2026-11-04"
    assert consumption.attributes["to"] == "2026-11-05"
    assert "state_class" not in consumption.attributes

    last_date_id = _entity_id(hass, f"{WATER}_last_reading_date")
    assert hass.states.get(last_date_id).state == "2026-11-05"
    assert er.async_get(hass).async_get(last_date_id).entity_category is EntityCategory.DIAGNOSTIC

    hall = hass.states.get(_entity_id(hass, f"{HALL}_reading"))
    assert hall.state == "3.454"
    assert hall.attributes[ATTR_UNIT_OF_MEASUREMENT] == "UN"
    assert hall.attributes[ATTR_ICON] == "mdi:radiator"
    assert ATTR_DEVICE_CLASS not in hall.attributes
    assert hass.states.get(_entity_id(hass, f"{HALL}_last_consumption")).state == "0.314"


async def test_bill_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    heating = hass.states.get(_entity_id(hass, f"{NUMBER}_last_bill_heat_cost_allocator"))
    assert heating.state == "17.11"
    assert heating.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"
    assert heating.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.MONETARY
    assert heating.attributes["date"] == "2026-05-31"
    water = hass.states.get(_entity_id(hass, f"{NUMBER}_last_bill_hot_water"))
    assert water.state == "0.0"
    assert water.attributes["date"] == "2026-05-30"


async def test_statistics_first_import(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    # sin estadísticas previas se pide el histórico inicial (365 días por defecto)
    assert len(mock_client.calls) == 1
    assert mock_client.calls[0] is not None
    today = dt_util.now().date()
    assert abs((today - timedelta(days=365) - mock_client.calls[0]).days) <= 1

    water = await _stats(hass, WATER)
    assert len(water) == 57
    assert water[-1]["state"] == 19.875
    assert water[-1]["sum"] == pytest.approx(19.875 - 16.758)
    # la lectura del 5/11 (00:00 en Madrid) es la fila que empieza el 4/11 a las 23:00
    assert dt_util.utc_from_timestamp(water[-1]["start"]) == statistic_start(date(2026, 11, 5))
    # 23:00 en Madrid: UTC+1 en invierno, UTC+2 en verano
    assert statistic_start(date(2026, 11, 5)) == datetime(2026, 11, 4, 22, tzinfo=UTC)
    assert statistic_start(date(2026, 7, 1)) == datetime(2026, 6, 30, 21, tzinfo=UTC)

    # el reinicio de temporada (1/10) no resta ni inventa consumo
    hall = await _stats(hass, HALL)
    assert len(hall) == 64
    assert hall[-1]["sum"] == pytest.approx(3.454)
    assert (await _stats(hass, BATH))[-1]["sum"] == pytest.approx(0.0)

    metadata = await get_instance(hass).async_add_executor_job(
        partial(get_metadata, hass, statistic_ids={statistic_id(WATER), statistic_id(HALL)})
    )
    water_meta = metadata[statistic_id(WATER)][1]
    assert water_meta["unit_of_measurement"] == "m³"
    assert water_meta["source"] == DOMAIN
    assert water_meta["has_sum"] is True
    assert water_meta["name"] == "ista · Agua caliente"
    assert metadata[statistic_id(HALL)][1]["name"] == "ista · Repartidor Hall 1"
    assert metadata[statistic_id(HALL)][1]["unit_of_measurement"] == "UN"


async def test_statistics_incremental(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    # nueva lectura publicada: ventana normal, solo se añade la fila nueva
    water = next(m for m in mock_client.default.meters if m.serial == WATER)
    water.readings.append(Reading(date(2026, 11, 6), 19.9))
    await _refresh(hass, config_entry)
    assert mock_client.calls[-1] is None

    rows = await _stats(hass, WATER)
    assert len(rows) == 58
    assert rows[-1]["state"] == 19.9
    assert rows[-1]["sum"] == pytest.approx(19.9 - 16.758)
    assert hass.states.get(_entity_id(hass, f"{WATER}_reading")).state == "19.9"


async def test_statistics_backfill_new_meter(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    new = Meter("900000010", MeterKind.COLD_WATER, "Radio agua fría", "m³", None, None,
                [Reading(date(2026, 11, 4), 5.0), Reading(date(2026, 11, 5), 5.5)])  # fmt: skip
    mock_client.default.dwellings[0].meters.append(new)
    mock_client.ranged.dwellings[0].meters.append(new)
    await _refresh(hass, config_entry)
    # el equipo nuevo no tiene estadísticas: se pide el histórico completo otra vez
    assert mock_client.calls[-2] is None
    assert mock_client.calls[-1] is not None
    assert len(await _stats(hass, "900000010")) == 2
    # y sus entidades y su dispositivo se crean sin reiniciar
    assert hass.states.get(_entity_id(hass, "900000010_reading")).state == "5.5"
    device = _device(hass, config_entry, "900000010")
    assert device.name == "Cold water meter"


async def test_statistics_disabled(hass: HomeAssistant, mock_client: FakeClient) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abonado@example.com",
        data={"username": "abonado@example.com", "password": "x"},
        options={CONF_IMPORT_STATISTICS: False, CONF_HISTORY_DAYS: 365},
    )
    entry.add_to_hass(hass)
    await _setup(hass, entry)
    assert mock_client.calls == [None]
    assert await _stats(hass, WATER) == []


async def test_history_after_restart(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-08T12:00:00+01:00")
    await _setup(hass, config_entry)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    # tras reiniciar, las estadísticas existen hasta el 5/11: basta la ventana normal
    assert mock_client.calls[-1] is None

    # HA parado tres semanas: se pide desde el día anterior a la última fila importada
    freezer.move_to("2026-11-29T12:00:00+01:00")
    await _refresh(hass, config_entry)
    assert mock_client.calls[-1] == date(2026, 11, 4)


@pytest.mark.parametrize("error", [InvalidAuth(), AuthActionRequired()])
async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, error
) -> None:
    mock_client.error = error
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_update_failure_marks_unavailable(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    mock_client.error = CannotConnect("caído")
    await _refresh(hass, config_entry)
    assert hass.states.get(_entity_id(hass, f"{WATER}_reading")).state == STATE_UNAVAILABLE
    mock_client.error = None
    await _refresh(hass, config_entry)
    assert hass.states.get(_entity_id(hass, f"{WATER}_reading")).state == "19.875"


async def test_remove_stale_device(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    water = _device(hass, config_entry, WATER)
    assert not await async_remove_config_entry_device(hass, config_entry, water)
    mock_client.default.dwellings[0].meters = [
        m for m in mock_client.default.dwellings[0].meters if m.serial != WATER
    ]
    await _refresh(hass, config_entry)
    assert hass.states.get(_entity_id(hass, f"{WATER}_reading")).state == STATE_UNAVAILABLE
    assert await async_remove_config_entry_device(hass, config_entry, water)


async def test_diagnostics_without_personal_data(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient
) -> None:
    await _setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    dump = json.dumps(diag, default=str)
    for secret in ("s3cret", "abonado@example.com", NUMBER, "FALSA", WATER, "AbonadoTest"):
        assert secret not in dump
    assert diag["data"]["dwellings"][0]["meters"][8]["kind"] == "hot_water"
    assert isinstance(datetime.fromisoformat(diag["data"]["window_end"]), datetime)
