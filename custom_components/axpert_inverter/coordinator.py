from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .axpert import AxpertInverter
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class AxpertDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Axpert Inverter data."""

    def __init__(self, hass: HomeAssistant, inverter: AxpertInverter, entry: ConfigEntry):
        """Initialize."""
        self.inverter = inverter
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.firmware_version = None
        self.model_id = None
        self.model_name = None

    async def _async_update_data(self):
        """Update data via library."""
        try:
            # We run the synchronous inverter methods in the executor
            data = await self.hass.async_add_executor_job(self._io_update)
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with inverter: {err}")

    def _io_update(self):
        """Synchronous update logic."""
        # Fetch static data if not present
        if not self.firmware_version:
            self.firmware_version = self.inverter.get_firmware_version()
        
        if not self.model_id:
            self.model_id = self.inverter.get_model_id()
        
        if not self.model_name:
            self.model_name = self.inverter.get_model_name()

        data = self.inverter.get_general_status()
        if not data:
            raise UpdateFailed("Received empty data from QPIGS")
            
        # Get warnings
        warnings = self.inverter.get_warnings()
        if warnings:
            data["warnings"] = warnings

        # Get mode
        mode = self.inverter.get_mode()
        if mode:
            data["mode"] = mode

        # Get QPIRI for selectors
        qpiri_data = self.inverter.get_rated_information()
        if qpiri_data:
            data.update(qpiri_data)
        
        return data
