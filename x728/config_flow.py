import voluptuous as vol
from homeassistant import config_entries
from .constants import DOMAIN, DEFAULT_NAME, DEFAULT_I2C_ADDRESS, DEFAULT_I2C_BUS, CONF_I2C_ADDRESS, CONF_I2C_BUS, CONF_NAME

class X728ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input.get(CONF_NAME, DEFAULT_NAME), data=user_input)

        data_schema = vol.Schema({
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): int,
            vol.Optional(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): int,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)