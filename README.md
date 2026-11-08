# ista Calista (España) para Home Assistant

Integración personalizada (HACS) para la **oficina virtual de abonados de ista España**
([Calista](https://oficina.ista.es/GesCon/)): lecturas diarias de los repartidores de
costes de calefacción y de los contadores de agua que ista lee por radio, con su histórico
en las estadísticas de Home Assistant y el importe de los últimos recibos.

> No es un producto oficial de ista. Solo **lee** datos: nunca envía lecturas ni cambia
> nada de tu cuenta.

## Qué ofrece

| Dispositivo | Entidades |
|-------------|-----------|
| **Cada equipo** (repartidor, agua caliente, agua fría, energía) | *Lectura* (acumulada, `total_increasing`), *Consumo del último día*, *Fecha de la última lectura* y *Sin lecturas recientes* (problema) |
| **Vivienda** (abonado) | *Último recibo* de cada tipo (calefacción, agua caliente…) en € con su fecha y el evento **Nuevo recibo** |
| **Estadísticas** | Una por equipo con **cada lectura en su día real** (`ista_calista_es:meter_<serie>`) y una de **coste** por tipo de recibo (`ista_calista_es:cost_<abonado>_<tipo>`), usables en el panel de **Energía → Agua** |
| **Reparaciones** | Avisos si el portal cambia de formato, si ista pide una acción en su web o si algún equipo deja de enviar lecturas |

Los equipos y tipos de recibo nuevos aparecen solos. Si la cuenta tiene varias viviendas,
se leen todas.

### Por qué estadísticas aparte

ista publica las lecturas de radio **una vez al día y con 2–3 días de retraso**. El estado
del sensor *Lectura* refleja el último dato publicado; si usaras ese sensor en el panel de
Energía, el consumo aparecería el día en que Home Assistant lo descarga. Por eso la
integración importa cada lectura diaria en una estadística propia, con su fecha:

- En *Ajustes → Paneles → Energía → Consumo de agua*, elige **«ista · Agua caliente»**
  (o la de tu contador), no el sensor *Lectura*. En *Costes*, «Usar una entidad que
  registre el coste total» → **«ista · Coste agua caliente»**.
- Para gráficas históricas usa la tarjeta **Gráfico de estadísticas** con esas mismas
  estadísticas (los repartidores también tienen la suya, en unidades `UN`).
- La primera vez se importan 365 días (configurable); después, solo lo nuevo.

### Repartidores de costes de calefacción

Miden **unidades de reparto** (`UN`), no energía: sirven para repartir el gasto de la
calefacción central entre vecinos. Se **reinician a 0 cada 1 de octubre** (inicio de
temporada); la integración lo tiene en cuenta para no generar consumos negativos.

El panel de Energía de Home Assistant no admite unidades de reparto, así que la
calefacción no aparece en él: usa la tarjeta **Gráfico de estadísticas** con
«ista · Repartidor …» (consumo) y «ista · Coste calefacción» (€ por mes).

### Coste

El historial completo de recibos se importa como coste acumulado por tipo: cada recibo
cuenta en la fecha de cierre de su periodo, así que la vista útil es la **mensual**.
Algunas comunidades facturan el agua caliente aparte: si tus recibos de agua salen a
0,00 €, su coste en Energía será 0.

### Avisos y automatizaciones

- **Nuevo recibo** (`event.vivienda_<abonado>_nuevo_recibo`): se dispara una vez por cada
  recibo nuevo, con `date`, `kind`, `type`, `amount` y `currency`. Al dar de alta la
  integración no avisa de los recibos que ya existían.

  ```yaml
  triggers:
    - trigger: state
      entity_id: event.vivienda_12345678_nuevo_recibo
  actions:
    - action: notify.mobile_app_mi_movil
      data:
        message: >
          Nuevo recibo de ista ({{ trigger.to_state.attributes.type }}):
          {{ trigger.to_state.attributes.amount }} €
  ```

- **Sin lecturas recientes**: se enciende si un equipo lleva más de 10 días (configurable)
  sin lectura; ista publica con ~3 días de retraso y a veces falta algún día. Además
  aparece un único aviso en *Ajustes → Reparaciones* con la lista de equipos afectados.
- **Reparaciones**: también avisa si el portal cambia de formato (con un enlace para
  informar del problema) o si ista te pide hacer algo en su web antes de entrar.

## Instalación

### HACS (repositorio personalizado)

1. HACS → ⋮ → *Repositorios personalizados* → `https://github.com/davidmc473/ista-calista-es`,
   tipo *Integración*.
2. Instala **ista Calista (España)** y reinicia Home Assistant.

### Manual

Copia `custom_components/ista_calista_es` en la carpeta `config/custom_components/` de tu
Home Assistant y reinicia.

## Configuración

*Ajustes → Dispositivos y servicios → Añadir integración → ista Calista (España)*, con el
e-mail y la contraseña de la oficina virtual de abonados.

> ⚠️ Si la contraseña deja de ser válida, la integración **no reintenta** (para no
> provocar un bloqueo de la cuenta): Home Assistant te pedirá la nueva. Si ista te obliga
> a hacer algo al entrar (cambiar la contraseña, aceptar condiciones…), entra una vez en
> la web, complétalo y vuelve a intentarlo.

### Opciones

| Opción | Por defecto | |
|--------|-------------|---|
| Intervalo de actualización | 6 h | 1–24 h. Más a menudo no aporta nada: ista publica una vez al día |
| Importar el histórico en las estadísticas | sí | |
| Histórico inicial | 365 días | 0–1095. Solo la primera vez (o para equipos nuevos) |
| Días sin lectura para avisar | 10 | 2–60 |

## Cómo funciona

El portal no tiene API pública. La integración hace lo mismo que un navegador:

1. Login OIDC en `login.ista.com` (Keycloak) → `acceso.ista.es` → `oficina.ista.es`.
2. Lee *Mis lecturas Radio* (últimos 15 días, o el rango que haga falta) y exporta
   *Mis recibos* en CSV (todo el historial en ~2 KB).
3. Cierra la sesión.

Un ciclo tarda ~2–3 s y descarga ~90 KB. Todo el HTML se interpreta con la librería
estándar de Python: la integración no tiene dependencias externas.

### Privacidad

Las entidades no exponen datos personales. Los diagnósticos quitan e-mail, nº de abonado,
dirección, identificadores internos y números de serie.

### Limitaciones

- Solo equipos **de radio** (*Mis lecturas Radio*). Las instalaciones de lectura manual
  aún no están soportadas (las lecturas facturadas de *Mis consumos* están en el backlog).
- Probado con repartidores y agua caliente. Agua fría y contadores de energía se clasifican
  por el texto y la unidad del portal; si tienes alguno, abre una incidencia con los
  diagnósticos.
- Las cuentas con **varias viviendas** siguen el mismo mecanismo que la web, pero no se
  han podido probar con una cuenta real.

## Desarrollo (SDD)

El proyecto sigue *Spec-Driven Development*:

```
.specify/memory/constitution.md        principios del proyecto
specs/001-lecturas-calista/            integración base: lecturas, histórico y recibos
  ├── research.md                      hallazgos del portal y decisiones
  ├── spec.md                          historias de usuario y requisitos
  ├── contracts/calista-http.md        protocolo HTTP
  ├── data-model.md                    modelos normalizados y estadísticas
  ├── plan.md                          arquitectura y catálogo de entidades
  └── tasks.md                         tareas y estado
specs/002-avisos-reparaciones/         avisos en «Reparaciones»
specs/003-icono-ista/                  icono y logo oficiales de ista
specs/004-coste-energia/               coste de los recibos en estadísticas y Energía
specs/005-evento-recibo/               evento «Nuevo recibo»
specs/006-equipo-sin-datos/            aviso de equipo sin lecturas recientes
```

```
custom_components/ista_calista_es/
├── api/          acceso al portal SIN Home Assistant (cliente, parser HTML, modelos)
├── coordinator.py · statistics.py · sensor.py · entity.py · config_flow.py · diagnostics.py
```

### Tests

```bash
pip install -r requirements_test.txt
pytest                               # capa api/ (funciona también en Windows)
pip install pytest-homeassistant-custom-component
pytest                               # tests de la integración (Linux/WSL/Docker)
pytest -p no:homeassistant           # tests de protocolo (el arnés de HA bloquea sockets)
```

Prueba en vivo de solo lectura contra el portal real:

```bash
ISTA_USER=... ISTA_PASSWORD=... python scripts/live_probe.py [--history-days 60]
```

Home Assistant de desarrollo con la integración montada:
`docker compose -f docker-compose.dev.yml up -d` → <http://localhost:8124>.

## Licencia

MIT
