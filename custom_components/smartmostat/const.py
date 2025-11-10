"""Constants for the Smart Thermostat integration."""

DOMAIN = "smartmostat"

# Configuration keys
CONF_PRIVATE = "_private"
CONF_HEATER = "heater"
CONF_COOLER = "cooler"
CONF_TARGET_SENSOR = "target_sensor"
CONF_INTERNAL_SENSOR = "internal_sensor"
CONF_OUTDOOR_SENSOR = "outdoor_sensor"
CONF_TARGET_CLIMATE = "target_climate"
CONF_PRICE_SENSOR = "price_sensor"
CONF_MAX_TOLERANCE = "max_tolerance"
CONF_MIN_TOLERANCE = "min_tolerance"
CONF_MAX_OFFSET = "max_offset"
CONF_MIN_OFFSET = "min_offset"
CONF_HEAT_OFFSET = "heat_offset"
CONF_COOL_OFFSET = "cool_offset"
CONF_BASE_STOP_HEAT_OFFSET = "base_stop_heat_offset"
CONF_MAX_STOP_HEAT_OFFSET = "max_stop_heat_offset"
CONF_TEMP_TOLERANCE = "temperature_tolerance"
CONF_FAN_ONLY_DIFF = "fan_only_difference"
CONF_COOL_INDOOR_THRESHOLD = "cool_indoor_threshold"
CONF_COOL_OUTDOOR_THRESHOLD = "cool_outdoor_threshold"
CONF_COOL_INDOOR_MIN = "cool_indoor_min"
CONF_ENABLE_FAN_ONLY_MODE = "enable_fan_only_mode"
CONF_ALLOW_HVAC_MODE_CHANGES = "allow_hvac_mode_changes"
CONF_ENABLE_DIAGNOSTIC_LOGGING = "enable_diagnostic_logging"
CONF_LOOKAHEAD_HOURS = "lookahead_hours"
CONF_PRECONDITIONING_ENABLED = "preconditioning_enabled"
CONF_CONTROL_MODE = "control_mode"

# Defaults
DEFAULT_MAX_TOLERANCE = 2.0
DEFAULT_MIN_TOLERANCE = 0.2
DEFAULT_MAX_OFFSET = 2.0
DEFAULT_MIN_OFFSET = -2.0
DEFAULT_HEAT_OFFSET = 1.0
DEFAULT_COOL_OFFSET = -1.0
DEFAULT_BASE_STOP_HEAT_OFFSET = -2.0
DEFAULT_MAX_STOP_HEAT_OFFSET = -5.0
DEFAULT_TEMP_TOLERANCE = 0.5
DEFAULT_FAN_ONLY_DIFF = 3.0
DEFAULT_COOL_INDOOR_THRESHOLD = 26.0
DEFAULT_COOL_OUTDOOR_THRESHOLD = 25.0
DEFAULT_COOL_INDOOR_MIN = 20.0
DEFAULT_ENABLE_FAN_ONLY_MODE = True
DEFAULT_ALLOW_HVAC_MODE_CHANGES = True
DEFAULT_ENABLE_DIAGNOSTIC_LOGGING = True
DEFAULT_LOOKAHEAD_HOURS = 3
DEFAULT_PRECONDITIONING_ENABLED = True

# Attributes
ATTR_CONTROL_MODE = "control_mode"
ATTR_CURRENT_COLD_TOLERANCE = "current_cold_tolerance"
ATTR_CURRENT_HOT_TOLERANCE = "current_hot_tolerance"
ATTR_CURRENT_PRICE = "current_price"
ATTR_MIN_PRICE = "min_price_24h"
ATTR_MAX_PRICE = "max_price_24h"
ATTR_PRICE_POSITION = "price_position"
ATTR_NEXT_HIGH_PRICE = "next_high_price_in_hours"
ATTR_NEXT_LOW_PRICE = "next_low_price_in_hours"
ATTR_HEATER_ENTITY = "heater_entity"
ATTR_COOLER_ENTITY = "cooler_entity"
ATTR_REMOTE_TEMPERATURE = "remote_temperature"
ATTR_INTERNAL_TEMPERATURE = "internal_temperature"
ATTR_OUTDOOR_TEMPERATURE = "outdoor_temperature"
ATTR_LAST_HVAC_MODE = "last_hvac_mode"

# Control modes
CONTROL_MODE_TOLERANCE = "tolerance"
CONTROL_MODE_TEMPERATURE = "temperature"
DEFAULT_CONTROL_MODE = CONTROL_MODE_TOLERANCE

