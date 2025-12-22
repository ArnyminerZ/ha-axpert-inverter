from datetime import datetime
import logging
from typing import Optional, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfApparentPower,
    UnitOfEnergy,
    UnitOfTemperature,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util

from .const import DOMAIN
from .coordinator import AxpertDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert sensor entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        AxpertSensor(coordinator, "grid_voltage", "Grid Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "grid_frequency", "Grid Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
        AxpertSensor(coordinator, "ac_output_voltage", "Output Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "ac_output_frequency", "Output Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
        AxpertSensor(coordinator, "ac_output_active_power", "Output Active Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        AxpertSensor(coordinator, "ac_output_apparent_power", "Output Apparent Power", UnitOfApparentPower.VOLT_AMPERE, SensorDeviceClass.APPARENT_POWER),
        AxpertSensor(coordinator, "output_load_percent", "Load Percent", PERCENTAGE, None),
        AxpertSensor(coordinator, "battery_voltage", "Battery Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "battery_charging_current", "Battery Charging Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
        AxpertSensor(coordinator, "battery_capacity", "Battery Capacity", PERCENTAGE, SensorDeviceClass.BATTERY),
        AxpertSensor(coordinator, "heat_sink_temperature", "Inverter Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
        AxpertSensor(coordinator, "pv_input_voltage", "PV Input Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "pv_input_current", "PV Input Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
        # Synthetic PV Power Sensor
        AxpertPVSensor(coordinator),
        # Synthetic Output Current Sensor
        AxpertOutputCurrentSensor(coordinator),
    ]
    
    # Energy Sensors (Integration)
    entities.append(AxpertEnergySensor(coordinator, "pv_energy", "PV Energy", "pv_power"))
    entities.append(AxpertEnergySensor(coordinator, "load_energy", "Load Energy", "ac_output_active_power"))

    async_add_entities(entities)

class AxpertSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Axpert Sensor."""

    def __init__(self, coordinator, key, name, unit, device_class):
        """Initialize."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"axpert_{key}"
        self._attr_state_class = SensorStateClass.MEASUREMENT if device_class else None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

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

class AxpertPVSensor(CoordinatorEntity, SensorEntity):
    """Synthetic sensor for PV Power (V * A)."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "PV Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_unique_id = "axpert_pv_power"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        v = self.coordinator.data.get("pv_input_voltage", 0)
        a = self.coordinator.data.get("pv_input_current", 0)
        return round(float(v) * float(a), 1)

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

class AxpertEnergySensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Sensor that integrates power over time to calculate energy (kWh)."""
    
    def __init__(self, coordinator, key, name, source_key):
        """Initialize."""
        super().__init__(coordinator)
        self._key = key
        self._source_key = source_key
        self._attr_name = name
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"axpert_{key}_total"
        
        self._state = 0.0
        self._last_update_time = None

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            try:
                self._state = float(state.state)
            except ValueError:
                self._state = 0.0
        
        self._last_update_time = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        now = dt_util.utcnow()
        if self._last_update_time is None:
            self._last_update_time = now
            return

        time_diff = (now - self._last_update_time).total_seconds() / 3600.0 # Hours
        
        # Get power value
        current_power = 0.0
        if self._source_key == "pv_power":
            v = self.coordinator.data.get("pv_input_voltage", 0)
            a = self.coordinator.data.get("pv_input_current", 0)
            current_power = float(v) * float(a)
        else:
            current_power = float(self.coordinator.data.get(self._source_key, 0))
            
        # Left Riemann Sum: energy += power * time_delta
        # (Assuming power was constant since last update. Valid for small intervals)
        # Or Trapezoidal: 0.5 * (prev_power + curr_power) * dt
        # For simplicity and given noisy polling, Left Sum with current power is "okay", 
        # but technically we should use previous power for Left Sum, or current for Right Sum.
        # Let's use simple accumulation of current rate.
        
        added_energy_kwh = (current_power / 1000.0) * time_diff
        
        if added_energy_kwh > 0:
            self._state += added_energy_kwh
            
        self._last_update_time = now
        self.async_write_ha_state()

    @property
    def native_value(self):
        return round(self._state, 2)
    
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

class AxpertOutputCurrentSensor(CoordinatorEntity, SensorEntity):
    """Synthetic sensor for Output Current (S / V) or (S / (V*1.732))."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Output Current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_unique_id = "axpert_output_current"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:current-ac"

    @property
    def native_value(self):
        s = self.coordinator.data.get("ac_output_apparent_power", 0)
        v = self.coordinator.data.get("ac_output_voltage", 0)
        
        try:
            s_val = float(s)
            v_val = float(v)
            if v_val == 0:
                return 0.0
            
            # Check phase config from coordinator
            is_tri_phase = self.coordinator.phase_config == PHASE_TRI
            
            if is_tri_phase:
                # I = S / (V * sqrt(3))
                return round(s_val / (v_val * 1.732), 1)
            else:
                # I = S / V
                return round(s_val / v_val, 1)
                
        except (ValueError, TypeError):
            return 0.0

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
