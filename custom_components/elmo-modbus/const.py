"""Constants for the Elmo Modbus integration."""

DOMAIN = "elmo_modbus"
PLATFORMS = ["alarm_control_panel"]
DEFAULT_SCAN_INTERVAL = 30

# The panel exposes the arming status for up to 64 sectors through the Modbus
# discrete input range ``0x3001``-``0x3040`` (FC2), i.e. address ``12289`` with
# a span of 64 bits.  Each bit represents whether the corresponding sector is
# armed (``True``) or disarmed (``False``).
REGISTER_STATUS_START = 12289
REGISTER_STATUS_COUNT = 64