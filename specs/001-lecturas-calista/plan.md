# Plan técnico 001 — Portal Calista

Entrada: [`spec.md`](spec.md) · Protocolo: [`contracts/calista-http.md`](contracts/calista-http.md)
· Modelos: [`data-model.md`](data-model.md) · Hallazgos: [`research.md`](research.md)

## 1. Stack

| Aspecto | Decisión |
|---------|----------|
| Lenguaje | Python ≥ 3.13 (el de Home Assistant) |
| HTTP | `aiohttp`: sesión compartida con `DummyCookieJar` + `CookieJar` propio por cliente; redirecciones a mano |
| HTML | `html.parser` de la stdlib → árbol ligero propio (`api/html.py`) |
| HA mínimo | 2025.10 (`entry.runtime_data`, `StatisticMeanType`, traducción de dispositivos) |
| Tests | `pytest`, `pytest-asyncio`, servidor `aiohttp` falso; `pytest-homeassistant-custom-component` (Docker) |
| Distribución | HACS (repositorio tipo *integration*) |

## 2. Arquitectura

```
custom_components/ista_calista_es/
├── api/                      ← SIN dependencias de Home Assistant (constitución IV)
│   ├── __init__.py           exports
│   ├── client.py             CalistaClient: login Keycloak, cookies, lecturas, recibos, logout
│   ├── html.py               árbol HTML mínimo (Element, parse_html) + decode_html
│   ├── parser.py             HTML → modelos (funciones puras)
│   ├── models.py             CalistaData, Dwelling, Meter, Reading, Bill, MeterKind
│   ├── exceptions.py         CalistaError, CannotConnect, InvalidAuth, AuthActionRequired,
│   │                         SessionExpired, ParseError
│   └── redact.py             redacción de datos personales
├── __init__.py               setup/unload, runtime_data, dispositivos de vivienda
├── config_flow.py            user + reauth + reconfigure + options
├── coordinator.py            CalistaDataUpdateCoordinator (+ importación de estadísticas)
├── statistics.py             estadísticas externas (US3)
├── entity.py                 entidades base (vivienda / equipo) y DeviceInfo
├── sensor.py                 sensores de equipo y de recibos, altas dinámicas
├── diagnostics.py
├── session.py                sesión HTTP compartida sin cookies
├── const.py · manifest.json · strings.json · translations/{en,es}.json · icons.json
```

### Ciclo de sondeo

```
coordinator._async_update_data()
  ├─ history_start = statistics.async_history_start(...)   ¿falta histórico?
  ├─ client.async_get_data(history_start)
  │    ├─ login()                         GET auth → POST credenciales → 3 redirecciones
  │    │                                  → aterrizaje = recibos del abonado activo
  │    ├─ GET preCargaLecturasRadio       ventana 15 días (+ POST rango si history_start)
  │    ├─ por cada otro abonado: POST cambioAbonado → (POST rango) → GET buscarRecibos
  │    └─ logout()                        siempre (finally)
  └─ statistics.async_import(data)        filas nuevas por equipo
```

Si una petición de datos devuelve `SessionExpired`, el ciclo completo se repite una vez.

### Decisión de histórico

```
async_history_start(serials conocidos):
    sin importación                         → None (ventana por defecto)
    algún equipo sin estadísticas            → hoy − días de histórico
    si no                                    → min(última fila importada) − 1 día
                                               (None si cae dentro de la ventana)
tras leer: equipos nuevos sin estadísticas y la ventana no cubre el histórico pedido
            → segunda lectura con el rango completo (raro: altas de equipos)
```

## 3. Catálogo de entidades

### Dispositivo «Vivienda `<nº abonado>`» (`identifiers = {(DOMAIN, "dwelling_<key>")}`)

| key | Nombre (es) | Clase | Notas |
|-----|-------------|-------|-------|
| `last_bill_heat_cost_allocator` | Último recibo de calefacción | `monetary` · EUR | atributo `date` |
| `last_bill_hot_water` | Último recibo de agua caliente | `monetary` · EUR | |
| `last_bill_cold_water` / `last_bill_water` | Último recibo de agua fría / de agua | `monetary` · EUR | |
| `last_bill_heat` | Último recibo de energía | `monetary` · EUR | |
| `last_bill_unknown` | Último recibo (otros) | `monetary` · EUR | atributo `type` |

Solo se crean los tipos que aparecen en los recibos.

### Dispositivo por equipo (`identifiers = {(DOMAIN, <serie>)}`, `via_device` = vivienda)

Nombre traducido: «Repartidor {location}», «Agua caliente {location}»… (o sin ubicación).

| key | Nombre (es) | Clase | Notas |
|-----|-------------|-------|-------|
| `reading` | Lectura | según tipo · `total_increasing` | |
| `last_consumption` | Consumo del último día | según tipo (sin `state_class`) | atributos `from`, `to` |
| `last_reading_date` | Fecha de la última lectura | `date` | diagnóstico |

Clase por tipo: agua → `water` (m³), energía → `energy` (kWh/MWh/GJ), repartidor → sin
clase, unidad `UN`, icono `mdi:radiator`.

## 4. Manejo de errores

| Situación | API | Coordinador / HA |
|-----------|-----|------------------|
| Timeout / red / HTTP inesperado | `CannotConnect` | `UpdateFailed` |
| Sesión caducada en mitad del ciclo | `SessionExpired` → ciclo repetido 1 vez | transparente |
| Credenciales rechazadas | `InvalidAuth` | `ConfigEntryAuthFailed` → reauth |
| Keycloak pide una acción | `AuthActionRequired` | `ConfigEntryAuthFailed` (reauth con mensaje) |
| HTML inesperado | `ParseError` | `UpdateFailed` |

## 5. Testing

| Nivel | Qué | Cómo |
|-------|-----|------|
| Unit | `html`, `parser`, `models` | fixtures anonimizadas en `tests/fixtures/` |
| Protocolo | login, cookies por dominio, redirecciones, credenciales malas, acción requerida, sesión caducada, rango, varios abonados, logout | portal falso `aiohttp` (`tests/fake_portal.py`) |
| HA | config flow, setup, entidades, estadísticas (reinicio de temporada, incremental), diagnósticos | `pytest-homeassistant-custom-component` en Docker |
| En vivo | ciclo real de solo lectura | `scripts/live_probe.py` con `ISTA_USER`/`ISTA_PASSWORD` |
