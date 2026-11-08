# Tareas 001 — Portal Calista

Leyenda: `[x]` hecho · `[ ]` pendiente · `[~]` requiere validación del usuario.
`[P]` = paralelizable. Cada tarea referencia la historia / requisito que satisface.

## Fase 0 — Investigación
- [x] T001 Explorar login Keycloak, secciones del portal, formatos y codificación (research.md)
- [x] T002 Documentar protocolo (contracts/calista-http.md)
- [x] T003 Prototipo aiohttp: login con cookies por dominio, lecturas, logout

## Fase 1 — Esqueleto del repositorio
- [x] T010 Estructura `custom_components/ista_calista_es/`, `manifest.json`, `hacs.json`
- [x] T011 [P] `README.md`, `LICENSE`, `.gitignore`, `pyproject.toml`, `requirements_test.txt`
- [x] T012 [P] Workflow CI: hassfest + validación HACS + ruff + pytest

## Fase 2 — Capa API (sin HA) — FR-001…FR-011
- [x] T020 `api/exceptions.py`, `api/models.py` (MeterKind, delta con reinicio)
- [x] T021 `api/html.py` (árbol HTML, cierres implícitos, decodificación mixta) + tests
- [x] T022 `api/parser.py` (login, cabecera, abonados, lecturas radio, recibos) + tests
- [x] T023 Fixtures anonimizadas a partir de páginas reales (sin datos personales)
- [x] T024 `api/client.py` (login, cookies, redirecciones, sesión caducada, rango, abonados, logout)
- [x] T025 `tests/fake_portal.py` + tests de protocolo
- [x] T026 `api/redact.py`

## Fase 3 — Integración Home Assistant
- [x] T030 `const.py`, `session.py`, `coordinator.py`, `entity.py`, `__init__.py`
- [x] T031 `config_flow.py`: user, reauth, reconfigure, options (US1, US6)
- [x] T032 `sensor.py`: equipos (US2) y recibos (US4), altas dinámicas
- [x] T033 `statistics.py`: importación inicial e incremental, reinicios (US3)
- [x] T034 `diagnostics.py` con redacción (US6)
- [x] T035 `strings.json`, `translations/en.json`, `translations/es.json`, `icons.json`
- [x] T036 Tests HA: flujo, setup, entidades, estadísticas, diagnósticos (Docker)

## Fase 4 — Validación
- [x] T040 `scripts/live_probe.py` (solo lectura) contra el portal real — ciclo completo 2,0 s;
      con 60 días de histórico 2,2 s
- [x] T041 Home Assistant 2026.10.3 real en Docker con la cuenta del usuario: entrada `loaded`
      en 5,3 s, 10 dispositivos (vivienda + 8 repartidores + agua caliente) y 29 entidades con
      nombres en español; 362 días de estadísticas por equipo (349 en el agua por días sin
      dato); agua aceptada por `energy/validate` sin incidencias; diagnósticos revisados sin
      datos personales; tras reiniciar HA solo se pide la ventana normal (1,9 s, ~85 KB)
- [x] T042 hassfest sin errores · ruff limpio · 71 tests con arnés HA (2026.10.4, Python 3.14)
      + 57 de protocolo/parser
- [~] T043 Cuenta con varias viviendas (US5)
- [~] T044 Otros tipos de equipo (agua fría, energía): fixtures de usuarios
- [x] T045 Publicado en https://github.com/davidmc473/ista-calista-es (público, topics HACS);
      CI verde: hassfest, validación HACS, ruff y tests
- [~] T046 Añadirlo como repositorio personalizado en el HACS del usuario e instalarlo

## Backlog (specs futuras)
- [ ] Spec 002: «Mis consumos» (lecturas facturadas) para equipos sin radio
- [ ] Spec 003: estadísticas de coste a partir de los recibos
