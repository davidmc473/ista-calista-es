# Constitución del proyecto «ista Calista ES» para Home Assistant

Principios que gobiernan todas las especificaciones, planes y tareas de este repositorio.
Cualquier spec o plan que los contradiga debe justificarlo explícitamente en su sección
«Complejidad / excepciones».

## I. Spec primero (SDD)

Ningún cambio funcional entra sin una especificación en `specs/NNN-nombre/`:
`spec.md` (qué y por qué) → `plan.md` (cómo) → `tasks.md` (pasos verificables).
El código sigue a la spec; si la implementación descubre algo que la contradice, se
actualiza primero la spec.

## II. Solo lectura

- La integración **nunca** modifica nada en el portal: no envía lecturas («Dar mi lectura»),
  no cambia alertas, datos personales, preferencia de recibo digital ni usa el simulador
  «¿Cuánto pagar?» (su formulario se llama `guardarLecturas`).
- Solo se usan peticiones de consulta que la web oficial hace al navegar: páginas `GET`,
  el `POST` de búsqueda de lecturas por fechas y el cambio de abonado (vivienda) activo.
- Nada de parámetros inventados: cada petición replica lo que envía la web.

## III. Datos personales fuera de entidades y logs

Credenciales, nombre, e-mail, teléfono, dirección, nº de abonado, identificadores internos
(`idAbonado`, `idFinca`, tickets, `idRecibo`) y números de serie **nunca** aparecen en logs.
Las entidades no exponen datos personales como atributos. Los diagnósticos los redactan.
Las fixtures de test están anonimizadas.

## IV. Capa de acceso independiente

El acceso al portal vive en `api/` **sin dependencias de Home Assistant** ni de librerías
externas (solo `aiohttp`, que HA ya incluye, y la librería estándar). Home Assistant solo
consume modelos normalizados (`CalistaData`). El HTML se interpreta con funciones puras
testeables.

## V. Respeto al portal

- Un único coordinador por cuenta; sondeo por defecto cada 6 h (mínimo 1 h): los datos
  de radio se actualizan una vez al día y llegan con días de retraso.
- Peticiones secuenciales. Cada ciclo abre sesión, lee y la cierra (logout).
- Credenciales rechazadas → nunca se reintenta automáticamente (Keycloak puede bloquear la
  cuenta): se pide reautenticación al usuario.
- El histórico largo se descarga solo cuando hace falta (primera vez o tras un hueco).

## VI. Testeable sin portal

Toda la lógica de parseo y protocolo se prueba con fixtures y con un portal falso.
La prueba en vivo (`scripts/live_probe.py`) es opcional, de solo lectura, y lee las
credenciales de variables de entorno.

## VII. Estándares Home Assistant

Config flow (sin YAML), `DataUpdateCoordinator`, `has_entity_name`, traducciones en/es,
`device_class`/`state_class`/`entity_category` correctos, estadísticas a largo plazo con la
fecha real de cada lectura, diagnósticos, reauth, reconfiguración y compatibilidad HACS.
