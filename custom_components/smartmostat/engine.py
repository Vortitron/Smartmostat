"""Decision engine: planner output + actuator + safety layer. Pure Python.

The controller gathers a snapshot of Home Assistant state, calls ``decide``
and sends whatever command comes back. Keeping this pure means a whole
evaluation can be tested without Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Any

from .actuators import (
	ClimateCommand,
	ClimateIntent,
	DeviceState,
	Readings,
	RemoteSensorConfig,
	SwitchCommand,
	SwitchConfig,
	SwitchState,
	diff_climate,
	heat_intent,
	off_intent,
	relay_change,
	remote_sensor_intent,
	setpoint_intent,
	switch_intent,
)
from .const import (
	HVAC_COOL,
	HVAC_HEAT,
	HVAC_OFF,
	MODE_REMOTE_SENSOR,
	MODE_SETPOINT,
	MODE_SWITCH,
	PRESET_AWAY,
	PRESET_SCHEDULE,
	REASON_FALLBACK,
	REASON_FROST,
	REASON_OFF,
	REASON_PAUSED,
	REASON_SHED,
)
from .planner import Plan, fmt_temp
from .price import PriceInfo
from .safety import (
	SafetyConfig,
	best_reading,
	duty_cycle_on,
	frost_active,
	frost_target,
	no_reading_cold,
	shed_allowed,
)


@dataclass(frozen=True)
class EngineConfig:
	"""Everything the engine needs besides the snapshot."""

	control_mode: str
	remote: RemoteSensorConfig = field(default_factory=RemoteSensorConfig)
	switch: SwitchConfig = field(default_factory=SwitchConfig)
	safety: SafetyConfig = field(default_factory=SafetyConfig)
	away_device_preset: str | None = None


@dataclass(frozen=True)
class EngineInputs:
	"""Snapshot for one evaluation."""

	now: datetime
	plan: Plan
	price: PriceInfo
	readings: Readings
	hvac_mode: str = HVAC_HEAT
	preset: str = PRESET_SCHEDULE
	override_active: bool = False
	paused_until: datetime | None = None
	device: DeviceState | None = None
	switch_state: SwitchState | None = None
	frost_latched: bool = False
	room_missing_since: datetime | None = None


@dataclass
class Decision:
	"""Result of one evaluation."""

	reason: str
	headline_reason: str
	action: str
	command: ClimateCommand | SwitchCommand | None = None
	intent: ClimateIntent | None = None
	frost: bool = False
	shed: bool = False
	fallback: bool = False
	paused: bool = False
	device_unavailable: bool = False
	bypass_rate_limit: bool = False
	details: dict[str, Any] = field(default_factory=dict)

	@property
	def headline(self) -> str:
		"""Sam-style "Reason · Action"."""
		return f"{self.headline_reason} · {self.action}"

	def change_key(self) -> tuple[Any, ...]:
		"""What counts as a change for events: reason and wanted command."""
		intent = None
		if self.intent is not None:
			intent = (self.intent.hvac_mode, self.intent.temperature)
		command = self.command.as_dict() if self.command is not None else None
		return (self.reason, self.action, intent, repr(command))


def _want_preset(cfg: EngineConfig, preset: str, device: DeviceState) -> str | None:
	"""Away device preset handling (Sam's heat_8_15)."""
	if not cfg.away_device_preset:
		return None
	if preset == PRESET_AWAY:
		return cfg.away_device_preset
	if device.preset == cfg.away_device_preset:
		return "none"
	return None


def _climate(
	intent: ClimateIntent, inputs: EngineInputs, cfg: EngineConfig, with_preset: bool = True
) -> ClimateCommand | None:
	assert inputs.device is not None
	want = _want_preset(cfg, inputs.preset, inputs.device) if with_preset else None
	return diff_climate(intent, inputs.device, want)


def decide(inputs: EngineInputs, cfg: EngineConfig) -> Decision:
	"""Run actuator and safety rules for one snapshot."""
	plan = inputs.plan
	readings = inputs.readings
	now = inputs.now
	control = plan.control_target
	is_switch = cfg.control_mode == MODE_SWITCH
	reason = plan.reason
	headline_reason = plan.headline_reason

	# Device availability.
	if is_switch:
		state = inputs.switch_state or SwitchState()
		available = (state.heater_on is not None and state.heater_available) or (
			state.cooler_on is not None and state.cooler_available
		)
	else:
		available = inputs.device is not None and inputs.device.available

	# Rule 1: frost guard beats everything, including "off" and pauses.
	best = best_reading(readings.room, readings.internal)
	if frost_active(best, inputs.frost_latched, cfg.safety):
		target = frost_target(control, cfg.safety)
		decision = Decision(REASON_FROST, "Frost guard", "Heating", frost=True, bypass_rate_limit=True)
		decision.details["frost_target"] = target
		if not available:
			decision.action = "Device unavailable"
			decision.device_unavailable = True
			return decision
		if is_switch:
			state = inputs.switch_state or SwitchState()
			heater, _held = relay_change(state.heater_on, True, state.heater_changed, now, cfg.switch, force=True)
			cooler, _held = relay_change(state.cooler_on, False, state.cooler_changed, now, cfg.switch, force=True)
			command = SwitchCommand(heater, cooler if state.cooler_on is not None else None)
			decision.command = None if command.empty else command
			decision.action = "Heating" if state.heater_on is not None else "No heater"
		else:
			intent = heat_intent(target, inputs.device, "Heating")
			decision.intent = intent
			decision.command = _climate(intent, inputs, cfg)
		return decision

	# Rule 4: device unavailable.
	if not available:
		return Decision(reason, headline_reason, "Device unavailable", device_unavailable=True)

	# Smartmostat switched off: turn the device off once, then leave it.
	if inputs.hvac_mode == HVAC_OFF:
		decision = Decision(REASON_OFF, "Off", "Off")
		if is_switch:
			command, _label = switch_intent(control, readings.room, HVAC_OFF, inputs.switch_state or SwitchState(), cfg.switch, now)
			decision.command = command
		else:
			intent = off_intent("Off")
			decision.intent = intent
			decision.command = _climate(intent, inputs, cfg, with_preset=False)
		return decision

	# Paused because a person changed the device itself.
	if inputs.paused_until is not None and now < inputs.paused_until:
		minutes = max(0, math.ceil((inputs.paused_until - now).total_seconds() / 60))
		return Decision(REASON_PAUSED, f"Paused: changed on device ({minutes}m)", "Paused", paused=True)

	# Rule 3: super-expensive shed, only with evidence.
	if shed_allowed(
		inputs.price.super_expensive,
		readings.room,
		inputs.preset == PRESET_AWAY,
		inputs.override_active,
		cfg.safety,
	):
		decision = Decision(REASON_SHED, "Super-expensive shed", "Shedding", shed=True)
		if is_switch:
			command, _label = switch_intent(control, readings.room, HVAC_OFF, inputs.switch_state or SwitchState(), cfg.switch, now)
			decision.command = command
		else:
			intent = off_intent("Shedding")
			decision.intent = intent
			decision.command = _climate(intent, inputs, cfg, with_preset=False)
		return decision

	# Rule 2: no reading at all and cold outside.
	if is_switch:
		return _switch_decision(inputs, cfg, reason, headline_reason)

	assert inputs.device is not None
	if readings.room is None and readings.internal is None and no_reading_cold(readings.outdoor, False):
		intent = heat_intent(control, inputs.device, "Heating")
		return Decision(
			REASON_FALLBACK,
			"No readings, safety heat",
			"Heating",
			command=_climate(intent, inputs, cfg),
			intent=intent,
			fallback=True,
		)

	if cfg.control_mode == MODE_SETPOINT:
		intent = setpoint_intent(control, inputs.device, cfg.remote.allow_hvac_mode_changes)
	else:
		intent = remote_sensor_intent(control, readings, inputs.device, cfg.remote, inputs.hvac_mode)
	decision = Decision(
		reason,
		headline_reason,
		intent.label,
		command=_climate(intent, inputs, cfg),
		intent=intent,
		details=dict(intent.details),
	)
	if cfg.control_mode == MODE_REMOTE_SENSOR and readings.room is None:
		decision.fallback = True
	return decision


def _switch_decision(
	inputs: EngineInputs, cfg: EngineConfig, reason: str, headline_reason: str
) -> Decision:
	"""Switch actuator plus the no-reading duty cycle."""
	now = inputs.now
	state = inputs.switch_state or SwitchState()
	readings = inputs.readings
	plan = inputs.plan
	cool_control = None
	if inputs.hvac_mode == HVAC_COOL:
		# Mirror the price adjustment for cooling: cheap means cool harder.
		cool_control = plan.base_target - plan.current_adjustment

	if readings.room is None:
		stale = timedelta(minutes=max(0.0, cfg.safety.stale_minutes))
		since = inputs.room_missing_since or now
		if now - since >= stale:
			anchor = since + stale
			if inputs.hvac_mode == HVAC_HEAT and state.heater_on is not None and no_reading_cold(readings.outdoor, True):
				want = duty_cycle_on(now, anchor)
				heater, _held = relay_change(state.heater_on, want, state.heater_changed, now, cfg.switch, force=True)
				command = SwitchCommand(heater, None)
				label = "Heater on (duty cycle)" if want else "Heater off (duty cycle)"
				return Decision(
					REASON_FALLBACK,
					"No readings, safety heat",
					label,
					command=None if command.empty else command,
					fallback=True,
				)
			command, _label = switch_intent(plan.control_target, None, HVAC_OFF, state, cfg.switch, now)
			return Decision(reason, headline_reason, "Off (no reading)", command=command, fallback=True)

	command, label = switch_intent(
		plan.control_target, readings.room, inputs.hvac_mode, state, cfg.switch, now, cool_control
	)
	decision = Decision(reason, headline_reason, label, command=command)
	decision.details = {
		"D": plan.control_target if cool_control is None else cool_control,
		"R": readings.room,
		"on_below": round((cool_control if cool_control is not None else plan.control_target) - cfg.switch.hysteresis, 2),
		"off_above": round((cool_control if cool_control is not None else plan.control_target) + cfg.switch.hysteresis, 2),
	}
	return decision


def status_line(decision: Decision, inputs: EngineInputs, mode: str) -> str:
	"""Full diagnostic line (Sam's sam_hvac_status, without the 255 limit)."""
	r = inputs.readings
	p = inputs.price
	plan = inputs.plan
	parts = [f"mode={mode}"]
	if decision.intent is not None:
		parts.append(f"send={decision.intent.hvac_mode or '-'}/{fmt_temp(decision.intent.temperature) if decision.intent.temperature is not None else '-'}")
	elif decision.command is not None:
		parts.append(f"send={decision.command.as_dict()}")
	parts.append(f"D={fmt_temp(plan.control_target)} base={fmt_temp(plan.base_target)}")
	parts.append(f"R={fmt_temp(r.room)}({r.room_source or 'none'})")
	parts.append(f"I={fmt_temp(r.internal)} O={fmt_temp(r.outdoor)}")
	for key in ("need", "boost", "stop", "idle"):
		if key in decision.details:
			parts.append(f"{key}={decision.details[key]}")
	guards = [
		name
		for name, flag in (
			("frost", decision.frost),
			("shed", decision.shed),
			("fallback", decision.fallback),
			("paused", decision.paused),
			("unavailable", decision.device_unavailable),
		)
		if flag
	]
	parts.append(f"guards={','.join(guards) or 'none'}")
	parts.append(
		"price="
		f"{p.status} now={p.price_now} hour={_r(p.hour_price)} avg={_r(p.day_average)} "
		f"fwd={_r(p.forward_average)} pct={_r(p.percentile_today)} "
		f"cheap={p.cheap_now} exp={p.expensive_now} super={p.super_expensive}"
	)
	flags = plan.flags
	if flags.get("prewarm_window") is not None:
		parts.append(
			"prewarm="
			f"window:{flags.get('prewarm_window')} hrs:{flags.get('hours_until_comfort')} "
			f"skip:{flags.get('prewarm_skip', '-')} target:{flags.get('prewarm_target', '-')} "
			f"to_comfort:{flags.get('hours_to_comfort', '-')}"
		)
	parts.append(f"reason={decision.reason}")
	return " | ".join(parts)


def _r(value: float | None) -> str:
	return "-" if value is None else f"{value:.3f}"
