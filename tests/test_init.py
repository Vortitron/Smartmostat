"""Set-up, migration, translations and diagnostics (spec 9, 13.2)."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.translation import async_get_translations
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.smartmostat import diagnostics
from custom_components.smartmostat.const import DOMAIN, REASONS

from .conftest import set_device, set_room, setup_entry

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN

# A real 0.1.0 entry: everything in data, options written by its options flow.
V1_DATA = {
	"name": "Living room",
	"target_climate": "climate.sam",
	"price_sensor": "sensor.nordpool",
	"max_increase": 2.0,
	"max_decrease": 2.0,
	"price_threshold_high": 1.2,
	"price_threshold_low": 0.8,
	"preheating_enabled": True,
	"precooling_enabled": True,
	"preheating_hours": 2,
	"precooling_hours": 2,
}
V1_OPTIONS = {"max_increase": 1.5, "precooling_enabled": False}

V2_TEMPERATURE = {
	"name": "Living room",
	"control_mode": "temperature",
	"target_sensor": "sensor.living_room_temperature",
	"outdoor_sensor": "sensor.outdoor_temperature",
	"target_climate": "climate.sam",
	"price_sensor": "sensor.nordpool",
	"heat_offset": 1.0,
	"cool_offset": -1.0,
	"base_stop_heat_offset": -2.0,
	"max_stop_heat_offset": -5.0,
	"temperature_tolerance": 0.5,
	"fan_only_difference": 3.0,
	"cool_indoor_threshold": 26.0,
	"cool_outdoor_threshold": 25.0,
	"cool_indoor_min": 20.0,
	"enable_fan_only_mode": True,
	"allow_hvac_mode_changes": True,
	"enable_diagnostic_logging": True,
	"lookahead_hours": 3,
	"preconditioning_enabled": True,
	"max_tolerance": 2.0,
	"min_tolerance": 0.2,
	"max_offset": 2.0,
	"min_offset": -2.0,
}

V2_TOLERANCE = {
	"name": "Bedroom",
	"control_mode": "tolerance",
	"target_sensor": "sensor.bedroom_temperature",
	"heater": "switch.heater",
	"price_sensor": "sensor.nordpool",
	"max_tolerance": 2.0,
	"min_tolerance": 0.2,
	"lookahead_hours": 3,
	"preconditioning_enabled": True,
	"enable_diagnostic_logging": True,
}


def _old_entry(hass: HomeAssistant, version: int, data: dict, options: dict | None = None, **kwargs) -> MockConfigEntry:
	entry = MockConfigEntry(domain=DOMAIN, title=data["name"], data=data, options=options or {}, version=version, **kwargs)
	entry.add_to_hass(hass)
	return entry


def _register_old_climate(hass: HomeAssistant, entry: MockConfigEntry, entity_id: str) -> None:
	"""The 0.1.0/0.2.0 climate entity, so we can prove its entity id survives."""
	er.async_get(hass).async_get_or_create(
		"climate", DOMAIN, f"{entry.entry_id}_climate", suggested_object_id=entity_id.split(".")[1], config_entry=entry
	)


async def test_migrate_v1_entry(sam_house) -> None:
	"""0.1.0 -> setpoint mode; entity id kept; comfort from the restored state."""
	hass = sam_house
	entry = _old_entry(hass, 1, V1_DATA, V1_OPTIONS, unique_id="climate.sam_smartmostat")
	_register_old_climate(hass, entry, "climate.smart_thermostat")
	mock_restore_cache(hass, [State("climate.smart_thermostat", "heat", {"temperature": 21.5, "preset_mode": None})])
	await setup_entry(hass, entry)
	assert entry.state is ConfigEntryState.LOADED
	assert entry.version == 3 and entry.minor_version == 1
	assert entry.unique_id == "climate.sam_smartmostat"
	assert entry.data["control_mode"] == "setpoint"
	assert entry.options["cheap_boost"] == 1.5  # options overrode data
	assert entry.options["expensive_ratio"] == 1.2
	assert entry.options["cheap_ratio"] == 0.8
	assert entry.options["lookahead_hours"] == 2
	assert "precooling_enabled" not in entry.options and "max_increase" not in entry.data
	# Comfort taken from the old entity's target at first start.
	assert entry.options["comfort_temperature"] == 21.5
	state = hass.states.get("climate.smart_thermostat")
	assert state is not None
	assert state.attributes["temperature"] == 21.5
	assert state.attributes["wrapped_climate_entity"] == "climate.sam"


async def test_migrate_v1_without_restored_state_uses_device_target(sam_house) -> None:
	"""No restore state: the wrapped device's target becomes comfort."""
	hass = sam_house
	entry = _old_entry(hass, 1, V1_DATA)
	await setup_entry(hass, entry)
	assert entry.options["comfort_temperature"] == 22  # climate.sam target


async def test_migrate_v2_temperature_entry(sam_house) -> None:
	"""0.2.0 temperature -> remote_sensor; old cooling defaults replaced."""
	hass = sam_house
	entry = _old_entry(hass, 2, V2_TEMPERATURE, {"heat_offset": 1.5})
	_register_old_climate(hass, entry, "climate.living_room")
	mock_restore_cache(hass, [State("climate.living_room", "heat", {"temperature": 20.5})])
	await setup_entry(hass, entry)
	assert entry.state is ConfigEntryState.LOADED
	assert entry.version == 3
	assert entry.data["control_mode"] == "remote_sensor"
	assert entry.data["room_sensors"] == ["sensor.living_room_temperature"]
	assert entry.options["heat_offset"] == 1.5
	assert entry.options["idle_mode"] == "fan_only"
	assert entry.options["cooling"] is False
	assert "cool_compressor_room" not in entry.options
	assert entry.options["comfort_temperature"] == 20.5
	assert hass.states.get("climate.living_room").attributes["remote_temperature"] == 15


async def test_migrate_v2_customised_cooling_kept(sam_house) -> None:
	"""A customised 0.2.0 cooling rule keeps its numbers."""
	hass = sam_house
	entry = _old_entry(hass, 2, V2_TEMPERATURE, {"cool_indoor_threshold": 28.0, "cool_outdoor_threshold": 27.0})
	await setup_entry(hass, entry)
	assert entry.options["cooling"] is True
	assert entry.options["cool_compressor_room"] == 28.0
	assert entry.options["cool_compressor_outdoor"] == 27.0
	assert hass.states.get("climate.living_room").attributes["hvac_modes"] == ["off", "heat", "heat_cool"]


async def test_migrate_v2_tolerance_entry(stockholm) -> None:
	"""0.2.0 tolerance -> switch with the exact threshold mapping."""
	hass = stockholm
	hass.states.async_set("switch.heater", "off")
	set_room(hass, 19, "sensor.bedroom_temperature")
	entry = _old_entry(hass, 2, V2_TOLERANCE, {"min_tolerance": 0.4})
	_register_old_climate(hass, entry, "climate.bedroom")
	await setup_entry(hass, entry)
	assert entry.state is ConfigEntryState.LOADED
	assert entry.data["control_mode"] == "switch"
	assert entry.data["heater"] == "switch.heater"
	assert entry.options["hysteresis"] == pytest.approx(1.2)
	assert entry.options["cheap_boost"] == pytest.approx(0.8)
	assert entry.options["expensive_cut"] == pytest.approx(0.8)
	assert entry.options["comfort_temperature"] == 20  # nothing to restore, no device target
	assert hass.states.get("climate.bedroom") is not None


async def test_future_version_fails(sam_house) -> None:
	"""A newer entry is refused (no downgrade)."""
	hass = sam_house
	entry = _old_entry(hass, 4, {"name": "Future"})
	assert not await hass.config_entries.async_setup(entry.entry_id)
	assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_minor_version_bump(sam_house, make_entry) -> None:
	"""Version 3 entries load as they are."""
	hass = sam_house
	entry = MockConfigEntry(domain=DOMAIN, data={"name": "X", "control_mode": "setpoint", "target_climate": "climate.sam", "price_sensor": "sensor.nordpool"}, version=3, minor_version=0)
	entry.add_to_hass(hass)
	await setup_entry(hass, entry)
	assert entry.minor_version == 1


async def test_translations_load(hass: HomeAssistant) -> None:
	"""en.json is complete JSON and matches strings.json (the 0.2.0 file was truncated)."""
	strings = json.loads((COMPONENT / "strings.json").read_text())
	english = json.loads((COMPONENT / "translations" / "en.json").read_text())
	assert strings == english
	config = await async_get_translations(hass, "en", "config", [DOMAIN])
	assert config[f"component.{DOMAIN}.config.step.user.data.control_mode"] == "Control mode"
	entity = await async_get_translations(hass, "en", "entity", [DOMAIN])
	for reason in REASONS:
		assert f"component.{DOMAIN}.entity.sensor.reason.state.{reason}" in entity, reason
	assert entity[f"component.{DOMAIN}.entity.climate.smartmostat.state_attributes.preset_mode.state.none"] == "Schedule"


async def test_manifest_and_hacs_json() -> None:
	"""Keys HACS and hassfest check."""
	manifest = json.loads((COMPONENT / "manifest.json").read_text())
	assert list(manifest)[:2] == ["domain", "name"]
	assert list(manifest)[2:] == sorted(list(manifest)[2:])
	assert manifest["version"] == "0.3.0"
	assert manifest["integration_type"] == "helper"
	assert manifest["iot_class"] == "calculated"
	assert manifest["config_flow"] is True
	hacs = json.loads((COMPONENT.parent.parent / "hacs.json").read_text())
	assert set(hacs) <= {"name", "render_readme", "homeassistant", "hacs", "content_in_root", "zip_release", "filename", "hide_default_branch", "country", "persistent_directory"}


async def test_diagnostics(sam_house, make_entry) -> None:
	"""Diagnostics include entry, state and the last decision."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
	assert result["entry"]["version"] == 3
	assert result["entry"]["data"]["target_climate"] == "climate.sam"
	assert result["runtime"]["decision"]["reason"] == "cheap_boost"
	assert result["runtime"]["state"]["hvac_mode"] == "heat"
	json.dumps(result)  # serialisable


async def test_remove_entry_cleans_storage(sam_house, make_entry, hass_storage) -> None:
	"""Removing the entry drops its stored runtime state."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	await hass.services.async_call(DOMAIN, "set_override", {"entity_id": "climate.living_room", "temperature": 22}, blocking=True)
	assert await hass.config_entries.async_unload(entry.entry_id)
	assert f"{DOMAIN}.{entry.entry_id}" in hass_storage
	await hass.config_entries.async_remove(entry.entry_id)
	await hass.async_block_till_done()
	assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage


@pytest.mark.parametrize(
	("attrs", "comfort"),
	[
		# 0.1.0 in an expensive hour: temperature = base + adjustment.
		({"temperature": 19.5, "base_temperature": 21.5, "current_adjustment": -2.0}, 21.5),
		# No base_temperature attribute: undo the adjustment.
		({"temperature": 22.5, "current_adjustment": 1.0}, 21.5),
	],
)
async def test_migrate_v1_comfort_is_the_users_setting(sam_house, attrs, comfort) -> None:
	"""The restored comfort is what the user asked for, not the price-shifted target."""
	hass = sam_house
	entry = _old_entry(hass, 1, V1_DATA, unique_id="climate.sam_smartmostat")
	_register_old_climate(hass, entry, "climate.smart_thermostat")
	mock_restore_cache(hass, [State("climate.smart_thermostat", "heat", attrs)])
	await setup_entry(hass, entry)
	assert entry.options["comfort_temperature"] == comfort


async def test_migrate_v1_device_in_cool_is_left_alone(sam_house, climate_calls) -> None:
	"""0.1.0 mirrored the device's modes; a cooling device must not be switched to heat."""
	hass = sam_house
	set_device(hass, "cool", temperature=24)
	entry = _old_entry(hass, 1, V1_DATA, unique_id="climate.sam_smartmostat")
	_register_old_climate(hass, entry, "climate.smart_thermostat")
	mock_restore_cache(
		hass, [State("climate.smart_thermostat", "cool", {"temperature": 24, "base_temperature": 24, "current_adjustment": 0})]
	)
	await setup_entry(hass, entry)
	state = hass.states.get("climate.smart_thermostat")
	assert state.state == "off"
	assert not any(climate_calls.values())
	issue_id = f"restored_mode_unsupported_{entry.entry_id}"
	issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
	assert issue is not None and issue.translation_placeholders["mode"] == "cool"
	# Still hands off after a restart (stored state).
	assert await hass.config_entries.async_reload(entry.entry_id)
	await hass.async_block_till_done()
	assert hass.states.get("climate.smart_thermostat").state == "off"
	assert not any(climate_calls.values())
	# Turning it on takes control; in setpoint mode a cooling device is still left alone.
	await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.smart_thermostat", "hvac_mode": "heat"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("climate.smart_thermostat").state == "heat"
	assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
	assert climate_calls["set_hvac_mode"] == []


async def test_migrate_v2_temperature_entry_in_cool_is_left_alone(sam_house, climate_calls) -> None:
	"""0.2.0 offered cool; with cooling off after migration the device must not be set to heat."""
	hass = sam_house
	set_device(hass, "cool", temperature=24)
	entry = _old_entry(hass, 2, V2_TEMPERATURE)
	_register_old_climate(hass, entry, "climate.living_room")
	mock_restore_cache(hass, [State("climate.living_room", "cool", {"temperature": 21})])
	await setup_entry(hass, entry)
	assert hass.states.get("climate.living_room").state == "off"
	assert hass.states.get("sensor.living_room_headline").state == "Off · Not controlling the device"
	assert not any(climate_calls.values())
