# Spec 002 — Avisos en «Reparaciones»

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-11-08 |
| Depende | Spec 001; el aviso de equipos sin datos usa la spec 006 |

## 1. Contexto

Con la spec 001, cuando algo va mal las entidades pasan a *no disponible* y el motivo solo
queda en el log. Hay tres situaciones que el usuario debe conocer y que no se arreglan
solas o requieren que haga algo fuera de Home Assistant.

## 2. Historias de usuario

### US7 — El portal ha cambiado (P1)
**Aceptación**
1. Si la respuesta del portal no tiene el formato esperado (`ParseError`), aparece en
   *Ajustes → Reparaciones* un aviso de severidad *error* «El portal de ista ha cambiado»,
   con el detalle y un enlace a las incidencias del repositorio.
2. El aviso desaparece solo en la primera lectura correcta.

### US8 — ista pide una acción (P1)
**Aceptación**
1. Si Keycloak pide una acción al iniciar sesión (cambiar la contraseña, aceptar condiciones,
   2FA…), aparece el aviso «ista necesita que completes una acción en su web» con enlace al
   portal, y se lanza la reautenticación (no se reintenta en bucle; constitución V).
2. El aviso desaparece en la primera lectura correcta.

### US9 — Equipos sin lecturas recientes (P2)
**Aceptación**
1. Si uno o más equipos superan el umbral de días sin lectura (spec 006), aparece **un único**
   aviso de severidad *advertencia* con la lista de equipos (con su nombre en HA) y el umbral.
2. Se actualiza en cada lectura y desaparece cuando todos vuelven a tener datos.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-201 | Avisos con `issue_registry`, no reparables desde HA (`is_fixable=False`), con traducciones en/es. |
| FR-202 | Un identificador por aviso y entrada (`<tipo>_<entry_id>`): varias cuentas no se pisan. |
| FR-203 | Al descargar o borrar la entrada se eliminan sus avisos. |
| FR-204 | Los avisos no incluyen credenciales; pueden incluir el título de la entrada (e-mail) porque solo los ve el propio usuario. |

## 4. Fuera de alcance

- Avisos por errores de red transitorios (las entidades ya quedan no disponibles y se recuperan solas).
