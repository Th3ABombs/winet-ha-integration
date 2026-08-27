"""Config flow for the WiNET pellet stove integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .api import WinetClient, WinetConnectionError, WinetError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import WinetConfigEntry

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


class WinetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the module address and validate it."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            # Accept a pasted URL as well as a bare host.
            host = host.removeprefix("http://").removeprefix("https://").rstrip("/")

            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            client = WinetClient(async_get_clientsession(self.hass), host)
            try:
                # Both are pure reads: nothing is sent to the stove board.
                await client.async_get_module_status()
                config = await client.async_get_config()
            except WinetConnectionError:
                errors["base"] = "cannot_connect"
            except WinetError:
                errors["base"] = "unexpected_response"
            else:
                name = user_input.get(CONF_NAME) or ""
                if not name.strip():
                    reported = str(config.get("name") or "").strip()
                    name = (
                        reported if reported and reported != "NO NAME" else DEFAULT_NAME
                    )
                return self.async_create_entry(title=name, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: WinetConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WinetOptionsFlow()


class WinetOptionsFlow(OptionsFlow):
    """Let the user change the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
