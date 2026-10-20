"""Planner tests, porting test_daytime_cheap_heat_templates.py (spec 5, 13.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time, timedelta

import pytest

from custom_components.smartmostat.const import (
	PRESET_AWAY,
	PRESET_COMFORT,
	PRESET_ECO,
	PRESET_SCHEDULE,
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
from custom_components.smartmostat.planner import (
	Override,
	PlannerConfig,
	PlannerInputs,
	base_target,
	hours_to_reach,
	hours_until_comfort,
	in_comfort_period,
	next_schedule_change,
	plan,
)
from custom_components.smartmostat.price import STATUS_FULL, STATUS_INVALID, STATUS_PARTIAL, PriceInfo

from ..helpers import local

DAY = date(2026, 10, 20)

# Sam's values: comfort 20 from 19:00 to 23:00, 16 otherwise, holiday 10, max 25.
SAM = PlannerConfig(
	comfort_temperature=20,
	eco_temperature=16,
	comfort_start=time(19),
	comfort_end=time(23),
	away_temperature=10,
	min_target=7,
	max_target=25,
	cheap_boost=3,
	boost_skip_margin=0.5,
	expensive_cut=2,
	prewarm_hours=4,
	prewarm_hours_cold=6,
	cold_outdoor=10,
	hot_day_max=25,
	morning_end=time(12),
)

CHEAP = PriceInfo(status=STATUS_FULL, price_now=0.3, cheap_now=True, relatively_cheap=True, absolutely_cheap=True)
EXPENSIVE = PriceInfo(status=STATUS_FULL, price_now=2.5, expensive_now=True)
NORMAL = PriceInfo(status=STATUS_FULL, price_now=1.0)


def run(hour: int, price: PriceInfo = CHEAP, cfg: PlannerConfig = SAM, minute: int = 0, **kwargs):
	"""Plan at a local hour of DAY."""
	inputs = PlannerInputs(now=local(DAY, hour, minute), price=price, **kwargs)
	return plan(inputs, cfg)


# --- base target (5.1) -------------------------------------------------------


def test_base_target_order() -> None:
	"""away > override > comfort preset > eco preset > schedule > comfort."""
	now = local(DAY, 10)
	override = Override(23, now + timedelta(minutes=90))
	assert base_target(PlannerInputs(now, NORMAL, PRESET_AWAY, override), SAM) == 10
	assert base_target(PlannerInputs(now, NORMAL, PRESET_COMFORT, override), SAM) == 23
	assert base_target(PlannerInputs(now, NORMAL, PRESET_COMFORT), SAM) == 20
	assert base_target(PlannerInputs(now, NORMAL, PRESET_ECO), SAM) == 16
	assert base_target(PlannerInputs(now, NORMAL, PRESET_ECO), replace(SAM, eco_temperature=None)) == 18
	assert base_target(PlannerInputs(now, NORMAL), SAM) == 16
	assert base_target(PlannerInputs(local(DAY, 20), NORMAL), SAM) == 20
	no_schedule = replace(SAM, comfort_start=None, comfort_end=None)
	assert base_target(PlannerInputs(now, NORMAL), no_schedule) == 20
	# Eco unset with a schedule: comfort all day.
	assert base_target(PlannerInputs(now, NORMAL), replace(SAM, eco_temperature=None)) == 20


def test_comfort_period_across_midnight() -> None:
	"""A 22:00 to 06:00 period wraps."""
	cfg = replace(SAM, comfort_start=time(22), comfort_end=time(6))
	assert in_comfort_period(local(DAY, 23), cfg)
	assert in_comfort_period(local(DAY, 5, 59), cfg)
	assert not in_comfort_period(local(DAY, 6), cfg)
	assert hours_until_comfort(local(DAY, 20), cfg) == 2
	assert next_schedule_change(local(DAY, 23), cfg) == local(DAY + timedelta(days=1), 6)


def test_hours_until_and_next_change() -> None:
	"""Schedule helpers."""
	assert hours_until_comfort(local(DAY, 15), SAM) == 4
	assert hours_until_comfort(local(DAY, 19, 30), SAM) == pytest.approx(23.5)
	assert next_schedule_change(local(DAY, 15), SAM) == local(DAY, 19)
	assert next_schedule_change(local(DAY, 20), SAM) == local(DAY, 23)
	assert next_schedule_change(local(DAY, 20), replace(SAM, comfort_start=None)) is None


# --- control target (5.2): ported DaytimeCheapHeat cases --------------------


def test_new_prewarm_target_values() -> None:
	"""clamp(floor + 2 + 2 * (floor - R), comfort, max): Sam's sizing."""
	for room, expected in [(17.4, 24.2), (18.9, 21.2), (10.0, 25), (0.0, 25)]:
		result = run(16, room=room, outdoor=12)
		assert result.reason == REASON_PREWARM, room
		assert result.control_target == pytest.approx(expected), room
		assert result.headline_reason == f"Pre-warm to {round(expected, 1):g}°C"
	# At or above the floor no pre-warm: falls through to the (skipped) boost.
	at_floor = run(16, room=19.0, outdoor=12)
	assert at_floor.reason == REASON_ECONOMY
	assert at_floor.control_target == 16
	assert at_floor.flags["prewarm_skip"] == "comfortable"


def test_control_prewarm_branch_reachable_and_falls_back_to_boost() -> None:
	"""Inside the window the sized pre-warm wins; outside it the flat +3."""
	assert run(16, room=17.4, outdoor=12).control_target == pytest.approx(24.2)
	outside_window = run(11, room=17.4, outdoor=12)
	assert outside_window.reason == REASON_CHEAP_BOOST
	assert outside_window.control_target == 19


def test_control_other_branches() -> None:
	"""Holiday, override, evening, expensive, normal."""
	assert run(16, preset=PRESET_AWAY, room=12).control_target == 10
	now = local(DAY, 16)
	override = Override(19.9, now + timedelta(minutes=90))
	result = run(16, price=EXPENSIVE, override=override, room=17)
	assert (result.control_target, result.reason) == (19.9, REASON_OVERRIDE)
	assert result.headline_reason == "You set 19.9°C (90m)"
	# Evening, cold room: hold comfort; no boost even though cheap.
	evening = run(20, room=17.0)
	assert (evening.control_target, evening.reason) == (20, REASON_COMFORT)
	warm_evening = run(20, room=20.5)
	assert (warm_evening.control_target, warm_evening.reason) == (20, REASON_COMFORT_HOLD)
	assert warm_evening.headline_reason == "Evening warm 20.5°C hold"
	# Expensive during the comfort period: no cut.
	assert run(20, price=EXPENSIVE, room=19.5).control_target == 20
	# Expensive outside it: eco 16 is already the floor.
	daytime = run(10, price=EXPENSIVE, room=18)
	assert (daytime.control_target, daytime.reason) == (16, REASON_EXPENSIVE)
	# Comfort preset (base 20) and genuinely expensive: cut by 2, not below eco.
	assert run(10, price=EXPENSIVE, preset=PRESET_COMFORT, room=20).control_target == 18
	assert run(10, price=EXPENSIVE, preset=PRESET_COMFORT, cfg=replace(SAM, expensive_cut=6), room=20).control_target == 16
	# Relative-dear but not genuinely expensive must not coast (10 Sep case).
	assert run(10, price=NORMAL, preset=PRESET_COMFORT, room=20).control_target == 20
	assert run(10, price=NORMAL, room=17).reason == REASON_ECONOMY


def test_away_beats_override_and_override_beats_price() -> None:
	"""Ordering of rows 1 to 3."""
	now = local(DAY, 10)
	override = Override(23, now + timedelta(minutes=30))
	assert run(10, preset=PRESET_AWAY, override=override).reason == REASON_AWAY
	assert run(10, price=PriceInfo(status=STATUS_INVALID), override=override).reason == REASON_OVERRIDE
	expired = Override(23, now - timedelta(minutes=1))
	assert run(10, override=expired, room=15).reason == REASON_CHEAP_BOOST


def test_prewarm_window_widens_when_cold() -> None:
	"""15:00 to 19:00, or 13:00 to 19:00 below 10 °C outside; never overnight."""
	cases = [
		(15, 14, False), (15, 15, True), (15, 18, True), (15, 19, False),
		(5, 12, False), (5, 13, True), (5, 18, True), (5, 19, False),
		(5, 3, False), (15, 3, False),
	]
	for outdoor, hour, expected in cases:
		result = run(hour, room=17.0, outdoor=outdoor)
		assert (result.reason == REASON_PREWARM) is expected, (outdoor, hour, result)
		if expected and outdoor < 10:
			assert result.headline_reason.endswith("(cold)")


def test_no_overnight_25c_blast() -> None:
	"""A cold, genuinely cheap 03:00 gets the modest +3, not 25 °C."""
	result = run(3, room=16.5, outdoor=2)
	assert result.reason == REASON_CHEAP_BOOST
	assert result.control_target == 19


def test_cold_afternoon_still_respects_the_skip_guards() -> None:
	"""Below 10 °C outside the skip guards still apply."""
	result = run(16, room=19.5, outdoor=4)
	assert result.control_target == 16
	assert result.flags["prewarm_skip"] == "comfortable"
	assert result.flags.get("boost_skipped") is True


def test_hot_day_morning_skip() -> None:
	"""No cheap heat before noon on a hot day unless it is really cold."""
	hot = run(8, room=20, outdoor=15, forecast_max=28)
	assert (hot.reason, hot.control_target) == (REASON_HOT_DAY, 16)
	assert hot.headline_reason == "Hot day, no morning heat"
	cold_room = run(8, room=14, outdoor=15, forecast_max=28)
	assert (cold_room.reason, cold_room.control_target) == (REASON_CHEAP_BOOST, 19)
	frosty_out = run(8, room=17, outdoor=2, forecast_max=28)
	assert frosty_out.reason == REASON_CHEAP_BOOST
	mild_day = run(8, room=17, outdoor=15, forecast_max=20)
	assert mild_day.reason == REASON_CHEAP_BOOST
	afternoon = run(16, room=17, outdoor=15, forecast_max=28)
	assert afternoon.reason == REASON_PREWARM


def test_boost_skip_margin_and_disable() -> None:
	"""Skip the boost when already within 0.5 of it; negative margin disables."""
	assert run(10, room=18.4).control_target == 19
	assert run(10, room=18.5).control_target == 16
	assert run(10, room=18.5, cfg=replace(SAM, boost_skip_margin=-1)).control_target == 19
	capped = run(10, preset=PRESET_COMFORT, cfg=replace(SAM, max_target=21), room=17)
	assert capped.control_target == 21


# --- thermal "on track" skip -------------------------------------------------


def test_thermal_on_track_skips_prewarm() -> None:
	"""R >= comfort - 2.5 and reachable in time: no pre-warm."""
	# T_eq = 5 + 2.5 / 0.1 = 30; from 18 to 20 takes 10 ln(12/10) = 1.82 h.
	assert hours_to_reach(18, 20, 5, 0.1, 2.5) == pytest.approx(1.823, abs=0.001)
	on_track = run(17, room=18, outdoor=5, thermal_k=0.1, thermal_h=2.5)
	assert on_track.flags["prewarm_skip"] == "on_track"
	assert on_track.reason == REASON_CHEAP_BOOST
	# Too cold to count as on track (below comfort - 2.5).
	behind = run(17, room=17.4, outdoor=5, thermal_k=0.1, thermal_h=2.5)
	assert behind.reason == REASON_PREWARM
	# Forecast mean preferred over the outdoor reading.
	via_forecast = run(17, room=18, outdoor=-20, forecast_mean=5, thermal_k=0.1, thermal_h=2.5)
	assert via_forecast.flags["prewarm_skip"] == "on_track"


def test_unreachable_or_missing_thermal_never_skips() -> None:
	"""T_eq too low, or no k/h: pre-warm as normal."""
	assert hours_to_reach(18, 20, 5, 0.1, 1.5) is None  # T_eq = 20
	unreachable = run(17, room=18, outdoor=5, thermal_k=0.1, thermal_h=1.5)
	assert unreachable.reason == REASON_PREWARM
	missing = run(17, room=18, outdoor=5)
	assert missing.reason == REASON_PREWARM
	no_outdoor = run(17, room=18, thermal_k=0.1, thermal_h=2.5)
	assert no_outdoor.reason == REASON_PREWARM
	assert hours_to_reach(21, 20, 5, 0.1, 2.5) == 0.0
	assert hours_to_reach(18, 20, 5, 0, 2.5) is None


# --- unknowns -----------------------------------------------------------------


def test_room_unknown_no_boost_no_prewarm() -> None:
	"""A boost needs evidence; base still applies."""
	prewarm_time = run(16, room=None, outdoor=5)
	assert prewarm_time.reason == REASON_ECONOMY
	assert prewarm_time.control_target == 16
	assert prewarm_time.flags["prewarm_skip"] == "no_room_reading"
	morning = run(10, room=None)
	assert morning.control_target == 16
	assert morning.flags["boost_skipped_no_room"] is True
	# Expensive still cuts without a room reading.
	assert run(10, price=EXPENSIVE, preset=PRESET_COMFORT, room=None).control_target == 18


def test_price_invalid_or_off_gives_base() -> None:
	"""Row 3: plain thermostat at base, with the right reason."""
	invalid = run(10, price=PriceInfo(status=STATUS_INVALID), room=15)
	assert (invalid.reason, invalid.control_target, invalid.headline_reason) == (REASON_NO_PRICE, 16, "No price data")
	off = run(10, cfg=replace(SAM, price_optimisation=False), room=15)
	assert (off.reason, off.control_target, off.headline_reason) == (REASON_PRICE_OFF, 16, "Price control off")
	# Partial data (state only) still runs; no signals means base.
	partial = run(10, price=PriceInfo(status=STATUS_PARTIAL, price_now=1.0), room=15)
	assert partial.reason == REASON_ECONOMY


def test_no_schedule_behaves_like_0_1_0() -> None:
	"""Without a schedule: comfort all day, boost and cut around it."""
	cfg = replace(SAM, comfort_start=None, comfort_end=None, eco_temperature=None)
	assert run(16, cfg=cfg, room=17).control_target == 23  # boost, no pre-warm
	assert run(16, cfg=cfg, price=EXPENSIVE, room=20).control_target == 18
	normal = run(16, cfg=cfg, price=NORMAL, room=20)
	assert (normal.control_target, normal.reason) == (20, REASON_COMFORT)
	assert normal.current_adjustment == 0


def test_clamped_to_min_and_max_target() -> None:
	"""Every control target lands inside [min_target, max_target]."""
	cfg = replace(SAM, away_temperature=3)
	assert run(10, cfg=cfg, preset=PRESET_AWAY).control_target == 7
	now = local(DAY, 10)
	override = Override(30, now + timedelta(minutes=5))
	assert run(10, override=override).control_target == 25
	assert run(10, preset=PRESET_SCHEDULE, room=15).current_adjustment == 3
