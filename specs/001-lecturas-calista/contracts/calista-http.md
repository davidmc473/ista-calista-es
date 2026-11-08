# Contrato: protocolo HTTP del portal Calista (ista España)

Obtenido navegando la web oficial (portal v.2.108.3, noviembre de 2026). Todas las URL son
HTTPS. Ninguna petición de esta lista modifica datos (constitución II).

## 1. Login (OIDC con Keycloak)

### 1.1 Autorización

```
GET https://login.ista.com/realms/GESCON-PORTAL-ES-APP-Abonado/protocol/openid-connect/auth
    ?client_id=abonado-service&response_type=code&scope=openid
    &redirect_uri=https%3A%2F%2Facceso.ista.es%2Fauth%2Fcallback%2Fabonado
    &state=https%3A%2F%2Foficina.ista.es%2FGesCon%2FAuthHandler.do
    &prompt=login&max_age=0
```

→ `200` HTML con `<form id="loginForm" action="https://login.ista.com/realms/…/login-actions/authenticate?session_code=…&execution=…&client_id=abonado-service&tab_id=…&client_data=…">`
(el `action` viene con `&amp;`). Campos: `username`, `password`.

### 1.2 Credenciales

`POST <action>` (`application/x-www-form-urlencoded`): `username`, `password`.

| Respuesta | Significado |
|-----------|-------------|
| `302` → `https://acceso.ista.es/auth/callback/abonado?state=…&session_state=…&iss=…&code=…` | Correcto |
| `200` con `#loginForm` y mensaje en `#content-area` | Credenciales incorrectas |
| `200` sin `#loginForm` | Acción requerida por Keycloak (no soportado) |

### 1.3 Redirecciones (seguir a mano, guardando cookies de cada salto)

```
302 acceso.ista.es/auth/callback/abonado?…           (cookies KEYCLOAK_* en login.ista.com)
303 oficina.ista.es/GesCon/AuthHandler.do?ticket=…    (cookie KCSESSID en acceso.ista.es)
302 oficina.ista.es/GesCon/GestionOficinaVirtual.do?metodo=loginAbonado&ticket=…  (JSESSIONID)
200 «CALISTA - Datos generales» = Mis recibos
```

Las URL de `Location` se usan tal cual (ya codificadas).

## 2. Sesión

- Cookie `JSESSIONID` (y de afinidad) en `oficina.ista.es`.
- Sesión inválida en una página de datos: `302` a
  `https://<host-interno>.gescon.ista.net:8443/GesCon/RedirectToKeycloak.do?metodo=reconectToKeycloak&tipoUsuario=…`
  (host no resoluble desde Internet) o `500` (p. ej. en `buscarRecibos`).
- Logout: `GET /GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado` → `302`.

## 3. Cabecera común de las páginas

```html
<table class="no-borde">
  <tr><td>Nombre</td><td>…</td><td>Teléfono</td><td>…</td></tr>
  <tr><td>Nº abonado</td><td>12345678</td><td>Email</td><td>…</td></tr>
</table>
<select name="idAbonado" onchange="cambiaAbonado(this)">       (primer select idAbonado)
  <option value="">DIRECCIÓN DEL ABONADO ACTIVO</option>
  <option value="" disabled>-----------------------------------</option>
  <option value="<idAbonado>">DIRECCIÓN</option>                  (uno por abonado)
</select>
```

## 4. Lecturas radio

### 4.1 Ventana por defecto (15 días)

`GET /GesCon/GestionFincas.do?metodo=preCargaLecturasRadio`

### 4.2 Rango de fechas

`POST /GesCon/GestionFincas.do`

| Campo | Valor |
|-------|-------|
| `metodo` | `listadoLecturasRadio` |
| `idFinca` | campo oculto `idFinca` de la página 4.1 |
| `idAbonado` | vacío (abonado activo) |
| `validacion` | `true` |
| `fechaDesdeRadio` / `fechaHastaRadio` | `dd/mm/aaaa` |

### 4.3 Formato

```html
<input type="text" name="fechaDesdeRadio" value="24/10/2026"> … name="fechaHastaRadio" …
<table id="listaLecturasRadio">
  <tr><th></th><th>Ubicacion</th><th>Nº serie</th><th>Tipo</th><th>Unidad Medida</th>
      <th>05/11/26</th><th>04/11/26</th>…</tr>                       (más reciente primero)
  <tr><td><a href="…generarGraficoOV…"><img></a></td>
      <td>(1-Dormitorio1)</td><td>900000001</td>
      <td>Radio Distribuidor de Costes de Calefacción</td><td>UN</td>
      <td><a href="…&cantidad=2.236&fechaCantidad=05/11/2026 00:00:00&…"> 2.236</a></td>
      <td></td>                                                       (día sin dato)
      …</tr>
</table>
```

Valores con punto decimal. Ubicación vacía en algunos equipos (agua).

## 5. Recibos

`GET /GesCon/GestionFacturacionBuscar.do?metodo=buscarRecibos` (también es la página de
aterrizaje del login).

```html
<table id="lista">
  <tr><th>Fecha lectura</th><th>Tipo equipo</th><th>Importe</th><th>Descargar</th></tr>
  <tr><td>31/05/2026</td><td>Radio Distribuidor de Costes de Calefacción</td><td>17,11</td><td><a …idRecibo=…></a></td></tr>
</table>
```

Importe con coma decimal (y punto de miles si lo hubiera). 15 filas por página.

## 6. Cambio de abonado (vivienda)

`POST /GesCon/GestionOficinaVirtual.do?metodo=cambioAbonado&param=<idAbonado>&metodoDestino=preCargaLecturasRadio`
con cuerpo `metodo=preCargaLecturasRadio` → `200` con la vista de lecturas radio del abonado
nuevo (la web envía el formulario de la página actual con esa `action`). Después,
`GET buscarRecibos` devuelve los recibos de ese abonado.
