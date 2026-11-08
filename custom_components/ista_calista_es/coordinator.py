"""Coordinador de sondeo de una cuenta de ista Calista."""

from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    AuthActionRequired,
    Bill,
    CalistaClient,
    CalistaData,
    CalistaError,
    InvalidAuth,
    Meter,
    ParseError,
)
from .bills import BillTracker
from .const import (
    CONF_HISTORY_DAYS,
    CONF_IMPORT_STATISTICS,
    CONF_STALE_DAYS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_IMPORT_STATISTICS,
    DEFAULT_STALE_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ISSUES_URL,
    PORTAL_TIMEZONE,
    PORTAL_URL,
)
from .issues import (
    ISSUE_ACTION_REQUIRED,
    ISSUE_PORTAL_CHANGED,
    async_clear_issues,
    async_raise_issue,
)
from .statistics import (
    async_history_start,
    async_import_costs,
    async_import_statistics,
    async_last_reading_days,
)

_LOGGER = logging.getLogger(__name__)

type CalistaConfigEntry = ConfigEntry[CalistaDataUpdateCoordinator]


class CalistaDataUpdateCoordinator(DataUpdateCoordinator[CalistaData]):
    """Lee la cuenta completa en cada ciclo e importa el histórico nuevo."""

    config_entry: CalistaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CalistaConfigEntry,
        client: CalistaClient,
        bill_tracker: BillTracker,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                hours=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
        )
        self.client = client
        self.bill_tracker = bill_tracker
        self.import_statistics: bool = entry.options.get(
            CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS
        )
        self.history_days: int = int(entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))
        self.stale_days: int = int(entry.options.get(CONF_STALE_DAYS, DEFAULT_STALE_DAYS))
        #: recibos aparecidos en la última lectura, por vivienda (spec 005)
        self.new_bills: dict[str, list[Bill]] = {}
        #: contador de lecturas correctas (las entidades de evento no repiten avisos)
        self.update_id = 0

    # --- equipos sin datos (spec 006) ---------------------------------------------

    @staticmethod
    def today() -> date:
        return dt_util.now(dt_util.get_time_zone(PORTAL_TIMEZONE)).date()

    def days_without_reading(self, meter: Meter) -> int | None:
        last = meter.last_reading
        return None if last is None else (self.today() - last.date).days

    def is_stale(self, meter: Meter) -> bool:
        days = self.days_without_reading(meter)
        return days is None or days > self.stale_days

    def stale_meters(self) -> list[Meter]:
        return [m for m in self.data.meters if self.is_stale(m)] if self.data else []

    # --- lectura ------------------------------------------------------------------

    @staticmethod
    def _serials(data: CalistaData) -> list[str]:
        return [meter.serial for meter in data.meters]

    def _known_serials(self) -> list[str]:
        """Equipos ya conocidos: los de la última lectura o los del registro de dispositivos."""
        if self.data is not None:
            return self._serials(self.data)
        serials: list[str] = []
        for device in dr.async_entries_for_config_entry(
            dr.async_get(self.hass), self.config_entry.entry_id
        ):
            serials.extend(
                ident
                for domain, ident in device.identifiers
                if domain == DOMAIN and not ident.startswith("dwelling_")
            )
        return serials

    async def _async_fetch(self, history_start: date | None) -> CalistaData:
        entry = self.config_entry
        try:
            data = await self.client.async_get_data(history_start)
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except AuthActionRequired as err:
            # Hay que hacer algo en la web de ista: aviso + reautenticación, sin reintentos
            async_raise_issue(
                self.hass,
                entry,
                ISSUE_ACTION_REQUIRED,
                severity=ir.IssueSeverity.ERROR,
                placeholders={"url": PORTAL_URL},
                learn_more_url=PORTAL_URL,
            )
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="action_required"
            ) from err
        except ParseError as err:
            async_raise_issue(
                self.hass,
                entry,
                ISSUE_PORTAL_CHANGED,
                severity=ir.IssueSeverity.ERROR,
                placeholders={"error": str(err), "url": ISSUES_URL},
                learn_more_url=ISSUES_URL,
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except CalistaError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        async_clear_issues(self.hass, entry, ISSUE_PORTAL_CHANGED, ISSUE_ACTION_REQUIRED)
        return data

    async def _async_update_data(self) -> CalistaData:
        self.new_bills = {}
        if not self.import_statistics:
            data = await self._async_fetch(None)
        else:
            start = await async_history_start(self.hass, self._known_serials(), self.history_days)
            data = await self._async_fetch(start)

            # Equipos que aparecen por primera vez (sin estadísticas) cuando no se ha pedido
            # ya el histórico inicial: se repite la lectura con el rango completo (raro)
            backfill = self.today() - timedelta(days=self.history_days)
            if (
                self.history_days > 0
                and (start is None or start > backfill)
                and None in (await async_last_reading_days(self.hass, self._serials(data))).values()
            ):
                data = await self._async_fetch(backfill)

            await async_import_statistics(self.hass, data)
            await async_import_costs(self.hass, data)

        self.new_bills = await self.bill_tracker.async_new_bills(data)
        self.update_id += 1
        return data
