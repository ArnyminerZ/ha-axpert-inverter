import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, 
    CONF_DEVICE_PATH, 
    CONF_SCAN_INTERVAL,
    DEFAULT_DEVICE_PATH,
    DEFAULT_SCAN_INTERVAL,
)
from .axpert import AxpertInverter

_LOGGER = logging.getLogger(__name__)

class AxpertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Axpert Inverter."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            device_path = user_input.get(CONF_DEVICE_PATH)
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            
            # Validate connection
            try:
                # We do a quick check in executor
                await self.hass.async_add_executor_job(self._validate_connection, device_path)
                
                return self.async_create_entry(
                    title=f"Axpert Inverter ({device_path})",
                    data=user_input
                )
            except Exception as e:
                _LOGGER.error(f"Failed to connect: {e}")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_PATH, default=DEFAULT_DEVICE_PATH): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AxpertOptionsFlowHandler()

    def _validate_connection(self, path: str):
        """Try to connect to the inverter."""
        inverter = AxpertInverter(path)
        # Try a simple command like QID or just QPIGS
        # But QID is safer/faster? 
        # Actually in axpert.py we implemented send_command.
        # Let's try get_device_id. If it fails, open might fail or read timeout.
        try:
            # Just instantiate and try one command
            # Note: get_device_id might not work on all firmware, QPIGS is safer as main data source.
            # But let's try QPIGS to be sure we can read data.
            res = inverter.get_general_status()
            if not res:
                raise Exception("Empty response from QPIGS during validation")
        except Exception as e:
            raise Exception(f"Validation failed: {e}")

class AxpertOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Axpert Inverter."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            device_path = user_input.get(CONF_DEVICE_PATH)

            # We can optionally validate the new path here
            # But normally we just accept it and let the reload handle connection
            try:
                # Basic validation using the executor
                inverter = AxpertInverter(device_path)
                await self.hass.async_add_executor_job(self._validate_connection_options, inverter)

                return self.async_create_entry(title="", data=user_input)
            except Exception as e:
                _LOGGER.error(f"Failed to connect to new path: {e}")
                errors["base"] = "cannot_connect"

        current_path = self.config_entry.options.get(
            CONF_DEVICE_PATH, self.config_entry.data.get(CONF_DEVICE_PATH, DEFAULT_DEVICE_PATH)
        )
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_PATH, default=current_path): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }),
            errors=errors,
        )

    def _validate_connection_options(self, inverter: AxpertInverter):
        """Validate connection during options update."""
        try:
            res = inverter.get_general_status()
            if not res:
                raise Exception("Empty response from QPIGS during validation")
        except Exception as e:
            raise Exception(f"Validation failed: {e}")
