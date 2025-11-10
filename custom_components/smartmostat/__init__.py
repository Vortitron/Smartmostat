"""The Smart Thermostat integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
	"""Set up the Smart Thermostat component."""
	return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Smart Thermostat from a config entry."""
	hass.data.setdefault(DOMAIN, {})
	hass.data[DOMAIN][entry.entry_id] = entry.data

	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
	
	if unload_ok:
		hass.data[DOMAIN].pop(entry.entry_id)

	return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload config entry."""
	await async_unload_entry(hass, entry)
	await async_setup_entry(hass, entry)

