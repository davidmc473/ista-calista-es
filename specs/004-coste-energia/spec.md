# Spec 004 — Coste de los recibos en estadísticas y en el panel de Energía

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-11-08 |
| Depende | Spec 001 (estadísticas, recibos) |

## 1. Contexto

La spec 001 solo lee la primera página de «Mis recibos» (15 de 34 en la cuenta de prueba) y
expone el último importe de cada tipo. Para ver el gasto en el tiempo y asociar un coste al
agua en el panel de Energía hace falta el historial completo como estadística acumulada.

## 2. Hallazgos (2026-11-08)

- La web pagina los recibos (`d-148657-p=N`, 15 por página) y además ofrece **exportarlos**:
  `GET /GesCon/GestionFacturacion.do?d-148657-e=1&metodo=listadoRecibos&metodo=buscarRecibos&6578706f7274=1`
  devuelve un **CSV UTF-8** con **todos** los recibos (34, desde 03/2023; ~2 KB), ordenado
  por fecha descendente:

  ```
  Fecha lectura,Tipo equipo,Importe
  31/05/2026,Radio Distribuidor de Costes de Calefacción,"17,11"
  30/05/2026,Agua caliente,"0,00"
  ```

- La exportación usa la lista que la sesión mostró por última vez: funciona tras el login
  (que aterriza en «Mis recibos») aunque luego se visiten las lecturas radio. Sin sesión,
  `302` al host interno (como el resto de páginas).
- En la cuenta de prueba los recibos de agua caliente valen 0,00 € (la comunidad lo factura
  aparte): su coste en Energía será 0. La calefacción sí tiene importes.
- El panel de Energía de HA solo admite **agua** (volumen), electricidad y gas (energía o
  volumen): los repartidores (unidades `UN`) no tienen sitio en él. Su coste queda como
  estadística para la tarjeta *Gráfico de estadísticas*.

## 3. Historias de usuario

### US10 — Coste acumulado por tipo de recibo (P1)
**Aceptación**
1. Una estadística externa por vivienda y tipo de recibo,
   `ista_calista_es:cost_<abonado>_<tipo>`, en `EUR`, con `sum` acumulado y una fila por
   recibo con su fecha (misma convención que las lecturas: fila que empieza a las 23:00 del
   día anterior a la fecha de lectura del recibo).
2. La primera vez se importa todo el historial; después solo los recibos nuevos. Si aparece
   un recibo con fecha anterior a la última importada (corrección), se recalcula la serie.
3. Varios recibos del mismo tipo y día se suman en una fila.

### US11 — Coste del agua en el panel de Energía (P1)
**Aceptación**
1. En *Energía → Consumo de agua → ista · Agua caliente*, la opción «Usar una entidad que
   registre el coste total» admite la estadística «ista · Coste agua caliente», y
   `energy/validate` no da incidencias.

### US12 — Último recibo con el historial completo (P2)
**Aceptación**
1. Los sensores *Último recibo* usan el historial completo (antes solo la primera página).

## 4. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-401 | `api`: exportación CSV de recibos tras «Mis recibos» (también tras cambiar de abonado); si falla con `ParseError`, se usa la primera página como hasta ahora. |
| FR-402 | Parser CSV con la librería estándar (`csv`), columnas por nombre de cabecera. |
| FR-403 | La importación de costes respeta la opción *Importar el histórico en las estadísticas*. |
| FR-404 | Nombre: «ista · Coste calefacción / agua caliente / …»; con varias viviendas se añade el nº de abonado. |

## 5. Fuera de alcance

- Repartir el importe de un recibo entre los días del periodo (el coste aparece el día de
  cierre del recibo; la vista mensual es la útil).
- Precio por m³ o por unidad (`entity_energy_price`): ista no lo publica.
