"""Planner: base target and price-adjusted control target.

A generalised version of the owner's ``DaytimeCheapHeat.yaml``. Pure Python.

Two numbers come out:

* ``base_target``: what a person asked for (preset, override or schedule);
* ``control_target``: the base adjusted for price, pre-warming and the
  comfort period. Actuators steer the device towards this number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import math
from typing import Any

from .const import (
	ON_TRACK_ROOM_MARGIN,
	PRESET_AWAY,
	PRESET_COMFORT,
	PRESET_ECO,
	PRESET_SCHEDULE,
	REALLY_COLD_OUTDOOR,
	REASON_AWAY,
	REASON_CHEAP_BOOST,
	REASON_COMFORT,
	REASON_COMFORT_HOLD,
	REASON_ECONOMY,
	REASON_EXPENSIVE,
	REASON_HOT_DAY,
	REASON_NO_PRICE,
	REASON_OVERRIDE,
	REASON_PREWARM,
	REASON_PRICE_OFF,
)
from .price import PriceInfo


def fmt_temp(value: float | None) -> str:
	"""Format a temperature for headlines: 20, 20.5, 24.2."""
	if value is None:
		return "?"
	return f"{round(value, 1):g}"


@dataclass(frozen=True)
class PlannerConfig:
	"""Planner tunables (section 4.3 of the spec)."""

	comfort_temperature: float = 20.0
	eco_temperature: float | None = None
	comfort_start: time | None = None
	comfort_end: time | None = None
	away_temperature: float = 10.0
	min_target: float = 7.0
	max_target: float = 25.0
	cheap_boost: float = 3.0
	boost_skip_margin: float = 0.5
	expensive_cut: float = 2.0
	prewarm_hours: float = 4.0
	prewarm_hours_cold: float = 6.0
	cold_outdoor: float = 10.0
	hot_day_max: float = 25.0
	morning_end: time = time(12, 0)
	price_optimisation: bool = True

	@property
	def schedule_configured(self) -> bool:
		"""True when a daily comfort period is set."""
		return (
			self.comfort_start is not None
			and self.comfort_end is not None
			and self.comfort_start != self.comfort_end
		)

	@property
	def comfort_floor(self) -> float:
		"""Below this the room counts as not yet comfortable (Sam: 19 for 20)."""
		return self.comfort_temperature - 1.0


@dataclass(frozen=True)
class Override:
	"""A person's temporary target. ``until`` None means until cleared."""

	temperature: float
	until: datetime | None = None

	def active(self, now: datetime) -> bool:
		"""True while the override still applies."""
		return self.until is None or now < self.until

	def minutes_left(self, now: datetime) -> int | None:
		"""Whole minutes remaining, None when open-ended."""
		if self.until is None:
			return None
		return max(0, math.ceil((self.until - now).total_seconds() / 60))


@dataclass(frozen=True)
class PlannerInputs:
	"""Everything the planner reads. ``now`` must be aware local time."""

	now: datetime
	price: PriceInfo
	preset: str = PRESET_SCHEDULE
	override: Override | None = None
	room: float | None = None
	outdoor: float | None = None
	forecast_max: float | None = None
	forecast_mean: float | None = None
	thermal_k: float | None = None
	thermal_h: float | None = None


@dataclass
class Plan:
	"""The planner's answer."""

	base_target: float
	control_target: float
	reason: str
	headline_reason: str
	flags: dict[str, Any] = field(default_factory=dict)

	@property
	def current_adjustment(self) -> float:
		"""Control minus base (0.1.0 attribute name)."""
		return round(self.control_target - self.base_target, 2)


def _at(now: datetime, day_offset: int, moment: time) -> datetime:
	"""Local datetime for ``moment`` on today + day_offset."""
	day = now.date() + timedelta(days=day_offset)
	return datetime.combine(day, moment, tzinfo=now.tzinfo)


def in_comfort_period(now: datetime, cfg: PlannerConfig) -> bool:
	"""True inside the daily comfort period (handles periods across midnight)."""
	if not cfg.schedule_configured:
		return False
	assert cfg.comfort_start is not None and cfg.comfort_end is not None
	current = now.time()
	start, end = cfg.comfort_start, cfg.comfort_end
	if start < end:
		return start <= current < end
	return current >= start or current < end


def hours_until_comfort(now: datetime, cfg: PlannerConfig) -> float | None:
	"""Hours until the next comfort period starts."""
	if not cfg.schedule_configured:
		return None
	assert cfg.comfort_start is not None
	start = _at(now, 0, cfg.comfort_start)
	if start <= now:
		start = _at(now, 1, cfg.comfort_start)
	return (start - now).total_seconds() / 3600


def next_schedule_change(now: datetime, cfg: PlannerConfig) -> datetime | None:
	"""The next comfort period start or end after ``now``."""
	if not cfg.schedule_configured:
		return None
	assert cfg.comfort_start is not None and cfg.comfort_end is not None
	candidates = []
	for moment in (cfg.comfort_start, cfg.comfort_end):
		for offset in (0, 1):
			candidate = _at(now, offset, moment)
			if candidate > now:
				candidates.append(candidate)
				break
	return min(candidates)


def hours_to_reach(
	room: float, target: float, outdoor: float, k: float, h: float
) -> float | None:
	"""Hours to heat from ``room`` to ``target`` with first-order model.

	dT/dt = -k (T - outdoor) + h, so the equilibrium is outdoor + h / k.
	Returns 0 when already there, None when unreachable.
	"""
	if k <= 0 or h <= 0:
		return None
	if room >= target:
		return 0.0
	equilibrium = outdoor + h / k
	if room < target < equilibrium - 0.5:
		return (1.0 / k) * math.log((equilibrium - room) / (equilibrium - target))
	return None


def base_target(inputs: PlannerInputs, cfg: PlannerConfig) -> float:
	"""Section 5.1: the target a person sees."""
	if inputs.preset == PRESET_AWAY:
		value = cfg.away_temperature
	elif inputs.override is not None and inputs.override.active(inputs.now):
		value = inputs.override.temperature
	elif inputs.preset == PRESET_COMFORT:
		value = cfg.comfort_temperature
	elif inputs.preset == PRESET_ECO:
		value = (
			cfg.eco_temperature
			if cfg.eco_temperature is not None
			else cfg.comfort_temperature - 2.0
		)
	elif cfg.schedule_configured and not in_comfort_period(inputs.now, cfg):
		value = cfg.eco_temperature if cfg.eco_temperature is not None else cfg.comfort_temperature
	else:
		value = cfg.comfort_temperature
	return _clamp(value, cfg)


def _clamp(value: float, cfg: PlannerConfig) -> float:
	return max(cfg.min_target, min(cfg.max_target, value))


def _base_reason(base: float, cfg: PlannerConfig) -> tuple[str, str]:
	if base < cfg.comfort_temperature:
		return REASON_ECONOMY, f"Economy {fmt_temp(base)}°C"
	return REASON_COMFORT, f"Comfort {fmt_temp(base)}°C"


def plan(inputs: PlannerInputs, cfg: PlannerConfig) -> Plan:
	"""Section 5.2: the control target, its reason and the headline fragment."""
	now = inputs.now
	room = inputs.room
	outdoor = inputs.outdoor
	price = inputs.price
	base = base_target(inputs, cfg)
	flags: dict[str, Any] = {
		"in_comfort_period": in_comfort_period(now, cfg),
		"schedule": cfg.schedule_configured,
	}

	def done(control: float, reason: str, headline: str) -> Plan:
		return Plan(base, _clamp(control, cfg), reason, headline, flags)

	# 1. Away always wins.
	if inputs.preset == PRESET_AWAY:
		return done(cfg.away_temperature, REASON_AWAY, f"Away {fmt_temp(cfg.away_temperature)}°C")

	# 2. Override: price ignored.
	override = inputs.override
	if override is not None and override.active(now):
		minutes = override.minutes_left(now)
		suffix = f" ({minutes}m)" if minutes is not None else ""
		return done(
			override.temperature,
			REASON_OVERRIDE,
			f"You set {fmt_temp(override.temperature)}°C{suffix}",
		)

	# 3. Price logic off or no data: plain thermostat at base.
	if not cfg.price_optimisation:
		return done(base, REASON_PRICE_OFF, "Price control off")
	if not price.usable:
		return done(base, REASON_NO_PRICE, "No price data")

	scheduled = inputs.preset == PRESET_SCHEDULE and cfg.schedule_configured

	# 4. Inside the comfort period: no boost, no cut.
	if scheduled and flags["in_comfort_period"]:
		if room is not None and room < cfg.comfort_floor:
			return done(max(base, cfg.comfort_temperature), REASON_COMFORT, f"Comfort {fmt_temp(max(base, cfg.comfort_temperature))}°C")
		if room is not None and room >= cfg.comfort_temperature:
			return done(base, REASON_COMFORT_HOLD, f"Evening warm {fmt_temp(room)}°C hold")
		return done(base, REASON_COMFORT, f"Comfort {fmt_temp(base)}°C")

	# Hot-day morning: no cheap heat before morning_end unless really cold.
	really_cold_room = (
		cfg.eco_temperature if cfg.eco_temperature is not None else cfg.comfort_temperature - 4.0
	)
	really_cold = (room is not None and room < really_cold_room) or (
		outdoor is not None and outdoor < REALLY_COLD_OUTDOOR
	)
	hot_day_morning = (
		inputs.forecast_max is not None
		and inputs.forecast_max > cfg.hot_day_max
		and now.time() < cfg.morning_end
		and not really_cold
	)
	flags["hot_day_morning"] = hot_day_morning

	# 5. Pre-warm in a window before the comfort period.
	if scheduled and price.cheap_now and not hot_day_morning:
		prewarm = _prewarm(inputs, cfg, flags)
		if prewarm is not None:
			target, cold = prewarm
			suffix = " (cold)" if cold else ""
			return done(target, REASON_PREWARM, f"Pre-warm to {fmt_temp(target)}°C{suffix}")

	# 6. Cheap power boost.
	if price.cheap_now:
		if hot_day_morning:
			return done(base, REASON_HOT_DAY, "Hot day, no morning heat")
		if room is not None:
			boosted = min(base + cfg.cheap_boost, cfg.max_target)
			if cfg.boost_skip_margin >= 0 and room >= boosted - cfg.boost_skip_margin:
				flags["boost_skipped"] = True
				reason, _headline = _base_reason(base, cfg)
				return done(base, reason, "Cheap power, already warm")
			if boosted > base:
				return done(boosted, REASON_CHEAP_BOOST, "Cheap power boost")
		else:
			flags["boost_skipped_no_room"] = True

	# 7. Expensive: cut, never below eco or min_target, never above base.
	if price.expensive_now:
		floor = cfg.eco_temperature if cfg.eco_temperature is not None else cfg.min_target
		control = min(base, max(base - cfg.expensive_cut, floor, cfg.min_target))
		return done(control, REASON_EXPENSIVE, "Electricity expensive")

	# 8. Otherwise base.
	reason, headline = _base_reason(base, cfg)
	return done(base, reason, headline)


def _prewarm(
	inputs: PlannerInputs, cfg: PlannerConfig, flags: dict[str, Any]
) -> tuple[float, bool] | None:
	"""Section 5.3. Returns (target, cold window) or None to skip."""
	hours_left = hours_until_comfort(inputs.now, cfg)
	if hours_left is None:
		return None
	cold = inputs.outdoor is not None and inputs.outdoor < cfg.cold_outdoor
	window = cfg.prewarm_hours_cold if cold else cfg.prewarm_hours
	in_window = 0 < hours_left <= window
	flags["prewarm_window"] = in_window
	flags["prewarm_window_hours"] = window
	flags["hours_until_comfort"] = round(hours_left, 2)
	if not in_window:
		return None
	room = inputs.room
	floor = cfg.comfort_floor
	if room is None:
		flags["prewarm_skip"] = "no_room_reading"
		return None
	if room >= floor:
		flags["prewarm_skip"] = "comfortable"
		return None
	reference = inputs.forecast_mean if inputs.forecast_mean is not None else inputs.outdoor
	if (
		inputs.thermal_k is not None
		and inputs.thermal_h is not None
		and reference is not None
	):
		needed = hours_to_reach(
			room, cfg.comfort_temperature, reference, inputs.thermal_k, inputs.thermal_h
		)
		flags["hours_to_comfort"] = None if needed is None else round(needed, 2)
		if (
			needed is not None
			and room >= cfg.comfort_temperature - ON_TRACK_ROOM_MARGIN
			and needed <= hours_left + 1
		):
			flags["prewarm_skip"] = "on_track"
			return None
	deficit = floor - room
	needed_target = floor + 2 + 2 * deficit
	target = max(min(needed_target, cfg.max_target), cfg.comfort_temperature)
	flags["prewarm_target"] = round(target, 2)
	return target, cold
