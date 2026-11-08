"""Representación de los datos sin información personal (constitución III)."""

from __future__ import annotations

from typing import Any

from .models import CalistaData

REDACTED = "**REDACTED**"


def anonymized_data(data: CalistaData) -> dict[str, Any]:
    """Datos normalizados para diagnósticos.

    Se quitan nº de abonado, dirección, ``idAbonado`` y números de serie; los equipos se
    identifican por su posición. Ubicaciones, tipos, lecturas e importes se mantienen
    porque son los datos que permiten diagnosticar un problema.
    """
    return {
        "window_start": data.window_start.isoformat() if data.window_start else None,
        "window_end": data.window_end.isoformat() if data.window_end else None,
        "dwellings": [
            {
                "index": d_index,
                "id": REDACTED if dwelling.id else None,
                "number": REDACTED if dwelling.number else None,
                "address": REDACTED if dwelling.address else None,
                "meters": [
                    {
                        "index": m_index,
                        "serial": REDACTED,
                        "kind": meter.kind.value,
                        "type_label": meter.type_label,
                        "unit": meter.unit,
                        "location": meter.location,
                        "location_code": meter.location_code,
                        "readings_count": len(meter.readings),
                        "first_reading": _reading(meter.readings[0]) if meter.readings else None,
                        "last_readings": [_reading(r) for r in meter.readings[-5:]],
                    }
                    for m_index, meter in enumerate(dwelling.meters)
                ],
                "bills": [
                    {
                        "date": bill.date.isoformat(),
                        "kind": bill.kind.value,
                        "type_label": bill.type_label,
                        "amount": bill.amount,
                    }
                    for bill in dwelling.bills
                ],
            }
            for d_index, dwelling in enumerate(data.dwellings)
        ],
    }


def _reading(reading: Any) -> dict[str, Any]:
    return {"date": reading.date.isoformat(), "value": reading.value}
