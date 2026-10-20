"""Shared test helpers: price days in the HACS Nordpool shape."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")

# 3 Sep 2026 (SE4), hourly SEK/kWh, shaped to match the facts recorded in
# README_SamHVAC.md: 02:00-06:00 trough at 0.32, 06:00 at 1.85 (9th dearest),
# 13:00-15:00 at about 0.50, 18:00 at 2.14 (2nd dearest).
SEP_3 = [
	0.60, 0.45, 0.32, 0.32, 0.32, 0.32, 1.85, 2.10,
	2.05, 1.60, 1.90, 0.90, 0.70, 0.50, 0.51, 0.80,
	1.40, 1.75, 2.14, 3.50, 2.13, 2.12, 2.10, 0.90,
]

# 10 Sep 2026 (SE4): 0.16 overnight, 0.657 at 09:40, evening 4 to 6 SEK.
SEP_10 = [
	0.16, 0.16, 0.16, 0.16, 0.16, 0.16, 0.16, 0.40,
	0.60, 0.657, 0.62, 0.55, 0.50, 0.48, 0.55, 0.80,
	1.50, 3.50, 4.50, 5.80, 4.80, 3.00, 1.20, 0.60,
]


def local(day: date, hour: int = 0, minute: int = 0) -> datetime:
	"""Aware local time."""
	return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def raw_slots(
	day: date,
	hourly: list[float],
	minutes: int = 60,
	as_datetime: bool = False,
	naive: bool = False,
	with_end: bool = True,
) -> list[dict]:
	"""raw_today-style slots; hourly values repeated for sub-hour slots.

	Built in UTC steps so DST days have the right number of slots.
	"""
	start = local(day).astimezone(UTC)
	end_of_day = local(day + timedelta(days=1)).astimezone(UTC)
	step = timedelta(minutes=minutes)
	slots = []
	index = 0
	moment = start
	while moment < end_of_day:
		hour_index = min(int((moment - start).total_seconds() // 3600), len(hourly) - 1)
		begin = moment.astimezone(TZ)
		finish = (moment + step).astimezone(TZ)
		if naive:
			begin_v = begin.replace(tzinfo=None).isoformat()
			finish_v = finish.replace(tzinfo=None).isoformat()
		elif as_datetime:
			begin_v, finish_v = begin, finish
		else:
			begin_v, finish_v = begin.isoformat(), finish.isoformat()
		slot = {"start": begin_v, "value": hourly[hour_index]}
		if with_end:
			slot["end"] = finish_v
		slots.append(slot)
		index += 1
		moment += step
	return slots


def nordpool_attrs(day: date, hourly: list[float], tomorrow: list[float] | None = None, minutes: int = 60, **kwargs) -> dict:
	"""Attributes as the HACS Nordpool sensor publishes them."""
	today_raw = raw_slots(day, hourly, minutes, **kwargs)
	attrs = {
		"raw_today": today_raw,
		"raw_tomorrow": raw_slots(day + timedelta(days=1), tomorrow, minutes, **kwargs) if tomorrow else [],
		"today": [slot["value"] for slot in today_raw],
		"tomorrow": [slot["value"] for slot in raw_slots(day + timedelta(days=1), tomorrow, minutes)] if tomorrow else [],
		"tomorrow_valid": bool(tomorrow),
		"average": round(sum(hourly) / len(hourly) + 0.13, 3),
		"unit_of_measurement": "SEK/kWh",
	}
	return attrs
