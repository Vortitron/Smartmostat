"""Actuators: turn a control target into a device command.

Pure Python. Each actuator works out an *intent* (what the device should be
doing); ``diff_climate`` then reduces it to the parts that differ from what
the device already reports, so nothing is sent when nothing would change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .const import (
	COOL_SETPOINT_CAP,
	HVAC_COOL,
	HVAC_FAN_ONLY,
	HVAC_HEAT,
	HVAC_HEAT_COOL,
	HVAC_OFF,
	IDLE_AUTO,
	IDLE_FAN_ONLY,
	IDLE_HEAT_LOW,
	IDLE_OFF,
)


@dataclass(frozen=True)
class DeviceState:
	"""What a wrapped climate entity reports."""

	available: bool = True
	hvac_mode: str | None = None
	target: float | None = None
	current: float | None = None
	hvac_modes: tuple[str, ...] = (HVAC_OFF, HVAC_HEAT)
	min_temp: float = 7.0
	max_temp: float = 35.0
	step: float = 0.5
	preset: str | None = None
	presets: tuple[str, ...] = ()
	hvac_action: str | None = None


@dataclass(frozen=True)
class Readings:
	"""Temperatures after aggregation and staleness checks (None = unusable)."""

	room: float | None = None
	room_max: float | None = None
	internal: float | None = None
	outdoor: float | None = None
	room_source: str | None = None


@dataclass(frozen=True)
class ClimateIntent:
	"""Desired device state. ``hvac_mode`` None means "do not touch the mode"."""

	hvac_mode: str | None
	temperature: float | None
	label: str
	details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClimateCommand:
	"""Only the parts that must be sent, in order: preset, mode, temperature."""

	hvac_mode: str | None = None
	temperature: float | None = None
	preset: str | None = None
	# The mode the device should end up in; sent along with the temperature.
	target_mode: str | None = None

	def as_dict(self) -> dict[str, Any]:
		"""Serialisable form."""
		return {
			"hvac_mode": self.hvac_mode,
			"temperature": self.temperature,
			"preset": self.preset,
		}


@dataclass(frozen=True)
class RemoteSensorConfig:
	"""Remote-sensor actuator tunables (names kept from 0.2.0)."""

	temperature_tolerance: float = 0.5
	heat_offset: float = 1.0
	base_stop_heat_offset: float = -2.0
	max_stop_heat_offset: float = -5.0
	room_max: float = 27.0
	fan_only_difference: float = 3.0
	idle_mode: str = IDLE_AUTO
	fallback_offset: float = 0.0
	allow_hvac_mode_changes: bool = True
	cooling: bool = False
	cool_fan_room: float = 25.0
	cool_outdoor_gate: float = 22.0
	cool_compressor_room: float = 27.0
	cool_compressor_outdoor: float = 27.0
	cool_offset: float = -1.0


def round_setpoint(value: float, device: DeviceState) -> float:
	"""Clamp to the device range and round to its step (as sam.yaml does)."""
	step = device.step if device.step and device.step > 0 else 0.5
	clamped = max(device.min_temp, min(device.max_temp, value))
	rounded = round(clamped / step) * step
	rounded = max(device.min_temp, min(device.max_temp, rounded))
	return round(rounded, 2)


def _idle_kind(cfg: RemoteSensorConfig, device: DeviceState, overheat: float, hard: bool) -> str:
	"""Resolve ``idle_mode`` for this device and situation."""
	kind = cfg.idle_mode
	if kind == IDLE_AUTO:
		kind = IDLE_FAN_ONLY if HVAC_FAN_ONLY in device.hvac_modes else IDLE_HEAT_LOW
	if kind == IDLE_FAN_ONLY and HVAC_FAN_ONLY not in device.hvac_modes:
		kind = IDLE_HEAT_LOW
	# Switching a heat pump off is drastic: only when well over target or at
	# the room ceiling; otherwise idle with a low heat set-point.
	if kind == IDLE_OFF and not hard and overheat <= cfg.fan_only_difference:
		kind = IDLE_HEAT_LOW
	return kind


def _express(
	mode: str,
	setpoint: float,
	label: str,
	cfg: RemoteSensorConfig,
	device: DeviceState,
	details: dict[str, Any],
	overheat: float = 0.0,
	hard: bool = False,
) -> ClimateIntent:
	"""Turn (heat|idle|cool|fan_only, setpoint) into a device intent."""
	if mode == "idle":
		kind = _idle_kind(cfg, device, overheat, hard)
		details["idle"] = kind
		if not cfg.allow_hvac_mode_changes or kind == IDLE_HEAT_LOW:
			target_mode = None if not cfg.allow_hvac_mode_changes else HVAC_HEAT
			return ClimateIntent(target_mode, round_setpoint(device.min_temp, device), label, details)
		if kind == IDLE_OFF:
			return ClimateIntent(HVAC_OFF, None, label, details)
		return ClimateIntent(HVAC_FAN_ONLY, round_setpoint(setpoint, device), label, details)
	target_mode = mode if cfg.allow_hvac_mode_changes else None
	return ClimateIntent(target_mode, round_setpoint(setpoint, device), label, details)


def remote_sensor_intent(
	control: float,
	readings: Readings,
	device: DeviceState,
	cfg: RemoteSensorConfig,
	hvac_mode: str = HVAC_HEAT,
) -> ClimateIntent:
	"""Section 6.1 and 6.3: generalised sam.yaml."""
	d = control
	r = readings.room
	i = readings.internal
	o = readings.outdoor
	details: dict[str, Any] = {"D": d, "R": r, "I": i, "O": o}

	if r is None:
		return _express(HVAC_HEAT, d + cfg.fallback_offset, "Device sensor only", cfg, device, details)
	if i is None:
		return _express(HVAC_HEAT, d, "No device reading", cfg, device, details)

	if cfg.cooling and hvac_mode == HVAC_HEAT_COOL and o is not None and o >= cfg.cool_outdoor_gate:
		if (
			r >= cfg.cool_compressor_room
			and o >= cfg.cool_compressor_outdoor
			and HVAC_COOL in device.hvac_modes
		):
			setpoint = min(i + cfg.cool_offset, COOL_SETPOINT_CAP)
			return _express(HVAC_COOL, setpoint, "Cooling", cfg, device, details)
		if r >= cfg.cool_fan_room and HVAC_FAN_ONLY in device.hvac_modes:
			return _express(HVAC_FAN_ONLY, i, "Fan only", cfg, device, details)

	tol = cfg.temperature_tolerance
	room_peak = readings.room_max if readings.room_max is not None else r
	need = d - r
	boost = max(cfg.heat_offset, need)
	stop = max(cfg.base_stop_heat_offset - (r - d), cfg.max_stop_heat_offset)
	details.update({"need": round(need, 2), "boost": round(boost, 2), "stop": round(stop, 2)})

	if room_peak >= cfg.room_max:
		return _express("idle", i + cfg.max_stop_heat_offset, "Room at max", cfg, device, details, r - d, True)
	if r > d:
		return _express("idle", i + stop, "Warm enough", cfg, device, details, r - d)
	if r < d - tol and o is not None and o > d:
		return _express("idle", i + boost, "Coasting (mild)", cfg, device, details, r - d)
	if r < d - tol:
		return _express(HVAC_HEAT, i + boost, "Heating", cfg, device, details)
	if r >= d:
		return _express(HVAC_HEAT, i + stop, "Holding", cfg, device, details)
	return _express(HVAC_HEAT, i, "Holding", cfg, device, details)


def setpoint_intent(
	control: float, device: DeviceState, allow_hvac_mode_changes: bool = True
) -> ClimateIntent:
	"""Section 6.2: tell the device the control target directly (0.1.0)."""
	mode = HVAC_HEAT if allow_hvac_mode_changes else None
	return ClimateIntent(mode, round_setpoint(control, device), f"Set {round_setpoint(control, device):g}°C")


def heat_intent(target: float, device: DeviceState, label: str) -> ClimateIntent:
	"""Plain heating at a set-point (safety rules)."""
	return ClimateIntent(HVAC_HEAT, round_setpoint(target, device), label)


def off_intent(label: str) -> ClimateIntent:
	"""Device off."""
	return ClimateIntent(HVAC_OFF, None, label)


def diff_climate(
	intent: ClimateIntent, device: DeviceState, want_preset: str | None = None
) -> ClimateCommand | None:
	"""Reduce an intent to what differs from the device. None = nothing to send."""
	mode = None
	if intent.hvac_mode is not None and intent.hvac_mode != device.hvac_mode:
		if intent.hvac_mode in device.hvac_modes or not device.hvac_modes:
			mode = intent.hvac_mode
	temperature = None
	final_mode = intent.hvac_mode or device.hvac_mode
	if intent.temperature is not None and final_mode != HVAC_OFF:
		step = device.step if device.step and device.step > 0 else 0.5
		if device.target is None or abs(device.target - intent.temperature) >= step / 2:
			temperature = intent.temperature
	preset = None
	if want_preset is not None and device.preset != want_preset:
		if want_preset in device.presets:
			preset = want_preset
	if mode is None and temperature is None and preset is None:
		return None
	return ClimateCommand(mode, temperature, preset, final_mode)


# --- Switch actuator --------------------------------------------------------


@dataclass(frozen=True)
class SwitchConfig:
	"""Switch actuator tunables."""

	hysteresis: float = 0.5
	min_cycle_minutes: float = 5


@dataclass(frozen=True)
class SwitchState:
	"""Current relay states and when each last changed."""

	heater_on: bool | None = None
	cooler_on: bool | None = None
	heater_changed: datetime | None = None
	cooler_changed: datetime | None = None
	heater_available: bool = True
	cooler_available: bool = True


@dataclass(frozen=True)
class SwitchCommand:
	"""Relay changes to send. None = leave as is."""

	heater_on: bool | None = None
	cooler_on: bool | None = None

	@property
	def empty(self) -> bool:
		"""True when nothing changes."""
		return self.heater_on is None and self.cooler_on is None

	def as_dict(self) -> dict[str, Any]:
		"""Serialisable form."""
		return {"heater_on": self.heater_on, "cooler_on": self.cooler_on}


def _can_change(changed: datetime | None, now: datetime, cfg: SwitchConfig) -> bool:
	if changed is None or cfg.min_cycle_minutes <= 0:
		return True
	return now - changed >= timedelta(minutes=cfg.min_cycle_minutes)


def relay_change(
	current: bool | None,
	want: bool | None,
	changed: datetime | None,
	now: datetime,
	cfg: SwitchConfig,
	force: bool = False,
) -> tuple[bool | None, bool]:
	"""Return (command, held_by_min_cycle)."""
	if want is None or current == want:
		return None, False
	if not force and current is not None and not _can_change(changed, now, cfg):
		return None, True
	return want, False


def switch_intent(
	control: float,
	room: float | None,
	hvac_mode: str,
	state: SwitchState,
	cfg: SwitchConfig,
	now: datetime,
	cool_control: float | None = None,
) -> tuple[SwitchCommand | None, str]:
	"""Section 6.4: hysteresis around the control target."""
	hyst = cfg.hysteresis
	eps = 1e-6  # float noise must not move a threshold
	want_heater: bool | None = None
	want_cooler: bool | None = None
	if hvac_mode == HVAC_OFF:
		want_heater = False if state.heater_on is not None else None
		want_cooler = False if state.cooler_on is not None else None
	elif hvac_mode == HVAC_HEAT:
		want_cooler = False if state.cooler_on is not None else None
		if room is not None and state.heater_on is not None:
			if room <= control - hyst + eps:
				want_heater = True
			elif room >= control + hyst - eps:
				want_heater = False
	elif hvac_mode == HVAC_COOL:
		want_heater = False if state.heater_on is not None else None
		target = cool_control if cool_control is not None else control
		if room is not None and state.cooler_on is not None:
			if room >= target + hyst - eps:
				want_cooler = True
			elif room <= target - hyst + eps:
				want_cooler = False

	# Turning things off for "off" mode or the other relay is never delayed.
	heater_cmd, heater_held = relay_change(
		state.heater_on, want_heater, state.heater_changed, now, cfg, force=hvac_mode != HVAC_HEAT
	)
	cooler_cmd, cooler_held = relay_change(
		state.cooler_on, want_cooler, state.cooler_changed, now, cfg, force=hvac_mode != HVAC_COOL
	)
	heater_final = heater_cmd if heater_cmd is not None else state.heater_on
	cooler_final = cooler_cmd if cooler_cmd is not None else state.cooler_on
	if cooler_final:
		label = "Cooler on"
	elif heater_final:
		label = "Heater on"
	elif hvac_mode == HVAC_COOL:
		label = "Cooler off"
	else:
		label = "Heater off"
	if room is None and hvac_mode != HVAC_OFF:
		label += " (no reading)"
	if heater_held or cooler_held:
		label += " (min cycle)"
	command = SwitchCommand(heater_cmd, cooler_cmd)
	return (None if command.empty else command), label
