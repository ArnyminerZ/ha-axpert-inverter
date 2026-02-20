import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError, HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from .axpert import AxpertInverter
from .const import DOMAIN, CONF_DEVICE_PATH
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.BINARY_SENSOR, Platform.NUMBER]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Axpert Inverter component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Axpert Inverter from a config entry."""
    # Prioritize options over data
    device_path = entry.options.get(CONF_DEVICE_PATH, entry.data.get(CONF_DEVICE_PATH))
    
    inverter = AxpertInverter(device_path)
    coordinator = AxpertDataUpdateCoordinator(hass, inverter, entry)

    # Listen for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Fetch firmware version once at startup
    try:
        coordinator.firmware_version = await hass.async_add_executor_job(inverter.get_firmware_version)
    except Exception as e:
        _LOGGER.warning(f"Failed to fetch firmware version: {e}")
        coordinator.firmware_version = "Unknown"

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_send_command(call: ServiceCall):
        """Handle the service call to send a command."""
        command = call.data.get("command")
        if command:
            try:
                _LOGGER.debug(f"Sending command: {command}")
                response = await hass.async_add_executor_job(inverter.send_command, command)
                _LOGGER.info(f"Command '{command}' response: {response}")
                return {"response": response}
            except Exception as e:
                err_msg = str(e)
                if "not supported" in err_msg:
                    raise ServiceValidationError(f"Command '{command}' is not supported by this inverter.")
                _LOGGER.error(f"Command failed: {e}")
                raise HomeAssistantError(f"Command failed: {e}")
        else:
            raise ValueError("No command provided")

    hass.services.async_register(
        DOMAIN, "send_command", handle_send_command, supports_response=SupportsResponse.OPTIONAL
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
