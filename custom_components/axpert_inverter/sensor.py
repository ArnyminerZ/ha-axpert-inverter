from datetime import datetime
import logging
import math
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
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util

from .const import DOMAIN
from .coordinator import AxpertDataUpdateCoordinator
from .entity import AxpertEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Axpert sensor entities."""
    coordinator: AxpertDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        AxpertSensor(coordinator, "grid_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "grid_frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
        AxpertSensor(coordinator, "ac_output_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "ac_output_frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
        AxpertSensor(coordinator, "ac_output_active_power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        AxpertSensor(coordinator, "ac_output_apparent_power", UnitOfApparentPower.VOLT_AMPERE, SensorDeviceClass.APPARENT_POWER),
        AxpertSensor(coordinator, "output_load_percent", PERCENTAGE, None),
        AxpertSensor(coordinator, "battery_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "battery_charging_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
        AxpertSensor(coordinator, "battery_discharge_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
        AxpertSensor(coordinator, "battery_capacity", PERCENTAGE, SensorDeviceClass.BATTERY),
        AxpertSensor(coordinator, "heat_sink_temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
        AxpertSensor(coordinator, "pv_input_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
        AxpertSensor(coordinator, "pv_input_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
        # Synthetic PV Power Sensor
        AxpertPVSensor(coordinator),
        # Real-time Output Current Sensor (Calculated)
        AxpertOutputCurrentSensor(coordinator),
        # Real-time Grid Current Sensor (Calculated)
        AxpertGridCurrentSensor(coordinator),
        # Real-time Grid Power Sensor (Calculated)
        AxpertGridPowerSensor(coordinator),
        # Inverter Status
        AxpertStatusSensor(coordinator),
        # Reactive Power and Power Factor
        AxpertReactivePowerSensor(coordinator),
        AxpertPowerFactorSensor(coordinator),
    ]
    
    # Energy Sensors (Integration)
    entities.append(AxpertEnergySensor(coordinator, "pv_energy", "PV Energy", "pv_power"))
    entities.append(AxpertEnergySensor(coordinator, "load_energy", "Load Energy", "ac_output_active_power"))

    async_add_entities(entities)

class AxpertSensor(AxpertEntity, SensorEntity):
    """Representation of an Axpert Sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, key, unit, device_class):
        """Initialize."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"axpert_{key}"
        self._attr_state_class = SensorStateClass.MEASUREMENT if device_class else None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

class AxpertPVSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for PV Power (V * A)."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
        self._attr_name = "PV Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_unique_id = "axpert_pv_power"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        # Prefer direct reading from inverter if available
        if "pv_charging_power" in self.coordinator.data:
            return float(self.coordinator.data["pv_charging_power"])

        v = self.coordinator.data.get("pv_input_voltage", 0)
        a = self.coordinator.data.get("pv_input_current", 0)
        return round(float(v) * float(a), 1)

class AxpertEnergySensor(AxpertEntity, RestoreEntity, SensorEntity):
    """Sensor that integrates power over time to calculate energy (kWh)."""
    
    _MAX_INTEGRATION_INTERVAL = 300  # 5 minutes in seconds

    def __init__(self, coordinator, key, name, source_key):
        """Initialize."""
        super().__init__(coordinator, source_type="calculated")
        self._key = key
        self._source_key = source_key
        self._attr_name = name
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"axpert_{key}_total"
        
        self._state = 0.0
        self._last_update_time = None
        self._last_power = None

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
        
        # Get current power value
        current_power = 0.0
        if self._source_key == "pv_power":
            if "pv_charging_power" in self.coordinator.data:
                current_power = float(self.coordinator.data["pv_charging_power"])
            else:
                v = self.coordinator.data.get("pv_input_voltage", 0)
                a = self.coordinator.data.get("pv_input_current", 0)
                current_power = float(v) * float(a)
        else:
            current_power = float(self.coordinator.data.get(self._source_key, 0))

        if self._last_update_time is None or self._last_power is None:
            self._last_update_time = now
            self._last_power = current_power
            return

        time_diff_seconds = (now - self._last_update_time).total_seconds()
        
        # Gap Detection: specific logic for long outages
        if time_diff_seconds > self._MAX_INTEGRATION_INTERVAL:
            _LOGGER.debug(f"Time difference {time_diff_seconds}s > {self._MAX_INTEGRATION_INTERVAL}s. Skipping integration to avoid spikes.")
            # We skip the integration for this extensive interval, 
            # effectively assuming 0 energy was processed (or data was lost).
            # We reset the last tracking points to now.
            self._last_update_time = now
            self._last_power = current_power
            return

        time_diff_hours = time_diff_seconds / 3600.0
        
        # Trapezoidal Rule: energy += (prev_power + curr_power) / 2 * time_delta
        avg_power = (self._last_power + current_power) / 2.0
        added_energy_kwh = (avg_power / 1000.0) * time_diff_hours
        
        if added_energy_kwh > 0:
            self._state += added_energy_kwh
            
        self._last_update_time = now
        self._last_power = current_power
        self.async_write_ha_state()

    @property
    def native_value(self):
        return round(self._state, 2)

class AxpertOutputCurrentSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for Output Current (Apparent Power / Voltage)."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
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
            
            # Simple I = S / V for real-time estimation
            return round(s_val / v_val, 1)
                
        except (ValueError, TypeError):
            return 0.0

class AxpertGridCurrentSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for Real-time Grid Current (Calculated)."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
        self._attr_name = "Grid Current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_unique_id = "axpert_grid_current"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:transmission-tower"

    @property
    def native_value(self):
        # P_grid = P_load + P_charge - P_discharge - P_pv
        # I_grid = P_grid / V_grid
        
        try:
            # Get values (default to 0.0)
            p_load = float(self.coordinator.data.get("ac_output_active_power", 0))
            
            batt_v = float(self.coordinator.data.get("battery_voltage", 0))
            batt_chg_i = float(self.coordinator.data.get("battery_charging_current", 0))
            p_charge = batt_v * batt_chg_i
            
            batt_dis_i = float(self.coordinator.data.get("battery_discharge_current", 0))
            p_discharge = batt_v * batt_dis_i
            
            pv_v = float(self.coordinator.data.get("pv_input_voltage", 0))
            pv_i = float(self.coordinator.data.get("pv_input_current", 0))
            p_pv = pv_v * pv_i
            
            p_grid = p_load + p_charge - p_discharge - p_pv
            
            v_grid = float(self.coordinator.data.get("grid_voltage", 0))
            
            if v_grid < 10:
                # No grid
                return 0.0
                
            i_grid = p_grid / v_grid
            
            # Clamp to 0 if negative (exporting? or just noise/imprecision)
            # Some inverters export, but usually Axpert doesn't support grid tie in this mode.
            if i_grid < 0:
                i_grid = 0.0
                
            return round(i_grid, 1)


        except (ValueError, TypeError):
            return 0.0

class AxpertGridPowerSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for Real-time Grid Power (Calculated)."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
        self._attr_name = "Grid Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_unique_id = "axpert_grid_power"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:transmission-tower"

    @property
    def native_value(self):
        # P_grid = P_load + P_charge - P_discharge - P_pv
        
        try:
            # Get values (default to 0.0)
            p_load = float(self.coordinator.data.get("ac_output_active_power", 0))
            
            batt_v = float(self.coordinator.data.get("battery_voltage", 0))
            batt_chg_i = float(self.coordinator.data.get("battery_charging_current", 0))
            p_charge = batt_v * batt_chg_i
            
            batt_dis_i = float(self.coordinator.data.get("battery_discharge_current", 0))
            p_discharge = batt_v * batt_dis_i
            
            pv_v = float(self.coordinator.data.get("pv_input_voltage", 0))
            pv_i = float(self.coordinator.data.get("pv_input_current", 0))
            p_pv = pv_v * pv_i
            
            p_grid = p_load + p_charge - p_discharge - p_pv
            
            # Clamp to 0 if negative (exporting? or just noise/imprecision)
            if p_grid < 0:
                p_grid = 0.0
                
            return round(p_grid, 1)

        except (ValueError, TypeError):
            return 0.0

class AxpertStatusSensor(AxpertEntity, SensorEntity):
    """Sensor for Inverter Status (Enum)."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "inverter_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = [
        "power_on",
        "standby",
        "line_mode",
        "battery_mode",
        "fault",
        "power_saving",
    ]

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = "axpert_inverter_status"

    @property
    def native_value(self):
        mode = self.coordinator.data.get("mode", "")
        
        # Mapping QMOD responses
        # P: Power On
        # S: Standby
        # L: Line Mode
        # B: Battery Mode
        # F: Fault
        # H: Power Saving
        
        if mode == "P":
            return "power_on"
        elif mode == "S":
            return "standby"
        elif mode == "L":
            return "line_mode"
        elif mode == "B":
            return "battery_mode"
        elif mode == "F":
            return "fault"
        elif mode == "H":
            return "power_saving"
        
        return None

class AxpertReactivePowerSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for Reactive Power (VAR)."""

    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
        self._attr_translation_key = "reactive_power"
        self._attr_native_unit_of_measurement = "VAR"
        self._attr_unique_id = "axpert_reactive_power"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:flash-outline"

    @property
    def native_value(self):
        s = float(self.coordinator.data.get("ac_output_apparent_power", 0))
        p = float(self.coordinator.data.get("ac_output_active_power", 0))
        
        # Q = sqrt(S^2 - P^2)
        try:
            # Precision issues might make P > S slightly, causing domain error.
            val = s**2 - p**2
            if val < 0: val = 0
            return round(math.sqrt(val), 1)
        except (ValueError, TypeError):
            return 0.0

class AxpertPowerFactorSensor(AxpertEntity, SensorEntity):
    """Synthetic sensor for Power Factor (%)."""

    def __init__(self, coordinator):
        super().__init__(coordinator, source_type="calculated")
        self._attr_translation_key = "power_factor"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR
        self._attr_unique_id = "axpert_power_factor"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:angle-acute"

    @property
    def native_value(self):
        s = float(self.coordinator.data.get("ac_output_apparent_power", 0))
        p = float(self.coordinator.data.get("ac_output_active_power", 0))

        try:
            if s == 0:
                return 0.0
            
            pf = (p / s) * 100
            # PF cannot exceed 100% technically but noise might cause it.
            if pf > 100: pf = 100.0
            
            return round(pf, 1)
        except (ValueError, TypeError):
            return 0.0
