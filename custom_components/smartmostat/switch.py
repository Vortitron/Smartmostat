"""Smartmostat price optimisation switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartmostatConfigEntry
from .coordinator import SmartmostatController
from .entity import SmartmostatEntity, build_device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
	hass: HomeAssistant,
	entry: SmartmostatConfigEntry,
	async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
	"""Add the switch."""
	controller = entry.runtime_data
	async_add_entities([PriceOptimisationSwitch(controller, build_device_info(hass, controller))])


class PriceOptimisationSwitch(SmartmostatEntity, SwitchEntity):
	"""Master price switch. Off behaves like a plain thermostat at the base target.

	The state lives in the entry options, so it survives restarts and shows in
	the options flow.
	"""

	_attr_translation_key = "price_optimisation"
	_attr_entity_category = EntityCategory.CONFIG

	def __init__(self, controller: SmartmostatController, device_info: Any) -> None:
		"""Create the switch."""
		super().__init__(controller, "price_optimisation", device_info)

	@property
	def is_on(self) -> bool:
		"""True when price optimisation is enabled."""
		return self.controller.settings.planner.price_optimisation

	async def async_turn_on(self, **kwargs: Any) -> None:
		"""Enable price optimisation."""
		await self.controller.async_set_price_optimisation(True)

	async def async_turn_off(self, **kwargs: Any) -> None:
		"""Disable price optimisation."""
		await self.controller.async_set_price_optimisation(False)
