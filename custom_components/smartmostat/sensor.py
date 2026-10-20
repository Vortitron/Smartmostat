"""Smartmostat sensors: control target, headline, reason and price diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
	SensorDeviceClass,
	SensorEntity,
	SensorEntityDescription,
	SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartmostatConfigEntry
from .const import ATTR_STATUS, PRICE_LEVELS, REASONS
from .coordinator import SmartmostatController
from .entity import SmartmostatEntity, build_device_info

PARALLEL_UPDATES = 0


def _control_target(c: SmartmostatController) -> float | None:
	return c.plan.control_target if c.plan else None


def _headline(c: SmartmostatController) -> str | None:
	return c.decision.headline[:255] if c.decision else None


def _reason(c: SmartmostatController) -> str | None:
	return c.decision.reason if c.decision else None


def _price_level(c: SmartmostatController) -> str | None:
	return c.price.level if c.price else None


def _price_position(c: SmartmostatController) -> float | None:
	if c.price is None or c.price.price_position is None:
		return None
	return round(c.price.price_position * 100, 1)


def _override_until(c: SmartmostatController) -> datetime | None:
	if c.override is not None and c.override.until is not None:
		return c.override.until
	return c.paused_until


def _headline_attrs(c: SmartmostatController) -> dict[str, Any]:
	attrs: dict[str, Any] = {ATTR_STATUS: c.status}
	if c.decision is not None:
		attrs["action"] = c.decision.action
	return attrs


@dataclass(frozen=True, kw_only=True)
class SmartmostatSensorDescription(SensorEntityDescription):
	"""Describes a Smartmostat sensor."""

	value_fn: Callable[[SmartmostatController], Any]
	attrs_fn: Callable[[SmartmostatController], dict[str, Any]] | None = None


SENSORS: tuple[SmartmostatSensorDescription, ...] = (
	SmartmostatSensorDescription(
		key="control_target",
		translation_key="control_target",
		device_class=SensorDeviceClass.TEMPERATURE,
		state_class=SensorStateClass.MEASUREMENT,
		native_unit_of_measurement=UnitOfTemperature.CELSIUS,
		suggested_display_precision=1,
		value_fn=_control_target,
	),
	SmartmostatSensorDescription(
		key="headline",
		translation_key="headline",
		value_fn=_headline,
		attrs_fn=_headline_attrs,
	),
	SmartmostatSensorDescription(
		key="reason",
		translation_key="reason",
		device_class=SensorDeviceClass.ENUM,
		options=list(REASONS),
		value_fn=_reason,
	),
	SmartmostatSensorDescription(
		key="price_level",
		translation_key="price_level",
		device_class=SensorDeviceClass.ENUM,
		options=list(PRICE_LEVELS),
		value_fn=_price_level,
	),
	SmartmostatSensorDescription(
		key="price_position",
		translation_key="price_position",
		native_unit_of_measurement=PERCENTAGE,
		state_class=SensorStateClass.MEASUREMENT,
		entity_category=EntityCategory.DIAGNOSTIC,
		suggested_display_precision=0,
		value_fn=_price_position,
	),
	SmartmostatSensorDescription(
		key="override_until",
		translation_key="override_until",
		device_class=SensorDeviceClass.TIMESTAMP,
		entity_category=EntityCategory.DIAGNOSTIC,
		value_fn=_override_until,
	),
)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: SmartmostatConfigEntry,
	async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
	"""Add the sensors."""
	controller = entry.runtime_data
	info = build_device_info(hass, controller)
	async_add_entities(SmartmostatSensor(controller, description, info) for description in SENSORS)


class SmartmostatSensor(SmartmostatEntity, SensorEntity):
	"""A Smartmostat diagnostic sensor."""

	entity_description: SmartmostatSensorDescription

	def __init__(self, controller: SmartmostatController, description: SmartmostatSensorDescription, device_info: Any) -> None:
		"""Create the sensor."""
		super().__init__(controller, description.key, device_info)
		self.entity_description = description

	@property
	def native_value(self) -> Any:
		"""Current value."""
		return self.entity_description.value_fn(self.controller)

	@property
	def extra_state_attributes(self) -> dict[str, Any] | None:
		"""Extra attributes (the headline's full status line)."""
		if self.entity_description.attrs_fn is None:
			return None
		return self.entity_description.attrs_fn(self.controller)
