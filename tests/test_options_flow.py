"""Options flow tests (spec 10.2)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from .conftest import set_room, setup_entry

SWITCH_DATA = {
	"name": "Bedroom",
	"control_mode": "switch",
	"heater": "switch.heater",
	"price_sensor": "sensor.nordpool",
	"room_sensors": ["sensor.bedroom_temperature"],
}


async def _open(hass: HomeAssistant, entry, step: str) -> dict:
	result = await hass.config_entries.options.async_init(entry.entry_id)
	assert result["type"] is FlowResultType.MENU
	return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": step})


async def test_menu_depends_on_mode(sam_house, make_entry) -> None:
	"""Cooling only for remote-sensor entries."""
	hass = sam_house
	remote = make_entry()
	await setup_entry(hass, remote)
	result = await hass.config_entries.options.async_init(remote.entry_id)
	assert result["menu_options"] == ["comfort", "price", "actuator", "cooling", "safety", "advanced"]
	hass.states.async_set("switch.heater", "off")
	set_room(hass, 19, "sensor.bedroom_temperature")
	switch = make_entry(data=SWITCH_DATA, options={})
	await hass.config_entries.async_setup(switch.entry_id)
	await hass.async_block_till_done()
	result = await hass.config_entries.options.async_init(switch.entry_id)
	assert "cooling" not in result["menu_options"]


@pytest.mark.parametrize(
	("step", "values", "check"),
	[
		("comfort", {"comfort_temperature": 21, "away_temperature": 12, "override_minutes": 60, "min_target": 8, "max_target": 24}, {"comfort_temperature": 21, "override_minutes": 60, "eco_temperature": None}),
		("price", {"price_optimisation": True, "lookahead_hours": 6, "relative_margin": 0.05, "cheap_ratio": 0.6, "cheap_percentile": 0.4, "expensive_ratio": 1.1, "cheap_boost": 2, "boost_skip_margin": 0.5, "expensive_cut": 1, "prewarm_hours": 3, "prewarm_hours_cold": 5, "cold_outdoor": 8, "hot_day_max": 24, "morning_end": "11:00:00", "shed_price": 4.5, "shed_hysteresis": 0.2, "shed_floor": 19}, {"lookahead_hours": 6, "shed_price": 4.5}),
		("actuator", {"temperature_tolerance": 0.3, "heat_offset": 1.5, "base_stop_heat_offset": -2, "max_stop_heat_offset": -5, "room_max": 26, "fan_only_difference": 3, "idle_mode": "heat_low", "fallback_offset": 2, "allow_hvac_mode_changes": True}, {"fallback_offset": 2, "idle_mode": "heat_low"}),
		("cooling", {"cooling": True, "cool_fan_room": 25, "cool_outdoor_gate": 22, "cool_compressor_room": 27, "cool_compressor_outdoor": 27, "cool_offset": -1}, {"cooling": True}),
		("safety", {"frost_protection": False, "frost_temperature": 6, "stale_minutes": 90, "diagnostic_events": False}, {"frost_protection": False, "stale_minutes": 90}),
		("advanced", {"forecast_hours": 3, "thermal_k": 0.08, "thermal_h": 2.0, "dry_run": True}, {"thermal_k": 0.08, "weather_entity": None, "dry_run": True}),
	],
)
async def test_each_step_saves_and_reloads(sam_house, make_entry, step: str, values: dict, check: dict) -> None:
	"""Every menu step saves its fields and reloads the entry."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	controller = entry.runtime_data
	result = await _open(hass, entry, step)
	assert result["type"] is FlowResultType.FORM and result["step_id"] == step
	result = await hass.config_entries.options.async_configure(result["flow_id"], values)
	await hass.async_block_till_done()
	assert result["type"] is FlowResultType.CREATE_ENTRY
	for key, value in check.items():
		assert entry.options[key] == value, key
	# Options from other steps are kept.
	assert entry.options["comfort_start"] == ("19:00:00" if step != "comfort" else None)
	assert entry.runtime_data is not controller  # reloaded


async def test_actuator_fields_match_mode(sam_house, make_entry) -> None:
	"""Only the fields for the entry's control mode are shown."""
	hass = sam_house
	hass.states.async_set("switch.heater", "off")
	set_room(hass, 19, "sensor.bedroom_temperature")
	entry = make_entry(data=SWITCH_DATA, options={})
	await setup_entry(hass, entry)
	result = await _open(hass, entry, "actuator")
	keys = {str(key) for key in result["data_schema"].schema}
	assert keys == {"hysteresis", "min_cycle_minutes"}
	result = await hass.config_entries.options.async_configure(result["flow_id"], {"hysteresis": 0.8, "min_cycle_minutes": 10})
	await hass.async_block_till_done()
	assert entry.options == {"hysteresis": 0.8, "min_cycle_minutes": 10}


async def test_comfort_validation(sam_house, make_entry) -> None:
	"""Incomplete schedule and min >= max are errors."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	result = await _open(hass, entry, "comfort")
	base = {"comfort_temperature": 20, "away_temperature": 10, "override_minutes": 90, "min_target": 7, "max_target": 25}
	result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, "comfort_end": "23:00:00"})
	assert result["errors"] == {"base": "schedule_incomplete"}
	result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, "min_target": 18, "max_target": 17})
	assert result["errors"] == {"base": "min_above_max"}


async def test_clearing_optional_values(sam_house, make_entry) -> None:
	"""A cleared optional field is stored as unset (feature off)."""
	hass = sam_house
	entry = make_entry(options={"comfort_temperature": 20, "shed_price": 4.0})
	await setup_entry(hass, entry)
	result = await _open(hass, entry, "price")
	values = {
		"price_optimisation": True, "lookahead_hours": 4, "relative_margin": 0, "cheap_ratio": 0.5,
		"cheap_percentile": 0.48, "expensive_ratio": 1, "cheap_boost": 3, "boost_skip_margin": 0.5,
		"expensive_cut": 2, "prewarm_hours": 4, "prewarm_hours_cold": 6, "cold_outdoor": 10,
		"hot_day_max": 25, "morning_end": "12:00:00", "shed_hysteresis": 0.15, "shed_floor": 19,
	}
	result = await hass.config_entries.options.async_configure(result["flow_id"], values)
	await hass.async_block_till_done()
	assert entry.options["shed_price"] is None
	assert entry.runtime_data.settings.price.shed_price is None
