"""Estadísticas externas con la fecha real de cada lectura (spec 001, US3).

ista publica las lecturas diarias con varios días de retraso: si solo se usara el estado
del sensor, Home Assistant atribuiría el consumo al día en que lo descarga. Aquí se
importa una fila por lectura con su fecha, como hace la integración ``ista_ecotrend``.

La lectura del día D es el valor del equipo a las 00:00 de D, así que la fila empieza a
las 23:00 de D-1 y el consumo entre dos lecturas cae en el día en que se produjo.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, VolumeConverter

from .api import (
    Bill,
    CalistaData,
    Dwelling,
    Meter,
    MeterKind,
    consumption_delta,
    default_window_start,
)
from .const import DOMAIN, MAX_HISTORY_DAYS, PORTAL_TIMEZONE

_LOGGER = logging.getLogger(__name__)

_TZ = ZoneInfo(PORTAL_TIMEZONE)

#: nombre de la estadística (no admite traducciones; la integración es solo para España)
_KIND_NAMES = {
    MeterKind.HEAT_COST_ALLOCATOR: "Repartidor",
    MeterKind.HOT_WATER: "Agua caliente",
    MeterKind.COLD_WATER: "Agua fría",
    MeterKind.WATER: "Agua",
    MeterKind.HEAT: "Energía",
}

try:  # HA ≥ 2025.4
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover
    StatisticMeanType = None  # type: ignore[assignment,misc]


def statistic_id(serial: str) -> str:
    return f"{DOMAIN}:meter_{serial.lower()}"


def statistic_name(meter: Meter) -> str:
    base = _KIND_NAMES.get(meter.kind, meter.type_label or "Equipo")
    return f"ista · {base} {meter.location}" if meter.location else f"ista · {base}"


def statistic_start(day: date) -> datetime:
    """Inicio (UTC) de la fila de una lectura del día ``day``."""
    return dt_util.as_utc(datetime.combine(day, time(0), tzinfo=_TZ) - timedelta(hours=1))


def _reading_day(start_timestamp: float) -> date:
    start = datetime.fromtimestamp(start_timestamp, tz=_TZ)
    return (start + timedelta(hours=1)).date()


def _unit_class(unit: str | None) -> str | None:
    if unit in VolumeConverter.VALID_UNITS:
        return VolumeConverter.UNIT_CLASS
    if unit in EnergyConverter.VALID_UNITS:
        return EnergyConverter.UNIT_CLASS
    return None


def statistic_metadata(meter: Meter) -> StatisticMetaData:
    unit = meter.unit or None
    metadata: dict[str, Any] = {
        "has_sum": True,
        "name": statistic_name(meter),
        "source": DOMAIN,
        "statistic_id": statistic_id(meter.serial),
        "unit_of_measurement": unit,
    }
    fields = StatisticMetaData.__annotations__
    if "mean_type" in fields and StatisticMeanType is not None:
        metadata["mean_type"] = StatisticMeanType.NONE
    else:  # pragma: no cover - HA antiguo
        metadata["has_mean"] = False
    if "unit_class" in fields:
        metadata["unit_class"] = _unit_class(unit)
    return metadata  # type: ignore[return-value]


async def _async_last_row(hass: HomeAssistant, stat_id: str) -> dict[str, Any] | None:
    result = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, stat_id, False, {"state", "sum"}
    )
    rows = result.get(stat_id)
    return dict(rows[0]) if rows else None


async def async_last_reading_days(
    hass: HomeAssistant, serials: Iterable[str]
) -> dict[str, date | None]:
    """Día de la última lectura importada de cada equipo (``None`` si no hay)."""
    days: dict[str, date | None] = {}
    for serial in serials:
        row = await _async_last_row(hass, statistic_id(serial))
        days[serial] = _reading_day(row["start"]) if row else None
    return days


async def async_history_start(
    hass: HomeAssistant, serials: Iterable[str], history_days: int, today: date | None = None
) -> date | None:
    """Desde qué día hay que pedir lecturas para no dejar huecos (``None`` = ventana normal).

    - Ningún equipo conocido o alguno sin estadísticas → ``history_days`` atrás.
    - Si no, el día siguiente a la última fila importada más antigua (con un día de margen),
      solo si queda fuera de la ventana que el portal devuelve por defecto.
    """
    today = today or dt_util.now(_TZ).date()
    backfill = today - timedelta(days=history_days) if history_days > 0 else None
    serials = list(serials)
    if not serials:
        return backfill
    days = await async_last_reading_days(hass, serials)
    if any(day is None for day in days.values()):
        return backfill
    oldest = min(day for day in days.values() if day is not None)
    start = max(oldest - timedelta(days=1), today - timedelta(days=MAX_HISTORY_DAYS))
    return start if start < default_window_start(today) else None


async def async_import_meter(hass: HomeAssistant, meter: Meter) -> int:
    """Importa las lecturas posteriores a la última fila. Devuelve las filas añadidas."""
    stat_id = statistic_id(meter.serial)
    last = await _async_last_row(hass, stat_id)
    last_start: float | None = last["start"] if last else None
    total: float = (last.get("sum") or 0.0) if last else 0.0
    previous: float | None = last.get("state") if last else None

    rows: list[StatisticData] = []
    for reading in meter.readings:
        start = statistic_start(reading.date)
        if last_start is not None and start.timestamp() <= last_start:
            continue
        total += consumption_delta(meter.kind, previous, reading.value)
        rows.append(StatisticData(start=start, state=reading.value, sum=round(total, 6)))
        previous = reading.value
    if rows:
        _LOGGER.debug("Importando %d filas en %s", len(rows), statistic_name(meter))
        async_add_external_statistics(hass, statistic_metadata(meter), rows)
    return len(rows)


async def async_import_statistics(hass: HomeAssistant, data: CalistaData) -> None:
    for meter in data.meters:
        await async_import_meter(hass, meter)


# --- coste de los recibos (spec 004) ------------------------------------------------

_COST_NAMES = {
    MeterKind.HEAT_COST_ALLOCATOR: "calefacción",
    MeterKind.HOT_WATER: "agua caliente",
    MeterKind.COLD_WATER: "agua fría",
    MeterKind.WATER: "agua",
    MeterKind.HEAT: "energía",
}


def cost_statistic_id(dwelling_key: str, kind: MeterKind) -> str:
    slug = re.sub(r"[^a-z0-9_]", "_", dwelling_key.lower())
    return f"{DOMAIN}:cost_{slug}_{kind.value}"


def cost_statistic_name(dwelling: Dwelling, kind: MeterKind, *, several: bool) -> str:
    label = next((b.type_label for b in dwelling.bills if b.kind is kind), "otros")
    name = f"ista · Coste {_COST_NAMES.get(kind, label.lower())}"
    return f"{name} ({dwelling.number or dwelling.key})" if several else name


def cost_rows(bills: Iterable[Bill]) -> list[StatisticData]:
    """Una fila por día de recibo (importes del mismo día sumados) con el coste acumulado."""
    per_start: dict[datetime, float] = {}
    for bill in bills:
        start = statistic_start(bill.date)
        per_start[start] = per_start.get(start, 0.0) + bill.amount
    total = 0.0
    rows: list[StatisticData] = []
    for start in sorted(per_start):
        total = round(total + per_start[start], 2)
        rows.append(StatisticData(start=start, state=round(per_start[start], 2), sum=total))
    return rows


def _cost_metadata(stat_id: str, name: str) -> StatisticMetaData:
    metadata: dict[str, Any] = {
        "has_sum": True,
        "name": name,
        "source": DOMAIN,
        "statistic_id": stat_id,
        "unit_of_measurement": "EUR",
    }
    fields = StatisticMetaData.__annotations__
    if "mean_type" in fields and StatisticMeanType is not None:
        metadata["mean_type"] = StatisticMeanType.NONE
    else:  # pragma: no cover - HA antiguo
        metadata["has_mean"] = False
    if "unit_class" in fields:
        metadata["unit_class"] = None
    return metadata  # type: ignore[return-value]


async def async_import_costs(hass: HomeAssistant, data: CalistaData) -> None:
    """Estadística de coste acumulado por vivienda y tipo de recibo.

    Si la última fila importada sigue coincidiendo con la serie, solo se añaden las filas
    nuevas; si no (recibo corregido o con fecha anterior), se reimporta la serie entera.
    """
    several = len(data.dwellings) > 1
    for dwelling in data.dwellings:
        kinds = sorted({bill.kind for bill in dwelling.bills})
        for kind in kinds:
            series = cost_rows(bill for bill in dwelling.bills if bill.kind is kind)
            stat_id = cost_statistic_id(dwelling.key, kind)
            last = await _async_last_row(hass, stat_id)
            rows = series
            if last is not None:
                match = next(
                    (row for row in series if row["start"].timestamp() == last["start"]), None
                )
                if match is not None and abs(match["sum"] - (last.get("sum") or 0.0)) < 0.005:
                    rows = [row for row in series if row["start"].timestamp() > last["start"]]
            if rows:
                _LOGGER.debug("Importando %d filas de coste en %s", len(rows), stat_id)
                async_add_external_statistics(
                    hass,
                    _cost_metadata(stat_id, cost_statistic_name(dwelling, kind, several=several)),
                    rows,
                )


def meter_label(meter: Meter) -> str:
    """Nombre legible de un equipo cuando aún no está en el registro de dispositivos."""
    return statistic_name(meter).removeprefix("ista · ")
