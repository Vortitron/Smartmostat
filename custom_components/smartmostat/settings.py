"""Turn entry data and options into typed settings. Pure Python."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from .actuators import RemoteSensorConfig, SwitchConfig
from .const import (
	AGGREGATE_FIRST,
	CONF_ALLOW_HVAC_MODE_CHANGES,
	CONF_AWAY_DEVICE_PRESET,
	CONF_AWAY_TEMPERATURE,
	CONF_BASE_STOP_HEAT_OFFSET,
	CONF_BOOST_SKIP_MARGIN,
	CONF_CHEAP_BOOST,
	CONF_CHEAP_PERCENTILE,
	CONF_CHEAP_RATIO,
	CONF_COLD_OUTDOOR,
	CONF_COMFORT_END,
	CONF_COMFORT_START,
	CONF_COMFORT_TEMPERATURE,
	CONF_CONTROL_MODE,
	CONF_COOL_COMPRESSOR_OUTDOOR,
	CONF_COOL_COMPRESSOR_ROOM,
	CONF_COOL_FAN_ROOM,
	CONF_COOL_OFFSET,
	CONF_COOL_OUTDOOR_GATE,
	CONF_COOLER,
	CONF_COOLING,
	CONF_DIAGNOSTIC_EVENTS,
	CONF_DRY_RUN,
	CONF_ECO_TEMPERATURE,
	CONF_EXPENSIVE_CUT,
	CONF_EXPENSIVE_RATIO,
	CONF_FALLBACK_OFFSET,
	CONF_FAN_ONLY_DIFF,
	CONF_FORECAST_HOURS,
	CONF_FROST_PROTECTION,
	CONF_FROST_TEMPERATURE,
	CONF_HEAT_OFFSET,
	CONF_HEATER,
	CONF_HOT_DAY_MAX,
	CONF_HYSTERESIS,
	CONF_IDLE_MODE,
	CONF_INTERNAL_SENSOR,
	CONF_LOOKAHEAD_HOURS,
	CONF_MAX_STOP_HEAT_OFFSET,
	CONF_MAX_TARGET,
	CONF_MIN_CYCLE_MINUTES,
	CONF_MIN_TARGET,
	CONF_MORNING_END,
	CONF_NAME,
	CONF_OUTDOOR_SENSOR,
	CONF_OVERRIDE_MINUTES,
	CONF_PREWARM_HOURS,
	CONF_PREWARM_HOURS_COLD,
	CONF_PRICE_OPTIMISATION,
	CONF_PRICE_SENSOR,
	CONF_RELATIVE_MARGIN,
	CONF_ROOM_AGGREGATE,
	CONF_ROOM_MAX,
	CONF_ROOM_SENSORS,
	CONF_SHED_FLOOR,
	CONF_SHED_HYSTERESIS,
	CONF_SHED_PRICE,
	CONF_STALE_MINUTES,
	CONF_TARGET_CLIMATE,
	CONF_TEMP_TOLERANCE,
	CONF_THERMAL_H,
	CONF_THERMAL_H_ENTITY,
	CONF_THERMAL_K,
	CONF_THERMAL_K_ENTITY,
	CONF_WEATHER_ENTITY,
	DEFAULTS,
	MODE_REMOTE_SENSOR,
)
from .engine import EngineConfig
from .planner import PlannerConfig
from .price import PriceSettings
from .safety import SafetyConfig


def parse_time(value: Any) -> time | None:
	"""Parse "HH:MM" or "HH:MM:SS" (TimeSelector output)."""
	if value is None or value == "":
		return None
	if isinstance(value, time):
		return value
	try:
		parts = [int(part) for part in str(value).split(":")]
	except ValueError:
		return None
	if not 2 <= len(parts) <= 3:
		return None
	hour, minute = parts[0], parts[1]
	second = parts[2] if len(parts) == 3 else 0
	if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
		return None
	return time(hour, minute, second)


def _number(options: Mapping[str, Any], key: str) -> float | None:
	value = options.get(key, DEFAULTS[key])
	if value is None or value == "":
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		default = DEFAULTS[key]
		return None if default is None else float(default)


def _req(options: Mapping[str, Any], key: str) -> float:
	value = _number(options, key)
	if value is None:
		return float(DEFAULTS[key])
	return value


def _bool(options: Mapping[str, Any], key: str) -> bool:
	return bool(options.get(key, DEFAULTS[key]))


def _str(options: Mapping[str, Any], key: str) -> str | None:
	value = options.get(key, DEFAULTS[key])
	if isinstance(value, str) and value.strip():
		return value.strip()
	return None


@dataclass(frozen=True)
class Settings:
	"""All typed settings for one entry."""

	name: str
	mode: str
	target_climate: str | None
	heater: str | None
	cooler: str | None
	price_sensor: str | None
	room_sensors: tuple[str, ...]
	room_aggregate: str
	internal_sensor: str | None
	outdoor_sensor: str | None
	comfort_configured: bool
	planner: PlannerConfig
	price: PriceSettings
	engine: EngineConfig
	override_minutes: int
	diagnostic_events: bool
	dry_run: bool
	weather_entity: str | None
	forecast_hours: int
	thermal_k: float | None
	thermal_h: float | None
	thermal_k_entity: str | None
	thermal_h_entity: str | None
	options: dict[str, Any] = field(default_factory=dict)

	@property
	def device_entities(self) -> tuple[str, ...]:
		"""Entities Smartmostat commands."""
		return tuple(e for e in (self.target_climate, self.heater, self.cooler) if e)

	@property
	def sensor_entities(self) -> tuple[str, ...]:
		"""Temperature and thermal inputs (debounced)."""
		items = [*self.room_sensors, self.internal_sensor, self.outdoor_sensor, self.thermal_k_entity, self.thermal_h_entity]
		return tuple(e for e in items if e)


def build_settings(data: Mapping[str, Any], options: Mapping[str, Any]) -> Settings:
	"""Combine entry data and options with defaults."""
	opts = dict(options or {})
	mode = data.get(CONF_CONTROL_MODE, MODE_REMOTE_SENSOR)
	comfort = _number(opts, CONF_COMFORT_TEMPERATURE)
	morning_end = parse_time(opts.get(CONF_MORNING_END, DEFAULTS[CONF_MORNING_END])) or time(12, 0)
	planner = PlannerConfig(
		comfort_temperature=comfort if comfort is not None else float(DEFAULTS[CONF_COMFORT_TEMPERATURE]),
		eco_temperature=_number(opts, CONF_ECO_TEMPERATURE),
		comfort_start=parse_time(opts.get(CONF_COMFORT_START)),
		comfort_end=parse_time(opts.get(CONF_COMFORT_END)),
		away_temperature=_req(opts, CONF_AWAY_TEMPERATURE),
		min_target=_req(opts, CONF_MIN_TARGET),
		max_target=_req(opts, CONF_MAX_TARGET),
		cheap_boost=_req(opts, CONF_CHEAP_BOOST),
		boost_skip_margin=_req(opts, CONF_BOOST_SKIP_MARGIN),
		expensive_cut=_req(opts, CONF_EXPENSIVE_CUT),
		prewarm_hours=_req(opts, CONF_PREWARM_HOURS),
		prewarm_hours_cold=_req(opts, CONF_PREWARM_HOURS_COLD),
		cold_outdoor=_req(opts, CONF_COLD_OUTDOOR),
		hot_day_max=_req(opts, CONF_HOT_DAY_MAX),
		morning_end=morning_end,
		price_optimisation=_bool(opts, CONF_PRICE_OPTIMISATION),
	)
	price = PriceSettings(
		lookahead_hours=int(_req(opts, CONF_LOOKAHEAD_HOURS)),
		relative_margin=_req(opts, CONF_RELATIVE_MARGIN),
		cheap_ratio=_req(opts, CONF_CHEAP_RATIO),
		cheap_percentile=_req(opts, CONF_CHEAP_PERCENTILE),
		expensive_ratio=_req(opts, CONF_EXPENSIVE_RATIO),
		shed_price=_number(opts, CONF_SHED_PRICE),
		shed_hysteresis=_req(opts, CONF_SHED_HYSTERESIS),
	)
	remote = RemoteSensorConfig(
		temperature_tolerance=_req(opts, CONF_TEMP_TOLERANCE),
		heat_offset=_req(opts, CONF_HEAT_OFFSET),
		base_stop_heat_offset=_req(opts, CONF_BASE_STOP_HEAT_OFFSET),
		max_stop_heat_offset=_req(opts, CONF_MAX_STOP_HEAT_OFFSET),
		room_max=_req(opts, CONF_ROOM_MAX),
		fan_only_difference=_req(opts, CONF_FAN_ONLY_DIFF),
		idle_mode=_str(opts, CONF_IDLE_MODE) or "auto",
		fallback_offset=_req(opts, CONF_FALLBACK_OFFSET),
		allow_hvac_mode_changes=_bool(opts, CONF_ALLOW_HVAC_MODE_CHANGES),
		cooling=_bool(opts, CONF_COOLING) and mode == MODE_REMOTE_SENSOR,
		cool_fan_room=_req(opts, CONF_COOL_FAN_ROOM),
		cool_outdoor_gate=_req(opts, CONF_COOL_OUTDOOR_GATE),
		cool_compressor_room=_req(opts, CONF_COOL_COMPRESSOR_ROOM),
		cool_compressor_outdoor=_req(opts, CONF_COOL_COMPRESSOR_OUTDOOR),
		cool_offset=_req(opts, CONF_COOL_OFFSET),
	)
	switch = SwitchConfig(
		hysteresis=_req(opts, CONF_HYSTERESIS),
		min_cycle_minutes=_req(opts, CONF_MIN_CYCLE_MINUTES),
	)
	safety = SafetyConfig(
		frost_protection=_bool(opts, CONF_FROST_PROTECTION),
		frost_temperature=_req(opts, CONF_FROST_TEMPERATURE),
		stale_minutes=_req(opts, CONF_STALE_MINUTES),
		shed_floor=_req(opts, CONF_SHED_FLOOR),
	)
	engine = EngineConfig(
		control_mode=mode,
		remote=remote,
		switch=switch,
		safety=safety,
		away_device_preset=_str(opts, CONF_AWAY_DEVICE_PRESET),
	)
	rooms = data.get(CONF_ROOM_SENSORS) or []
	if isinstance(rooms, str):
		rooms = [rooms]

	def ent(key: str) -> str | None:
		value = data.get(key)
		return value if isinstance(value, str) and value else None

	return Settings(
		name=data.get(CONF_NAME) or "Smartmostat",
		mode=mode,
		target_climate=ent(CONF_TARGET_CLIMATE),
		heater=ent(CONF_HEATER),
		cooler=ent(CONF_COOLER),
		price_sensor=ent(CONF_PRICE_SENSOR),
		room_sensors=tuple(r for r in rooms if r),
		room_aggregate=data.get(CONF_ROOM_AGGREGATE) or AGGREGATE_FIRST,
		internal_sensor=ent(CONF_INTERNAL_SENSOR),
		outdoor_sensor=ent(CONF_OUTDOOR_SENSOR),
		comfort_configured=comfort is not None,
		planner=planner,
		price=price,
		engine=engine,
		override_minutes=int(_req(opts, CONF_OVERRIDE_MINUTES)),
		diagnostic_events=_bool(opts, CONF_DIAGNOSTIC_EVENTS),
		dry_run=_bool(opts, CONF_DRY_RUN),
		weather_entity=_str(opts, CONF_WEATHER_ENTITY),
		forecast_hours=int(_req(opts, CONF_FORECAST_HOURS)),
		thermal_k=_number(opts, CONF_THERMAL_K),
		thermal_h=_number(opts, CONF_THERMAL_H),
		thermal_k_entity=_str(opts, CONF_THERMAL_K_ENTITY),
		thermal_h_entity=_str(opts, CONF_THERMAL_H_ENTITY),
		options=opts,
	)
