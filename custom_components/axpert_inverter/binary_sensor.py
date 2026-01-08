from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AxpertDataUpdateCoordinator

# QPIWS Response Mapping (Index -> Translation Key & Name suffix)
WARNING_MAPPING = {
    # 0: reserved
    1: ("inverter_fault", "Inverter Fault"),
    2: ("bus_over", "Bus Over"),
    3: ("bus_under", "Bus Under"),
    4: ("bus_soft_fail", "Bus Soft Fail"),
    5: ("line_fail", "Line Fail"),
    6: ("opv_short", "OPV Short"),
    7: ("inverter_voltage_too_low", "Inverter Voltage Too Low"),
    8: ("inverter_voltage_too_high", "Inverter Voltage Too High"),
    9: ("over_temperature", "Over Temperature"),
    10: ("fan_locked", "Fan Locked"),
    11: ("battery_voltage_high", "Battery Voltage High"),
    12: ("battery_low_alarm", "Battery Low Alarm"),
    # 13 is Reserved
    14: ("battery_under_shutdown", "Battery Under Shutdown"),
    # 15 is Reserved
    16: ("over_load", "Over Load"),
    17: ("eeprom_fault", "EEPROM Fault"),
    18: ("inverter_over_current", "Inverter Over Current"),
    19: ("inverter_soft_fail", "Inverter Soft Fail"),
    20: ("self_test_fail", "Self Test Fail"),
    21: ("op_dc_voltage_over", "OP DC Voltage Over"),
    22: ("battery_open", "Battery Open"),
    23: ("current_sensor_fail", "Current Sensor Fail"),
    24: ("battery_short", "Battery Short"),
    25: ("power_limit", "Power Limit"),
    26: ("pv_voltage_high", "PV Voltage High"),
    27: ("mppt_overload", "MPPT Overload"),
    28: ("mppt_over_temperature", "MPPT Over Temperature"),
    29: ("battery_too_low_to_charge", "Battery Too Low To Charge"),
    # 30: reserved
    # 31: reserved
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert binary sensor entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    for index, (key, name) in WARNING_MAPPING.items():
        entities.append(AxpertWarningSensor(coordinator, index, key, name))
        
    async_add_entities(entities)

class AxpertWarningSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for Axpert warnings."""
    
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, index: int, key: str, name: str):
        """Initialize."""
        super().__init__(coordinator)
        self._index = index
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"axpert_warning_{key}"
        # Fallback name if translation missing
        self._attr_name = name

    @property
    def is_on(self) -> bool | None:
        """Return true if the warning is active."""
        warnings = self.coordinator.data.get("warnings", "")
        if not warnings or len(warnings) <= self._index:
            return None
            
        return warnings[self._index] == '1'

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "sw_version": self.coordinator.firmware_version,
        }
