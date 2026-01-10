from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

class AxpertEntity(CoordinatorEntity):
    """Base class for Axpert entities."""

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "axpert_inverter")},
            "name": "Axpert Inverter",
            "manufacturer": "Voltronic",
            "model": self.coordinator.model_name,
            "model_id": self.coordinator.model_id,
            "sw_version": self.coordinator.firmware_version,
        }
