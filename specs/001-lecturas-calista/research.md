# Research 001 — Hallazgos sobre el portal Calista de ista España

Sesión de exploración: 2026-11-08, cuenta real de un abonado con 8 repartidores de
costes de calefacción y 1 contador de agua caliente, todos vía radio. Portal `v.2.108.3`.

## Arquitectura del portal

| Pieza | Valor observado |
|-------|-----------------|
| Proveedor de identidad | Keycloak, realm `GESCON-PORTAL-ES-APP-Abonado`, cliente `abonado-service` (`login.ista.com`) |
| Pasarela OIDC | `acceso.ista.es/auth/callback/abonado` (canjea el `code` y emite un *ticket*) |
| Aplicación | `oficina.ista.es/GesCon` (Java/Struts `.do`, tablas *displaytag*), detrás de Azure Application Gateway |
| Cookies | `login.ista.com`: `AUTH_SESSION_ID`, `KEYCLOAK_*`… · `acceso.ista.es`: `KCSESSID` · `oficina.ista.es`: `JSESSIONID`, `ApplicationGatewayAffinity*`, `delegacion`, `rol` |
| User-Agent | Se aceptan tanto el de aiohttp como el de Home Assistant (sin bloqueo del WAF en páginas `.do`; los `.js` estáticos dan 403, no se necesitan) |
| Codificación | Las cabeceras dicen UTF-8 y el contenido de datos lo es, pero hay fragmentos en Latin-1 → decodificar UTF-8 con respaldo cp1252 por fragmento |

## Login (ver `contracts/calista-http.md`)

1. `GET` URL de autorización (con `prompt=login&max_age=0`) → formulario `#loginForm`
   (solo `username` y `password`).
2. `POST` → `302` a `acceso.ista.es` → `303` a `oficina…/AuthHandler.do?ticket=…` → `302` a
   `GestionOficinaVirtual.do?metodo=loginAbonado&ticket=…` → `200`.
3. La página de aterrizaje es **«Mis recibos»** (datos del abonado + primera página de recibos).
4. Login completo ≈ 1,5 s con aiohttp.

**Credenciales incorrectas**: `200` con `#loginForm` otra vez y el texto «El correo
electrónico y/o la contraseña son incorrectas…» en `#content-area`. Probado con un usuario
inexistente para no arriesgar bloqueos de la cuenta real. → *Decisión*: `200` + `#loginForm`
= `InvalidAuth`; cualquier otra página de Keycloak (cambio de contraseña obligatorio,
aceptar términos, OTP…) = `AuthActionRequired`.

**Sesión caducada / inválida**: `302` a un **host interno inexistente**
(`https://lmad02istaapp4.gescon.ista.net:8443/GesCon/RedirectToKeycloak.do?…`) o `500` en
algunas páginas. → *Decisión*: nunca seguir redirecciones en peticiones de datos; `3xx`/`500`
= `SessionExpired` (se reintenta el ciclo una vez con login nuevo).

**Logout**: `GET …/GestionOficinaVirtual.do?metodo=logOutAbonado` → `302` a
`RedirectToKeycloak.do` → página de login. Tras él, la sesión queda invalidada.

## Secciones del menú

| Sección | URL | Interés |
|---------|-----|---------|
| Mis recibos | `GestionFacturacionBuscar.do?metodo=buscarRecibos` | Fecha, tipo de equipo, importe (€). 15 por página, orden no cronológico |
| Dar mi lectura | `GestionOficinaVirtualInsertarLectura.do?metodo=lecturaAbonado` | **Escritura** — prohibido (constitución II) |
| Mis consumos | `GestionLecturasBusqueda.do?metodo=buscarLecturas` | Lecturas *facturadas* por periodo; paginado (250 filas, 17 páginas). En repartidores todo vale `0 UN`; en agua, lecturas enteras. Su CSV no trae lecturas |
| **Mis lecturas Radio** | `GestionFincas.do?metodo=preCargaLecturasRadio` | **Lectura diaria de cada equipo** → fuente principal |
| ¿Cuánto pagar? | `GestionFacturacion_Abo.do?metodo=recogeLecturasRecibosWeb` | Simulador (`guardarLecturas`) — no se usa |
| Mis alertas | `GestionOficinaVirtualAlertas.do?metodo=preCargaAvisosAbonado` | Configuración (escritura) — no se usa |
| Gráfico | `GestionLecturas.do?metodo=generarGraficoOV` | Imagen PNG generada en servidor — no aporta datos |

## «Mis lecturas Radio»

- `GET` devuelve la ventana por defecto (últimos 15 días). `POST listadoLecturasRadio` con
  `idFinca` (campo oculto de la página) y `fechaDesdeRadio`/`fechaHastaRadio` (`dd/mm/aaaa`)
  devuelve cualquier rango: 60 días ≈ 190 KB, 14 meses ≈ 1,2 MB (429 columnas).
- Tabla `#listaLecturasRadio`: columnas *(gráfico)*, *Ubicacion* `(1-Dormitorio1)`, *Nº serie*,
  *Tipo*, *Unidad Medida* y una columna por día (`dd/mm/aa`, de más reciente a más antiguo,
  sin huecos de fechas). Cada celda es un enlace con `fechaCantidad=dd/mm/aaaa 00:00:00`.
- Hay **celdas vacías** (días sin dato): el agua tenía 45 de 429.
- La última lectura disponible es de hace ~3 días.
- Tipos vistos: `Radio Distribuidor de Costes de Calefacción` (unidad `UN`) y
  `Radio agua caliente` (`m3`). El contador de agua no tiene ubicación.
- **Los repartidores se reinician a 0 cada 1 de octubre** (inicio de temporada; visto en
  2025 y 2026). El agua es acumulada y nunca baja.
- Valores con punto decimal (`19.875`, `0.0`).

## Recibos

- Tabla `#lista`: *Fecha lectura* (`dd/mm/aaaa`), *Tipo equipo* (`Agua caliente`,
  `Radio Distribuidor de Costes de Calefacción`), *Importe* con coma decimal (`17,11`),
  enlace de descarga PDF (`duplicarReciboIndividualCalista&idRecibo=…`).
- Mensuales por tipo; en esta cuenta el agua caliente sale a `0,00`.

## Varias viviendas (abonados)

Un `select` (sin `id`) lista los abonados: la primera opción (sin valor) muestra el activo;
luego un separador deshabilitado y una opción por abonado con su `idAbonado` opaco. La web
cambia de abonado con `POST GestionOficinaVirtual.do?metodo=cambioAbonado&param=<id>&metodoDestino=<metodo>`
y responde directamente con la vista destino. Probado con el único abonado de la cuenta.
→ *Riesgo*: no se ha podido validar con una cuenta de varias viviendas.

## Datos personales presentes

E-mail, nombre, teléfono, nº de abonado y dirección (cabecera de todas las páginas),
`idAbonado`, `idFinca`, tickets y `idRecibo` en enlaces, números de serie de los equipos.
→ Lista de redacción y fixtures anonimizadas.

## Integraciones existentes

- `ista_ecotrend` (núcleo de HA) es para ista Alemania (otra plataforma). Su patrón de
  **estadísticas externas** con la fecha real de consumo se adopta aquí.
- Existen integraciones comunitarias para Calista basadas en el login antiguo
  (formulario propio de GesCon); el portal ya usa Keycloak.

## Decisiones

| # | Decisión | Motivo |
|---|----------|--------|
| D1 | Parser HTML propio con `html.parser` | Sin dependencias (constitución IV); las páginas son tablas simples |
| D2 | Cookies por cliente con un `CookieJar` propio y sesión HTTP compartida sin cookies | Aislar cuentas; HA no recomienda cerrar sesiones propias |
| D3 | Seguir redirecciones a mano | Capturar cookies de cada salto y detectar el host interno de sesión caducada |
| D4 | Login → datos → logout en cada ciclo | Ciclos cada horas: la sesión caducaría igualmente; no dejar sesiones abiertas |
| D5 | Estadísticas externas con la fecha de cada lectura | El dato llega con días de retraso: el estado del sensor lo atribuiría al día equivocado |
| D6 | Lectura de fecha D = valor a las 00:00 de D → fila de estadística que empieza a las 23:00 de D-1 | Así el consumo entre dos lecturas cae en el día en que se produjo |
| D7 | En repartidores, una bajada es reinicio de temporada (delta = nuevo valor); en el resto, una bajada se ignora (delta 0) | Evitar consumos ficticios por correcciones del contador |
| D8 | «Mis consumos» (lecturas facturadas) fuera de la v0.1 | Redundante con radio y costoso (paginado); spec futura para instalaciones sin radio |
