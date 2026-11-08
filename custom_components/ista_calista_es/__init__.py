"""Integración ista Calista (España) para Home Assistant."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .api import CalistaClient
from .const import DOMAIN, PLATFORMS
from .coordinator import CalistaConfigEntry, CalistaDataUpdateCoordinator
from .entity import async_register_devices
from .session import async_get_session


async def async_setup_entry(hass: HomeAssistant, entry: CalistaConfigEntry) -> bool:
    """Configura una cuenta."""
    client = CalistaClient(
        async_get_session(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = CalistaDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Viviendas y equipos antes que las entidades (estas solo los referencian)
    @callback
    def _async_register_devices() -> None:
        async_register_devices(hass, entry)

    _async_register_devices()
    entry.async_on_unload(coordinator.async_add_listener(_async_register_devices))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalistaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CalistaConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Permite borrar a mano equipos o viviendas que ya no aparecen en el portal."""
    data = entry.runtime_data.data
    current = {(DOMAIN, meter.serial) for meter in data.meters} | {
        (DOMAIN, f"dwelling_{dwelling.key}") for dwelling in data.dwellings
    }
    return not device.identifiers & current


async def _async_update_listener(hass: HomeAssistant, entry: CalistaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
