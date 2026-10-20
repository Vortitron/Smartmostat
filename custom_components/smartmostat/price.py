"""Price analysis for Smartmostat.

Pure Python, no Home Assistant imports. Parses a HACS Nordpool style price
sensor into time slots and derives the signals the planner uses.

Rules that fixed the 0.1.0 and 0.2.0 bugs:

* every time is timezone aware; naive inputs are taken as local time;
* zero and negative prices are ordinary values (never "missing");
* nothing divides by the price itself;
* decisions use the clock-hour mean, so 15-minute jitter cannot flip them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
import math
from typing import Any

from .const import (
	LEVEL_CHEAP,
	LEVEL_EXPENSIVE,
	LEVEL_NORMAL,
	LEVEL_SUPER_EXPENSIVE,
	LEVEL_UNKNOWN,
)

STATUS_FULL = "full"
STATUS_PARTIAL = "partial"
STATUS_INVALID = "invalid"
STATUS_MISSING = "missing"

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class PriceSlot:
	"""One price interval. ``start`` and ``end`` are aware UTC datetimes."""

	start: datetime
	end: datetime
	value: float


@dataclass(frozen=True)
class PriceSettings:
	"""Tunables that affect price signals."""

	lookahead_hours: int = 4
	relative_margin: float = 0.0
	cheap_ratio: float = 0.5
	cheap_percentile: float = 0.48
	expensive_ratio: float = 1.0
	shed_price: float | None = None
	shed_hysteresis: float = 0.15


@dataclass
class PriceInfo:
	"""Everything the planner and the entities need to know about price."""

	status: str = STATUS_MISSING
	price_now: float | None = None
	hour_price: float | None = None
	day_average: float | None = None
	forward_average: float | None = None
	percentile_today: float | None = None
	price_position: float | None = None
	min_price_24h: float | None = None
	max_price_24h: float | None = None
	relatively_cheap: bool = False
	relatively_expensive: bool = False
	absolutely_cheap: bool = False
	absolutely_expensive: bool = False
	cheap_now: bool = False
	expensive_now: bool = False
	super_expensive: bool = False
	level: str = LEVEL_UNKNOWN
	next_high_price_in_hours: float | None = None
	next_low_price_in_hours: float | None = None
	slot_count: int = 0
	bad_slots: int = 0
	slot_minutes: float | None = None
	has_tomorrow: bool = False
	notes: list[str] = field(default_factory=list)

	@property
	def usable(self) -> bool:
		"""True when the price logic can run (full or partial data)."""
		return self.status in (STATUS_FULL, STATUS_PARTIAL)

	def as_dict(self) -> dict[str, Any]:
		"""Serialisable view for attributes, events and diagnostics."""
		data = asdict(self)
		for key, value in data.items():
			if isinstance(value, float):
				data[key] = round(value, 4)
		return data


def _to_float(value: Any) -> float | None:
	"""Convert to a finite float, or None. Zero and negatives are valid."""
	if value is None or isinstance(value, bool):
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if math.isnan(number) or math.isinf(number):
		return None
	return number


def _to_datetime(value: Any, tz: tzinfo) -> datetime | None:
	"""Parse an ISO string or datetime. Naive values are local time."""
	if isinstance(value, datetime):
		parsed = value
	elif isinstance(value, str):
		try:
			parsed = datetime.fromisoformat(value.strip())
		except ValueError:
			return None
	else:
		return None
	if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
		parsed = parsed.replace(tzinfo=tz)
	return parsed.astimezone(UTC)


def _local_midnight(day: date, tz: tzinfo) -> datetime:
	"""Local midnight of ``day`` as aware UTC."""
	return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)


def _parse_raw(entries: Any, tz: tzinfo) -> tuple[list[PriceSlot], int, int]:
	"""Parse one raw_today/raw_tomorrow list. Returns (slots, total, bad)."""
	if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
		return [], 0, 0
	total = len(entries)
	bad = 0
	parsed: list[tuple[datetime, datetime | None, float]] = []
	for entry in entries:
		if not isinstance(entry, Mapping):
			bad += 1
			continue
		start = _to_datetime(entry.get("start"), tz)
		value = _to_float(entry.get("value"))
		if start is None or value is None:
			bad += 1
			continue
		end = _to_datetime(entry.get("end"), tz) if entry.get("end") is not None else None
		parsed.append((start, end, value))
	parsed.sort(key=lambda item: item[0])
	default_length = timedelta(hours=24) / total if total else HOUR
	slots: list[PriceSlot] = []
	for index, (start, end, value) in enumerate(parsed):
		if end is None or end <= start:
			if index + 1 < len(parsed) and parsed[index + 1][0] > start:
				end = parsed[index + 1][0]
			else:
				end = start + default_length
		slots.append(PriceSlot(start, end, value))
	return slots, total, bad


def _parse_floats(values: Any, day: date, tz: tzinfo) -> tuple[list[PriceSlot], int, int]:
	"""Parse a ``today``/``tomorrow`` float list starting at local midnight."""
	if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
		return [], 0, 0
	start_of_day = _local_midnight(day, tz)
	end_of_day = _local_midnight(day + timedelta(days=1), tz)
	length = (end_of_day - start_of_day) / len(values)
	slots: list[PriceSlot] = []
	bad = 0
	for index, raw in enumerate(values):
		value = _to_float(raw)
		if value is None:
			bad += 1
			continue
		start = start_of_day + length * index
		slots.append(PriceSlot(start, start + length, value))
	return slots, len(values), bad


def _merge(slots: list[PriceSlot]) -> list[PriceSlot]:
	"""Sort and drop duplicate starts (today/tomorrow can overlap)."""
	seen: dict[datetime, PriceSlot] = {}
	for slot in slots:
		seen.setdefault(slot.start, slot)
	return [seen[key] for key in sorted(seen)]


def parse_slots(attributes: Mapping[str, Any] | None, now: datetime) -> tuple[list[PriceSlot], int, int, str]:
	"""Find price slots in sensor attributes.

	Returns (slots, total_entries, bad_entries, source) where source is
	``raw``, ``floats`` or ``none``.
	"""
	if now.tzinfo is None:
		raise ValueError("now must be timezone aware")
	tz = now.tzinfo
	attributes = attributes or {}
	today = now.astimezone(tz).date()

	raw_slots: list[PriceSlot] = []
	raw_total = raw_bad = 0
	for key in ("raw_today", "raw_tomorrow"):
		slots, total, bad = _parse_raw(attributes.get(key), tz)
		raw_slots.extend(slots)
		raw_total += total
		raw_bad += bad
	if raw_slots and raw_bad * 2 <= raw_total:
		return _merge(raw_slots), raw_total, raw_bad, "raw"

	float_slots: list[PriceSlot] = []
	float_total = float_bad = 0
	for key, day in (("today", today), ("tomorrow", today + timedelta(days=1))):
		slots, total, bad = _parse_floats(attributes.get(key), day, tz)
		float_slots.extend(slots)
		float_total += total
		float_bad += bad
	if float_slots and float_bad * 2 <= float_total:
		return _merge(float_slots), float_total, float_bad, "floats"

	if raw_total or float_total:
		return [], raw_total or float_total, raw_bad if raw_total else float_bad, "invalid"
	return [], 0, 0, "none"


def _hour_key(moment: datetime, tz: tzinfo) -> datetime:
	"""Start of the local clock hour containing ``moment``, as aware UTC."""
	local = moment.astimezone(tz)
	return moment.astimezone(UTC) - timedelta(
		minutes=local.minute, seconds=local.second, microseconds=local.microsecond
	)


def hourly_means(slots: list[PriceSlot], tz: tzinfo) -> dict[datetime, float]:
	"""Duration-weighted mean per local clock hour."""
	sums: dict[datetime, float] = {}
	weights: dict[datetime, float] = {}
	for slot in slots:
		key = _hour_key(slot.start, tz)
		weight = (slot.end - slot.start).total_seconds() or 1.0
		sums[key] = sums.get(key, 0.0) + slot.value * weight
		weights[key] = weights.get(key, 0.0) + weight
	return {key: sums[key] / weights[key] for key in sorted(sums)}


def _weighted_mean(slots: list[PriceSlot]) -> float | None:
	total = sum((slot.end - slot.start).total_seconds() for slot in slots)
	if total <= 0:
		return None
	return sum(slot.value * (slot.end - slot.start).total_seconds() for slot in slots) / total


def _is_cheap_ratio(value: float, average: float, ratio: float) -> bool:
	if average > 0:
		return value <= ratio * average
	return value <= average


def _is_expensive_ratio(value: float, average: float, ratio: float) -> bool:
	if average > 0:
		return value >= ratio * average
	return value >= average


def analyse(
	state: Any,
	attributes: Mapping[str, Any] | None,
	now: datetime,
	settings: PriceSettings | None = None,
	shed_latched: bool = False,
) -> PriceInfo:
	"""Analyse a price sensor state at ``now`` (aware)."""
	settings = settings or PriceSettings()
	tz = now.tzinfo
	if tz is None:
		raise ValueError("now must be timezone aware")
	attributes = attributes or {}
	info = PriceInfo()
	slots, total, bad, source = parse_slots(attributes, now)
	info.slot_count = len(slots)
	info.bad_slots = bad
	state_price = _to_float(state)
	now_utc = now.astimezone(UTC)
	today = now.astimezone(tz).date()

	if slots:
		lengths = sorted((slot.end - slot.start).total_seconds() / 60 for slot in slots)
		info.slot_minutes = lengths[len(lengths) // 2]
		tomorrow_start = _local_midnight(today + timedelta(days=1), tz)
		info.has_tomorrow = any(slot.start >= tomorrow_start for slot in slots)

	current = next((slot for slot in slots if slot.start <= now_utc < slot.end), None)
	info.price_now = current.value if current is not None else state_price

	day_start = _local_midnight(today, tz)
	day_end = _local_midnight(today + timedelta(days=1), tz)
	today_slots = [slot for slot in slots if day_start <= slot.start < day_end]
	info.day_average = _weighted_mean(today_slots) if today_slots else None
	if info.day_average is None:
		info.day_average = _to_float(attributes.get("average"))

	hours = hourly_means(slots, tz)
	current_key = _hour_key(now_utc, tz)
	if current is None or current_key not in hours:
		# No slot covers now: only the absolute shed threshold can work.
		if source == "invalid":
			info.status = STATUS_INVALID
			info.notes.append("more than half of the price slots are unparsable")
		elif info.price_now is not None:
			info.status = STATUS_PARTIAL
		else:
			info.status = STATUS_MISSING
		info.hour_price = info.price_now
		_finish(info, settings, shed_latched)
		return info

	info.status = STATUS_FULL
	hour_price = hours[current_key]
	info.hour_price = hour_price

	today_hours = [value for key, value in hours.items() if day_start <= key < day_end]
	if len(today_hours) > 1:
		rank = sum(1 for value in today_hours if value < hour_price)
		info.percentile_today = rank / (len(today_hours) - 1)
	elif today_hours:
		info.percentile_today = 0.0

	lookahead = max(1, int(settings.lookahead_hours))
	forward = [
		value
		for key, value in hours.items()
		if current_key < key <= current_key + HOUR * lookahead
	]
	if forward:
		info.forward_average = sum(forward) / len(forward)

	window = [value for key, value in hours.items() if current_key <= key < current_key + HOUR * 24]
	info.min_price_24h = min(window)
	info.max_price_24h = max(window)
	spread = info.max_price_24h - info.min_price_24h
	info.price_position = 0.5 if spread <= 1e-9 else (hour_price - info.min_price_24h) / spread

	if info.forward_average is not None:
		info.relatively_cheap = hour_price < info.forward_average - settings.relative_margin
		info.relatively_expensive = hour_price > info.forward_average + settings.relative_margin

	average = info.day_average
	ratio_cheap = average is not None and _is_cheap_ratio(hour_price, average, settings.cheap_ratio)
	percentile_cheap = (
		info.percentile_today is not None and info.percentile_today <= settings.cheap_percentile
	)
	info.absolutely_cheap = bool(ratio_cheap or percentile_cheap)
	info.absolutely_expensive = average is not None and _is_expensive_ratio(
		hour_price, average, settings.expensive_ratio
	)
	info.cheap_now = info.relatively_cheap and info.absolutely_cheap
	info.expensive_now = info.relatively_expensive and info.absolutely_expensive

	if average is not None:
		for key, value in hours.items():
			if key <= current_key:
				continue
			hours_ahead = round((key - now_utc).total_seconds() / 3600, 2)
			if info.next_high_price_in_hours is None and _is_expensive_ratio(
				value, average, settings.expensive_ratio
			):
				info.next_high_price_in_hours = hours_ahead
			if info.next_low_price_in_hours is None and _is_cheap_ratio(
				value, average, settings.cheap_ratio
			):
				info.next_low_price_in_hours = hours_ahead

	_finish(info, settings, shed_latched)
	return info


def _finish(info: PriceInfo, settings: PriceSettings, shed_latched: bool) -> None:
	"""Super-expensive latch and the overall level."""
	if settings.shed_price is not None and info.price_now is not None:
		if shed_latched:
			info.super_expensive = info.price_now >= settings.shed_price - settings.shed_hysteresis
		else:
			info.super_expensive = info.price_now >= settings.shed_price
	if info.price_now is None:
		info.level = LEVEL_UNKNOWN
	elif info.super_expensive:
		info.level = LEVEL_SUPER_EXPENSIVE
	elif info.expensive_now:
		info.level = LEVEL_EXPENSIVE
	elif info.cheap_now:
		info.level = LEVEL_CHEAP
	else:
		info.level = LEVEL_NORMAL


def find_price_slots(attributes: Mapping[str, Any] | None, now: datetime) -> bool:
	"""True when the attributes contain usable price slots (config flow check)."""
	slots, _total, _bad, _source = parse_slots(attributes, now)
	return bool(slots)
