"""Tests del flujo de configuración (T031, US1, US6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ista_calista_es.api import (
    AuthActionRequired,
    CannotConnect,
    InvalidAuth,
    ParseError,
    SessionExpired,
)
from custom_components.ista_calista_es.const import (
    CONF_HISTORY_DAYS,
    CONF_IMPORT_STATISTICS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)

from .conftest import USERNAME, build_data

USER_INPUT = {CONF_USERNAME: "  Abonado@Example.com ", CONF_PASSWORD: "s3cret"}
VALIDATE = "custom_components.ista_calista_es.config_flow.async_validate_input"


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.ista_calista_es.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(VALIDATE, AsyncMock(return_value=build_data("radio.html"))) as validate:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    validate.assert_awaited_once_with(hass, "Abonado@Example.com", "s3cret")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ista Calista (Abonado@Example.com)"
    assert result["data"] == {CONF_USERNAME: "Abonado@Example.com", CONF_PASSWORD: "s3cret"}
    assert result["result"].unique_id == USERNAME


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (InvalidAuth(), "invalid_auth"),
        (AuthActionRequired(), "action_required"),
        (CannotConnect(), "cannot_connect"),
        (SessionExpired(), "cannot_connect"),
        (ParseError(), "unsupported"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, error: Exception, key: str) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(VALIDATE, AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}

    # se recupera tras corregir el problema
    with patch(VALIDATE, AsyncMock(return_value=build_data("radio.html"))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(VALIDATE, AsyncMock()) as validate:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    validate.assert_not_awaited()  # no se gasta un login


async def test_reauth(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(VALIDATE, AsyncMock(side_effect=InvalidAuth())):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "mala"}
        )
    assert result["errors"] == {"base": "invalid_auth"}
    with patch(VALIDATE, AsyncMock(return_value=build_data("radio.html"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "nueva"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "nueva"
    assert config_entry.data[CONF_USERNAME] == USERNAME


async def test_reconfigure(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(VALIDATE, AsyncMock(return_value=build_data("radio.html"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "ABONADO@example.com", CONF_PASSWORD: "otra"}
        )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {CONF_USERNAME: "ABONADO@example.com", CONF_PASSWORD: "otra"}


async def test_reconfigure_other_account(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(VALIDATE, AsyncMock()) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "otra@example.com", CONF_PASSWORD: "x"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    validate.assert_not_awaited()


async def test_options(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_UPDATE_INTERVAL: 12.0, CONF_IMPORT_STATISTICS: False, CONF_HISTORY_DAYS: 30.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {
        CONF_UPDATE_INTERVAL: 12,
        CONF_IMPORT_STATISTICS: False,
        CONF_HISTORY_DAYS: 30,
    }
