"""Aviso de equipo sin lecturas recientes (spec 006)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Meter
from .const import DOMAIN
from .coordinator import CalistaConfigEntry, CalistaDataUpdateCoordinator
from .entity import CalistaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalistaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        new = [
            StaleMeterBinarySensor(coordinator, meter)
            for meter in coordinator.data.meters
            if meter.serial not in known
        ]
        known.update(entity.serial for entity in new)
        if new:
            async_add_entities(new)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class StaleMeterBinarySensor(CalistaEntity, BinarySensorEntity):
    """Encendido si el equipo lleva más días sin lectura que el umbral (o no tiene ninguna)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "stale"

    def __init__(self, coordinator: CalistaDataUpdateCoordinator, meter: Meter) -> None:
        super().__init__(coordinator, (DOMAIN, meter.serial), f"{meter.serial}_stale")
        self.serial = meter.serial

    @property
    def _meter(self) -> Meter | None:
        found = self.coordinator.data.find_meter(self.serial)
        return found[1] if found else None

    @property
    def available(self) -> bool:
        return super().available and self._meter is not None

    @property
    def is_on(self) -> bool | None:
        meter = self._meter
        return self.coordinator.is_stale(meter) if meter else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        meter = self._meter
        if meter is None:
            return None
        last = meter.last_reading
        return {
            "last_reading": last.date.isoformat() if last else None,
            "days_without_reading": self.coordinator.days_without_reading(meter),
            "threshold": self.coordinator.stale_days,
        }
