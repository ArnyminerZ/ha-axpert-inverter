import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .axpert import AxpertInverter
from .const import DOMAIN, CONF_DEVICE_PATH
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Axpert Inverter component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Axpert Inverter from a config entry."""
    device_path = entry.data[CONF_DEVICE_PATH]
    
    inverter = AxpertInverter(device_path)
    coordinator = AxpertDataUpdateCoordinator(hass, inverter)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_send_command(call: ServiceCall):
        """Handle the service call to send a command."""
        command = call.data.get("command")
        if command:
            try:
                response = await hass.async_add_executor_job(inverter.send_command, command)
                _LOGGER.info(f"Command '{command}' response: {response}")
                return {"response": response}
            except Exception as e:
                _LOGGER.error(f"Command failed: {e}")
                raise e

    hass.services.async_register(DOMAIN, "send_command", handle_send_command)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
