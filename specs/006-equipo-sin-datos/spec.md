# Spec 006 — Aviso de equipo sin datos

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-11-08 |
| Depende | Spec 001; el aviso en «Reparaciones» es de la spec 002 |

## 1. Contexto

Un equipo de radio puede dejar de transmitir (batería, avería, obra). En el portal solo se
nota porque sus celdas quedan vacías, y en HA porque la *Fecha de la última lectura* deja de
avanzar.

## 2. Hallazgos (2026-11-08, 400 días de la cuenta de prueba)

| Equipo | Huecos | Mayor hueco |
|--------|--------|-------------|
| 7 repartidores | 0 | — |
| Repartidor Cocina | 1 | 4 días |
| Agua caliente | 4 | 6 días |

A eso se suma el retraso normal de publicación (~3 días). Con **10 días** sin lectura no
habría habido ninguna falsa alarma.

## 3. Historias de usuario

### US14 — Sensor de problema por equipo (P1)
**Aceptación**
1. Cada equipo tiene un `binary_sensor` *Sin lecturas recientes* (`problem`, diagnóstico):
   encendido si su última lectura tiene más días que el umbral, o si no tiene ninguna.
2. Atributos: `last_reading` (fecha ISO o nada), `days_without_reading` y `threshold`.

### US15 — Umbral configurable (P2)
**Aceptación**
1. Opción *Días sin lectura para avisar* (2–60, por defecto 10).

### US16 — Aviso en «Reparaciones» (P2)
Ver spec 002, US9.

## 4. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-601 | Los días se cuentan respecto a la fecha actual en `Europe/Madrid`. |
| FR-602 | El estado se recalcula en cada lectura del portal (cada 6 h por defecto). |
