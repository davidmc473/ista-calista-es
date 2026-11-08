"""Modelos normalizados del portal Calista (ver specs/001-lecturas-calista/data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class MeterKind(StrEnum):
    """Tipo de equipo de medida (también clasifica los recibos)."""

    HEAT_COST_ALLOCATOR = "heat_cost_allocator"
    HOT_WATER = "hot_water"
    COLD_WATER = "cold_water"
    WATER = "water"
    HEAT = "heat"
    UNKNOWN = "unknown"

    @property
    def resets_yearly(self) -> bool:
        """Los repartidores vuelven a 0 al empezar la temporada (1 de octubre)."""
        return self is MeterKind.HEAT_COST_ALLOCATOR

    @property
    def is_water(self) -> bool:
        return self in (MeterKind.HOT_WATER, MeterKind.COLD_WATER, MeterKind.WATER)


def consumption_delta(kind: MeterKind, previous: float | None, value: float) -> float:
    """Consumo entre dos lecturas consecutivas disponibles.

    Una bajada en un repartidor es el reinicio de temporada (se cuenta el valor nuevo);
    en cualquier otro equipo es una corrección y no se cuenta como consumo.
    """
    if previous is None:
        return 0.0
    if value >= previous:
        return value - previous
    return value if kind.resets_yearly else 0.0


@dataclass(slots=True, frozen=True)
class Reading:
    date: date
    value: float


@dataclass(slots=True, frozen=True)
class Consumption:
    """Consumo entre dos lecturas (``start`` exclusivo, ``end`` inclusivo)."""

    start: date
    end: date
    value: float


@dataclass(slots=True)
class Meter:
    serial: str
    kind: MeterKind
    type_label: str
    unit: str
    location: str | None = None
    location_code: str | None = None
    #: lecturas disponibles en orden ascendente de fecha (sin días vacíos)
    readings: list[Reading] = field(default_factory=list)

    @property
    def last_reading(self) -> Reading | None:
        return self.readings[-1] if self.readings else None

    def last_consumption(self) -> Consumption | None:
        """Consumo entre las dos últimas lecturas disponibles."""
        if len(self.readings) < 2:
            return None
        previous, last = self.readings[-2], self.readings[-1]
        value = consumption_delta(self.kind, previous.value, last.value)
        return Consumption(start=previous.date, end=last.date, value=round(value, 6))


@dataclass(slots=True, frozen=True)
class Bill:
    date: date
    type_label: str
    kind: MeterKind
    #: importe en euros
    amount: float


@dataclass(slots=True)
class Dwelling:
    """Una vivienda (abonado) de la cuenta."""

    #: identificador opaco del portal (``idAbonado``); puede faltar si solo hay uno
    id: str | None
    #: «Nº abonado» de la cabecera
    number: str | None
    #: dirección tal y como la muestra el portal (dato personal)
    address: str | None
    meters: list[Meter] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Identificador estable para Home Assistant."""
        return self.number or self.id or "default"

    def latest_bills(self) -> dict[MeterKind, Bill]:
        """El recibo más reciente de cada tipo."""
        latest: dict[MeterKind, Bill] = {}
        for bill in self.bills:
            current = latest.get(bill.kind)
            if current is None or bill.date > current.date:
                latest[bill.kind] = bill
        return latest


@dataclass(slots=True)
class CalistaData:
    dwellings: list[Dwelling] = field(default_factory=list)
    #: rango de fechas consultado en «Mis lecturas Radio»
    window_start: date | None = None
    window_end: date | None = None

    @property
    def meters(self) -> list[Meter]:
        return [meter for dwelling in self.dwellings for meter in dwelling.meters]

    def find_meter(self, serial: str) -> tuple[Dwelling, Meter] | None:
        for dwelling in self.dwellings:
            for meter in dwelling.meters:
                if meter.serial == serial:
                    return dwelling, meter
        return None

    def find_dwelling(self, key: str) -> Dwelling | None:
        return next((d for d in self.dwellings if d.key == key), None)
