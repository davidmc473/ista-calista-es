"""Tests de avisos en «Reparaciones» (spec 002) y equipos sin datos (spec 006)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ista_calista_es.api import (
    AuthActionRequired,
    CannotConnect,
    ParseError,
    Reading,
)
from custom_components.ista_calista_es.const import CONF_STALE_DAYS, DOMAIN

from .common import entity_id, refresh, setup
from .conftest import HALL, WATER, FakeClient


def _issue(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


# --- spec 002: avisos ---------------------------------------------------------------


async def test_portal_changed_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-08T12:00:00+01:00")
    await setup(hass, config_entry)
    assert _issue(hass, config_entry, "portal_changed") is None

    mock_client.error = ParseError("Tabla de lecturas radio sin columnas de serie/tipo")
    await refresh(hass, config_entry)
    issue = _issue(hass, config_entry, "portal_changed")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert not issue.is_fixable
    assert issue.translation_placeholders["error"].startswith("Tabla de lecturas")
    assert issue.translation_placeholders["account"] == config_entry.title
    assert issue.learn_more_url.endswith("/ista-calista-es/issues")

    # un fallo de red no crea ni borra el aviso
    mock_client.error = CannotConnect("caído")
    await refresh(hass, config_entry)
    assert _issue(hass, config_entry, "portal_changed") is not None

    mock_client.error = None
    await refresh(hass, config_entry)
    assert _issue(hass, config_entry, "portal_changed") is None


async def test_action_required_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-08T12:00:00+01:00")
    mock_client.error = AuthActionRequired("El portal pide una acción")
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    issue = _issue(hass, config_entry, "action_required")
    assert issue is not None
    assert issue.learn_more_url == "https://oficina.ista.es/GesCon/"
    assert [f["context"]["source"] for f in hass.config_entries.flow.async_progress()] == [
        SOURCE_REAUTH
    ]
    # tras completar la acción en la web, la siguiente lectura correcta borra el aviso
    mock_client.error = None
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert _issue(hass, config_entry, "action_required") is None


async def test_unload_clears_issues(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-30T12:00:00+01:00")  # todos los equipos sin datos
    await setup(hass, config_entry)
    assert _issue(hass, config_entry, "stale_meters") is not None
    await hass.config_entries.async_unload(config_entry.entry_id)
    assert _issue(hass, config_entry, "stale_meters") is None


# --- spec 006: equipos sin datos ----------------------------------------------------


async def test_no_stale_meters_with_normal_delay(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-08T12:00:00+01:00")  # última lectura 5/11: 3 días
    await setup(hass, config_entry)
    state = hass.states.get(entity_id(hass, f"{WATER}_stale", "binary_sensor"))
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PROBLEM
    assert state.attributes["last_reading"] == "2026-11-05"
    assert state.attributes["days_without_reading"] == 3
    assert state.attributes["threshold"] == 10
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    assert registry_entry.entity_category is not None
    assert _issue(hass, config_entry, "stale_meters") is None


async def test_stale_meter_sensor_and_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-08T12:00:00+01:00")
    await setup(hass, config_entry)
    # el agua deja de transmitir; el resto sigue
    for meter in mock_client.default.meters:
        if meter.serial != WATER:
            meter.readings.append(Reading(meter.readings[-1].date.replace(day=17), 5.0))
    freezer.move_to("2026-11-19T12:00:00+01:00")  # agua: 14 días; resto: 2 días
    await refresh(hass, config_entry)

    water = hass.states.get(entity_id(hass, f"{WATER}_stale", "binary_sensor"))
    assert water.state == STATE_ON
    assert water.attributes["days_without_reading"] == 14
    hall = hass.states.get(entity_id(hass, f"{HALL}_stale", "binary_sensor"))
    assert hall.state == STATE_OFF

    issue = _issue(hass, config_entry, "stale_meters")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["meters"] == "Hot water meter"
    assert issue.translation_placeholders["days"] == "10"

    # vuelve a transmitir: aviso borrado
    water_meter = next(m for m in mock_client.default.meters if m.serial == WATER)
    water_meter.readings.append(Reading(water_meter.readings[-1].date.replace(day=17), 20.0))
    await refresh(hass, config_entry)
    assert hass.states.get(water.entity_id).state == STATE_OFF
    assert _issue(hass, config_entry, "stale_meters") is None


async def test_stale_threshold_from_options(
    hass: HomeAssistant, mock_client: FakeClient, freezer
) -> None:
    freezer.move_to("2026-11-20T12:00:00+01:00")  # 15 días sin lectura
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abonado@example.com",
        title="ista Calista (abonado@example.com)",
        data={"username": "abonado@example.com", "password": "x"},
        options={CONF_STALE_DAYS: 30},
    )
    entry.add_to_hass(hass)
    await setup(hass, entry)
    state = hass.states.get(entity_id(hass, f"{WATER}_stale", "binary_sensor"))
    assert state.state == STATE_OFF
    assert state.attributes["threshold"] == 30
    assert _issue(hass, entry, "stale_meters") is None
