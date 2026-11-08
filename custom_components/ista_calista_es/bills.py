"""Recibos ya vistos, para avisar solo de los nuevos (spec 005)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import Bill, CalistaData
from .const import DOMAIN

STORAGE_VERSION = 1
#: un recibo que aparece tarde y es mucho más antiguo que el último conocido es historial
#: que el portal no mostraba antes (p. ej. si una lectura solo trajo la primera página)
LATE_HISTORY = timedelta(days=90)


def bill_key(bill: Bill) -> str:
    return f"{bill.date.isoformat()}|{bill.type_label}|{bill.amount:.2f}"


class BillTracker:
    """Guarda las claves de los recibos vistos por vivienda en ``.storage``."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, list[str]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.bills"
        )
        self._known: dict[str, set[str]] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._known = {key: set(values) for key, values in stored.items()}

    async def async_new_bills(self, data: CalistaData) -> dict[str, list[Bill]]:
        """Recibos no vistos por vivienda (del más antiguo al más reciente).

        La primera vez que se ve una vivienda solo se registran sus recibos (sin avisos).
        """
        new: dict[str, list[Bill]] = {}
        changed = False
        for dwelling in data.dwellings:
            current = {bill_key(bill): bill for bill in dwelling.bills}
            known = self._known.get(dwelling.key)
            if known is None:
                self._known[dwelling.key] = set(current)
                changed = bool(current) or changed
                continue
            fresh = [bill for key, bill in current.items() if key not in known]
            if not fresh:
                continue
            known.update(bill_key(bill) for bill in fresh)
            changed = True
            dates = [bill.date for key, bill in current.items() if key in known]
            newest = max(dates)
            fresh = [bill for bill in fresh if bill.date >= newest - LATE_HISTORY]
            if fresh:
                new[dwelling.key] = sorted(fresh, key=lambda bill: bill.date)
        if changed:
            await self._store.async_save({k: sorted(v) for k, v in self._known.items()})
        return new

    async def async_remove(self) -> None:
        await self._store.async_remove()
