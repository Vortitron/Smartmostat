"""Actuator tests, porting test_sam_hvac_templates.py by name (spec 6, 13.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time, timedelta

import pytest

from custom_components.smartmostat.actuators import (
	ClimateCommand,
	DeviceState,
	Readings,
	RemoteSensorConfig,
	SwitchConfig,
	SwitchState,
	diff_climate,
	remote_sensor_intent,
	round_setpoint,
	setpoint_intent,
	switch_intent,
)
from custom_components.smartmostat.const import PRESET_COMFORT
from custom_components.smartmostat.migration import tolerance_mapping
from custom_components.smartmostat.planner import PlannerConfig, PlannerInputs, plan
from custom_components.smartmostat.price import STATUS_FULL, PriceInfo

from ..helpers import local

# climate.sam: panasonic_cc, 16..30 in 0.5 steps.
SAM_DEVICE = DeviceState(
	hvac_mode="heat",
	target=22,
	current=20,
	hvac_modes=("off", "heat_cool", "cool", "dry", "fan_only", "heat"),
	min_temp=16,
	max_temp=30,
	step=0.5,
	presets=("none", "quiet", "powerful", "heat_8_15"),
	preset="none",
)

# sam.yaml constants.
SAM_CFG = RemoteSensorConfig(
	temperature_tolerance=0.5,
	heat_offset=1,
	base_stop_heat_offset=-2,
	max_stop_heat_offset=-5,
	room_max=27,
	fan_only_difference=3,
	fallback_offset=2,
	cooling=True,
	cool_fan_room=25,
	cool_outdoor_gate=22,
	cool_compressor_room=27,
	cool_compressor_outdoor=27,
	cool_offset=-1,
)


def sam_readings(s: dict) -> Readings:
	"""Same derivation as build_context() in Sam's tests.

	Fan running with both sensors -> min(living, bedroom) (room_aggregate: min);
	otherwise living, else bedroom; neither -> no room reading.
	"""
	living_ok = s.get("living_room_temp_ok", True)
	bedroom_ok = s.get("bedroom_temp_ok", True)
	living = float(s["living"])
	bedroom = float(s.get("bedroom", living))
	usable = [v for v, ok in ((living, living_ok), (bedroom, bedroom_ok)) if ok]
	if not usable:
		room = None
	elif s.get("fan_running") and living_ok and bedroom_ok:
		room = min(living, bedroom)
	else:
		room = living if living_ok else bedroom
	return Readings(
		room=room,
		room_max=max(usable) if usable else None,
		internal=float(s["internal"]),
		outdoor=float(s["outdoor"]),
	)


HEAT_SCENARIOS = [
	("live_now_overheat_guard", dict(living=19.2, bedroom=20.45, outdoor=14, internal=18, control=16, fan_running=True), "fan_only", 16.0),
	("very_cold_full_boost", dict(living=12, bedroom=13, outdoor=2, internal=18, control=20), "heat", 26.0),
	("at_target_nudge_down", dict(living=20, bedroom=20, outdoor=10, internal=21, control=20), "heat", 19.0),
	("mild_coasting_fan_only", dict(living=15, bedroom=15, outdoor=22, internal=18, control=20), "fan_only", 23.0),
	("unit_overreads_keeps_heating", dict(living=15, bedroom=15, outdoor=5, internal=28, control=20), "heat", 30.0),
	("live_short_cycle_fixed", dict(living=16.3, bedroom=18.7, outdoor=15, internal=27, control=23), "heat", 30.0),
	("half_degree_rounding", dict(living=18.3, bedroom=18.3, outdoor=5, internal=22, control=20), "heat", 23.5),
	("room_at_heat_max", dict(living=27.2, bedroom=18, outdoor=5, internal=24, control=28, fan_running=True), "fan_only", 19.0),
	("strong_overheat_guard", dict(living=25, bedroom=24, outdoor=10, internal=22, control=20), "fan_only", 17.0),
	("warm_room_cool_out", dict(living=27, bedroom=26, outdoor=20, internal=24, control=20), "fan_only", 19.0),
	(
		"live_tuya_signed_out_fallback",
		dict(living=0, bedroom=0, living_room_temp_ok=False, bedroom_temp_ok=False, outdoor=13, internal=19, control=23),
		"heat",
		25.0,
	),
	(
		"fallback_internal_overreads",
		dict(living=0, bedroom=0, living_room_temp_ok=False, bedroom_temp_ok=False, outdoor=5, internal=27, control=20),
		"heat",
		22.0,
	),
	(
		"fallback_economy_target",
		dict(living=0, bedroom=0, living_room_temp_ok=False, bedroom_temp_ok=False, outdoor=10, internal=19, control=16),
		"heat",
		18.0,
	),
	(
		"bedroom_down_uses_living",
		dict(living=17, bedroom=0, bedroom_temp_ok=False, outdoor=10, internal=20, control=20, fan_running=True),
		"heat",
		23.0,
	),
]


@pytest.mark.parametrize(("name", "scenario", "mode", "setpoint"), HEAT_SCENARIOS, ids=[s[0] for s in HEAT_SCENARIOS])
def test_sam_heating_scenarios(name: str, scenario: dict, mode: str, setpoint: float) -> None:
	"""Mode and set-point exactly as sam.yaml computes them (heat mode, no cooling)."""
	intent = remote_sensor_intent(scenario["control"], sam_readings(scenario), SAM_DEVICE, SAM_CFG, "heat")
	assert intent.hvac_mode == mode, name
	assert intent.temperature == pytest.approx(setpoint), name
	assert 16 <= intent.temperature <= 30
	assert intent.temperature * 2 == int(intent.temperature * 2)


COOL_SCENARIOS = [
	# (name, scenario, expected mode, expected set-point or None for "not cooling")
	("today_bug_no_cool", dict(living=20.1, outdoor=25, internal=20, control=16), "fan_only", 16.0),
	("very_hot_both", dict(living=28, outdoor=28, internal=27, control=20), "cool", 26.0),
	("hot_in_mild_out", dict(living=28, outdoor=24, internal=26, control=20), "fan_only", 26.0),
	("warm_room_not_27", dict(living=26, outdoor=28, internal=25, control=20), "fan_only", 25.0),
	("winter_prewarm_not_cooling", dict(living=25, outdoor=5, internal=22, control=25), "heat", 20.0),
]


@pytest.mark.parametrize(("name", "scenario", "mode", "setpoint"), COOL_SCENARIOS, ids=[s[0] for s in COOL_SCENARIOS])
def test_sam_cooling_scenarios(name: str, scenario: dict, mode: str, setpoint: float) -> None:
	"""Basic cooling: compressor only when 27 inside and 27 outside."""
	intent = remote_sensor_intent(scenario["control"], sam_readings(scenario), SAM_DEVICE, SAM_CFG, "heat_cool")
	assert intent.hvac_mode == mode, name
	assert intent.temperature == pytest.approx(setpoint), name
	if name == "today_bug_no_cool":
		# 20 °C room, 25 °C outside: must not cool (it idles the heating instead).
		assert intent.label == "Warm enough"
	if name == "winter_prewarm_not_cooling":
		assert intent.label == "Holding"


def test_cooling_never_in_heat_mode_or_when_disabled() -> None:
	"""Cooling needs the option and the heat_cool mode."""
	hot = sam_readings(dict(living=28, outdoor=28, internal=27))
	assert remote_sensor_intent(20, hot, SAM_DEVICE, SAM_CFG, "heat").hvac_mode == "fan_only"
	off_cfg = replace(SAM_CFG, cooling=False)
	assert remote_sensor_intent(20, hot, SAM_DEVICE, off_cfg, "heat_cool").hvac_mode == "fan_only"
	capped = remote_sensor_intent(20, sam_readings(dict(living=30, outdoor=32, internal=30)), SAM_DEVICE, SAM_CFG, "heat_cool")
	assert capped.temperature == 27  # set-point cap


def test_idle_mode_without_fan_only() -> None:
	"""Auto idle uses heat at the device minimum when there is no fan_only."""
	device = replace(SAM_DEVICE, hvac_modes=("off", "heat"))
	readings = sam_readings(dict(living=25, outdoor=10, internal=22))
	intent = remote_sensor_intent(20, readings, device, SAM_CFG, "heat")
	assert (intent.hvac_mode, intent.temperature, intent.details["idle"]) == ("heat", 16, "heat_low")
	# fan_only requested but not supported falls back too.
	fan_cfg = replace(SAM_CFG, idle_mode="fan_only")
	assert remote_sensor_intent(20, readings, device, fan_cfg, "heat").hvac_mode == "heat"


def test_idle_mode_off_only_when_far_over_target() -> None:
	"""idle_mode off switches off only past fan_only_difference or at room max."""
	cfg = replace(SAM_CFG, idle_mode="off")
	slightly_warm = sam_readings(dict(living=21, outdoor=10, internal=22))
	assert remote_sensor_intent(20, slightly_warm, SAM_DEVICE, cfg, "heat").hvac_mode == "heat"
	very_warm = sam_readings(dict(living=23.5, outdoor=10, internal=22))
	intent = remote_sensor_intent(20, very_warm, SAM_DEVICE, cfg, "heat")
	assert (intent.hvac_mode, intent.temperature) == ("off", None)
	at_max = sam_readings(dict(living=27.5, outdoor=10, internal=26))
	assert remote_sensor_intent(28, at_max, SAM_DEVICE, cfg, "heat").hvac_mode == "off"


def test_allow_hvac_mode_changes_off() -> None:
	"""Only set-points are sent; idle becomes the device minimum."""
	cfg = replace(SAM_CFG, allow_hvac_mode_changes=False)
	cold = remote_sensor_intent(20, sam_readings(dict(living=12, outdoor=2, internal=18)), SAM_DEVICE, cfg, "heat")
	assert (cold.hvac_mode, cold.temperature) == (None, 26)
	warm = remote_sensor_intent(20, sam_readings(dict(living=25, outdoor=10, internal=22)), SAM_DEVICE, cfg, "heat")
	assert (warm.hvac_mode, warm.temperature) == (None, 16)
	command = diff_climate(warm, replace(SAM_DEVICE, hvac_mode="fan_only", target=22))
	assert command is not None and command.hvac_mode is None and command.temperature == 16


def test_clamp_and_step_rounding() -> None:
	"""16..30, 0.5 steps; other steps work too."""
	assert round_setpoint(12, SAM_DEVICE) == 16
	assert round_setpoint(33, SAM_DEVICE) == 30
	assert round_setpoint(23.7, SAM_DEVICE) == 23.5
	assert round_setpoint(23.8, SAM_DEVICE) == 24
	whole = replace(SAM_DEVICE, step=1.0)
	assert round_setpoint(21.4, whole) == 21
	assert round_setpoint(21.6, whole) == 22


def test_no_change_no_command() -> None:
	"""Never send what the device already reports (within half a step)."""
	intent = remote_sensor_intent(20, sam_readings(dict(living=20, outdoor=10, internal=21)), SAM_DEVICE, SAM_CFG, "heat")
	assert intent.temperature == 19
	same = replace(SAM_DEVICE, hvac_mode="heat", target=19.0)
	assert diff_climate(intent, same) is None
	close = replace(SAM_DEVICE, hvac_mode="heat", target=19.2)
	assert diff_climate(intent, close) is None
	command = diff_climate(intent, replace(SAM_DEVICE, hvac_mode="fan_only", target=19))
	assert command.hvac_mode == "heat" and command.temperature is None
	command = diff_climate(intent, replace(SAM_DEVICE, hvac_mode="heat", target=22))
	assert command.hvac_mode is None and command.temperature == 19 and command.target_mode == "heat"


def test_device_preset_handling() -> None:
	"""Away device preset (heat_8_15) set while away and cleared afterwards."""
	intent = setpoint_intent(10, replace(SAM_DEVICE, min_temp=8))
	command = diff_climate(intent, replace(SAM_DEVICE, min_temp=8, target=10, preset="none"), "heat_8_15")
	assert command.preset == "heat_8_15"
	assert diff_climate(intent, replace(SAM_DEVICE, min_temp=8, target=10, preset="heat_8_15"), "heat_8_15") is None
	assert diff_climate(intent, replace(SAM_DEVICE, target=16), "not_a_preset") is not None


def test_setpoint_actuator() -> None:
	"""0.1.0 behaviour: the control target as the set-point, in heat."""
	heating = replace(SAM_DEVICE, hvac_mode="heat", target=20)
	intent = setpoint_intent(21.3, heating)
	assert (intent.hvac_mode, intent.temperature) == (None, 21.5)
	assert diff_climate(intent, heating) == ClimateCommand(None, 21.5, None, "heat")
	off = replace(SAM_DEVICE, hvac_mode="off", target=20)
	intent = setpoint_intent(21.3, off)
	assert (intent.hvac_mode, intent.temperature) == ("heat", 21.5)
	command = diff_climate(intent, off)
	assert command.hvac_mode == "heat" and command.temperature == 21.5
	assert setpoint_intent(21, off, allow_hvac_mode_changes=False).hvac_mode is None


@pytest.mark.parametrize("mode", ["cool", "heat_cool", "auto", "dry", "fan_only"])
def test_setpoint_actuator_leaves_other_modes_alone(mode: str) -> None:
	"""Spec 6.2: heat only from off. A device a person put in cooling stays cooling."""
	device = replace(SAM_DEVICE, hvac_mode=mode, target=24, hvac_modes=("off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"))
	intent = setpoint_intent(22, device)
	assert intent.hvac_mode is None and intent.temperature is None
	assert diff_climate(intent, device) is None


# --- switch actuator -----------------------------------------------------------

NOW = local(date(2026, 10, 20), 12)
LONG_AGO = NOW - timedelta(hours=1)
SW = SwitchConfig(hysteresis=0.5, min_cycle_minutes=5)


def test_switch_hysteresis() -> None:
	"""On at D - h, off at D + h, unchanged in between."""
	off = SwitchState(heater_on=False, heater_changed=LONG_AGO)
	on = SwitchState(heater_on=True, heater_changed=LONG_AGO)
	assert switch_intent(20, 19.5, "heat", off, SW, NOW)[0].heater_on is True
	assert switch_intent(20, 19.6, "heat", off, SW, NOW)[0] is None
	assert switch_intent(20, 20.4, "heat", on, SW, NOW)[0] is None
	command, label = switch_intent(20, 20.5, "heat", on, SW, NOW)
	assert command.heater_on is False and label == "Heater off"


def test_switch_min_cycle() -> None:
	"""Relay protection: no change within min_cycle_minutes."""
	recent = SwitchState(heater_on=False, heater_changed=NOW - timedelta(minutes=2))
	command, label = switch_intent(20, 18, "heat", recent, SW, NOW)
	assert command is None and label.endswith("(min cycle)")
	later = SwitchState(heater_on=False, heater_changed=NOW - timedelta(minutes=5))
	assert switch_intent(20, 18, "heat", later, SW, NOW)[0].heater_on is True
	# Turning off for "off" mode is never delayed.
	running = SwitchState(heater_on=True, heater_changed=NOW - timedelta(minutes=1))
	assert switch_intent(20, 18, "off", running, SW, NOW)[0].heater_on is False


def test_switch_cooler() -> None:
	"""Cooler mirrors the heater; heater forced off in cool mode."""
	state = SwitchState(heater_on=True, cooler_on=False, heater_changed=LONG_AGO, cooler_changed=LONG_AGO)
	command, label = switch_intent(22, 23, "cool", state, SW, NOW)
	assert command.cooler_on is True and command.heater_on is False and label == "Cooler on"
	cooling = SwitchState(cooler_on=True, cooler_changed=LONG_AGO)
	assert switch_intent(22, 21.5, "cool", cooling, SW, NOW)[0].cooler_on is False
	# A mirrored cooling target is honoured.
	assert switch_intent(22, 21.0, "cool", SwitchState(cooler_on=False, cooler_changed=LONG_AGO), SW, NOW, cool_control=20)[0].cooler_on is True


def test_switch_missing_reading_keeps_state() -> None:
	"""No reading: the switch keeps its last state (safety rule 2 takes over later)."""
	on = SwitchState(heater_on=True, heater_changed=LONG_AGO)
	command, label = switch_intent(20, None, "heat", on, SW, NOW)
	assert command is None and label == "Heater on (no reading)"


@pytest.mark.parametrize(("a", "b"), [(0.2, 2.0), (0.5, 1.5), (0.1, 0.9), (1.0, 1.0)])
def test_tolerance_equivalence_with_0_2_0(a: float, b: float) -> None:
	"""Migrated thresholds equal 0.2.0's at price position 0 and 1.

	0.2.0: cheapest -> on at T - a, off at T + b; dearest -> on at T - b, off at T + a.
	"""
	target = 21.0
	mapping = tolerance_mapping(a, b)
	cfg = PlannerConfig(
		comfort_temperature=target,
		cheap_boost=mapping["cheap_boost"],
		expensive_cut=mapping["expensive_cut"],
		boost_skip_margin=-1,
		min_target=5,
		max_target=30,
	)
	hyst = mapping["hysteresis"]
	for price, on_at, off_at in (
		(PriceInfo(status=STATUS_FULL, price_now=0.1, cheap_now=True), target - a, target + b),
		(PriceInfo(status=STATUS_FULL, price_now=9.0, expensive_now=True), target - b, target + a),
	):
		for room in (on_at, (on_at + off_at) / 2, off_at):
			control = plan(PlannerInputs(local(date(2026, 10, 20), 12), price, PRESET_COMFORT, room=room), cfg).control_target
			assert control - hyst == pytest.approx(on_at)
			assert control + hyst == pytest.approx(off_at)
		state_off = SwitchState(heater_on=False, heater_changed=LONG_AGO)
		state_on = SwitchState(heater_on=True, heater_changed=LONG_AGO)
		control = plan(PlannerInputs(local(date(2026, 10, 20), 12), price, PRESET_COMFORT, room=on_at), cfg).control_target
		assert switch_intent(control, on_at, "heat", state_off, SwitchConfig(hyst, 0), NOW)[0].heater_on is True
		assert switch_intent(control, on_at + 0.01, "heat", state_off, SwitchConfig(hyst, 0), NOW)[0] is None or a == b
		control = plan(PlannerInputs(local(date(2026, 10, 20), 12), price, PRESET_COMFORT, room=off_at), cfg).control_target
		assert switch_intent(control, off_at, "heat", state_on, SwitchConfig(hyst, 0), NOW)[0].heater_on is False


def test_morning_end_type() -> None:
	"""PlannerConfig defaults stay sane."""
	assert PlannerConfig().morning_end == time(12)
