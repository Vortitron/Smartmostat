"""Smartmostat: price-aware thermostat control for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, Platform
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
	ATTR_MINUTES,
	CONFIG_MINOR_VERSION,
	CONFIG_VERSION,
	DOMAIN,
	SERVICE_CLEAR_OVERRIDE,
	SERVICE_EVALUATE,
	SERVICE_RESUME,
	SERVICE_SET_OVERRIDE,
	STORAGE_VERSION,
)
from .coordinator import SmartmostatController
from .migration import migrate

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type SmartmostatConfigEntry = ConfigEntry[SmartmostatController]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
	"""Register the entity services once."""
	service.async_register_platform_entity_service(
		hass,
		DOMAIN,
		SERVICE_SET_OVERRIDE,
		entity_domain=CLIMATE_DOMAIN,
		schema={
			vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
			vol.Optional(ATTR_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=0, max=7 * 24 * 60)),
		},
		func="async_service_set_override",
	)
	service.async_register_platform_entity_service(
		hass,
		DOMAIN,
		SERVICE_CLEAR_OVERRIDE,
		entity_domain=CLIMATE_DOMAIN,
		schema=None,
		func="async_service_clear_override",
	)
	service.async_register_platform_entity_service(
		hass,
		DOMAIN,
		SERVICE_RESUME,
		entity_domain=CLIMATE_DOMAIN,
		schema=None,
		func="async_service_resume",
	)
	service.async_register_platform_entity_service(
		hass,
		DOMAIN,
		SERVICE_EVALUATE,
		entity_domain=CLIMATE_DOMAIN,
		schema=None,
		func="async_service_evaluate",
		supports_response=SupportsResponse.OPTIONAL,
	)
	return True


async def async_setup_entry(hass: HomeAssistant, entry: SmartmostatConfigEntry) -> bool:
	"""Set up one Smartmostat zone."""
	controller = SmartmostatController(hass, entry)
	await controller.async_setup()
	entry.runtime_data = controller
	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
	entry.async_on_unload(entry.add_update_listener(_async_update_listener))
	await controller.async_start()
	return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartmostatConfigEntry) -> bool:
	"""Unload. The device is left exactly as it is."""
	unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
	if unloaded:
		await entry.runtime_data.async_shutdown()
	return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SmartmostatConfigEntry) -> None:
	"""Entry deleted: remove stored runtime state."""
	await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
	for issue in ("frost_while_off", "no_readings"):
		ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry.entry_id}")


async def _async_update_listener(hass: HomeAssistant, entry: SmartmostatConfigEntry) -> None:
	"""Reload on option changes, except the ones that apply live."""
	controller = entry.runtime_data
	if controller.only_live_changes(entry):
		controller.apply_live_options()
		return
	await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Migrate 0.1.0 (version 1) and 0.2.0 (version 2) entries to version 3."""
	if entry.version > CONFIG_VERSION:
		# Downgrade from a future version is not supported.
		return False
	if entry.version == CONFIG_VERSION:
		if entry.minor_version < CONFIG_MINOR_VERSION:
			hass.config_entries.async_update_entry(entry, minor_version=CONFIG_MINOR_VERSION)
		return True
	_LOGGER.info("Migrating Smartmostat entry %s from version %s", entry.title, entry.version)
	data, options = migrate(entry.version, entry.data, entry.options)
	hass.config_entries.async_update_entry(
		entry,
		data=data,
		options=options,
		version=CONFIG_VERSION,
		minor_version=CONFIG_MINOR_VERSION,
	)
	_LOGGER.info("Smartmostat entry %s migrated to version %s", entry.title, CONFIG_VERSION)
	return True
