# Spec 001 — Integración HACS para el portal Calista de ista España

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada y validada en vivo con HA 2026.10 (pendiente: varias viviendas y otros tipos de equipo, ver `tasks.md`) |
| Fecha   | 2026-11-08 |
| Portal  | `oficina.ista.es/GesCon` v.2.108.3, login Keycloak `GESCON-PORTAL-ES-APP-Abonado` |
| Dominio | `ista_calista_es` |

## 1. Contexto y problema

ista instala en muchas comunidades de vecinos españolas repartidores de costes de
calefacción y contadores de agua que se leen por radio. El abonado solo puede consultar sus
lecturas en la web Calista (`oficina.ista.es`), sin API pública ni aplicación integrable.
El login se ha migrado a Keycloak (`login.ista.com`), lo que dejó obsoletas las
integraciones comunitarias que usaban el formulario antiguo.

Queremos ver en Home Assistant la lectura de cada equipo, el histórico diario con la fecha
real en que se produjo el consumo (para gráficas y el panel de Energía) y el importe de los
últimos recibos.

## 2. Historias de usuario

### US1 — Configurar la cuenta desde la UI (P1)
Como abonado, quiero añadir mi cuenta de Calista con mi e-mail y contraseña desde
*Ajustes → Dispositivos y servicios*.

**Aceptación**
1. *Dadas* credenciales correctas, *cuando* envío el formulario, *entonces* se crea una
   entrada «ista Calista (`<e-mail>`)» y aparecen los dispositivos de la US2 y la US4.
2. *Dadas* credenciales incorrectas → «E-mail o contraseña incorrectos». Nunca se reintenta solo.
3. *Dado* que Keycloak pide una acción (cambiar contraseña, aceptar condiciones, 2FA…) →
   «El portal pide una acción: entra en la web de ista, complétala y vuelve a intentarlo».
4. *Dado* un fallo de red o del portal → «No se puede conectar con el portal de ista».
5. *Dado* que la cuenta ya está configurada (mismo e-mail, sin distinguir mayúsculas) →
   «Esta cuenta ya está configurada».

### US2 — Lectura de cada contador (P1)
Como abonado, quiero un dispositivo por cada equipo de medida con su última lectura.

**Aceptación**
1. Un dispositivo por nº de serie, fabricante «ista», modelo = tipo que muestra el portal,
   nombre según tipo y ubicación (p. ej. «Repartidor Dormitorio 1», «Agua caliente»).
2. Sensor *Lectura*: último valor disponible, unidad del portal (`UN`, `m³`, `kWh`…),
   `state_class: total_increasing`. Agua: `device_class: water`; energía: `energy`.
3. Sensor *Consumo del último día*: diferencia con la lectura anterior disponible (si el
   repartidor se ha reiniciado, el valor nuevo); atributos `from` y `to` (fechas).
4. Sensor *Fecha de la última lectura* (`date`, diagnóstico) para detectar datos atascados.
5. Los días sin dato se ignoran. Un equipo sin ninguna lectura en la ventana queda *desconocido*.
6. Los equipos nuevos que aparezcan se añaden sin reiniciar HA.

### US3 — Histórico con la fecha real (P1)
Como usuario, quiero que el consumo de cada día aparezca en ese día, aunque ista lo
publique con días de retraso, y poder usar el agua en el panel de Energía.

**Aceptación**
1. Por cada equipo se importa una estadística externa `ista_calista_es:meter_<serie>` con una
   fila por lectura diaria (`state` = lectura, `sum` = consumo acumulado).
2. La primera vez se importan los últimos *N* días (opción, 365 por defecto); después solo
   las lecturas nuevas. Si HA ha estado parado más que la ventana normal, se descarga el
   hueco.
3. El reinicio anual de los repartidores no genera consumos negativos ni ficticios.
4. La estadística del agua tiene unidad de volumen y se puede elegir en *Energía → Agua*.
5. Se puede desactivar la importación en las opciones.

### US4 — Recibos (P2)
**Aceptación**
1. Un dispositivo «Vivienda `<nº abonado>`» por abonado, del que cuelgan sus equipos.
2. Un sensor *Último recibo de calefacción / agua caliente / agua fría / …* por cada tipo
   de recibo visto: importe en € (`monetary`) y atributo `date`.

### US5 — Varias viviendas (P3)
**Aceptación**
1. Si la cuenta tiene varios abonados, se leen todos (cambiando de abonado como la web) y
   cada uno es una vivienda con sus equipos y recibos.

### US6 — Soporte (P2)
**Aceptación**
1. Diagnósticos con los datos normalizados **sin datos personales**.
2. Si la contraseña cambia, HA lanza la *reautenticación*; también se puede *reconfigurar*.
3. Opciones: intervalo de sondeo (1–24 h, por defecto 6 h), importar estadísticas (sí/no),
   días de histórico inicial (0–1095, por defecto 365).

## 3. Requisitos funcionales

| ID     | Requisito |
|--------|-----------|
| FR-001 | Login OIDC: `GET` autorización → `#loginForm` → `POST` credenciales → redirecciones seguidas a mano (máx. 10) hasta un `200` en `oficina.ista.es` (ver contrato). |
| FR-002 | `200` con `#loginForm` tras el `POST` → `InvalidAuth`; otra página de Keycloak → `AuthActionRequired`. |
| FR-003 | En peticiones de datos: `3xx` o `500` → `SessionExpired`; el ciclo se repite una vez con login nuevo. |
| FR-004 | Lecturas: `GET preCargaLecturasRadio` (ventana por defecto); si se necesita más histórico, `POST listadoLecturasRadio` con `idFinca` y fechas. |
| FR-005 | Recibos: página de aterrizaje del login (= «Mis recibos», primera página); último recibo por tipo. |
| FR-006 | Varios abonados: `POST cambioAbonado` con `metodoDestino=preCargaLecturasRadio`, luego `GET buscarRecibos`. |
| FR-007 | Decodificación UTF-8 con respaldo cp1252 por fragmento. |
| FR-008 | HTML interpretado con `html.parser` de la librería estándar. |
| FR-009 | Cada ciclo: login → lecturas → logout (best effort). |
| FR-010 | Estadísticas externas por equipo (US3), incrementales a partir de la última fila importada. |
| FR-011 | Tipo de equipo por texto (repartidor, agua caliente, agua fría, energía) y unidad; tipos desconocidos se muestran con la unidad del portal. |

## 4. Requisitos no funcionales

| ID      | Requisito |
|---------|-----------|
| NFR-001 | Sin dependencias nuevas: solo `aiohttp` (incluido en HA) y la librería estándar. |
| NFR-002 | Ciclo normal < 5 s y < 100 KB; descarga de histórico ≤ 1,5 MB y solo cuando haga falta. |
| NFR-003 | Ningún dato personal en entidades, atributos, logs ni diagnósticos (constitución III). |
| NFR-004 | `api/` no importa nada de `homeassistant`. |
| NFR-005 | Tests del parser y del protocolo con fixtures anonimizadas y un portal falso. |
| NFR-006 | Compatible con HACS y validable con `hassfest`. |

## 5. Fuera de alcance (v0.1)

- «Mis consumos» (lecturas facturadas) y equipos sin radio (lectura manual).
- Descargar los PDF de los recibos.
- «Dar mi lectura», alertas, simulador y cualquier escritura (constitución II).
- Estadísticas de coste a partir de los recibos.

## 6. Preguntas abiertas / riesgos

| # | Tema | Mitigación |
|---|------|------------|
| 1 | ¿La lectura del día D es el valor a las 00:00 de D? (`fechaCantidad=D 00:00:00`) | Se toma literalmente (decisión D6 de `research.md`). |
| 2 | Otros tipos de equipo (agua fría, contadores de energía) sin muestras reales | Clasificación por texto + unidad; desconocidos → sensor genérico. Pedir fixtures. |
| 3 | Cuentas con varias viviendas sin validar | Se replica el mecanismo de la web; marcado `[~]` en tareas. |
| 4 | Política de bloqueo de Keycloak desconocida | Nunca reintentar tras `InvalidAuth` (reauth). |
| 5 | Cambios en el HTML del portal | `ParseError` con mensaje claro → entidades no disponibles, sin borrar históricos. |
