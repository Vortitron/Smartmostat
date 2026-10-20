"""Safety rules (section 8 of the spec). Pure Python.

These rules run after the planner and the actuator. They can only add heat
or stop a shed; they never make a house colder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import (
	DUTY_ON_MINUTES,
	DUTY_PERIOD_MINUTES,
	FROST_RELEASE_MARGIN,
	NO_READING_COLD_OUTDOOR,
	RATE_LIMIT_SECONDS,
)


@dataclass(frozen=True)
class SafetyConfig:
	"""Safety tunables."""

	frost_protection: bool = True
	frost_temperature: float = 5.0
	stale_minutes: float = 180
	shed_floor: float = 19.0


def best_reading(room: float | None, internal: float | None) -> float | None:
	"""Room first, then the device's internal reading."""
	return room if room is not None else internal


def frost_active(best: float | None, latched: bool, cfg: SafetyConfig) -> bool:
	"""Rule 1: below frost_temperature, released at frost_temperature + 3."""
	if not cfg.frost_protection or best is None:
		return False
	if latched:
		return best < cfg.frost_temperature + FROST_RELEASE_MARGIN
	return best < cfg.frost_temperature


def frost_target(control: float, cfg: SafetyConfig) -> float:
	"""Set-point while the frost guard is active."""
	return max(control, cfg.frost_temperature + FROST_RELEASE_MARGIN)


def no_reading_cold(outdoor: float | None, unknown_counts_as_cold: bool) -> bool:
	"""Rule 2 condition on the outdoor temperature."""
	if outdoor is None:
		return unknown_counts_as_cold
	return outdoor < NO_READING_COLD_OUTDOOR


def duty_cycle_on(now: datetime, since: datetime) -> bool:
	"""Rule 2 for switches: on for 10 minutes in every 30, from ``since``."""
	elapsed = (now - since).total_seconds() / 60
	if elapsed < 0:
		return True
	return (elapsed % DUTY_PERIOD_MINUTES) < DUTY_ON_MINUTES


def shed_allowed(
	super_expensive: bool,
	room: float | None,
	away: bool,
	override_active: bool,
	cfg: SafetyConfig,
) -> bool:
	"""Rule 3: shed only with a room reading above the floor.

	Away and an active override both beat the shed, so a person who asks for
	heat during a price spike gets it.
	"""
	if not super_expensive or away or override_active:
		return False
	if room is None:
		return False
	return room > cfg.shed_floor


def is_stale(last_reported: datetime | None, now: datetime, stale_minutes: float) -> bool:
	"""Rule 6: a sensor silent for ``stale_minutes`` counts as unavailable."""
	if stale_minutes <= 0 or last_reported is None:
		return False
	return now - last_reported > timedelta(minutes=stale_minutes)


class RateLimiter:
	"""Rule 7: at most one command per device per 60 s, with bypasses."""

	def __init__(self, seconds: float = RATE_LIMIT_SECONDS) -> None:
		"""Create the limiter."""
		self._seconds = seconds
		self._last: dict[str, datetime] = {}

	def allowed(self, device: str, now: datetime, bypass: bool = False) -> bool:
		"""True when a command may be sent now."""
		if bypass:
			return True
		last = self._last.get(device)
		return last is None or (now - last).total_seconds() >= self._seconds

	def record(self, device: str, now: datetime) -> None:
		"""Remember that a command was sent."""
		self._last[device] = now

	def last(self, device: str) -> datetime | None:
		"""When the last command was sent."""
		return self._last.get(device)
