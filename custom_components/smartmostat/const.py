"""Constants for Smartmostat.

This module has no Home Assistant imports so the pure core (price, planner,
actuators, safety, engine, migration) can be tested without an HA instance.
"""

from __future__ import annotations

from typing import Any, Final

DOMAIN: Final = "smartmostat"

CONFIG_VERSION: Final = 3
CONFIG_MINOR_VERSION: Final = 1

# --- Control modes ---------------------------------------------------------
MODE_REMOTE_SENSOR: Final = "remote_sensor"
MODE_SETPOINT: Final = "setpoint"
MODE_SWITCH: Final = "switch"
CONTROL_MODES: Final = [MODE_REMOTE_SENSOR, MODE_SETPOINT, MODE_SWITCH]

# --- Entity keys (entry.data) ----------------------------------------------
CONF_NAME: Final = "name"
CONF_CONTROL_MODE: Final = "control_mode"
CONF_TARGET_CLIMATE: Final = "target_climate"
CONF_HEATER: Final = "heater"
CONF_COOLER: Final = "cooler"
CONF_PRICE_SENSOR: Final = "price_sensor"
CONF_ROOM_SENSORS: Final = "room_sensors"
CONF_ROOM_AGGREGATE: Final = "room_aggregate"
CONF_INTERNAL_SENSOR: Final = "internal_sensor"
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"

DATA_KEYS: Final = (
	CONF_NAME,
	CONF_CONTROL_MODE,
	CONF_TARGET_CLIMATE,
	CONF_HEATER,
	CONF_COOLER,
	CONF_PRICE_SENSOR,
	CONF_ROOM_SENSORS,
	CONF_ROOM_AGGREGATE,
	CONF_INTERNAL_SENSOR,
	CONF_OUTDOOR_SENSOR,
)

AGGREGATE_FIRST: Final = "first_available"
AGGREGATE_MIN: Final = "min"
AGGREGATE_MEAN: Final = "mean"
AGGREGATES: Final = [AGGREGATE_FIRST, AGGREGATE_MIN, AGGREGATE_MEAN]

# --- Tunables (entry.options) ----------------------------------------------
# Comfort and schedule
CONF_COMFORT_TEMPERATURE: Final = "comfort_temperature"
CONF_ECO_TEMPERATURE: Final = "eco_temperature"
CONF_COMFORT_START: Final = "comfort_start"
CONF_COMFORT_END: Final = "comfort_end"
CONF_AWAY_TEMPERATURE: Final = "away_temperature"
CONF_OVERRIDE_MINUTES: Final = "override_minutes"
CONF_AWAY_DEVICE_PRESET: Final = "away_device_preset"
CONF_MIN_TARGET: Final = "min_target"
CONF_MAX_TARGET: Final = "max_target"

# Price behaviour
CONF_PRICE_OPTIMISATION: Final = "price_optimisation"
CONF_LOOKAHEAD_HOURS: Final = "lookahead_hours"
CONF_RELATIVE_MARGIN: Final = "relative_margin"
CONF_CHEAP_RATIO: Final = "cheap_ratio"
CONF_CHEAP_PERCENTILE: Final = "cheap_percentile"
CONF_EXPENSIVE_RATIO: Final = "expensive_ratio"
CONF_CHEAP_BOOST: Final = "cheap_boost"
CONF_BOOST_SKIP_MARGIN: Final = "boost_skip_margin"
CONF_EXPENSIVE_CUT: Final = "expensive_cut"
CONF_PREWARM_HOURS: Final = "prewarm_hours"
CONF_PREWARM_HOURS_COLD: Final = "prewarm_hours_cold"
CONF_COLD_OUTDOOR: Final = "cold_outdoor"
CONF_HOT_DAY_MAX: Final = "hot_day_max"
CONF_MORNING_END: Final = "morning_end"
CONF_SHED_PRICE: Final = "shed_price"
CONF_SHED_HYSTERESIS: Final = "shed_hysteresis"
CONF_SHED_FLOOR: Final = "shed_floor"

# Remote-sensor actuator
CONF_TEMP_TOLERANCE: Final = "temperature_tolerance"
CONF_HEAT_OFFSET: Final = "heat_offset"
CONF_BASE_STOP_HEAT_OFFSET: Final = "base_stop_heat_offset"
CONF_MAX_STOP_HEAT_OFFSET: Final = "max_stop_heat_offset"
CONF_ROOM_MAX: Final = "room_max"
CONF_FAN_ONLY_DIFF: Final = "fan_only_difference"
CONF_IDLE_MODE: Final = "idle_mode"
CONF_FALLBACK_OFFSET: Final = "fallback_offset"
CONF_ALLOW_HVAC_MODE_CHANGES: Final = "allow_hvac_mode_changes"

# Cooling (remote-sensor only)
CONF_COOLING: Final = "cooling"
CONF_COOL_FAN_ROOM: Final = "cool_fan_room"
CONF_COOL_OUTDOOR_GATE: Final = "cool_outdoor_gate"
CONF_COOL_COMPRESSOR_ROOM: Final = "cool_compressor_room"
CONF_COOL_COMPRESSOR_OUTDOOR: Final = "cool_compressor_outdoor"
CONF_COOL_OFFSET: Final = "cool_offset"

# Switch actuator
CONF_HYSTERESIS: Final = "hysteresis"
CONF_MIN_CYCLE_MINUTES: Final = "min_cycle_minutes"

# Safety
CONF_FROST_PROTECTION: Final = "frost_protection"
CONF_FROST_TEMPERATURE: Final = "frost_temperature"
CONF_STALE_MINUTES: Final = "stale_minutes"
CONF_DIAGNOSTIC_EVENTS: Final = "diagnostic_events"

# Advanced
CONF_WEATHER_ENTITY: Final = "weather_entity"
CONF_FORECAST_HOURS: Final = "forecast_hours"
CONF_THERMAL_K: Final = "thermal_k"
CONF_THERMAL_H: Final = "thermal_h"
CONF_THERMAL_K_ENTITY: Final = "thermal_k_entity"
CONF_THERMAL_H_ENTITY: Final = "thermal_h_entity"
CONF_DRY_RUN: Final = "dry_run"

IDLE_AUTO: Final = "auto"
IDLE_FAN_ONLY: Final = "fan_only"
IDLE_HEAT_LOW: Final = "heat_low"
IDLE_OFF: Final = "off"
IDLE_MODES: Final = [IDLE_AUTO, IDLE_FAN_ONLY, IDLE_HEAT_LOW, IDLE_OFF]

# Option defaults. ``None`` means "unset" (the feature is disabled).
DEFAULTS: Final[dict[str, Any]] = {
	CONF_COMFORT_TEMPERATURE: 20.0,
	CONF_ECO_TEMPERATURE: None,
	CONF_COMFORT_START: None,
	CONF_COMFORT_END: None,
	CONF_AWAY_TEMPERATURE: 10.0,
	CONF_OVERRIDE_MINUTES: 90,
	CONF_AWAY_DEVICE_PRESET: None,
	CONF_MIN_TARGET: 7.0,
	CONF_MAX_TARGET: 25.0,
	CONF_PRICE_OPTIMISATION: True,
	CONF_LOOKAHEAD_HOURS: 4,
	CONF_RELATIVE_MARGIN: 0.0,
	CONF_CHEAP_RATIO: 0.5,
	CONF_CHEAP_PERCENTILE: 0.48,
	CONF_EXPENSIVE_RATIO: 1.0,
	CONF_CHEAP_BOOST: 3.0,
	CONF_BOOST_SKIP_MARGIN: 0.5,
	CONF_EXPENSIVE_CUT: 2.0,
	CONF_PREWARM_HOURS: 4.0,
	CONF_PREWARM_HOURS_COLD: 6.0,
	CONF_COLD_OUTDOOR: 10.0,
	CONF_HOT_DAY_MAX: 25.0,
	CONF_MORNING_END: "12:00:00",
	CONF_SHED_PRICE: None,
	CONF_SHED_HYSTERESIS: 0.15,
	CONF_SHED_FLOOR: 19.0,
	CONF_TEMP_TOLERANCE: 0.5,
	CONF_HEAT_OFFSET: 1.0,
	CONF_BASE_STOP_HEAT_OFFSET: -2.0,
	CONF_MAX_STOP_HEAT_OFFSET: -5.0,
	CONF_ROOM_MAX: 27.0,
	CONF_FAN_ONLY_DIFF: 3.0,
	CONF_IDLE_MODE: IDLE_AUTO,
	CONF_FALLBACK_OFFSET: 0.0,
	CONF_ALLOW_HVAC_MODE_CHANGES: True,
	CONF_COOLING: False,
	CONF_COOL_FAN_ROOM: 25.0,
	CONF_COOL_OUTDOOR_GATE: 22.0,
	CONF_COOL_COMPRESSOR_ROOM: 27.0,
	CONF_COOL_COMPRESSOR_OUTDOOR: 27.0,
	CONF_COOL_OFFSET: -1.0,
	CONF_HYSTERESIS: 0.5,
	CONF_MIN_CYCLE_MINUTES: 5,
	CONF_FROST_PROTECTION: True,
	CONF_FROST_TEMPERATURE: 5.0,
	CONF_STALE_MINUTES: 180,
	CONF_DIAGNOSTIC_EVENTS: True,
	CONF_WEATHER_ENTITY: None,
	CONF_FORECAST_HOURS: 4,
	CONF_THERMAL_K: None,
	CONF_THERMAL_H: None,
	CONF_THERMAL_K_ENTITY: None,
	CONF_THERMAL_H_ENTITY: None,
	CONF_DRY_RUN: False,
}

OPTION_KEYS: Final = tuple(DEFAULTS)

# Options that can change without reloading the entry (written by the
# climate entity and the price switch).
LIVE_OPTION_KEYS: Final = frozenset({CONF_COMFORT_TEMPERATURE, CONF_PRICE_OPTIMISATION})

# Fixed constants that are not worth an option.
COOL_SETPOINT_CAP: Final = 27.0
FROST_RELEASE_MARGIN: Final = 3.0
NO_READING_COLD_OUTDOOR: Final = 3.0
DUTY_ON_MINUTES: Final = 10
DUTY_PERIOD_MINUTES: Final = 30
RATE_LIMIT_SECONDS: Final = 60
DEVICE_CHANGE_GRACE_SECONDS: Final = 30
# A device report matching anything we sent this recently is our own command
# arriving late (polled cloud integrations), not a person.
OWN_COMMAND_MEMORY_MINUTES: Final = 15
SENSOR_DEBOUNCE_SECONDS: Final = 30
WATCHDOG_MINUTES: Final = 5
STARTUP_DELAY_SECONDS: Final = 30
WEATHER_REFRESH_MINUTES: Final = 30
COMMAND_TIMEOUT_SECONDS: Final = 10
ON_TRACK_ROOM_MARGIN: Final = 2.5
REALLY_COLD_OUTDOOR: Final = 5.0

# --- Reasons and levels -----------------------------------------------------
REASON_AWAY: Final = "away"
REASON_OVERRIDE: Final = "override"
REASON_PAUSED: Final = "paused"
REASON_NO_PRICE: Final = "no_price"
REASON_PRICE_OFF: Final = "price_off"
REASON_COMFORT: Final = "comfort"
REASON_COMFORT_HOLD: Final = "comfort_hold"
REASON_PREWARM: Final = "prewarm"
REASON_CHEAP_BOOST: Final = "cheap_boost"
REASON_HOT_DAY: Final = "hot_day"
REASON_EXPENSIVE: Final = "expensive"
REASON_SHED: Final = "shed"
REASON_ECONOMY: Final = "economy"
REASON_FROST: Final = "frost"
REASON_FALLBACK: Final = "fallback"
REASON_OFF: Final = "off"
REASONS: Final = [
	REASON_AWAY,
	REASON_OVERRIDE,
	REASON_PAUSED,
	REASON_NO_PRICE,
	REASON_PRICE_OFF,
	REASON_COMFORT,
	REASON_COMFORT_HOLD,
	REASON_PREWARM,
	REASON_CHEAP_BOOST,
	REASON_HOT_DAY,
	REASON_EXPENSIVE,
	REASON_SHED,
	REASON_ECONOMY,
	REASON_FROST,
	REASON_FALLBACK,
	REASON_OFF,
]

LEVEL_CHEAP: Final = "cheap"
LEVEL_NORMAL: Final = "normal"
LEVEL_EXPENSIVE: Final = "expensive"
LEVEL_SUPER_EXPENSIVE: Final = "super_expensive"
LEVEL_UNKNOWN: Final = "unknown"
PRICE_LEVELS: Final = [LEVEL_CHEAP, LEVEL_NORMAL, LEVEL_EXPENSIVE, LEVEL_SUPER_EXPENSIVE, LEVEL_UNKNOWN]

# Presets exposed on the Smartmostat climate entity ("none" is shown as Schedule).
PRESET_SCHEDULE: Final = "none"
PRESET_COMFORT: Final = "comfort"
PRESET_ECO: Final = "eco"
PRESET_AWAY: Final = "away"
PRESETS: Final = [PRESET_SCHEDULE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]

# Smartmostat's own hvac modes (strings match homeassistant.components.climate.HVACMode).
HVAC_OFF: Final = "off"
HVAC_HEAT: Final = "heat"
HVAC_COOL: Final = "cool"
HVAC_HEAT_COOL: Final = "heat_cool"
HVAC_FAN_ONLY: Final = "fan_only"

EVENT_DECISION: Final = "smartmostat_decision"

SERVICE_SET_OVERRIDE: Final = "set_override"
SERVICE_CLEAR_OVERRIDE: Final = "clear_override"
SERVICE_RESUME: Final = "resume"
SERVICE_EVALUATE: Final = "evaluate"
ATTR_MINUTES: Final = "minutes"

STORAGE_VERSION: Final = 1

# Attribute names kept from 0.1.0 and 0.2.0.
ATTR_CONTROL_TARGET: Final = "control_target"
ATTR_BASE_TEMPERATURE: Final = "base_temperature"
ATTR_CURRENT_ADJUSTMENT: Final = "current_adjustment"
ATTR_REASON: Final = "reason"
ATTR_HEADLINE: Final = "headline"
ATTR_CONTROL_MODE: Final = "control_mode"
ATTR_WRAPPED_CLIMATE: Final = "wrapped_climate_entity"
ATTR_REMOTE_TEMPERATURE: Final = "remote_temperature"
ATTR_INTERNAL_TEMPERATURE: Final = "internal_temperature"
ATTR_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature"
ATTR_CURRENT_PRICE: Final = "current_price"
ATTR_AVERAGE_PRICE: Final = "average_price"
ATTR_PRICE_RATIO: Final = "price_ratio"
ATTR_MIN_PRICE: Final = "min_price_24h"
ATTR_MAX_PRICE: Final = "max_price_24h"
ATTR_PRICE_POSITION: Final = "price_position"
ATTR_NEXT_HIGH_PRICE: Final = "next_high_price_in_hours"
ATTR_NEXT_LOW_PRICE: Final = "next_low_price_in_hours"
ATTR_PRICE_LEVEL: Final = "price_level"
ATTR_OVERRIDE_UNTIL: Final = "override_until"
ATTR_PAUSED_UNTIL: Final = "paused_until"
ATTR_STATUS: Final = "status"
