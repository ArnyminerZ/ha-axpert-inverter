import logging

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert number entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        AxpertMaxChargingCurrent(coordinator),
        AxpertMaxUtilityChargingCurrent(coordinator),
        AxpertBatteryCutoffVoltage(coordinator),
        AxpertBatteryBulkVoltage(coordinator),
        AxpertBatteryFloatVoltage(coordinator),
    ]
    async_add_entities(entities)

class AxpertNumberEntity(CoordinatorEntity, NumberEntity):
    """Base class for Axpert number entities."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator)
        
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "sw_version": self.coordinator.firmware_version,
        }

    async def _async_set_value_generic(self, func, value):
        """Generic set value helper."""
        success = await self.hass.async_add_executor_job(func, value)
        if not success:
            _LOGGER.warning(f"Failed to set value {value} for {self.entity_id} (NAK). Marking unavailable.")
            self._attr_available = False
            self.async_write_ha_state()
        else:
            # Refresh data
            await self.coordinator.async_request_refresh()

class AxpertMaxChargingCurrent(AxpertNumberEntity):
    """Entity for Max Charging Current."""
    
    _attr_translation_key = "max_charging_current"
    _attr_unique_id = "axpert_max_charging_current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_min_value = 2
    _attr_native_max_value = 120
    _attr_native_step = 1 # Often 10A steps, but 1 is safe

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("max_charging_current")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_value_generic(
            self.coordinator.inverter.set_max_charging_current, int(value)
        )

class AxpertMaxUtilityChargingCurrent(AxpertNumberEntity):
    """Entity for Max Utility Charging Current."""
    
    _attr_translation_key = "max_utility_charging_current"
    _attr_unique_id = "axpert_max_utility_charging_current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_min_value = 2
    _attr_native_max_value = 120
    _attr_native_step = 1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("max_ac_charging_current")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_value_generic(
            self.coordinator.inverter.set_max_utility_charging_current, int(value)
        )

class AxpertBatteryCutoffVoltage(AxpertNumberEntity):
    """Entity for Battery Cut-off Voltage."""
    
    _attr_translation_key = "battery_cutoff_voltage"
    _attr_unique_id = "axpert_battery_cutoff_voltage"
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = NumberDeviceClass.VOLTAGE
    _attr_native_min_value = 10.0
    _attr_native_max_value = 65.0
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("battery_cutoff_voltage")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_value_generic(
            self.coordinator.inverter.set_battery_cutoff_voltage, float(value)
        )

class AxpertBatteryBulkVoltage(AxpertNumberEntity):
    """Entity for Battery Bulk (C.V.) Voltage."""
    
    _attr_translation_key = "battery_bulk_voltage"
    _attr_unique_id = "axpert_battery_bulk_voltage"
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = NumberDeviceClass.VOLTAGE
    _attr_native_min_value = 10.0
    _attr_native_max_value = 65.0
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("battery_bulk_voltage")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_value_generic(
            self.coordinator.inverter.set_battery_bulk_voltage, float(value)
        )

class AxpertBatteryFloatVoltage(AxpertNumberEntity):
    """Entity for Battery Float Voltage."""
    
    _attr_translation_key = "battery_float_voltage"
    _attr_unique_id = "axpert_battery_float_voltage"
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = NumberDeviceClass.VOLTAGE
    _attr_native_min_value = 10.0
    _attr_native_max_value = 65.0
    _attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("battery_float_voltage")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_value_generic(
            self.coordinator.inverter.set_battery_float_voltage, float(value)
        )
