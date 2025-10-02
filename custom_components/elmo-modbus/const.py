"""Constants for the Elmo Modbus integration."""

DOMAIN = "elmo-modbus"
PLATFORMS = ["alarm_control_panel", "binary_sensor", "sensor", "switch"]
DEFAULT_SCAN_INTERVAL = 1  # in seconds
DEFAULT_NAME = "Elmo Modbus"
DEFAULT_SECTORS = 64
DEFAULT_INPUT_SENSORS = "1-16"
DEFAULT_OUTPUT_SWITCHES = "1-16"

CONF_SECTORS = "sectors"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INPUT_SENSORS = "input_sensors"
CONF_OUTPUT_SWITCHES = "output_switches"

OPTION_ARMED_AWAY_SECTORS = "armed_away_sectors"
OPTION_ARMED_HOME_SECTORS = "armed_home_sectors"
OPTION_ARMED_NIGHT_SECTORS = "armed_night_sectors"
OPTION_DISARM_SECTORS = "disarm_sectors"
OPTION_PANELS = "panels"
OPTION_USER_CODES = "user_codes"
OPTION_INPUT_NAMES = "input_names"
OPTION_OUTPUT_NAMES = "output_names"

# The panel exposes the arming status for up to 64 sectors through the Modbus
# discrete input range ``0x3001``-``0x3040`` (FC2), i.e. address ``12289`` with
# a span of 64 bits.  Each bit represents whether the corresponding sector is
# armed (``True``) or disarmed (``False``).
REGISTER_STATUS_START = 12289
REGISTER_STATUS_COUNT = 64

REGISTER_COMMAND_START = 12289
REGISTER_COMMAND_COUNT = 64

INPUT_SENSOR_START = 4097
INPUT_SENSOR_COUNT = 1024

OUTPUT_SWITCH_START = 20481
OUTPUT_SWITCH_COUNT = 1024
