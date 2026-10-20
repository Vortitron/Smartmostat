"""Safety rules through the engine (spec 8, 13.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from custom_components.smartmostat.actuators import DeviceState, Readings, RemoteSensorConfig, SwitchConfig, SwitchState
from custom_components.smartmostat.const import (
	MODE_REMOTE_SENSOR,
	MODE_SETPOINT,
	MODE_SWITCH,
	PRESET_AWAY,
	REASON_COMFORT,
	REASON_FALLBACK,
	REASON_FROST,
	REASON_OFF,
	REASON_PAUSED,
	REASON_SHED,
)
from custom_components.smartmostat.engine import Decision, EngineConfig, EngineInputs, decide, status_line
from custom_components.smartmostat.planner import Plan
from custom_components.smartmostat.price import STATUS_FULL, PriceInfo
from custom_components.smartmostat.safety import RateLimiter, SafetyConfig, duty_cycle_on, frost_active, is_stale

from ..helpers import local

NOW = local(date(2026, 1, 15), 12)
DEVICE = DeviceState(hvac_mode="heat", target=20, current=18, hvac_modes=("off", "heat", "fan_only"), min_temp=16, max_temp=30)
PLAN = Plan(base_target=20, control_target=20, reason=REASON_COMFORT, headline_reason="Comfort 20°C")
PRICE = PriceInfo(status=STATUS_FULL, price_now=1.0)
SUPER = PriceInfo(status=STATUS_FULL, price_now=9.0, super_expensive=True)
SAFETY = SafetyConfig(frost_protection=True, frost_temperature=5, stale_minutes=180, shed_floor=19)
CLIMATE_MODES = [MODE_REMOTE_SENSOR, MODE_SETPOINT]
SWITCH_STATE = SwitchState(heater_on=False, heater_changed=NOW - timedelta(hours=1))


def cfg(mode: str = MODE_REMOTE_SENSOR, **safety) -> EngineConfig:
	return EngineConfig(control_mode=mode, remote=RemoteSensorConfig(), switch=SwitchConfig(), safety=replace(SAFETY, **safety))


def inputs(mode: str = MODE_REMOTE_SENSOR, **kwargs) -> EngineInputs:
	values = dict(
		now=NOW,
		plan=PLAN,
		price=PRICE,
		readings=Readings(room=19.5, room_max=19.5, internal=19, outdoor=-5),
		device=DEVICE if mode != MODE_SWITCH else None,
		switch_state=SWITCH_STATE if mode == MODE_SWITCH else None,
	)
	values.update(kwargs)
	return EngineInputs(**values)


FROST_READINGS = Readings(room=4.0, room_max=4.0, internal=6, outdoor=-10)


@pytest.mark.parametrize("mode", [MODE_REMOTE_SENSOR, MODE_SETPOINT, MODE_SWITCH])
@pytest.mark.parametrize(
	"situation",
	[
		{"hvac_mode": "off"},
		{"override_active": True},
		{"paused_until": NOW + timedelta(minutes=30)},
		{"price": SUPER},
		{"preset": PRESET_AWAY},
	],
	ids=["off", "override", "paused", "shed", "away"],
)
def test_frost_guard_beats_everything(mode: str, situation: dict) -> None:
	"""Frost guard heats in every mode, including off, override, pause and shed."""
	decision = decide(inputs(mode, readings=FROST_READINGS, **situation), cfg(mode))
	assert decision.reason == REASON_FROST
	assert decision.frost and decision.bypass_rate_limit
	assert decision.headline == "Frost guard · Heating"
	if mode == MODE_SWITCH:
		assert decision.command.heater_on is True
	else:
		assert decision.intent.hvac_mode == "heat"
		assert decision.intent.temperature == 20  # max(control 20, 5 + 3)


def test_frost_target_and_release_hysteresis() -> None:
	"""Heat at max(control, frost + 3); released only at frost + 3."""
	cold_plan = replace(PLAN, control_target=7, base_target=7)
	decision = decide(inputs(plan=cold_plan, readings=FROST_READINGS, hvac_mode="off"), cfg())
	assert decision.intent.temperature == 16  # 8, clamped to the device minimum
	assert frost_active(6.0, latched=True, cfg=SAFETY)
	assert not frost_active(6.0, latched=False, cfg=SAFETY)
	assert not frost_active(8.0, latched=True, cfg=SAFETY)
	still = decide(inputs(readings=Readings(room=7.5, internal=7.5), frost_latched=True, hvac_mode="off"), cfg())
	assert still.reason == REASON_FROST
	released = decide(inputs(readings=Readings(room=8.0, internal=8.0), frost_latched=True, hvac_mode="off"), cfg())
	assert released.reason == REASON_OFF
	disabled = decide(inputs(readings=FROST_READINGS, hvac_mode="off"), cfg(frost_protection=False))
	assert disabled.reason == REASON_OFF
	# Internal reading used when the room sensor is gone.
	internal_only = decide(inputs(readings=Readings(room=None, internal=3)), cfg())
	assert internal_only.reason == REASON_FROST


def test_frost_with_device_unavailable() -> None:
	"""Nothing can be sent to an unavailable device."""
	decision = decide(inputs(readings=FROST_READINGS, device=replace(DEVICE, available=False)), cfg())
	assert decision.frost and decision.device_unavailable and decision.command is None


def test_off_turns_device_off_once() -> None:
	"""Smartmostat off: device off, then nothing more."""
	decision = decide(inputs(hvac_mode="off"), cfg())
	assert decision.reason == REASON_OFF and decision.command.hvac_mode == "off"
	already = decide(inputs(hvac_mode="off", device=replace(DEVICE, hvac_mode="off")), cfg())
	assert already.command is None
	switch = decide(inputs(MODE_SWITCH, hvac_mode="off", switch_state=replace(SWITCH_STATE, heater_on=True)), cfg(MODE_SWITCH))
	assert switch.command.heater_on is False


def test_paused_sends_nothing() -> None:
	"""A device-side change pauses Smartmostat."""
	decision = decide(inputs(paused_until=NOW + timedelta(minutes=42)), cfg())
	assert decision.reason == REASON_PAUSED and decision.command is None
	assert decision.headline_reason == "Paused: changed on device (42m)"
	expired = decide(inputs(paused_until=NOW - timedelta(seconds=1)), cfg())
	assert expired.reason == REASON_COMFORT


def test_no_reading_cold_fallback_climate() -> None:
	"""No room or internal reading and below 3 °C outside: heat at D."""
	readings = Readings(room=None, internal=None, outdoor=-2)
	for mode in CLIMATE_MODES:
		decision = decide(inputs(mode, readings=readings, device=replace(DEVICE, current=None, hvac_mode="fan_only")), cfg(mode))
		assert decision.reason == REASON_FALLBACK and decision.fallback
		assert decision.intent.hvac_mode == "heat" and decision.intent.temperature == 20
	mild = decide(inputs(readings=Readings(room=None, internal=None, outdoor=10)), cfg())
	assert mild.reason == REASON_COMFORT  # remote-sensor row 1 still heats as a thermostat
	assert mild.intent.hvac_mode == "heat"


def test_switch_duty_cycle_without_reading() -> None:
	"""Switch: keeps state until stale, then 10 minutes in every 30 when cold."""
	readings = Readings(room=None, outdoor=None)
	fresh = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=NOW - timedelta(minutes=10)), cfg(MODE_SWITCH))
	assert fresh.command is None and fresh.reason == REASON_COMFORT
	since = NOW - timedelta(minutes=185)  # stale since 5 minutes ago
	on_phase = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=since), cfg(MODE_SWITCH))
	assert on_phase.reason == REASON_FALLBACK and on_phase.command.heater_on is True
	since = NOW - timedelta(minutes=195)  # 15 minutes into the period
	off_phase = decide(
		inputs(MODE_SWITCH, readings=readings, room_missing_since=since, switch_state=replace(SWITCH_STATE, heater_on=True)),
		cfg(MODE_SWITCH),
	)
	assert off_phase.command.heater_on is False and off_phase.action == "Heater off (duty cycle)"
	warm_out = decide(
		inputs(MODE_SWITCH, readings=Readings(room=None, outdoor=22), room_missing_since=NOW - timedelta(hours=4), switch_state=replace(SWITCH_STATE, heater_on=True)),
		cfg(MODE_SWITCH),
	)
	# Warmer outside than the target: no heat is needed, so off is safe.
	assert warm_out.command.heater_on is False and warm_out.reason != REASON_FALLBACK
	assert duty_cycle_on(NOW, NOW) and duty_cycle_on(NOW + timedelta(minutes=9), NOW)
	assert not duty_cycle_on(NOW + timedelta(minutes=10), NOW)
	assert duty_cycle_on(NOW + timedelta(minutes=31), NOW)


def test_shed_needs_evidence_and_yields_to_people() -> None:
	"""Shed only with a room reading above the floor; override and away win."""
	shed = decide(inputs(price=SUPER, readings=Readings(room=20, internal=20, outdoor=0)), cfg())
	assert shed.reason == REASON_SHED and shed.command.hvac_mode == "off"
	blind = decide(inputs(price=SUPER, readings=Readings(room=None, internal=20, outdoor=0)), cfg())
	assert blind.reason != REASON_SHED
	at_floor = decide(inputs(price=SUPER, readings=Readings(room=19, internal=20, outdoor=0)), cfg())
	assert at_floor.reason != REASON_SHED
	override = decide(inputs(price=SUPER, override_active=True, readings=Readings(room=21, internal=20)), cfg())
	assert override.reason != REASON_SHED
	away = decide(inputs(price=SUPER, preset=PRESET_AWAY, readings=Readings(room=21, internal=20)), cfg())
	assert away.reason != REASON_SHED
	switch = decide(inputs(MODE_SWITCH, price=SUPER, switch_state=replace(SWITCH_STATE, heater_on=True), readings=Readings(room=21)), cfg(MODE_SWITCH))
	assert switch.reason == REASON_SHED and switch.command.heater_on is False


def test_device_unavailable() -> None:
	"""No commands, headline says so."""
	decision = decide(inputs(device=replace(DEVICE, available=False)), cfg())
	assert decision.device_unavailable and decision.command is None
	assert decision.headline == "Comfort 20°C · Device unavailable"
	missing = decide(inputs(device=None), cfg())
	assert missing.device_unavailable
	no_switch = decide(inputs(MODE_SWITCH, switch_state=SwitchState(heater_on=False, heater_available=False)), cfg(MODE_SWITCH))
	assert no_switch.device_unavailable


def test_stale_detection() -> None:
	"""A sensor silent for stale_minutes is unusable; 0 disables."""
	assert is_stale(NOW - timedelta(minutes=181), NOW, 180)
	assert not is_stale(NOW - timedelta(minutes=179), NOW, 180)
	assert not is_stale(NOW - timedelta(days=3), NOW, 0)
	assert not is_stale(None, NOW, 180)


def test_rate_limit() -> None:
	"""One command per device per 60 s, except frost and user actions."""
	limiter = RateLimiter()
	assert limiter.allowed("climate.sam", NOW)
	limiter.record("climate.sam", NOW)
	assert not limiter.allowed("climate.sam", NOW + timedelta(seconds=30))
	assert limiter.allowed("climate.sam", NOW + timedelta(seconds=30), bypass=True)
	assert limiter.allowed("climate.other", NOW)
	assert limiter.allowed("climate.sam", NOW + timedelta(seconds=60))
	assert limiter.last("climate.sam") == NOW


def test_status_line_and_change_key() -> None:
	"""The full diagnostic line carries the useful numbers."""
	snapshot = inputs()
	decision = decide(snapshot, cfg())
	line = status_line(decision, snapshot, "heat")
	for part in ("mode=heat", "D=20", "R=19.5", "I=19", "O=-5", "price=full", "reason=comfort"):
		assert part in line
	assert isinstance(decision, Decision)
	assert decision.change_key() == decide(snapshot, cfg()).change_key()


def test_switch_without_reading_never_leaves_a_mild_zone_unheated() -> None:
	"""A dead room sensor at 3 to 10 C outside: duty cycle, not off for ever."""
	on = replace(SWITCH_STATE, heater_on=True, heater_changed=NOW - timedelta(hours=2))
	readings = Readings(room=None, outdoor=5)
	held = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=NOW - timedelta(minutes=10), switch_state=on), cfg(MODE_SWITCH))
	assert held.command is None and held.action == "Heater on (no reading)"
	# 181 minutes missing with stale_minutes 180: one minute into the duty cycle.
	stale = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=NOW - timedelta(minutes=181), switch_state=on), cfg(MODE_SWITCH))
	assert stale.reason == REASON_FALLBACK and stale.command is None and stale.action == "Heater on (duty cycle)"
	# The off phase comes round, and so does the next on phase.
	off_phase = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=NOW - timedelta(minutes=195), switch_state=on), cfg(MODE_SWITCH))
	assert off_phase.command.heater_on is False and off_phase.reason == REASON_FALLBACK
	off = replace(on, heater_on=False)
	next_on = decide(inputs(MODE_SWITCH, readings=readings, room_missing_since=NOW - timedelta(minutes=211), switch_state=off), cfg(MODE_SWITCH))
	assert next_on.command.heater_on is True


def test_switch_stale_minutes_zero_keeps_a_grace_period() -> None:
	"""stale_minutes = 0 disables staleness; a sensor blip must not switch the heater off."""
	on = replace(SWITCH_STATE, heater_on=True, heater_changed=NOW - timedelta(hours=2))
	blip = decide(
		inputs(MODE_SWITCH, readings=Readings(room=None, outdoor=5), room_missing_since=NOW, switch_state=on),
		cfg(MODE_SWITCH, stale_minutes=0),
	)
	assert blip.command is None and blip.reason != REASON_FALLBACK and blip.action == "Heater on (no reading)"


def test_off_hands_off_sends_nothing() -> None:
	"""An upgrade that restored an unsupported mode: off, but the device is left alone."""
	cooling = replace(DEVICE, hvac_mode="cool", target=24, hvac_modes=("off", "heat", "cool"))
	plain_off = decide(inputs(hvac_mode="off", device=cooling), cfg())
	assert plain_off.command is not None and plain_off.command.hvac_mode == "off"
	hands_off = decide(inputs(hvac_mode="off", device=cooling, hands_off=True), cfg())
	assert hands_off.reason == REASON_OFF and hands_off.command is None and hands_off.intent is None
	# The frost guard still applies.
	frost = decide(inputs(hvac_mode="off", device=cooling, hands_off=True, readings=Readings(room=3, internal=3)), cfg())
	assert frost.reason == REASON_FROST and frost.command.hvac_mode == "heat"


def test_setpoint_mode_leaves_a_cooling_device_alone() -> None:
	"""The reviewer's probe: setpoint mode, device in cool, warm room and outdoor."""
	for mode in ("cool", "heat_cool", "auto"):
		device = DeviceState(hvac_mode=mode, target=24, current=26, hvac_modes=("off", "heat", "cool", "heat_cool", "auto"))
		decision = decide(
			inputs(MODE_SETPOINT, device=device, readings=Readings(room=26, outdoor=28), plan=Plan(22, 22, REASON_COMFORT, "c")),
			cfg(MODE_SETPOINT),
		)
		assert decision.command is None, mode
