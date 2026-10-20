"""Pytest fixtures for Smartmostat."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartmostat.const import DOMAIN
from custom_components.smartmostat.coordinator import SmartmostatController

from .helpers import nordpool_attrs

# 20 Oct 2026, 10:00 in Stockholm (CEST, UTC+2).
FROZEN = "2026-10-20 08:00:00+00:00"
TODAY = date(2026, 10, 20)

# Cheap at 10:00 (0.30, dearer later), expensive in the evening.
CHEAP_MORNING = [
	0.80, 0.70, 0.60, 0.60, 0.60, 0.70, 1.50, 2.00,
	1.80, 1.20, 0.30, 0.90, 1.00, 1.10, 1.20, 1.40,
	1.90, 2.40, 2.80, 3.00, 2.60, 1.80, 1.20, 0.90,
]
# Expensive at 10:00 (2.9, cheaper later).
DEAR_MORNING = [
	0.80, 0.70, 0.60, 0.60, 0.60, 0.70, 1.50, 2.00,
	1.80, 2.40, 2.90, 1.00, 0.90, 0.80, 0.70, 0.60,
	0.60, 0.70, 0.80, 0.90, 0.80, 0.70, 0.60, 0.50,
]

SAM_ATTRS = {
	"hvac_modes": ["off", "heat_cool", "cool", "dry", "fan_only", "heat"],
	"min_temp": 16,
	"max_temp": 30,
	"target_temp_step": 0.5,
	"temperature": 22,
	"current_temperature": 20,
	"preset_modes": ["none", "quiet", "powerful", "heat_8_15"],
	"preset_mode": "none",
	"hvac_action": "heating",
	"friendly_name": "Sam",
}

REMOTE_DATA = {
	"name": "Living room",
	"control_mode": "remote_sensor",
	"target_climate": "climate.sam",
	"price_sensor": "sensor.nordpool",
	"room_sensors": ["sensor.living_room_temperature"],
	"room_aggregate": "first_available",
	"outdoor_sensor": "sensor.outdoor_temperature",
}

REMOTE_OPTIONS = {
	"comfort_temperature": 20.0,
	"eco_temperature": 16.0,
	"comfort_start": "19:00:00",
	"comfort_end": "23:00:00",
	"away_temperature": 10.0,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
	"""Load custom_components/ in every Home Assistant test."""
	return


@pytest.fixture
async def stockholm(hass: HomeAssistant, freezer) -> HomeAssistant:
	"""Frozen at 10:00 local on 20 Oct 2026 in Stockholm."""
	freezer.move_to(FROZEN)
	await hass.config.async_set_time_zone("Europe/Stockholm")
	return hass


def set_price(hass: HomeAssistant, hourly: list[float] = CHEAP_MORNING, state: str | None = None) -> None:
	"""Publish a HACS Nordpool style sensor (15-minute slots)."""
	attrs = nordpool_attrs(TODAY, hourly, minutes=15)
	hass.states.async_set("sensor.nordpool", state if state is not None else str(hourly[10]), attrs)


def set_room(hass: HomeAssistant, value: Any, entity_id: str = "sensor.living_room_temperature") -> None:
	"""Room sensor reading."""
	hass.states.async_set(entity_id, str(value), {"unit_of_measurement": "°C", "device_class": "temperature"})


def set_device(hass: HomeAssistant, state: str = "heat", **attrs: Any) -> None:
	"""climate.sam-like device."""
	hass.states.async_set("climate.sam", state, {**SAM_ATTRS, **attrs})


class RecordedCall:
	"""A service call Smartmostat sent to a device."""

	def __init__(self, domain: str, service: str, data: dict[str, Any]) -> None:
		"""Record it."""
		self.domain = domain
		self.service = service
		self.data = dict(data)


@pytest.fixture
def climate_calls() -> dict[str, list[RecordedCall]]:
	"""Capture every device command Smartmostat sends.

	Patching the controller's call helper (rather than mocking the climate
	services) keeps the real climate services working for Smartmostat's own
	entity. Climate calls are keyed by service, others by "domain.service".
	"""
	calls: dict[str, list[RecordedCall]] = defaultdict(list)

	async def record(self, domain: str, service: str, data: dict[str, Any]) -> bool:
		key = service if domain == "climate" else f"{domain}.{service}"
		calls[key].append(RecordedCall(domain, service, data))
		return True

	with patch.object(SmartmostatController, "_call", record):
		yield calls


@pytest.fixture
def sam_house(stockholm: HomeAssistant, climate_calls) -> HomeAssistant:
	"""Sam's setup: heat pump, living-room sensor, outdoor sensor, Nordpool."""
	hass = stockholm
	set_device(hass)
	set_room(hass, 15)
	set_room(hass, -2, "sensor.outdoor_temperature")
	set_price(hass)
	return hass


@pytest.fixture
def make_entry(hass: HomeAssistant) -> Callable[..., MockConfigEntry]:
	"""Create (not set up) a version 3 entry."""

	def _make(data: dict | None = None, options: dict | None = None, **kwargs: Any) -> MockConfigEntry:
		entry = MockConfigEntry(
			domain=DOMAIN,
			title=(data or REMOTE_DATA).get("name", "Smartmostat"),
			data=dict(data or REMOTE_DATA),
			options=dict(REMOTE_OPTIONS if options is None else options),
			version=3,
			minor_version=1,
			**kwargs,
		)
		entry.add_to_hass(hass)
		return entry

	return _make


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
	"""Set up and let the first evaluation finish."""
	assert await hass.config_entries.async_setup(entry.entry_id)
	await hass.async_block_till_done()
