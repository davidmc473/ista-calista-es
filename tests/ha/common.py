"""Utilidades compartidas por los tests de Home Assistant."""

from __future__ import annotations

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.ista_calista_es.const import DOMAIN
from custom_components.ista_calista_es.statistics import statistic_id


def device(hass: HomeAssistant, entry: MockConfigEntry, ident: str) -> dr.DeviceEntry:
    devices = dr.async_get(hass).async_get_devices(
        identifiers={(DOMAIN, ident)}, config_entry_id=entry.entry_id
    )
    assert len(devices) == 1, f"dispositivo {ident}: {devices}"
    return devices[0]


def entity_id(hass: HomeAssistant, unique_id: str, platform: str = "sensor") -> str:
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert found, f"{platform} {unique_id} no registrado"
    return found


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def stats_rows(hass: HomeAssistant, stat_id: str) -> list[dict]:
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


async def meter_stats(hass: HomeAssistant, serial: str) -> list[dict]:
    return await stats_rows(hass, statistic_id(serial))
