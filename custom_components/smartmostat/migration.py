"""Config entry migration from 0.1.0 (version 1) and 0.2.0 (version 2).

Pure functions over plain dicts so they can be tested without Home Assistant.
``__init__.async_migrate_entry`` applies the result to the entry. Unknown
keys are dropped; unique ids are never touched.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
	AGGREGATE_FIRST,
	CONF_BOOST_SKIP_MARGIN,
	CONF_CHEAP_BOOST,
	CONF_CHEAP_RATIO,
	CONF_COMFORT_TEMPERATURE,
	CONF_CONTROL_MODE,
	CONF_COOL_COMPRESSOR_OUTDOOR,
	CONF_COOL_COMPRESSOR_ROOM,
	CONF_COOL_FAN_ROOM,
	CONF_COOLER,
	CONF_COOLING,
	CONF_DIAGNOSTIC_EVENTS,
	CONF_EXPENSIVE_CUT,
	CONF_EXPENSIVE_RATIO,
	CONF_HEATER,
	CONF_HYSTERESIS,
	CONF_IDLE_MODE,
	CONF_INTERNAL_SENSOR,
	CONF_LOOKAHEAD_HOURS,
	CONF_NAME,
	CONF_OUTDOOR_SENSOR,
	CONF_PRICE_OPTIMISATION,
	CONF_PRICE_SENSOR,
	CONF_ROOM_AGGREGATE,
	CONF_ROOM_SENSORS,
	CONF_TARGET_CLIMATE,
	IDLE_FAN_ONLY,
	IDLE_HEAT_LOW,
	MODE_REMOTE_SENSOR,
	MODE_SETPOINT,
	MODE_SWITCH,
)

DEFAULT_NAME = "Smart Thermostat"

# 0.1.0 defaults (const.py of 0.1.0), used when a key was never stored.
V1_DEFAULTS = {
	"max_increase": 2.0,
	"max_decrease": 2.0,
	"price_threshold_high": 1.2,
	"price_threshold_low": 0.8,
	"preheating_hours": 2,
}

# 0.2.0 defaults.
V2_DEFAULT_MIN_TOLERANCE = 0.2
V2_DEFAULT_MAX_TOLERANCE = 2.0
V2_COOL_DEFAULTS = {
	"cool_indoor_threshold": 26.0,
	"cool_outdoor_threshold": 25.0,
	"cool_indoor_min": 20.0,
}

# 0.2.0 keys whose meaning is unchanged in 0.3.0.
V2_SAME_OPTIONS = (
	"heat_offset",
	"cool_offset",
	"base_stop_heat_offset",
	"max_stop_heat_offset",
	"temperature_tolerance",
	"fan_only_difference",
	"allow_hvac_mode_changes",
)


def _merged(data: Mapping[str, Any], options: Mapping[str, Any]) -> dict[str, Any]:
	"""0.1.0 and 0.2.0 both read data with options taking precedence."""
	return {**dict(data), **dict(options or {})}


def _float(value: Any, default: float) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _entity(value: Any) -> str | None:
	if isinstance(value, str) and value.strip():
		return value.strip()
	return None


def migrate_v1(data: Mapping[str, Any], options: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
	"""0.1.0 wrapped a climate and shifted its set-point: becomes ``setpoint``."""
	old = _merged(data, options)
	new_data: dict[str, Any] = {
		CONF_NAME: old.get(CONF_NAME) or DEFAULT_NAME,
		CONF_CONTROL_MODE: MODE_SETPOINT,
		CONF_ROOM_AGGREGATE: AGGREGATE_FIRST,
		CONF_ROOM_SENSORS: [],
	}
	for key in (CONF_TARGET_CLIMATE, CONF_PRICE_SENSOR):
		if _entity(old.get(key)):
			new_data[key] = _entity(old.get(key))

	def v1(key: str) -> float:
		return _float(old.get(key, V1_DEFAULTS[key]), V1_DEFAULTS[key])

	new_options: dict[str, Any] = {
		CONF_CHEAP_BOOST: v1("max_increase"),
		CONF_EXPENSIVE_CUT: v1("max_decrease"),
		CONF_EXPENSIVE_RATIO: v1("price_threshold_high"),
		CONF_CHEAP_RATIO: v1("price_threshold_low"),
		CONF_LOOKAHEAD_HOURS: max(1, int(round(v1("preheating_hours")))),
		CONF_PRICE_OPTIMISATION: True,
		# Taken from the restored climate state at first start (section 9.1).
		CONF_COMFORT_TEMPERATURE: None,
	}
	return new_data, new_options


def tolerance_mapping(min_tolerance: float, max_tolerance: float) -> dict[str, float]:
	"""0.2.0 price-dependent band -> hysteresis plus boost/cut.

	0.2.0 switched on at T - a and off at T + b at the cheapest price
	(and T - b / T + a at the dearest). With control T +/- (b - a) / 2 and a
	band of (a + b) / 2 the same four thresholds come out.
	"""
	a, b = float(min_tolerance), float(max_tolerance)
	return {
		CONF_HYSTERESIS: round((a + b) / 2, 4),
		CONF_CHEAP_BOOST: round((b - a) / 2, 4),
		CONF_EXPENSIVE_CUT: round((b - a) / 2, 4),
	}


def migrate_v2(data: Mapping[str, Any], options: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
	"""0.2.0 "temperature" -> ``remote_sensor``, "tolerance" -> ``switch``."""
	old = _merged(data, options)
	old_mode = old.get(CONF_CONTROL_MODE, "tolerance")
	mode = MODE_REMOTE_SENSOR if old_mode == "temperature" else MODE_SWITCH

	new_data: dict[str, Any] = {
		CONF_NAME: old.get(CONF_NAME) or DEFAULT_NAME,
		CONF_CONTROL_MODE: mode,
		CONF_ROOM_AGGREGATE: AGGREGATE_FIRST,
	}
	sensor = _entity(old.get("target_sensor"))
	new_data[CONF_ROOM_SENSORS] = [sensor] if sensor else []
	for key in (
		CONF_INTERNAL_SENSOR,
		CONF_OUTDOOR_SENSOR,
		CONF_TARGET_CLIMATE,
		CONF_HEATER,
		CONF_COOLER,
		CONF_PRICE_SENSOR,
	):
		if _entity(old.get(key)):
			new_data[key] = _entity(old.get(key))

	new_options: dict[str, Any] = {CONF_COMFORT_TEMPERATURE: None}
	for key in V2_SAME_OPTIONS:
		if key in old and old[key] is not None:
			new_options[key] = old[key]

	thresholds = {key: _float(old.get(key, default), default) for key, default in V2_COOL_DEFAULTS.items()}
	customised = any(abs(thresholds[key] - V2_COOL_DEFAULTS[key]) > 1e-9 for key in thresholds)
	if customised:
		new_options[CONF_COOL_COMPRESSOR_ROOM] = thresholds["cool_indoor_threshold"]
		new_options[CONF_COOL_COMPRESSOR_OUTDOOR] = thresholds["cool_outdoor_threshold"]
		new_options[CONF_COOL_FAN_ROOM] = thresholds["cool_indoor_min"]
	if mode == MODE_REMOTE_SENSOR:
		new_options[CONF_COOLING] = bool(new_data.get(CONF_COOLER)) or customised
		if "enable_fan_only_mode" in old:
			new_options[CONF_IDLE_MODE] = IDLE_FAN_ONLY if old["enable_fan_only_mode"] else IDLE_HEAT_LOW

	if mode == MODE_SWITCH:
		new_options.update(
			tolerance_mapping(
				_float(old.get("min_tolerance"), V2_DEFAULT_MIN_TOLERANCE),
				_float(old.get("max_tolerance"), V2_DEFAULT_MAX_TOLERANCE),
			)
		)
		# 0.2.0 had no "already warm" skip; keep its thresholds exact.
		new_options[CONF_BOOST_SKIP_MARGIN] = -1.0

	if "lookahead_hours" in old:
		new_options[CONF_LOOKAHEAD_HOURS] = max(1, int(round(_float(old["lookahead_hours"], 4))))
	if "preconditioning_enabled" in old:
		new_options[CONF_PRICE_OPTIMISATION] = bool(old["preconditioning_enabled"])
	if "enable_diagnostic_logging" in old:
		new_options[CONF_DIAGNOSTIC_EVENTS] = bool(old["enable_diagnostic_logging"])
	return new_data, new_options


def migrate(version: int, data: Mapping[str, Any], options: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
	"""Migrate from ``version`` (1 or 2) to 3."""
	if version == 1:
		return migrate_v1(data, options)
	if version == 2:
		return migrate_v2(data, options)
	raise ValueError(f"cannot migrate from version {version}")
