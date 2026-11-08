"""Diagnósticos sin datos personales (US6, constitución III)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api.redact import anonymized_data
from .coordinator import CalistaConfigEntry

TO_REDACT_ENTRY = {CONF_PASSWORD, CONF_USERNAME, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CalistaConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
        "last_update_success": coordinator.last_update_success,
        "import_statistics": coordinator.import_statistics,
        "history_days": coordinator.history_days,
        "data": anonymized_data(coordinator.data) if coordinator.data else None,
    }
