import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CMD_PGR00, CMD_PGR01
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

OPTION_APPLIANCE = "Appliance (Generator)"
OPTION_UPS = "UPS (Grid)"

OPTIONS = [OPTION_APPLIANCE, OPTION_UPS]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert select entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        AxpertACInputSelect(coordinator)
    ])

class AxpertACInputSelect(CoordinatorEntity, SelectEntity):
    """Select entity for AC Input Range."""

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = "AC Input Range"
        self._attr_unique_id = "axpert_ac_input_range"
        self._attr_options = OPTIONS
        self._attr_current_option = OPTION_APPLIANCE # Default assumption

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        cmd = CMD_PGR00 if option == OPTION_APPLIANCE else CMD_PGR01
        
        # Send command
        success = await self.hass.async_add_executor_job(
            self.coordinator.inverter.set_ac_input_range, cmd
        )
        
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()
            _LOGGER.info(f"Set AC Input Range to {option}")
        else:
            _LOGGER.error(f"Failed to set AC Input Range to {option}")

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "model": "Axpert",
            "sw_version": self.coordinator.firmware_version,
        }
