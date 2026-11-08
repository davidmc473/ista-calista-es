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
| **Cada equipo** (repartidor, agua caliente, agua fría, energía) | *Lectura* (acumulada, `total_increasing`), *Consumo del último día* y *Fecha de la última lectura* |
| **Vivienda** (abonado) | *Último recibo* de cada tipo (calefacción, agua caliente…) en € con su fecha |
| **Estadísticas** | Una estadística por equipo con **cada lectura en su día real** (`ista_calista_es:meter_<serie>`), usable en el panel de **Energía → Agua** |

Los equipos y tipos de recibo nuevos aparecen solos. Si la cuenta tiene varias viviendas,
se leen todas.

### Por qué estadísticas aparte

ista publica las lecturas de radio **una vez al día y con 2–3 días de retraso**. El estado
del sensor *Lectura* refleja el último dato publicado; si usaras ese sensor en el panel de
Energía, el consumo aparecería el día en que Home Assistant lo descarga. Por eso la
integración importa cada lectura diaria en una estadística propia, con su fecha:

- En *Ajustes → Paneles → Energía → Consumo de agua*, elige **«ista · Agua caliente»**
  (o la de tu contador), no el sensor *Lectura*.
- Para gráficas históricas usa la tarjeta **Gráfico de estadísticas** con esas mismas
  estadísticas (los repartidores también tienen la suya, en unidades `UN`).
- La primera vez se importan 365 días (configurable); después, solo lo nuevo.

### Repartidores de costes de calefacción

Miden **unidades de reparto** (`UN`), no energía: sirven para repartir el gasto de la
calefacción central entre vecinos. Se **reinician a 0 cada 1 de octubre** (inicio de
temporada); la integración lo tiene en cuenta para no generar consumos negativos.

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

## Cómo funciona

El portal no tiene API pública. La integración hace lo mismo que un navegador:

1. Login OIDC en `login.ista.com` (Keycloak) → `acceso.ista.es` → `oficina.ista.es`.
2. Lee *Mis lecturas Radio* (últimos 15 días, o el rango que haga falta) y la página de
   *Mis recibos*.
3. Cierra la sesión.

Un ciclo tarda ~2 s y descarga ~85 KB. Todo el HTML se interpreta con la librería
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
