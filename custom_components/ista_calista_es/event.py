"""Evento «Nuevo recibo» por vivienda (spec 005)."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CalistaConfigEntry, CalistaDataUpdateCoordinator
from .entity import CalistaEntity, dwelling_identifier

PARALLEL_UPDATES = 0

EVENT_NEW_BILL = "new_bill"


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
            NewBillEvent(coordinator, dwelling.key)
            for dwelling in coordinator.data.dwellings
            if dwelling.key not in known
        ]
        known.update(entity.dwelling_key for entity in new)
        if new:
            async_add_entities(new)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class NewBillEvent(CalistaEntity, EventEntity):
    """Se dispara una vez por cada recibo nuevo de la vivienda."""

    _attr_translation_key = EVENT_NEW_BILL
    _attr_event_types: ClassVar[list[str]] = [EVENT_NEW_BILL]

    def __init__(self, coordinator: CalistaDataUpdateCoordinator, dwelling_key: str) -> None:
        super().__init__(coordinator, dwelling_identifier(dwelling_key), f"{dwelling_key}_new_bill")
        self.dwelling_key = dwelling_key
        # Las lecturas anteriores al alta de la entidad no generan eventos
        self._handled_update = coordinator.update_id

    @property
    def available(self) -> bool:
        return (
            super().available and self.coordinator.data.find_dwelling(self.dwelling_key) is not None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        coordinator = self.coordinator
        if coordinator.update_id != self._handled_update:
            self._handled_update = coordinator.update_id
            for bill in coordinator.new_bills.get(self.dwelling_key, []):
                self._trigger_event(
                    EVENT_NEW_BILL,
                    {
                        "date": bill.date.isoformat(),
                        "kind": bill.kind.value,
                        "type": bill.type_label,
                        "amount": bill.amount,
                        "currency": "EUR",
                    },
                )
                self.async_write_ha_state()
        self.async_write_ha_state()
