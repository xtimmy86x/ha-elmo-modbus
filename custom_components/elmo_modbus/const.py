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

# Modbus addresses — the same address may appear twice when the panel
# uses one function code for reading (FC2 read discrete inputs) and
# another for writing (FC5/FC15 write coils).

REGISTER_ALARM_START = 5121  # FC2: alarm/triggered status per sector

# Sector arming: same address 12289 is read via FC2 (status) and
# written via FC15 (arm/disarm command).
REGISTER_STATUS_START = 12289   # FC2:  read armed status per sector
REGISTER_COMMAND_START = 12289  # FC15: write arm/disarm command

INPUT_SENSOR_START = 4097  # FC2: alarm input state

# Input exclusion: same address 8193 is read via FC2 (current exclusion
# state) and written via FC5 (exclude/include command).
INPUT_SENSOR_EXCLUDED_START = 8193  # FC2: read exclusion state
INPUT_EXCLUDE_START = 8193          # FC5: write exclude/include command

INPUT_BATTERY_START = 0x8001  # 32769 — FC2: low battery status (0/1)
OUTPUT_SWITCH_START = 20481   # FC1/FC5: output relay coils
INOUT_MAX_COUNT = 1024
