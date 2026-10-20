"""Price analyser tests (spec section 4.2 and 13.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.smartmostat.const import (
	LEVEL_CHEAP,
	LEVEL_EXPENSIVE,
	LEVEL_NORMAL,
	LEVEL_SUPER_EXPENSIVE,
	LEVEL_UNKNOWN,
)
from custom_components.smartmostat.price import (
	STATUS_FULL,
	STATUS_INVALID,
	STATUS_MISSING,
	STATUS_PARTIAL,
	PriceSettings,
	analyse,
	find_price_slots,
	parse_slots,
)

from ..helpers import SEP_3, SEP_10, TZ, local, nordpool_attrs, raw_slots

DAY = date(2026, 10, 20)
FLAT_RAMP = [1.0 + 0.1 * hour for hour in range(24)]


def quarter_values(hourly: list[float]) -> list[float]:
	"""Distinct quarter-hour values whose hourly mean equals ``hourly``."""
	values = []
	for value in hourly:
		values += [value - 0.03, value - 0.01, value + 0.01, value + 0.03]
	return values


def test_live_format_96_quarter_hours_iso_strings() -> None:
	"""96 x 15-minute slots with ISO strings, as the live SE4 sensor publishes."""
	attrs = nordpool_attrs(DAY, FLAT_RAMP, minutes=15)
	# Give each quarter its own value so slot and hour differ.
	for index, slot in enumerate(attrs["raw_today"]):
		slot["value"] = quarter_values(FLAT_RAMP)[index]
	info = analyse("1.0", attrs, local(DAY, 10, 7))
	assert info.status == STATUS_FULL
	assert info.slot_count == 96
	assert info.slot_minutes == 15
	assert info.price_now == pytest.approx(2.0 - 0.03)  # 10:00-10:15 slot
	assert info.hour_price == pytest.approx(2.0)  # clock-hour mean
	expected_avg = sum(FLAT_RAMP) / 24
	assert info.day_average == pytest.approx(expected_avg)
	# Our own mean, not the sensor's (different) "average" attribute.
	assert info.day_average != pytest.approx(attrs["average"])


def test_datetime_objects_and_naive_strings_match_iso() -> None:
	"""start may be a datetime inside HA, or a naive local string."""
	now = local(DAY, 14, 30)
	iso = analyse(None, nordpool_attrs(DAY, SEP_3, minutes=15), now)
	dt_objs = analyse(None, nordpool_attrs(DAY, SEP_3, minutes=15, as_datetime=True), now)
	naive = analyse(None, nordpool_attrs(DAY, SEP_3, minutes=15, naive=True), now)
	for other in (dt_objs, naive):
		assert other.status == STATUS_FULL
		assert other.price_now == iso.price_now
		assert other.forward_average == pytest.approx(iso.forward_average)
		assert other.percentile_today == pytest.approx(iso.percentile_today)
		assert other.price_position == pytest.approx(iso.price_position)


def test_hourly_slots_and_missing_end() -> None:
	"""24 x 60-minute slots; slot length from the gap to the next start."""
	attrs = nordpool_attrs(DAY, SEP_3, with_end=False)
	slots, total, bad, source = parse_slots(attrs, local(DAY, 1))
	assert source == "raw"
	assert (total, bad) == (24, 0)
	assert all(slot.end - slot.start == timedelta(hours=1) for slot in slots)
	info = analyse(None, attrs, local(DAY, 3, 59))
	assert info.price_now == 0.32


def test_today_float_list_fallback() -> None:
	"""No raw lists: today's floats start at local midnight."""
	attrs = {"today": quarter_values(FLAT_RAMP), "tomorrow": []}
	info = analyse(None, attrs, local(DAY, 10, 20))
	assert info.status == STATUS_FULL
	assert info.slot_minutes == 15
	assert info.price_now == pytest.approx(2.0 - 0.01)


@pytest.mark.parametrize(
	("attrs", "state", "status"),
	[
		(None, None, STATUS_MISSING),
		({}, "unavailable", STATUS_MISSING),
		({"raw_today": "garbage"}, None, STATUS_MISSING),
		({"raw_today": [{"start": "nope", "value": "x"}] * 10}, None, STATUS_INVALID),
		({}, "1.5", STATUS_PARTIAL),
	],
)
def test_empty_none_and_garbage(attrs, state, status) -> None:
	"""Missing or broken data never raises."""
	info = analyse(state, attrs, local(DAY, 12))
	assert info.status == status
	assert info.cheap_now is False
	assert info.expensive_now is False


def test_more_than_half_bad_is_invalid_but_some_bad_is_fine() -> None:
	"""Unparsable slots are skipped and counted."""
	slots = raw_slots(DAY, FLAT_RAMP)
	for slot in slots[:10]:
		slot["value"] = None
	info = analyse(None, {"raw_today": slots}, local(DAY, 15))
	assert info.status == STATUS_FULL
	assert info.bad_slots == 10
	for slot in slots[:13]:
		slot["value"] = "bad"
	assert analyse(None, {"raw_today": slots}, local(DAY, 15)).status == STATUS_INVALID


def test_slot_boundaries() -> None:
	"""now exactly at a boundary belongs to the new slot."""
	attrs = nordpool_attrs(DAY, FLAT_RAMP, minutes=15)
	for index, slot in enumerate(attrs["raw_today"]):
		slot["value"] = float(index)
	assert analyse(None, attrs, local(DAY, 10, 15)).price_now == 41.0
	assert analyse(None, attrs, local(DAY, 10, 14)).price_now == 40.0
	assert analyse(None, attrs, local(DAY, 0, 0)).price_now == 0.0


def test_forward_average_uses_tomorrow_and_truncates_without_it() -> None:
	"""Across midnight the forward window reads tomorrow's slots."""
	tomorrow = [5.0] * 24
	now = local(DAY, 22, 30)
	with_tomorrow = analyse(None, nordpool_attrs(DAY, FLAT_RAMP, tomorrow), now)
	assert with_tomorrow.has_tomorrow
	# Next 4 hours after 22:00: 23:00 (3.3) and 00:00 to 02:00 tomorrow (5.0).
	assert with_tomorrow.forward_average == pytest.approx((3.3 + 15.0) / 4)
	assert with_tomorrow.relatively_cheap
	without = analyse(None, nordpool_attrs(DAY, FLAT_RAMP), now)
	assert without.forward_average == pytest.approx(3.3)  # only 23:00 left
	at_last_hour = analyse(None, nordpool_attrs(DAY, FLAT_RAMP), local(DAY, 23, 30))
	assert at_last_hour.forward_average is None
	assert at_last_hour.relatively_cheap is False
	assert at_last_hour.relatively_expensive is False


def test_dst_autumn_25_hour_day() -> None:
	"""25 Oct 2026: clocks go back, 25 hours and 100 quarter-hours."""
	day = date(2026, 10, 25)
	hourly = [float(h) for h in range(25)]
	attrs = nordpool_attrs(day, hourly, minutes=15)
	assert len(attrs["raw_today"]) == 100
	# The second 02:00 hour (after the change) is hour index 3.
	second_two = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 02:30 CET
	info = analyse(None, attrs, second_two.astimezone(TZ))
	assert info.price_now == 3.0
	assert info.hour_price == 3.0
	floats = analyse(None, {"today": attrs["today"]}, second_two.astimezone(TZ))
	assert floats.price_now == 3.0
	assert floats.slot_minutes == 15


def test_dst_spring_23_hour_day() -> None:
	"""29 Mar 2026: clocks go forward, 23 hours."""
	day = date(2026, 3, 29)
	hourly = [float(h) for h in range(23)]
	attrs = nordpool_attrs(day, hourly)
	assert len(attrs["raw_today"]) == 23
	info = analyse(None, attrs, local(day, 3, 30))  # 03:30 CEST is hour index 2
	assert info.price_now == 2.0
	floats = analyse(None, {"today": hourly}, local(day, 3, 30))
	assert floats.price_now == 2.0
	assert floats.slot_minutes == 60


def test_zero_and_negative_prices_are_valid() -> None:
	"""0 is a price, not missing data (0.1.0 bug); negatives too."""
	hourly = [0.0] * 6 + [-0.2] * 6 + [0.0] * 6 + [0.5] * 6
	attrs = nordpool_attrs(DAY, hourly)
	info = analyse("0", attrs, local(DAY, 2))
	assert info.status == STATUS_FULL
	assert info.price_now == 0.0
	assert info.day_average == pytest.approx(0.075)
	negative = analyse(None, attrs, local(DAY, 8))
	assert negative.price_now == -0.2
	assert negative.absolutely_cheap  # percentile 0


def test_day_average_not_positive_uses_plain_comparison() -> None:
	"""With an average at or below zero the ratio test becomes price <= average."""
	hourly = [-1.0] * 12 + [0.5] * 12
	info = analyse(None, nordpool_attrs(DAY, hourly), local(DAY, 11), PriceSettings(cheap_percentile=0))
	assert info.day_average == pytest.approx(-0.25)
	assert info.absolutely_cheap  # -1 <= -0.25
	assert not info.absolutely_expensive


def test_price_position_and_next_high_low() -> None:
	"""price_position over the next 24 h; next high/low actually work now."""
	info = analyse(None, nordpool_attrs(DAY, SEP_10), local(DAY, 9, 40))
	assert info.min_price_24h == pytest.approx(0.48)
	assert info.max_price_24h == pytest.approx(5.8)
	assert info.price_position == pytest.approx((0.657 - 0.48) / (5.8 - 0.48))
	assert info.next_high_price_in_hours == pytest.approx(6 + 20 / 60, abs=0.01)  # 16:00 (1.50 >= average)
	assert info.next_low_price_in_hours == pytest.approx(20 / 60, abs=0.01)  # 10:00 is <= half the average
	flat = analyse(None, nordpool_attrs(DAY, [1.0] * 24), local(DAY, 9))
	assert flat.price_position == 0.5


def test_super_expensive_latch_and_hysteresis() -> None:
	"""Latches at shed_price, releases below shed_price - hysteresis."""
	settings = PriceSettings(shed_price=3.0, shed_hysteresis=0.15)
	hourly = [2.9] * 24
	attrs = nordpool_attrs(DAY, hourly)
	assert not analyse(None, attrs, local(DAY, 9), settings).super_expensive
	assert analyse(None, attrs, local(DAY, 9), settings, shed_latched=True).super_expensive
	attrs = nordpool_attrs(DAY, [2.8] * 24)
	assert not analyse(None, attrs, local(DAY, 9), settings, shed_latched=True).super_expensive
	attrs = nordpool_attrs(DAY, [3.0] * 24)
	info = analyse(None, attrs, local(DAY, 9), settings)
	assert info.super_expensive
	assert info.level == LEVEL_SUPER_EXPENSIVE
	# State-only data still allows shedding (partial).
	partial = analyse("3.5", {}, local(DAY, 9), settings)
	assert partial.status == STATUS_PARTIAL
	assert partial.super_expensive


def test_levels() -> None:
	"""cheap / normal / expensive / unknown."""
	assert analyse(None, nordpool_attrs(DAY, SEP_3), local(DAY, 3)).level == LEVEL_CHEAP
	assert analyse(None, nordpool_attrs(DAY, SEP_10), local(DAY, 21, 30)).level == LEVEL_EXPENSIVE
	assert analyse(None, nordpool_attrs(DAY, SEP_10), local(DAY, 9, 40)).level == LEVEL_NORMAL
	assert analyse(None, None, local(DAY, 9)).level == LEVEL_UNKNOWN


def test_naive_now_rejected() -> None:
	"""Mixing naive and aware times was the 0.1.0/0.2.0 bug."""
	with pytest.raises(ValueError):
		analyse(None, {}, datetime(2026, 10, 20, 12))


def test_find_price_slots() -> None:
	"""Config flow validation helper."""
	assert find_price_slots(nordpool_attrs(DAY, SEP_3), local(DAY, 12))
	assert not find_price_slots({"foo": 1}, local(DAY, 12))


# --- Sam regressions replayed -----------------------------------------------

SEP_3_DAY = date(2026, 9, 3)
SEP_10_DAY = date(2026, 9, 10)


@pytest.mark.parametrize(
	("hour", "cheap"),
	[(2, True), (3, True), (5, True), (6, False), (13, True), (14, True), (18, False)],
)
def test_price_gate_rejects_the_run_up_into_a_peak(hour: int, cheap: bool) -> None:
	"""3 Sep 2026 SE4: 06:00 (1.85) and 18:00 (2.14) are not cheap_now; troughs are."""
	info = analyse(None, nordpool_attrs(SEP_3_DAY, SEP_3), local(SEP_3_DAY, hour, 10))
	assert info.cheap_now is cheap, info.as_dict()
	if hour in (6, 18):
		# The relative signal alone fires on the run-up into the peak...
		assert info.relatively_cheap
		# ...and the absolute gate is what rejects it.
		assert not info.absolutely_cheap


def test_below_average_morning_is_not_called_expensive() -> None:
	"""10 Sep 2026 09:40: 0.657 SEK, average about 1.23, evening 4 to 6 SEK."""
	info = analyse(None, nordpool_attrs(SEP_10_DAY, SEP_10), local(SEP_10_DAY, 9, 40))
	assert info.day_average == pytest.approx(sum(SEP_10) / 24)
	assert 1.2 < info.day_average < 1.3
	assert info.relatively_expensive  # dearer than the next 4 hours
	assert not info.absolutely_expensive  # but well below the day average
	assert not info.expensive_now
	assert not info.cheap_now


def test_cheap_ratio_is_an_absolute_escape_hatch() -> None:
	"""Sam's cheap_leccy: a dear-looking rank still counts when <= half the average."""
	hourly = [0.10] * 12 + [0.40] + [0.45] * 4 + [8.0] * 4 + [0.42] * 3
	info = analyse(None, nordpool_attrs(DAY, hourly), local(DAY, 12, 5))
	assert info.percentile_today > 0.48  # rank says "dear half of the day"
	assert info.hour_price <= 0.5 * info.day_average
	assert info.absolutely_cheap
	assert info.cheap_now  # cheaper than the coming hours, and genuinely cheap


def test_today_cheap_even_cheaper_later() -> None:
	"""Cheap now but cheaper still later: relative test says wait, so no boost.

	This is the heating side's deliberate choice (DaytimeCheapHeat needs both
	signals); sam.yaml's cooling-only escape hatch is out of scope (spec 11).
	"""
	hourly = [1.0] * 8 + [0.3] + [0.1] * 4 + [1.5] * 11
	info = analyse(None, nordpool_attrs(DAY, hourly), local(DAY, 8, 10))
	assert info.absolutely_cheap
	assert not info.relatively_cheap
	assert not info.cheap_now
