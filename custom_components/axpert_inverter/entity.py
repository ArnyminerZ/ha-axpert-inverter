from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

class AxpertEntity(CoordinatorEntity):
    """Base class for Axpert entities."""

    def __init__(self, coordinator, source_type: str = "measurement"):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._source_type = source_type

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

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {
            "source_type": self._source_type,
        }
