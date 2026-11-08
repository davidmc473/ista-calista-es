"""Avisos en «Reparaciones» (spec 002)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .const import DOMAIN
from .statistics import meter_label

if TYPE_CHECKING:
    from .coordinator import CalistaConfigEntry

ISSUE_PORTAL_CHANGED = "portal_changed"
ISSUE_ACTION_REQUIRED = "action_required"
ISSUE_STALE_METERS = "stale_meters"
ALL_ISSUES = (ISSUE_PORTAL_CHANGED, ISSUE_ACTION_REQUIRED, ISSUE_STALE_METERS)


def issue_id(entry: ConfigEntry, key: str) -> str:
    """Un aviso por tipo y entrada: varias cuentas no se pisan."""
    return f"{key}_{entry.entry_id}"


@callback
def async_raise_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    key: str,
    *,
    severity: ir.IssueSeverity,
    placeholders: dict[str, str] | None = None,
    learn_more_url: str | None = None,
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry, key),
        is_fixable=False,
        is_persistent=False,
        severity=severity,
        translation_key=key,
        translation_placeholders={"account": entry.title, **(placeholders or {})},
        learn_more_url=learn_more_url,
    )


@callback
def async_clear_issues(hass: HomeAssistant, entry: ConfigEntry, *keys: str) -> None:
    for key in keys or ALL_ISSUES:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry, key))


@callback
def async_update_stale_issue(hass: HomeAssistant, entry: CalistaConfigEntry) -> None:
    """Un único aviso con los equipos sin lecturas recientes (specs 002 y 006)."""
    coordinator = entry.runtime_data
    stale = coordinator.stale_meters()
    if not stale:
        async_clear_issues(hass, entry, ISSUE_STALE_METERS)
        return
    names: dict[str, str] = {}
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        for domain, ident in device.identifiers:
            if domain == DOMAIN and (name := device.name_by_user or device.name):
                names[ident] = name
    async_raise_issue(
        hass,
        entry,
        ISSUE_STALE_METERS,
        severity=ir.IssueSeverity.WARNING,
        placeholders={
            "meters": ", ".join(names.get(m.serial) or meter_label(m) for m in stale),
            "days": str(coordinator.stale_days),
        },
    )
