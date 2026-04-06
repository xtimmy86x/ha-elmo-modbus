"""Constants for the Elmo Modbus integration."""

DOMAIN = "elmo_modbus"
PLATFORMS = ["alarm_control_panel", "binary_sensor", "sensor", "switch"]
DEFAULT_SCAN_INTERVAL = 1  # in seconds
DEFAULT_NAME = "Elmo Modbus"
DEFAULT_SECTORS = 64

CONF_SECTORS = "sectors"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INPUT_SENSORS = "input_sensors"
CONF_OUTPUT_SWITCHES = "output_switches"
CONF_SECTOR_SWITCHES = "sector_switches"

OPTION_ARMED_AWAY_SECTORS = "armed_away_sectors"
OPTION_ARMED_HOME_SECTORS = "armed_home_sectors"
OPTION_ARMED_NIGHT_SECTORS = "armed_night_sectors"
OPTION_DISARM_SECTORS = "disarm_sectors"
OPTION_PANELS = "panels"
OPTION_USER_CODES = "user_codes"
OPTION_INPUT_NAMES = "input_names"
OPTION_INPUT_BATTERY = "input_battery"
OPTION_OUTPUT_NAMES = "output_names"
OPTION_SECTOR_SWITCH_NAMES = "sector_switch_names"

REGISTER_ALARM_START = 5121
REGISTER_STATUS_START = 12289
REGISTER_COMMAND_START = 12289

INPUT_SENSOR_START = 4097
INPUT_SENSOR_EXCLUDED_START = 8193
INPUT_BATTERY_START = 0x8001  # 32769 - low battery status (FC2, 0/1)
OUTPUT_SWITCH_START = 20481
INPUT_EXCLUDE_START = 8193
INOUT_MAX_COUNT = 1024
