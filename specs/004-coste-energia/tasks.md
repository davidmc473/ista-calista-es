# Tareas 004 — Coste en estadísticas y panel de Energía

- [x] T401 Explorar paginación y exportación de «Mis recibos» (CSV con todo el historial)
- [x] T402 `parser.parse_bills_csv` + fixture `bills.csv` + tests
- [x] T403 `client`: exportación CSV en ambos flujos (una o varias viviendas) con respaldo a la primera página
- [x] T404 Portal falso: exportación CSV (exige haber mostrado la lista en la sesión) + tests de protocolo
- [x] T405 `statistics.async_import_costs`: serie por vivienda y tipo, incremental, recálculo ante correcciones
- [x] T406 Tests HA: importación inicial, incremental, corrección, opción desactivada
- [x] T407 Validado en vivo: 34 recibos (CSV de 1,9 KB), «ista · Coste calefacción» 337,83 € en 25 meses,
      agua caliente con `stat_cost` aceptada por `energy/validate` sin incidencias
