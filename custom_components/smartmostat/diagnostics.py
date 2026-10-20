"""Diagnostics for Smartmostat."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SmartmostatConfigEntry


async def async_get_config_entry_diagnostics(
	hass: HomeAssistant, entry: SmartmostatConfigEntry
) -> dict[str, Any]:
	"""Entry data, options and the last decision. Nothing secret is stored."""
	controller = entry.runtime_data
	return {
		"entry": {
			"version": entry.version,
			"minor_version": entry.minor_version,
			"data": dict(entry.data),
			"options": dict(entry.options),
		},
		"runtime": controller.diagnostics(),
	}
