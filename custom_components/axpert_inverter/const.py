"""Constants for the Axpert Inverter integration."""

DOMAIN = "axpert_inverter"

# Configuration
CONF_DEVICE_PATH = "device_path"
DEFAULT_DEVICE_PATH = "/dev/hidraw0"

# Default poll interval (seconds)
DEFAULT_SCAN_INTERVAL = 5

# Commands
CMD_QPIGS = "QPIGS"
CMD_QMOD = "QMOD"
CMD_QID = "QID"
CMD_PGR00 = "PGR00"  # Appliance range (Generator)
CMD_PGR01 = "PGR01"  # UPS range (Grid)

# Device Info
MANUFACTURER = "Voltronic/Axpert"
MODEL = "Axpert Inverter"
