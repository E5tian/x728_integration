"""Config flow for the X728 UPS."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import BooleanSelector, NumberSelector, NumberSelectorConfig, NumberSelectorMode

from .constants import (
    CONF_CHARGE_CONTROL, CONF_I2C_ADDRESS, CONF_I2C_BUS, CONF_LOW_BATTERY,
    CONF_NAME, CONF_SCAN_INTERVAL, DEFAULT_I2C_ADDRESS, DEFAULT_I2C_BUS,
    DEFAULT_LOW_BATTERY, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _check_gauge(bus_number: int, address: int) -> None:
    """Verify the fuel gauge answers during setup (blocking)."""
    import smbus2

    with smbus2.SMBus(bus_number) as bus:
        bus.read_word_data(address, 0x04)


class X728ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure X728 I2C and board capabilities."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    _check_gauge, user_input[CONF_I2C_BUS], user_input[CONF_I2C_ADDRESS]
                )
            except (OSError, ImportError) as err:
                _LOGGER.warning("X728 fuel gauge is not reachable: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_I2C_BUS]}_{user_input[CONF_I2C_ADDRESS]:02x}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): vol.All(int, vol.Range(min=0x03, max=0x77)),
            vol.Required(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): vol.All(int, vol.Range(min=0, max=20)),
            vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=5, max=3600)),
            vol.Required(CONF_LOW_BATTERY, default=DEFAULT_LOW_BATTERY): vol.All(int, vol.Range(min=1, max=99)),
            vol.Required(CONF_CHARGE_CONTROL, default=False): BooleanSelector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
