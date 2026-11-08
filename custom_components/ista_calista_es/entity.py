"""Dispositivos (vivienda y equipos) y entidades base."""

from __future__ import annotations

import inspect
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Dwelling, Meter, MeterKind
from .const import DOMAIN, MANUFACTURER, PORTAL_URL
from .coordinator import CalistaConfigEntry, CalistaDataUpdateCoordinator

#: HA 2026.8+ enlaza con ``via_device_id``; ``via_device`` queda obsoleto (fin en 2027.8)
_HAS_VIA_DEVICE_ID = (
    "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)


def dwelling_identifier(key: str) -> tuple[str, str]:
    return (DOMAIN, f"dwelling_{key}")


def dwelling_device_info(dwelling: Dwelling) -> DeviceInfo:
    return DeviceInfo(
        identifiers={dwelling_identifier(dwelling.key)},
        manufacturer=MANUFACTURER,
        model="Calista",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=PORTAL_URL,
        translation_key="dwelling",
        translation_placeholders={"number": dwelling.number or dwelling.key},
    )


def meter_device_info(meter: Meter) -> DeviceInfo:
    """Nombre traducido según tipo y ubicación (``Repartidor Dormitorio 1``)."""
    key = meter.kind.value + ("_location" if meter.location else "")
    placeholders: dict[str, str] = {}
    if meter.location:
        placeholders["location"] = meter.location
    if meter.kind is MeterKind.UNKNOWN:
        placeholders["type"] = meter.type_label or "?"
    return DeviceInfo(
        identifiers={(DOMAIN, meter.serial)},
        manufacturer=MANUFACTURER,
        model=meter.type_label or None,
        serial_number=meter.serial,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


@callback
def async_register_devices(hass: HomeAssistant, entry: CalistaConfigEntry) -> None:
    """Da de alta (o actualiza) viviendas y equipos; los equipos cuelgan de su vivienda."""
    registry = dr.async_get(hass)
    for dwelling in entry.runtime_data.data.dwellings:
        parent = registry.async_get_or_create(
            config_entry_id=entry.entry_id, **dwelling_device_info(dwelling)
        )
        via: dict[str, Any] = (
            {"via_device_id": parent.id}
            if _HAS_VIA_DEVICE_ID
            else {"via_device": dwelling_identifier(dwelling.key)}
        )
        for meter in dwelling.meters:
            registry.async_get_or_create(
                config_entry_id=entry.entry_id, **meter_device_info(meter), **via
            )


class CalistaEntity(CoordinatorEntity[CalistaDataUpdateCoordinator]):
    """Entidad enlazada a un dispositivo ya registrado (solo por su identificador)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CalistaDataUpdateCoordinator,
        device_identifier: tuple[str, str],
        unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(identifiers={device_identifier})
