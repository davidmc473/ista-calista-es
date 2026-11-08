"""Sensores de los equipos (US2) y de los recibos de cada vivienda (US4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import Bill, Meter, MeterKind
from .const import DOMAIN
from .coordinator import CalistaConfigEntry, CalistaDataUpdateCoordinator
from .entity import CalistaEntity, dwelling_identifier

# El coordinador centraliza las lecturas: las entidades no hacen peticiones
PARALLEL_UPDATES = 0

_WATER_UNITS = {UnitOfVolume.CUBIC_METERS, UnitOfVolume.LITERS}
_ENERGY_UNITS = {UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.MEGA_WATT_HOUR, UnitOfEnergy.GIGA_JOULE}


def _consumption_attrs(meter: Meter) -> dict[str, Any]:
    consumption = meter.last_consumption()
    if consumption is None:
        return {}
    return {"from": consumption.start.isoformat(), "to": consumption.end.isoformat()}


@dataclass(frozen=True, kw_only=True)
class MeterSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[Meter], StateType | date]
    attrs_fn: Callable[[Meter], dict[str, Any]] | None = None
    #: toma la clase y la unidad del equipo
    measures: bool = True


METER_SENSORS: tuple[MeterSensorEntityDescription, ...] = (
    MeterSensorEntityDescription(
        key="reading",
        translation_key="reading",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda m: m.last_reading.value if m.last_reading else None,
    ),
    MeterSensorEntityDescription(
        key="last_consumption",
        translation_key="last_consumption",
        value_fn=lambda m: c.value if (c := m.last_consumption()) else None,
        attrs_fn=_consumption_attrs,
    ),
    MeterSensorEntityDescription(
        key="last_reading_date",
        translation_key="last_reading_date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        measures=False,
        value_fn=lambda m: m.last_reading.date if m.last_reading else None,
    ),
)


def meter_device_class(meter: Meter) -> SensorDeviceClass | None:
    if meter.unit in _WATER_UNITS:
        return SensorDeviceClass.WATER
    if meter.unit in _ENERGY_UNITS:
        return SensorDeviceClass.ENERGY
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalistaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known_meters: set[str] = set()
    known_bills: set[tuple[str, MeterKind]] = set()

    @callback
    def _async_add_new() -> None:
        """Altas de equipos y tipos de recibo que aparecen después del arranque."""
        new: list[SensorEntity] = []
        for dwelling in coordinator.data.dwellings:
            for meter in dwelling.meters:
                if meter.serial not in known_meters:
                    known_meters.add(meter.serial)
                    new.extend(MeterSensor(coordinator, meter, desc) for desc in METER_SENSORS)
            for kind in dwelling.latest_bills():
                if (dwelling.key, kind) not in known_bills:
                    known_bills.add((dwelling.key, kind))
                    new.append(BillSensor(coordinator, dwelling.key, kind))
        if new:
            async_add_entities(new)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class MeterSensor(CalistaEntity, SensorEntity):
    """Lectura, consumo del último día o fecha de la última lectura de un equipo."""

    entity_description: MeterSensorEntityDescription

    def __init__(
        self,
        coordinator: CalistaDataUpdateCoordinator,
        meter: Meter,
        description: MeterSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, (DOMAIN, meter.serial), f"{meter.serial}_{description.key}")
        self.entity_description = description
        self._serial = meter.serial
        if description.measures:
            self._attr_device_class = meter_device_class(meter)
            self._attr_native_unit_of_measurement = meter.unit or None
            self._attr_suggested_display_precision = 3
            if self._attr_device_class is None:
                self._attr_icon = (
                    "mdi:radiator" if meter.kind is MeterKind.HEAT_COST_ALLOCATOR else "mdi:counter"
                )

    @property
    def _meter(self) -> Meter | None:
        found = self.coordinator.data.find_meter(self._serial)
        return found[1] if found else None

    @property
    def available(self) -> bool:
        return super().available and self._meter is not None

    @property
    def native_value(self) -> StateType | date:
        meter = self._meter
        return self.entity_description.value_fn(meter) if meter else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        meter = self._meter
        if meter is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(meter)


class BillSensor(CalistaEntity, SensorEntity):
    """Importe del último recibo de un tipo (calefacción, agua caliente…)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: CalistaDataUpdateCoordinator, dwelling_key: str, kind: MeterKind
    ) -> None:
        super().__init__(
            coordinator,
            dwelling_identifier(dwelling_key),
            f"{dwelling_key}_last_bill_{kind.value}",
        )
        self._attr_translation_key = f"last_bill_{kind.value}"
        self._dwelling_key = dwelling_key
        self._kind = kind

    @property
    def _bill(self) -> Bill | None:
        dwelling = self.coordinator.data.find_dwelling(self._dwelling_key)
        return dwelling.latest_bills().get(self._kind) if dwelling else None

    @property
    def available(self) -> bool:
        return super().available and self._bill is not None

    @property
    def native_value(self) -> float | None:
        bill = self._bill
        return bill.amount if bill else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bill = self._bill
        if bill is None:
            return None
        attrs: dict[str, Any] = {"date": bill.date.isoformat()}
        if self._kind is MeterKind.UNKNOWN:
            attrs["type"] = bill.type_label
        return attrs
