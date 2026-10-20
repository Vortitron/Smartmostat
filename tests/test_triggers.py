"""Triggers, start-up, switch pauses, thermal entities and units (spec 2, 5.5, 8)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.smartmostat.const import DOMAIN

from .conftest import REMOTE_DATA, set_price, set_room, setup_entry


async def _tick(hass: HomeAssistant, freezer, seconds: float) -> None:
	freezer.tick(timedelta(seconds=seconds))
	async_fire_time_changed(hass)
	await hass.async_block_till_done()


async def test_waits_for_start_then_30_seconds(sam_house, make_entry, climate_calls, freezer) -> None:
	"""Rule 8: nothing until HA has started, first run 30 s later."""
	hass = sam_house
	hass.set_state(CoreState.not_running)
	entry = make_entry()
	await setup_entry(hass, entry)
	assert climate_calls["set_temperature"] == []
	assert hass.states.get("sensor.living_room_reason").state == "unknown"
	hass.set_state(CoreState.running)
	hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
	await hass.async_block_till_done()
	await _tick(hass, freezer, 10)
	assert climate_calls["set_temperature"] == []
	await _tick(hass, freezer, 25)
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"
	assert climate_calls["set_temperature"]


async def test_sensor_changes_are_debounced(sam_house, make_entry, freezer) -> None:
	"""Room sensor updates trigger a run 30 s later, not instantly."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	set_room(hass, 25)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"
	await _tick(hass, freezer, 31)
	assert hass.states.get("sensor.living_room_reason").state == "economy"
	assert hass.states.get("sensor.living_room_headline").state == "Cheap power, already warm · Warm enough"


async def test_watchdog_reevaluates(sam_house, make_entry, freezer) -> None:
	"""The 5-minute watchdog catches the schedule moving on."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	evaluated = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.last_evaluated
	await _tick(hass, freezer, 5 * 60 + 1)
	assert hass.config_entries.async_entries(DOMAIN)[0].runtime_data.last_evaluated > evaluated


async def test_switch_toggled_by_hand_pauses(stockholm, make_entry, climate_calls, freezer) -> None:
	"""Section 5.5 for relays: a person flipping the heater pauses Smartmostat."""
	hass = stockholm
	hass.states.async_set("switch.heater", "off")
	set_room(hass, 19, "sensor.bedroom_temperature")
	data = {"name": "Bedroom", "control_mode": "switch", "heater": "switch.heater", "price_sensor": "sensor.nordpool", "room_sensors": ["sensor.bedroom_temperature"]}
	set_price(hass)
	await setup_entry(hass, make_entry(data=data, options={"comfort_temperature": 19}))
	assert hass.states.get("sensor.bedroom_reason").state in ("economy", "comfort", "cheap_boost")
	await _tick(hass, freezer, 120)
	hass.states.async_set("switch.heater", "on")
	await hass.async_block_till_done()
	assert hass.states.get("sensor.bedroom_reason").state == "paused"


async def test_thermal_entities_and_fahrenheit_sensor(sam_house, make_entry) -> None:
	"""k and h from entities; a °F room sensor is converted."""
	hass = sam_house
	hass.states.async_set("input_number.house_heat_loss_k", "0.1")
	hass.states.async_set("input_number.house_heat_rate", "2.5")
	hass.states.async_set("sensor.living_room_temperature", "64.4", {"unit_of_measurement": "°F"})
	options = {
		"comfort_temperature": 20,
		"eco_temperature": 16,
		"comfort_start": "19:00:00",
		"comfort_end": "23:00:00",
		"thermal_k_entity": "input_number.house_heat_loss_k",
		"thermal_h_entity": "input_number.house_heat_rate",
	}
	entry = make_entry(options=options)
	await setup_entry(hass, entry)
	controller = entry.runtime_data
	assert controller.readings.room == 18.0
	assert controller._thermal("input_number.house_heat_loss_k", None, None) == 0.1  # noqa: SLF001
	assert controller._thermal(None, 0.2, None) == 0.2  # noqa: SLF001
	assert controller._thermal("input_number.missing", None, None) is None  # noqa: SLF001


async def test_heat_cool_mode_offered_with_cooling(sam_house, make_entry, climate_calls) -> None:
	"""Cooling adds Heat/Cool; hot inside and out runs the compressor."""
	hass = sam_house
	set_room(hass, 28)
	set_room(hass, 28, "sensor.outdoor_temperature")
	hass.states.async_set("climate.sam", "heat", {**hass.states.get("climate.sam").attributes, "current_temperature": 27})
	await setup_entry(hass, make_entry(data=REMOTE_DATA, options={"comfort_temperature": 20, "cooling": True}))
	climate = hass.states.get("climate.living_room")
	assert climate.state == "heat_cool"
	assert climate.attributes["hvac_modes"] == ["off", "heat", "heat_cool"]
	assert climate_calls["set_hvac_mode"][-1].data["hvac_mode"] == "cool"
	assert climate_calls["set_temperature"][-1].data["temperature"] == 26
