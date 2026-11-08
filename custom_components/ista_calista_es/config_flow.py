"""Flujo de configuración: alta, reautenticación, reconfiguración y opciones (US1, US6)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import voluptuous as vol

from .api import (
    AuthActionRequired,
    CalistaClient,
    CalistaData,
    CannotConnect,
    InvalidAuth,
    ParseError,
    SessionExpired,
)
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
    MAX_HISTORY_DAYS,
    MAX_STALE_DAYS,
    MAX_UPDATE_INTERVAL,
    MIN_STALE_DAYS,
    MIN_UPDATE_INTERVAL,
    PORTAL_URL,
)
from .coordinator import CalistaConfigEntry
from .session import async_get_session

_LOGGER = logging.getLogger(__name__)

_EMAIL_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL, autocomplete="username")
)
_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(
        type=selector.TextSelectorType.PASSWORD, autocomplete="current-password"
    )
)


def _credentials_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): _EMAIL_SELECTOR,
            vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        }
    )


def _account_id(username: str) -> str:
    return username.strip().lower()


async def async_validate_input(hass: HomeAssistant, username: str, password: str) -> CalistaData:
    """Ciclo completo de lectura (login, lecturas, logout) con las credenciales dadas."""
    client = CalistaClient(async_get_session(hass), username, password)
    return await client.async_get_data()


async def _async_try_validate(
    hass: HomeAssistant, username: str, password: str, errors: dict[str, str]
) -> CalistaData | None:
    try:
        return await async_validate_input(hass, username, password)
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except AuthActionRequired:
        errors["base"] = "action_required"
    except (CannotConnect, SessionExpired):
        errors["base"] = "cannot_connect"
    except ParseError:
        errors["base"] = "unsupported"
    except Exception:
        _LOGGER.exception("Error inesperado validando la cuenta de ista")
        errors["base"] = "unknown"
    return None


class CalistaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Alta de una cuenta de la oficina virtual de ista."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(_account_id(username))
            self._abort_if_unique_id_configured()
            data = await _async_try_validate(self.hass, username, user_input[CONF_PASSWORD], errors)
            if data is not None:
                return self.async_create_entry(
                    title=f"ista Calista ({username})",
                    data={CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input or {}),
            description_placeholders={"url": PORTAL_URL},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = await _async_try_validate(
                self.hass, entry.data[CONF_USERNAME], user_input[CONF_PASSWORD], errors
            )
            if data is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"username": entry.data[CONF_USERNAME], "url": PORTAL_URL},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(_account_id(username))
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            data = await _async_try_validate(self.hass, username, user_input[CONF_PASSWORD], errors)
            if data is not None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CalistaConfigEntry) -> OptionsFlow:
        return CalistaOptionsFlow()


class CalistaOptionsFlow(OptionsFlow):
    """Opciones: intervalo de sondeo e importación del histórico."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_UPDATE_INTERVAL] = int(user_input[CONF_UPDATE_INTERVAL])
            user_input[CONF_HISTORY_DAYS] = int(user_input[CONF_HISTORY_DAYS])
            user_input[CONF_STALE_DAYS] = int(user_input[CONF_STALE_DAYS])
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL,
                        max=MAX_UPDATE_INTERVAL,
                        step=1,
                        unit_of_measurement="h",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_IMPORT_STATISTICS,
                    default=options.get(CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_HISTORY_DAYS,
                    default=options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=MAX_HISTORY_DAYS,
                        step=1,
                        unit_of_measurement="d",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_STALE_DAYS,
                    default=options.get(CONF_STALE_DAYS, DEFAULT_STALE_DAYS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_STALE_DAYS,
                        max=MAX_STALE_DAYS,
                        step=1,
                        unit_of_measurement="d",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
