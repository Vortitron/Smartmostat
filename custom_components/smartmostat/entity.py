"""Shared entity base for Smartmostat."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import SmartmostatController


def build_device_info(hass: HomeAssistant, controller: SmartmostatController) -> DeviceInfo:
	"""One service device per entry, linked to the wrapped device when known."""
	info = DeviceInfo(
		identifiers={(DOMAIN, controller.entry.entry_id)},
		name=controller.settings.name,
		manufacturer="Smartmostat",
		model=controller.settings.mode.replace("_", " ").capitalize(),
		entry_type=DeviceEntryType.SERVICE,
	)
	wrapped = controller.settings.target_climate or controller.settings.heater
	if wrapped:
		entity = er.async_get(hass).async_get(wrapped)
		if entity is not None and entity.device_id:
			device = dr.async_get(hass).async_get(entity.device_id)
			if device is not None and device.identifiers:
				info["via_device"] = next(iter(sorted(device.identifiers)))
	return info


class SmartmostatEntity(Entity):
	"""Base: pushes updates from the controller."""

	_attr_has_entity_name = True
	_attr_should_poll = False

	def __init__(self, controller: SmartmostatController, key: str, device_info: DeviceInfo) -> None:
		"""Create the entity."""
		self.controller = controller
		self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
		self._attr_device_info = device_info

	async def async_added_to_hass(self) -> None:
		"""Subscribe to controller updates."""
		await super().async_added_to_hass()
		self.async_on_remove(self.controller.async_add_listener(self._handle_update))

	@callback
	def _handle_update(self) -> None:
		self.async_write_ha_state()
