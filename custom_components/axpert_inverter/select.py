import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CMD_PGR00, CMD_PGR01
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

OPTION_APPLIANCE = "appliance"
OPTION_UPS = "ups"

OPTIONS = [OPTION_APPLIANCE, OPTION_UPS]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert select entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        AxpertACInputSelect(coordinator),
        AxpertOutputPrioritySelect(coordinator),
        AxpertChargerPrioritySelect(coordinator),
        AxpertBatteryTypeSelect(coordinator),
    ])

class AxpertACInputSelect(CoordinatorEntity, SelectEntity):
    """Select entity for AC Input Range."""
    
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_translation_key = "ac_input_range"
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
    def current_option(self) -> str | None:
        # Check coordinator data if available
        val = self.coordinator.data.get("ac_input_range")
        if val == "0":
            return OPTION_APPLIANCE
        elif val == "1":
            return OPTION_UPS
        return self._attr_current_option

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

class AxpertOutputPrioritySelect(CoordinatorEntity, SelectEntity):
    """Select entity for Output Source Priority."""
    
    _attr_has_entity_name = True

    # 0: USB (Utility First), 1: SUB (Solar First), 2: SBU (SBU Priority)
    OPTIONS_MAP = {
        "utility_first": "00",
        "solar_first": "01",
        "sbu_priority": "02",
    }
    REVERSE_MAP = {v: k for k, v in OPTIONS_MAP.items()}

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_translation_key = "output_source_priority"
        self._attr_unique_id = "axpert_output_priority"
        self._attr_options = list(self.OPTIONS_MAP.keys())
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def current_option(self) -> str | None:
        # QPIRI returns 0, 1, 2
        val = self.coordinator.data.get("output_source_priority")
        if val is not None:
             # QPIRI returns single digit '0', '1', '2'. We map to '00', '01', '02' internally if needed, 
             # or just handle the mapping here.
             # Let's assume QPIRI returns '0', '1', '2' as per docs string.
             # The set command uses '00', '01'.
             
             # Pad with 0 just in case
             key = str(val).zfill(2)
             return self.REVERSE_MAP.get(key)
        return None

    async def async_select_option(self, option: str) -> None:
        val = self.OPTIONS_MAP[option] # e.g. "00"
        success = await self.hass.async_add_executor_job(
            self.coordinator.inverter.set_output_source_priority, val
        )
        if success:
            # Optimistically update? Or wait for poll.
            # Wait for poll is safer but slower. 
            pass

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "sw_version": self.coordinator.firmware_version,
        }

class AxpertChargerPrioritySelect(CoordinatorEntity, SelectEntity):
    """Select entity for Charger Source Priority."""
    
    _attr_has_entity_name = True

    # 0: Utility first, 1: Solar first, 2: Solar + Utility, 3: Only Solar
    OPTIONS_MAP = {
        "utility_first": "00",
        "solar_first": "01",
        "solar_and_utility": "02",
        "only_solar": "03",
    }
    REVERSE_MAP = {v: k for k, v in OPTIONS_MAP.items()}

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_translation_key = "charger_source_priority"
        self._attr_unique_id = "axpert_charger_priority"
        self._attr_options = list(self.OPTIONS_MAP.keys())
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def current_option(self) -> str | None:
        val = self.coordinator.data.get("charger_source_priority")
        if val is not None:
             key = str(val).zfill(2)
             return self.REVERSE_MAP.get(key)
        return None

    async def async_select_option(self, option: str) -> None:
        val = self.OPTIONS_MAP[option]
        success = await self.hass.async_add_executor_job(
            self.coordinator.inverter.set_charger_source_priority, val
        )
        if success:
            pass

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "sw_version": self.coordinator.firmware_version,
        }

class AxpertBatteryTypeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for Battery Type."""
    
    _attr_has_entity_name = True

    # 00: AGM, 01: Flooded, 02: User
    OPTIONS_MAP = {
        "agm": "00",
        "flooded": "01",
        "user": "02",
    }
    REVERSE_MAP = {v: k for k, v in OPTIONS_MAP.items()}

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_translation_key = "battery_type"
        self._attr_unique_id = "axpert_battery_type"
        self._attr_options = list(self.OPTIONS_MAP.keys())
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def current_option(self) -> str | None:
        val = self.coordinator.data.get("battery_type")
        if val is not None:
             key = str(val).zfill(2)
             return self.REVERSE_MAP.get(key)
        return None

    async def async_select_option(self, option: str) -> None:
        val = self.OPTIONS_MAP[option]
        success = await self.hass.async_add_executor_job(
            self.coordinator.inverter.set_battery_type, val
        )
        if not success:
            _LOGGER.warning(f"Failed to set Battery Type to {option}")
            self._attr_available = False
            self.async_write_ha_state()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "sw_version": self.coordinator.firmware_version,
        }
