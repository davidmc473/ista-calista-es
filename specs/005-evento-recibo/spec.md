# Spec 005 — Evento «Nuevo recibo»

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-11-08 |
| Depende | Spec 004 (historial completo de recibos) |

## 1. Contexto

El usuario quiere enterarse cuando ista emite un recibo (p. ej. una notificación al móvil
con el importe) sin comparar sensores a mano.

## 2. Historias de usuario

### US13 — Evento por cada recibo nuevo (P1)
**Aceptación**
1. Cada vivienda tiene una entidad `event` *Nuevo recibo* (`event_types: [new_bill]`).
2. Cuando aparece un recibo que no se había visto, se dispara un evento con `date`
   (ISO), `kind` (tipo normalizado), `type` (texto del portal), `amount` y `currency` (`EUR`).
   Si aparecen varios a la vez, un evento por recibo, del más antiguo al más reciente.
3. La primera lectura de una vivienda (alta de la integración o vivienda nueva) solo registra
   los recibos existentes: **no** dispara eventos por el historial.
4. Reiniciar Home Assistant no repite eventos: los recibos vistos se guardan en
   `.storage/ista_calista_es.<entry_id>.bills`, que se borra al eliminar la entrada.
5. Un recibo antiguo que aparece tarde (más de 90 días anterior al más reciente conocido) se
   registra sin evento, para no avisar por historial que el portal no mostraba antes.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-501 | Clave de un recibo: fecha + texto del tipo + importe. Un importe corregido cuenta como recibo nuevo. |
| FR-502 | Entidad con nombre traducido y el estado traducido del tipo de evento (en/es). |

## 4. Ejemplo de automatización

```yaml
triggers:
  - trigger: state
    entity_id: event.vivienda_12345678_nuevo_recibo
actions:
  - action: notify.mobile_app_movil
    data:
      message: >
        Nuevo recibo de ista ({{ trigger.to_state.attributes.type }}):
        {{ trigger.to_state.attributes.amount }} €
```
