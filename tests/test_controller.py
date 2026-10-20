"""End-to-end tests with a fake heat pump and sensors (spec 13.2)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.smartmostat.const import DOMAIN, EVENT_DECISION

from .conftest import DEAR_MORNING, REMOTE_DATA, set_device, set_price, set_room, setup_entry


def last(calls) -> dict:
	"""Data of the last call."""
	return dict(calls[-1].data)


async def advance(hass: HomeAssistant, freezer, seconds: float) -> None:
	"""Move the clock and fire timers."""
	freezer.tick(timedelta(seconds=seconds))
	async_fire_time_changed(hass)
	await hass.async_block_till_done()


async def evaluate(hass: HomeAssistant) -> dict:
	"""Call smartmostat.evaluate and return its response."""
	response = await hass.services.async_call(
		DOMAIN, "evaluate", {"entity_id": "climate.living_room"}, blocking=True, return_response=True
	)
	return response["climate.living_room"]


async def test_entities_and_unique_ids(sam_house, make_entry) -> None:
	"""One climate, six sensors and a switch, unique ids kept from 0.1.0/0.2.0."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	registry = er.async_get(hass)
	expected = {
		"climate.living_room": f"{entry.entry_id}_climate",
		"sensor.living_room_control_target": f"{entry.entry_id}_control_target",
		"sensor.living_room_headline": f"{entry.entry_id}_headline",
		"sensor.living_room_reason": f"{entry.entry_id}_reason",
		"sensor.living_room_price_level": f"{entry.entry_id}_price_level",
		"sensor.living_room_price_position": f"{entry.entry_id}_price_position",
		"sensor.living_room_override_until": f"{entry.entry_id}_override_until",
		"switch.living_room_price_optimisation": f"{entry.entry_id}_price_optimisation",
	}
	for entity_id, unique_id in expected.items():
		assert registry.async_get(entity_id).unique_id == unique_id, entity_id
	climate = hass.states.get("climate.living_room")
	assert climate.state == "heat"
	assert climate.attributes["preset_mode"] == "none"
	assert climate.attributes["temperature"] == 16  # eco, outside the comfort period
	assert climate.attributes["control_target"] == 19  # cheap boost
	assert climate.attributes["wrapped_climate_entity"] == "climate.sam"
	assert climate.attributes["control_mode"] == "remote_sensor"
	assert climate.attributes["price_level"] == "cheap"
	assert climate.attributes["current_temperature"] == 15


async def test_price_change_moves_control_target_and_device(sam_house, make_entry, climate_calls, freezer) -> None:
	"""Cheap -> boost and dynamic set-point; expensive -> cut; only on change."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	assert hass.states.get("sensor.living_room_control_target").state == "19.0"
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"
	assert hass.states.get("sensor.living_room_headline").state == "Cheap power boost · Heating"
	# R 15, D 19: internal 20 + max(1, 4) = 24, mode already heat.
	assert last(climate_calls["set_temperature"]) == {"entity_id": "climate.sam", "temperature": 24, "hvac_mode": "heat"}
	assert climate_calls["set_hvac_mode"] == []

	await advance(hass, freezer, 61)
	set_device(hass, temperature=24)
	set_price(hass, DEAR_MORNING)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "expensive"
	assert hass.states.get("sensor.living_room_control_target").state == "16.0"
	# D 16, R 15: 15 < 15.5 so still heating gently: 20 + 1 = 21.
	assert last(climate_calls["set_temperature"])["temperature"] == 21
	count = len(climate_calls["set_temperature"])

	# Same inputs again: nothing sent.
	set_device(hass, temperature=21)
	await advance(hass, freezer, 61)
	await evaluate(hass)
	assert len(climate_calls["set_temperature"]) == count


async def test_rate_limit_holds_back_a_second_command(sam_house, make_entry, climate_calls) -> None:
	"""Automatic changes within 60 s wait for the next run."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	count = len(climate_calls["set_temperature"])
	set_room(hass, 18.4)
	set_price(hass, DEAR_MORNING)
	await hass.async_block_till_done()
	assert len(climate_calls["set_temperature"]) == count


async def test_device_side_change_pauses_and_resume(sam_house, make_entry, climate_calls, freezer) -> None:
	"""A person using the remote pauses Smartmostat for override_minutes."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	set_device(hass, temperature=24)  # our own command arriving
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"
	await advance(hass, freezer, 120)
	sent = len(climate_calls["set_temperature"])
	set_device(hass, temperature=27)  # someone with the remote
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "paused"
	assert hass.states.get("sensor.living_room_headline").state == "Paused: changed on device (90m) · Paused"
	assert hass.states.get("sensor.living_room_override_until").state != "unknown"
	await advance(hass, freezer, 120)
	assert len(climate_calls["set_temperature"]) == sent
	await hass.services.async_call(DOMAIN, "resume", {"entity_id": "climate.living_room"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"
	assert last(climate_calls["set_temperature"])["temperature"] == 24


async def test_pause_expires(sam_house, make_entry, freezer) -> None:
	"""After override_minutes the pause ends by itself."""
	hass = sam_house
	await setup_entry(hass, make_entry(options={"override_minutes": 30}))
	set_device(hass, temperature=24)
	await advance(hass, freezer, 60)
	set_device(hass, temperature=26)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "paused"
	await advance(hass, freezer, 31 * 60)
	assert hass.states.get("sensor.living_room_reason").state != "paused"


async def test_device_switched_off_by_hand_is_followed(sam_house, make_entry, climate_calls, freezer) -> None:
	"""Device off -> Smartmostat follows to off; turning it on resumes."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	set_device(hass, temperature=24)
	await advance(hass, freezer, 60)
	set_device(hass, "off", temperature=24)
	await hass.async_block_till_done()
	assert hass.states.get("climate.living_room").state == "off"
	assert hass.states.get("sensor.living_room_reason").state == "off"
	await hass.services.async_call("climate", "turn_on", {"entity_id": "climate.living_room"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("climate.living_room").state == "heat"
	assert last(climate_calls["set_hvac_mode"]) == {"entity_id": "climate.sam", "hvac_mode": "heat"}


async def test_frost_heats_even_when_off(sam_house, make_entry, climate_calls) -> None:
	"""Frost guard: heat although Smartmostat is off, with a repairs issue."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": "climate.living_room", "hvac_mode": "off"}, blocking=True)
	await hass.async_block_till_done()
	assert last(climate_calls["set_hvac_mode"])["hvac_mode"] == "off"
	set_device(hass, "off")
	set_room(hass, 3.5)
	await evaluate(hass)
	assert hass.states.get("sensor.living_room_reason").state == "frost"
	assert last(climate_calls["set_hvac_mode"])["hvac_mode"] == "heat"
	# max(control 19 (cheap boost), frost 5 + 3)
	assert last(climate_calls["set_temperature"])["temperature"] == 19
	assert ir.async_get(hass).async_get_issue(DOMAIN, f"frost_while_off_{entry.entry_id}") is not None
	set_room(hass, 9)
	await evaluate(hass)
	assert hass.states.get("sensor.living_room_reason").state == "off"
	assert ir.async_get(hass).async_get_issue(DOMAIN, f"frost_while_off_{entry.entry_id}") is None


async def test_override_services_and_restart_restores(sam_house, make_entry) -> None:
	"""set_override / clear_override, and an override survives a restart."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	await hass.services.async_call(
		DOMAIN, "set_override", {"entity_id": "climate.living_room", "temperature": 23, "minutes": 30}, blocking=True
	)
	await hass.async_block_till_done()
	climate = hass.states.get("climate.living_room")
	assert climate.attributes["temperature"] == 23
	assert climate.attributes["control_target"] == 23
	assert hass.states.get("sensor.living_room_reason").state == "override"
	assert hass.states.get("sensor.living_room_headline").state.startswith("You set 23°C (30m)")
	until = hass.states.get("sensor.living_room_override_until").state
	assert until != "unknown"

	assert await hass.config_entries.async_reload(entry.entry_id)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "override"
	assert hass.states.get("sensor.living_room_override_until").state == until

	await hass.services.async_call(DOMAIN, "clear_override", {"entity_id": "climate.living_room"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"


async def test_set_temperature_with_schedule_is_an_override(sam_house, make_entry) -> None:
	"""climate.set_temperature: Sam's 90-minute lock; a preset clears it."""
	hass = sam_house
	await setup_entry(hass, make_entry())
	await hass.services.async_call("climate", "set_temperature", {"entity_id": "climate.living_room", "temperature": 22}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "override"
	assert hass.states.get("sensor.living_room_headline").state.startswith("You set 22°C (90m)")
	await hass.services.async_call("climate", "set_preset_mode", {"entity_id": "climate.living_room", "preset_mode": "away"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "away"
	assert hass.states.get("climate.living_room").attributes["temperature"] == 10


async def test_set_temperature_without_schedule_changes_comfort(sam_house, make_entry) -> None:
	"""No schedule: like any thermostat, without a reload, and price logic stays."""
	hass = sam_house
	entry = make_entry(options={"comfort_temperature": 20})
	await setup_entry(hass, entry)
	controller = entry.runtime_data
	await hass.services.async_call("climate", "set_temperature", {"entity_id": "climate.living_room", "temperature": 21}, blocking=True)
	await hass.async_block_till_done()
	assert entry.options["comfort_temperature"] == 21
	assert entry.runtime_data is controller  # no reload
	climate = hass.states.get("climate.living_room")
	assert climate.attributes["temperature"] == 21
	assert climate.attributes["control_target"] == 24  # cheap boost on top
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"


async def test_price_switch(sam_house, make_entry) -> None:
	"""Price optimisation switch: plain thermostat at base, state in options."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	controller = entry.runtime_data
	await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.living_room_price_optimisation"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("switch.living_room_price_optimisation").state == "off"
	assert hass.states.get("sensor.living_room_reason").state == "price_off"
	assert hass.states.get("sensor.living_room_control_target").state == "16.0"
	assert entry.options["price_optimisation"] is False
	assert entry.runtime_data is controller
	await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.living_room_price_optimisation"}, blocking=True)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"


async def test_unavailable_price_sensor_falls_back(sam_house, make_entry) -> None:
	"""No price data: plain thermostat at the base target."""
	hass = sam_house
	hass.states.async_set("sensor.nordpool", "unavailable", {})
	await setup_entry(hass, make_entry())
	assert hass.states.get("sensor.living_room_reason").state == "no_price"
	assert hass.states.get("sensor.living_room_price_level").state == "unknown"
	assert hass.states.get("sensor.living_room_headline").state == "No price data · Heating"
	set_price(hass)
	await hass.async_block_till_done()
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"


async def test_unavailable_room_sensor_uses_device_sensor(sam_house, make_entry, climate_calls) -> None:
	"""Room sensor gone: the device heats as its own thermostat."""
	hass = sam_house
	set_room(hass, "unavailable")
	await setup_entry(hass, make_entry(options={"fallback_offset": 2, "comfort_temperature": 20, "eco_temperature": 16, "comfort_start": "19:00:00", "comfort_end": "23:00:00"}))
	assert hass.states.get("sensor.living_room_headline").state.endswith("· Device sensor only")
	# No room reading means no boost: control 16, set-point 16 + 2.
	assert last(climate_calls["set_temperature"])["temperature"] == 18


async def test_stale_room_sensor(sam_house, make_entry, freezer) -> None:
	"""A sensor that stops reporting counts as unavailable after stale_minutes."""
	hass = sam_house
	await setup_entry(hass, make_entry(options={"stale_minutes": 60}))
	assert hass.states.get("climate.living_room").attributes["remote_temperature"] == 15
	set_price(hass)  # keep the price fresh, the room sensor goes quiet
	freezer.tick(timedelta(minutes=61))
	set_device(hass)
	await evaluate(hass)
	assert hass.states.get("climate.living_room").attributes["remote_temperature"] is None


async def test_events_and_sensor_updates_only_on_change(sam_house, make_entry) -> None:
	"""smartmostat_decision fires on change only; diagnostics sensors do not churn."""
	hass = sam_house
	events = []
	hass.bus.async_listen(EVENT_DECISION, events.append)
	await setup_entry(hass, make_entry())
	assert len(events) == 1
	assert events[0].data["reason"] == "cheap_boost"
	changed = hass.states.get("sensor.living_room_reason").last_changed
	response = await evaluate(hass)
	await evaluate(hass)
	await hass.async_block_till_done()
	assert len(events) == 1
	assert hass.states.get("sensor.living_room_reason").last_changed == changed
	assert response["reason"] == "cheap_boost"
	assert response["control_target"] == 19
	assert response["intent"] == {"hvac_mode": "heat", "temperature": 24}
	assert response["price"]["cheap_now"] is True
	assert "status" in response and "D=19" in response["status"]
	set_room(hass, 25)
	response = await evaluate(hass)
	assert response["reason"] == "economy", response
	await hass.async_block_till_done()
	assert len(events) == 2


async def test_dry_run_sends_nothing(sam_house, make_entry, climate_calls) -> None:
	"""Shadow mode logs commands without sending them."""
	hass = sam_house
	await setup_entry(hass, make_entry(options={"dry_run": True}))
	assert climate_calls["set_temperature"] == []
	assert hass.states.get("sensor.living_room_reason").state == "cheap_boost"


async def test_away_sets_and_clears_device_preset(sam_house, make_entry, climate_calls, freezer) -> None:
	"""away_device_preset (Sam's heat_8_15) while away, cleared afterwards."""
	hass = sam_house
	await setup_entry(hass, make_entry(options={"away_device_preset": "heat_8_15", "eco_temperature": 16, "comfort_start": "19:00:00", "comfort_end": "23:00:00"}))
	await hass.services.async_call("climate", "set_preset_mode", {"entity_id": "climate.living_room", "preset_mode": "away"}, blocking=True)
	await hass.async_block_till_done()
	assert last(climate_calls["set_preset_mode"]) == {"entity_id": "climate.sam", "preset_mode": "heat_8_15"}
	set_device(hass, preset_mode="heat_8_15", min_temp=8)
	await advance(hass, freezer, 61)
	await hass.services.async_call("climate", "set_preset_mode", {"entity_id": "climate.living_room", "preset_mode": "none"}, blocking=True)
	await hass.async_block_till_done()
	assert last(climate_calls["set_preset_mode"]) == {"entity_id": "climate.sam", "preset_mode": "none"}


async def test_super_expensive_shed(sam_house, make_entry, climate_calls) -> None:
	"""Shed turns the device off only with a warm room reading."""
	hass = sam_house
	set_room(hass, 21)
	set_price(hass, DEAR_MORNING)
	await setup_entry(hass, make_entry(options={"shed_price": 2.5}))
	assert hass.states.get("sensor.living_room_reason").state == "shed"
	assert hass.states.get("sensor.living_room_price_level").state == "super_expensive"
	assert last(climate_calls["set_hvac_mode"])["hvac_mode"] == "off"


async def test_weather_forecast_hot_day(sam_house, make_entry) -> None:
	"""Weather forecast feeds the hot-day morning skip."""
	hass = sam_house
	set_room(hass, 17)
	set_room(hass, 15, "sensor.outdoor_temperature")
	hass.states.async_set("weather.home", "sunny", {"temperature_unit": "°C"})
	forecast = {
		"weather.home": {
			"forecast": [
				{"datetime": "2026-10-20T08:00:00+00:00", "temperature": 18},
				{"datetime": "2026-10-20T09:00:00+00:00", "temperature": 22},
				{"datetime": "2026-10-20T12:00:00+00:00", "temperature": 29},
			]
		}
	}
	daily = {"weather.home": {"forecast": [{"datetime": "2026-10-20T10:00:00+00:00", "temperature": 29}]}}

	async def get_forecasts(call: ServiceCall) -> dict:
		return daily if call.data["type"] == "daily" else forecast

	hass.services.async_register("weather", "get_forecasts", get_forecasts, supports_response=SupportsResponse.ONLY)
	await setup_entry(hass, make_entry(options={**REMOTE_OPTIONS_WITH_WEATHER}))
	assert hass.states.get("sensor.living_room_reason").state == "hot_day"
	assert hass.states.get("sensor.living_room_headline").state.startswith("Hot day, no morning heat")


REMOTE_OPTIONS_WITH_WEATHER = {
	"comfort_temperature": 20.0,
	"eco_temperature": 16.0,
	"comfort_start": "19:00:00",
	"comfort_end": "23:00:00",
	"weather_entity": "weather.home",
}


async def test_setpoint_mode(stockholm, make_entry, climate_calls) -> None:
	"""0.1.0 behaviour: the device gets the control target."""
	hass = stockholm
	set_device(hass)
	set_price(hass)
	data = {"name": "Hall", "control_mode": "setpoint", "target_climate": "climate.sam", "price_sensor": "sensor.nordpool", "room_sensors": []}
	await setup_entry(hass, make_entry(data=data, options={"comfort_temperature": 20}))
	# No room reading: no boost (it needs evidence); cheap hour, comfort 20.
	assert hass.states.get("sensor.hall_control_target").state == "20.0"
	assert last(climate_calls["set_temperature"]) == {"entity_id": "climate.sam", "temperature": 22 - 2, "hvac_mode": "heat"}
	assert hass.states.get("climate.hall").attributes["current_temperature"] == 20  # device reading


async def test_switch_mode(stockholm, make_entry, climate_calls, freezer) -> None:
	"""0.2.0 tolerance mode: heater relay with hysteresis around the control target."""
	hass = stockholm
	turn_on = climate_calls["switch.turn_on"]
	turn_off = climate_calls["switch.turn_off"]
	hass.states.async_set("switch.heater", "off")
	set_room(hass, 18, "sensor.bedroom_temperature")
	set_price(hass, DEAR_MORNING)
	data = {
		"name": "Bedroom",
		"control_mode": "switch",
		"heater": "switch.heater",
		"price_sensor": "sensor.nordpool",
		"room_sensors": ["sensor.bedroom_temperature"],
	}
	await setup_entry(hass, make_entry(data=data, options={"comfort_temperature": 20}))
	# Expensive: control 18, room 18 is inside the band, so nothing happens.
	assert hass.states.get("sensor.bedroom_control_target").state == "18.0"
	assert turn_on == [] and turn_off == []
	freezer.tick(timedelta(minutes=6))  # past the minimum cycle time
	set_room(hass, 17.4, "sensor.bedroom_temperature")
	await hass.services.async_call(DOMAIN, "evaluate", {"entity_id": "climate.bedroom"}, blocking=True, return_response=True)
	assert dict(turn_on[-1].data) == {"entity_id": "switch.heater"}
	assert hass.states.get("climate.bedroom").attributes["hvac_modes"] == ["off", "heat"]


async def test_unload_leaves_device_alone(sam_house, make_entry, climate_calls) -> None:
	"""Unloading never switches the device off."""
	hass = sam_house
	entry = make_entry()
	await setup_entry(hass, entry)
	before = {name: len(calls) for name, calls in climate_calls.items()}
	assert await hass.config_entries.async_unload(entry.entry_id)
	await hass.async_block_till_done()
	assert {name: len(calls) for name, calls in climate_calls.items()} == before


async def test_two_entries_independent(sam_house, make_entry) -> None:
	"""Entries keep their own state."""
	hass = sam_house
	set_room(hass, 19, "sensor.bedroom_temperature")
	hass.states.async_set("climate.other", "heat", {"hvac_modes": ["off", "heat"], "temperature": 20, "current_temperature": 19})
	first = make_entry()
	second = make_entry(data={**REMOTE_DATA, "name": "Bedroom", "target_climate": "climate.other", "room_sensors": ["sensor.bedroom_temperature"]})
	await setup_entry(hass, first)  # sets up every entry of the domain
	assert second.state.value == "loaded"
	assert hass.states.get("climate.living_room") is not None
	assert hass.states.get("climate.bedroom") is not None
	assert first.runtime_data is not second.runtime_data
