# Modelo de datos 001

Modelos normalizados de `api/models.py`, independientes del HTML. Un campo `None` significa
«no disponible».

```text
CalistaData
├── dwellings: list[Dwelling]               una por abonado
│   └── Dwelling
│       ├── key: str                        ← number o, si falta, id (unique_id del dispositivo)
│       ├── id: str | None                  ← value del <option> (idAbonado opaco)
│       ├── number: str | None              ← cabecera «Nº abonado»
│       ├── address: str | None             ← texto del <option> activo (dato personal)
│       ├── meters: list[Meter]
│       └── bills: list[Bill]               orden de la web
│           └── latest_bills() → dict[MeterKind, Bill]   el más reciente por tipo
├── window_start / window_end: date | None  ← fechaDesdeRadio / fechaHastaRadio
└── meters → todos los equipos de todas las viviendas

Meter
├── serial: str                             ← «Nº serie» (unique_id)
├── kind: MeterKind                         ← clasificar(tipo, unidad)
├── type_label: str                         ← «Tipo» tal cual (modelo del dispositivo)
├── unit: str                               ← «Unidad Medida» normalizada (m3 → m³)
├── location: str | None                    ← «(1-Dormitorio1)» → «Dormitorio 1»
├── location_code: str | None               ← «1»
├── readings: list[Reading]                 ascendente, sin días vacíos
│   └── Reading(date: date, value: float)
├── last_reading → Reading | None
└── last_consumption() → Consumption | None  (from, to, value) con reinicio por tipo

Bill(date: date, type_label: str, kind: MeterKind, amount: float)   (€)

MeterKind (StrEnum)
├── heat_cost_allocator   «Distribuidor de Costes de Calefacción», «repartidor»; unidad UN
├── hot_water             «agua caliente»
├── cold_water            «agua fría»
├── water                 «agua» sin más
├── heat                  «energía», «calor», «calorías», «frigorías» o unidad kWh/MWh/GJ
└── unknown
    resets_yearly → True solo en heat_cost_allocator
```

## Consumo entre lecturas

```
delta(prev, value):
    prev is None           → 0
    value >= prev          → value - prev
    kind.resets_yearly     → value          (reinicio de temporada, 1 de octubre)
    resto                  → 0              (corrección del contador; se ignora)
```

## Estadística externa (HA, `statistics.py`)

| Campo | Valor |
|-------|-------|
| `statistic_id` | `ista_calista_es:meter_<serie>` |
| `source` | `ista_calista_es` |
| `name` | `<nombre del dispositivo> (ista)` |
| `unit_of_measurement` | `m³`, `kWh`, `MWh`, `GJ` o la del portal (`UN`) |
| `unit_class` | `volume` / `energy` / `None` |
| `has_sum` / `mean_type` | `True` / `NONE` |
| fila | `start` = (fecha 00:00 Europe/Madrid) − 1 h · `state` = lectura · `sum` = Σ delta |
