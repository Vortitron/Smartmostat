"""Pure migration mapping tests (spec 9)."""

from __future__ import annotations

import pytest

from custom_components.smartmostat.migration import migrate, migrate_v1, migrate_v2, tolerance_mapping
from custom_components.smartmostat.settings import build_settings, parse_time

V1_DATA = {
	"name": "Living room",
	"target_climate": "climate.sam",
	"price_sensor": "sensor.nordpool_kwh_se4_sek_3_10_025",
	"max_increase": 1.5,
	"max_decrease": 2.5,
	"price_threshold_high": 1.3,
	"price_threshold_low": 0.7,
	"preheating_enabled": True,
	"precooling_enabled": True,
	"preheating_hours": 3,
	"precooling_hours": 2,
}


def test_v1_maps_to_setpoint() -> None:
	"""0.1.0 keys map one to one; precooling is dropped."""
	data, options = migrate_v1(V1_DATA, {"max_increase": 2.0})
	assert data == {
		"name": "Living room",
		"control_mode": "setpoint",
		"room_aggregate": "first_available",
		"room_sensors": [],
		"target_climate": "climate.sam",
		"price_sensor": "sensor.nordpool_kwh_se4_sek_3_10_025",
	}
	assert options["cheap_boost"] == 2.0  # options override data
	assert options["expensive_cut"] == 2.5
	assert options["expensive_ratio"] == 1.3
	assert options["cheap_ratio"] == 0.7
	assert options["lookahead_hours"] == 3
	assert options["price_optimisation"] is True
	assert options["comfort_temperature"] is None
	assert not any(key.startswith("precooling") for key in {**data, **options})


def test_v1_defaults_when_keys_missing() -> None:
	"""0.1.0 defaults apply to keys that were never stored."""
	_data, options = migrate_v1({"target_climate": "climate.x", "price_sensor": "sensor.p"}, {})
	assert options["cheap_boost"] == 2.0
	assert options["expensive_ratio"] == 1.2
	assert options["cheap_ratio"] == 0.8
	assert options["lookahead_hours"] == 2


V2_TEMPERATURE = {
	"name": "Sam",
	"control_mode": "temperature",
	"target_sensor": "sensor.living_room_temperature",
	"internal_sensor": "sensor.sam_inside_temperature",
	"outdoor_sensor": "sensor.outdoor_temperature",
	"target_climate": "climate.sam",
	"price_sensor": "sensor.nordpool",
	"heat_offset": 1.5,
	"cool_offset": -1.5,
	"base_stop_heat_offset": -2.5,
	"max_stop_heat_offset": -6,
	"temperature_tolerance": 0.3,
	"fan_only_difference": 2.5,
	"cool_indoor_threshold": 26.0,
	"cool_outdoor_threshold": 25.0,
	"cool_indoor_min": 20.0,
	"enable_fan_only_mode": False,
	"allow_hvac_mode_changes": True,
	"enable_diagnostic_logging": False,
	"lookahead_hours": 3,
	"preconditioning_enabled": True,
	"max_offset": 2.0,
	"min_offset": -2.0,
	"max_tolerance": 2.0,
	"min_tolerance": 0.2,
}


def test_v2_temperature_mode() -> None:
	"""temperature -> remote_sensor; same-named keys copied; old cooling defaults replaced."""
	data, options = migrate_v2(V2_TEMPERATURE, {})
	assert data["control_mode"] == "remote_sensor"
	assert data["room_sensors"] == ["sensor.living_room_temperature"]
	assert data["internal_sensor"] == "sensor.sam_inside_temperature"
	assert data["outdoor_sensor"] == "sensor.outdoor_temperature"
	assert options["heat_offset"] == 1.5
	assert options["max_stop_heat_offset"] == -6
	assert options["idle_mode"] == "heat_low"
	assert options["diagnostic_events"] is False
	assert options["lookahead_hours"] == 3
	assert options["price_optimisation"] is True
	# Default 0.2.0 cooling thresholds were the over-eager rule: 0.3.0 defaults instead.
	assert "cool_compressor_room" not in options
	assert options["cooling"] is False
	for dropped in ("max_offset", "min_offset", "target_sensor", "cool_indoor_threshold", "max_tolerance"):
		assert dropped not in data and dropped not in options
	settings = build_settings(data, options)
	assert settings.engine.remote.cool_compressor_room == 27


def test_v2_customised_cooling_kept() -> None:
	"""Customised cooling thresholds map onto the new keys and enable cooling."""
	_data, options = migrate_v2(V2_TEMPERATURE, {"cool_indoor_threshold": 28.0, "enable_fan_only_mode": True})
	assert options["cool_compressor_room"] == 28.0
	assert options["cool_compressor_outdoor"] == 25.0
	assert options["cool_fan_room"] == 20.0
	assert options["cooling"] is True
	assert options["idle_mode"] == "fan_only"


V2_TOLERANCE = {
	"name": "Bedroom",
	"control_mode": "tolerance",
	"target_sensor": "sensor.bedroom_temperature",
	"heater": "switch.bedroom_heater",
	"price_sensor": "sensor.nordpool",
	"max_tolerance": 2.0,
	"min_tolerance": 0.2,
	"target_climate": "",
	"enable_diagnostic_logging": True,
}


def test_v2_tolerance_mode() -> None:
	"""tolerance -> switch; tolerances -> hysteresis plus boost and cut."""
	data, options = migrate_v2(V2_TOLERANCE, {"max_tolerance": 1.6})
	assert data["control_mode"] == "switch"
	assert data["heater"] == "switch.bedroom_heater"
	assert "target_climate" not in data  # empty strings dropped
	assert options["hysteresis"] == pytest.approx(0.9)
	assert options["cheap_boost"] == pytest.approx(0.7)
	assert options["expensive_cut"] == pytest.approx(0.7)
	assert options["boost_skip_margin"] == -1.0
	assert "cooling" not in options


def test_tolerance_mapping_maths() -> None:
	"""(a + b) / 2 and (b - a) / 2."""
	assert tolerance_mapping(0.2, 2.0) == {"hysteresis": 1.1, "cheap_boost": 0.9, "expensive_cut": 0.9}


def test_unknown_version() -> None:
	"""Only 1 and 2 can be migrated."""
	with pytest.raises(ValueError):
		migrate(7, {}, {})


def test_parse_time() -> None:
	"""TimeSelector strings."""
	assert str(parse_time("19:00:00")) == "19:00:00"
	assert str(parse_time("07:30")) == "07:30:00"
	assert parse_time("25:00") is None
	assert parse_time("") is None
	assert parse_time("x") is None


def test_settings_defaults_and_mode_specific() -> None:
	"""Defaults apply; cooling only for remote-sensor."""
	settings = build_settings({"control_mode": "switch", "heater": "switch.h", "room_sensors": "sensor.r"}, {"cooling": True})
	assert settings.room_sensors == ("sensor.r",)
	assert settings.engine.remote.cooling is False
	assert settings.planner.comfort_temperature == 20
	assert settings.comfort_configured is True  # missing key means the default
	assert build_settings({}, {"comfort_temperature": None}).comfort_configured is False  # migrated
	assert settings.device_entities == ("switch.h",)
