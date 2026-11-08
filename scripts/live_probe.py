"""Prueba en vivo (SOLO LECTURA) del cliente contra el portal real de ista.

Uso::

    ISTA_USER=... ISTA_PASSWORD=... python scripts/live_probe.py [--history-days N]

No envía lecturas ni modifica nada en la cuenta. La salida oculta los números de serie,
pero muestra ubicaciones, lecturas e importes: no la publiques sin revisarla.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "ista_calista_es"

# Importa la capa api/ sin cargar la parte de Home Assistant
sys.path.insert(0, str(ROOT))
for name, path in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.ista_calista_es", PKG_DIR),
):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)

import aiohttp  # noqa: E402

from custom_components.ista_calista_es.api import CalistaClient  # noqa: E402


def _mask(serial: str) -> str:
    return "*" * max(0, len(serial) - 3) + serial[-3:]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-days", type=int, default=0, help="pide N días de histórico")
    args = parser.parse_args()
    user, password = os.environ.get("ISTA_USER"), os.environ.get("ISTA_PASSWORD")
    if not user or not password:
        print("Define ISTA_USER e ISTA_PASSWORD", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    history_start = date.today() - timedelta(days=args.history_days) if args.history_days else None
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = CalistaClient(session, user, password)
        t0 = time.perf_counter()
        data = await client.async_get_data(history_start)
        print(f"Ciclo completo (login + lectura + logout) en {time.perf_counter() - t0:.2f}s")
        print(f"Ventana: {data.window_start} → {data.window_end}")
        for dwelling in data.dwellings:
            number = "sí" if dwelling.number else "no"
            print(f"\nVivienda: abonado {number} · id {'sí' if dwelling.id else 'no'}")
            for meter in dwelling.meters:
                last = meter.last_reading
                cons = meter.last_consumption()
                print(
                    f"  [{meter.kind.value:20}] {_mask(meter.serial)} {meter.location or '-':14} "
                    f"{len(meter.readings):3} lecturas · última {last.value if last else '-'} "
                    f"{meter.unit} ({last.date if last else '-'}) · consumo último día "
                    f"{cons.value if cons else '-'}"
                )
            for kind, bill in dwelling.latest_bills().items():
                amount = f"{bill.amount:8.2f} €"
                print(f"  Recibo {kind.value:20} {bill.date} {amount}  ({bill.type_label})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
