"""Coordinador de sondeo de una cuenta de ista Calista."""

from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    AuthActionRequired,
    CalistaClient,
    CalistaData,
    CalistaError,
    InvalidAuth,
)
from .const import (
    CONF_HISTORY_DAYS,
    CONF_IMPORT_STATISTICS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_IMPORT_STATISTICS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PORTAL_TIMEZONE,
)
from .statistics import async_history_start, async_import_statistics, async_last_reading_days

_LOGGER = logging.getLogger(__name__)

type CalistaConfigEntry = ConfigEntry[CalistaDataUpdateCoordinator]


class CalistaDataUpdateCoordinator(DataUpdateCoordinator[CalistaData]):
    """Lee la cuenta completa en cada ciclo e importa el histórico nuevo."""

    config_entry: CalistaConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: CalistaConfigEntry, client: CalistaClient
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
        self.import_statistics: bool = entry.options.get(
            CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS
        )
        self.history_days: int = int(entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))

    @staticmethod
    def _serials(data: CalistaData) -> list[str]:
        return [meter.serial for meter in data.meters]

    def _known_serials(self) -> list[str]:
        """Equipos ya conocidos: los de la última lectura o los del registro de dispositivos."""
        if self.data is not None:
            return [meter.serial for meter in self.data.meters]
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
        try:
            return await self.client.async_get_data(history_start)
        except (InvalidAuth, AuthActionRequired) as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="action_required"
                if isinstance(err, AuthActionRequired)
                else "invalid_auth",
            ) from err
        except CalistaError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_update_data(self) -> CalistaData:
        if not self.import_statistics:
            return await self._async_fetch(None)

        start = await async_history_start(self.hass, self._known_serials(), self.history_days)
        data = await self._async_fetch(start)

        # Equipos que aparecen por primera vez (sin estadísticas) cuando no se ha pedido ya
        # el histórico inicial: se repite la lectura con el rango completo (poco frecuente)
        today = dt_util.now(dt_util.get_time_zone(PORTAL_TIMEZONE)).date()
        backfill = today - timedelta(days=self.history_days)
        if (
            self.history_days > 0
            and (start is None or start > backfill)
            and None in (await async_last_reading_days(self.hass, self._serials(data))).values()
        ):
            data = await self._async_fetch(backfill)

        await async_import_statistics(self.hass, data)
        return data
