"""Config flow and reconfigure flow tests (spec 10.1)."""

from __future__ import annotations

import logging
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

import custom_components.smartmostat as smartmostat
from custom_components.smartmostat.const import DOMAIN

from .conftest import REMOTE_DATA, set_device, set_price, set_room, setup_entry


async def _start(hass: HomeAssistant, name: str = "Living room", mode: str = "remote_sensor") -> dict:
	result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
	assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
	return await hass.config_entries.flow.async_configure(result["flow_id"], {"name": name, "control_mode": mode})


async def test_remote_sensor_happy_path(sam_house) -> None:
	"""user -> devices -> price (auto-detected) -> comfort -> entry."""
	hass = sam_house
	result = await _start(hass)
	assert result["step_id"] == "devices"
	schema_keys = {str(key) for key in result["data_schema"].schema}
	assert {"target_climate", "room_sensors", "room_aggregate", "internal_sensor", "outdoor_sensor"} <= schema_keys
	assert "heater" not in schema_keys
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			"target_climate": "climate.sam",
			"room_sensors": ["sensor.living_room_temperature"],
			"room_aggregate": "first_available",
			"outdoor_sensor": "sensor.outdoor_temperature",
		},
	)
	assert result["step_id"] == "price"
	defaults = {str(key): key.default() for key in result["data_schema"].schema if hasattr(key, "default") and callable(key.default)}
	assert defaults["price_sensor"] == "sensor.nordpool"  # auto-detected by raw_today
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.nordpool"})
	assert result["step_id"] == "comfort"
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{"comfort_temperature": 20, "eco_temperature": 16, "comfort_start": "19:00:00", "comfort_end": "23:00:00", "away_temperature": 10},
	)
	await hass.async_block_till_done()
	assert result["type"] is FlowResultType.CREATE_ENTRY
	assert result["title"] == "Living room"
	assert result["data"] == {
		"name": "Living room",
		"control_mode": "remote_sensor",
		"target_climate": "climate.sam",
		"room_sensors": ["sensor.living_room_temperature"],
		"room_aggregate": "first_available",
		"outdoor_sensor": "sensor.outdoor_temperature",
		"price_sensor": "sensor.nordpool",
	}
	assert result["options"]["comfort_start"] == "19:00:00"
	entry = result["result"]
	assert entry.version == 3 and entry.minor_version == 1
	assert hass.states.get("climate.living_room") is not None


async def test_switch_needs_heater_or_cooler(sam_house) -> None:
	"""Switch mode without either relay is an error."""
	hass = sam_house
	result = await _start(hass, "Bedroom", "switch")
	schema_keys = {str(key) for key in result["data_schema"].schema}
	assert {"heater", "cooler", "room_sensors"} <= schema_keys and "target_climate" not in schema_keys
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "min"}
	)
	assert result["errors"] == {"base": "need_heater_or_cooler"}
	hass.states.async_set("switch.heater", "off")
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"heater": "switch.heater", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "min"}
	)
	assert result["step_id"] == "price"


async def test_missing_entities(sam_house) -> None:
	"""Entities must exist; room sensors are required outside set-point mode."""
	hass = sam_house
	result = await _start(hass)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{"target_climate": "climate.nope", "room_sensors": ["sensor.nope"], "room_aggregate": "first_available"},
	)
	assert result["errors"] == {"target_climate": "entity_not_found", "room_sensors": "entity_not_found"}
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"target_climate": "climate.sam", "room_sensors": [], "room_aggregate": "first_available"}
	)
	assert result["errors"] == {"room_sensors": "room_sensor_required"}


async def test_setpoint_room_sensors_optional(sam_house) -> None:
	"""Set-point mode works without room sensors."""
	hass = sam_house
	result = await _start(hass, "Hall", "setpoint")
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"target_climate": "climate.sam", "room_aggregate": "first_available"}
	)
	assert result["step_id"] == "price"


async def test_invalid_and_unavailable_price_sensor(sam_house) -> None:
	"""No slots is an error; unavailable is only a warning."""
	hass = sam_house
	hass.states.async_set("sensor.flat_price", "1.2", {})
	result = await _start(hass)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{"target_climate": "climate.sam", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "first_available"},
	)
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.flat_price"})
	assert result["errors"] == {"price_sensor": "invalid_price_sensor"}
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.missing"})
	assert result["errors"] == {"price_sensor": "entity_not_found"}
	hass.states.async_set("sensor.slow_nordpool", "unavailable", {})
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.slow_nordpool"})
	assert result["step_id"] == "comfort"
	assert "unavailable" in result["description_placeholders"]["price_note"]


async def test_comfort_schedule_validation(sam_house) -> None:
	"""Start without end is an error."""
	hass = sam_house
	result = await _start(hass)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{"target_climate": "climate.sam", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "first_available"},
	)
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.nordpool"})
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"comfort_temperature": 20, "comfort_start": "19:00:00", "away_temperature": 10}
	)
	assert result["errors"] == {"base": "schedule_incomplete"}
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"comfort_temperature": 21, "away_temperature": 10})
	assert result["type"] is FlowResultType.CREATE_ENTRY
	assert result["options"]["comfort_start"] is None
	assert result["options"]["eco_temperature"] is None


async def test_duplicate_device_aborts(sam_house, make_entry) -> None:
	"""Two controllers on one device fight: abort."""
	hass = sam_house
	make_entry()
	result = await _start(hass, "Second")
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{"target_climate": "climate.sam", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "first_available"},
	)
	assert result["type"] is FlowResultType.ABORT
	assert result["reason"] == "already_controlled"


async def test_reconfigure(sam_house, make_entry, caplog) -> None:
	"""Change the room sensors and aggregate; the entry reloads."""
	hass = sam_house
	set_room(hass, 18, "sensor.bedroom_temperature")
	entry = make_entry()
	await setup_entry(hass, entry)
	original = smartmostat.async_setup_entry
	setups = 0

	async def counting(hass_: HomeAssistant, entry_) -> bool:
		nonlocal setups
		setups += 1
		return await original(hass_, entry_)

	with patch.object(smartmostat, "async_setup_entry", counting), caplog.at_level(logging.WARNING):
		result = await entry.start_reconfigure_flow(hass)
		assert result["step_id"] == "reconfigure"
		result = await hass.config_entries.flow.async_configure(result["flow_id"], {"control_mode": "remote_sensor"})
		assert result["step_id"] == "devices"
		result = await hass.config_entries.flow.async_configure(
			result["flow_id"],
			{
				"target_climate": "climate.sam",
				"room_sensors": ["sensor.living_room_temperature", "sensor.bedroom_temperature"],
				"room_aggregate": "min",
			},
		)
		assert result["step_id"] == "price"
		result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.nordpool"})
		await hass.async_block_till_done()
	assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
	# Exactly one reload, done by the update listener (HA 2026.10 warns about,
	# and 2026.12 breaks, async_update_reload_and_abort with a listener).
	assert setups == 1
	assert "should use it for scheduling a reload" not in caplog.text
	assert entry.data["room_sensors"] == ["sensor.living_room_temperature", "sensor.bedroom_temperature"]
	assert entry.data["room_aggregate"] == "min"
	assert "outdoor_sensor" not in entry.data  # cleared in the form
	assert entry.options["comfort_start"] == "19:00:00"  # options kept
	assert hass.states.get("climate.living_room").attributes["remote_temperature"] == 15  # min(15, 18)


async def test_reconfigure_to_switch_mode(sam_house, make_entry) -> None:
	"""Changing mode replaces the device keys."""
	hass = sam_house
	hass.states.async_set("switch.heater", "off")
	entry = make_entry(data={**REMOTE_DATA})
	await setup_entry(hass, entry)
	result = await entry.start_reconfigure_flow(hass)
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"control_mode": "switch"})
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"heater": "switch.heater", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "first_available"}
	)
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.nordpool"})
	await hass.async_block_till_done()
	assert result["reason"] == "reconfigure_successful"
	assert entry.data["control_mode"] == "switch"
	assert entry.data["heater"] == "switch.heater"
	assert "target_climate" not in entry.data


async def test_no_price_sensor_detected(stockholm) -> None:
	"""Without any Nordpool sensor the field has no default."""
	hass = stockholm
	set_device(hass)
	set_room(hass, 20)
	result = await _start(hass)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"target_climate": "climate.sam", "room_sensors": ["sensor.living_room_temperature"], "room_aggregate": "first_available"}
	)
	assert result["step_id"] == "price"
	set_price(hass)
	result = await hass.config_entries.flow.async_configure(result["flow_id"], {"price_sensor": "sensor.nordpool"})
	assert result["step_id"] == "comfort"
