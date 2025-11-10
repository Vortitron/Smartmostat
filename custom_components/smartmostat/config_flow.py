"""Config flow for Smart Thermostat integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
	BooleanSelector,
	EntitySelector,
	EntitySelectorConfig,
	NumberSelector,
	NumberSelectorConfig,
	NumberSelectorMode,
	SelectOptionDict,
	SelectSelector,
	SelectSelectorConfig,
)

from .const import (
	CONTROL_MODE_TEMPERATURE,
	CONTROL_MODE_TOLERANCE,
	DEFAULT_ALLOW_HVAC_MODE_CHANGES,
	DEFAULT_BASE_STOP_HEAT_OFFSET,
	DEFAULT_COOL_INDOOR_MIN,
	DEFAULT_COOL_INDOOR_THRESHOLD,
	DEFAULT_COOL_OFFSET,
	DEFAULT_COOL_OUTDOOR_THRESHOLD,
	DEFAULT_CONTROL_MODE,
	DEFAULT_ENABLE_DIAGNOSTIC_LOGGING,
	DEFAULT_ENABLE_FAN_ONLY_MODE,
	DEFAULT_FAN_ONLY_DIFF,
	DEFAULT_HEAT_OFFSET,
	DEFAULT_LOOKAHEAD_HOURS,
	DEFAULT_MAX_OFFSET,
	DEFAULT_MAX_STOP_HEAT_OFFSET,
	DEFAULT_MAX_TOLERANCE,
	DEFAULT_MIN_OFFSET,
	DEFAULT_MIN_TOLERANCE,
	DEFAULT_PRECONDITIONING_ENABLED,
	DEFAULT_TEMP_TOLERANCE,
	DOMAIN,
	CONF_ALLOW_HVAC_MODE_CHANGES,
	CONF_BASE_STOP_HEAT_OFFSET,
	CONF_COOLER,
	CONF_COOL_INDOOR_MIN,
	CONF_COOL_INDOOR_THRESHOLD,
	CONF_COOL_OFFSET,
	CONF_COOL_OUTDOOR_THRESHOLD,
	CONF_CONTROL_MODE,
	CONF_ENABLE_DIAGNOSTIC_LOGGING,
	CONF_ENABLE_FAN_ONLY_MODE,
	CONF_HEATER,
	CONF_HEAT_OFFSET,
	CONF_INTERNAL_SENSOR,
	CONF_LOOKAHEAD_HOURS,
	CONF_MAX_OFFSET,
	CONF_MAX_STOP_HEAT_OFFSET,
	CONF_MAX_TOLERANCE,
	CONF_MIN_OFFSET,
	CONF_MIN_TOLERANCE,
	CONF_OUTDOOR_SENSOR,
	CONF_PRECONDITIONING_ENABLED,
	CONF_PRICE_SENSOR,
	CONF_TARGET_CLIMATE,
	CONF_TARGET_SENSOR,
	CONF_TEMP_TOLERANCE,
	CONF_FAN_ONLY_DIFF,
)

_LOGGER = logging.getLogger(__name__)


def _build_schema(defaults: dict[str, Any]) -> vol.Schema:
	"""Build the configuration schema."""
	control_mode_default = defaults.get(CONF_CONTROL_MODE, DEFAULT_CONTROL_MODE)
	return vol.Schema(
		{
			vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Smart Thermostat")): str,
			vol.Required(
				CONF_CONTROL_MODE,
				default=control_mode_default,
			): SelectSelector(
				SelectSelectorConfig(
					options=[
						SelectOptionDict(
							value=CONTROL_MODE_TOLERANCE,
							label="Tolerance (switch control)",
						),
						SelectOptionDict(
							value=CONTROL_MODE_TEMPERATURE,
							label="Temperature (set-point control)",
						),
					],
					mode="dropdown",
				)
			),
			vol.Optional(
				CONF_TARGET_SENSOR,
				default=defaults.get(CONF_TARGET_SENSOR),
			): EntitySelector(EntitySelectorConfig(domain="sensor")),
			vol.Optional(
				CONF_INTERNAL_SENSOR,
				default=defaults.get(CONF_INTERNAL_SENSOR),
			): EntitySelector(EntitySelectorConfig(domain="sensor")),
			vol.Optional(
				CONF_OUTDOOR_SENSOR,
				default=defaults.get(CONF_OUTDOOR_SENSOR),
			): EntitySelector(EntitySelectorConfig(domain="sensor")),
			vol.Optional(
				CONF_TARGET_CLIMATE,
				default=defaults.get(CONF_TARGET_CLIMATE),
			): EntitySelector(EntitySelectorConfig(domain="climate")),
			vol.Optional(
				CONF_HEATER,
				default=defaults.get(CONF_HEATER),
			): EntitySelector(
				EntitySelectorConfig(domain=["switch", "climate", "fan", "input_boolean"])
			),
			vol.Optional(
				CONF_COOLER,
				default=defaults.get(CONF_COOLER),
			): EntitySelector(
				EntitySelectorConfig(domain=["switch", "climate", "fan", "input_boolean"])
			),
			vol.Required(
				CONF_PRICE_SENSOR,
				default=defaults.get(CONF_PRICE_SENSOR),
			): EntitySelector(EntitySelectorConfig(domain="sensor")),
			vol.Optional(
				CONF_MAX_TOLERANCE,
				default=defaults.get(CONF_MAX_TOLERANCE, DEFAULT_MAX_TOLERANCE),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=5.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_MIN_TOLERANCE,
				default=defaults.get(CONF_MIN_TOLERANCE, DEFAULT_MIN_TOLERANCE),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=5.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_MAX_OFFSET,
				default=defaults.get(CONF_MAX_OFFSET, DEFAULT_MAX_OFFSET),
			): NumberSelector(
				NumberSelectorConfig(
					min=-10.0,
					max=10.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_MIN_OFFSET,
				default=defaults.get(CONF_MIN_OFFSET, DEFAULT_MIN_OFFSET),
			): NumberSelector(
				NumberSelectorConfig(
					min=-10.0,
					max=10.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_HEAT_OFFSET,
				default=defaults.get(CONF_HEAT_OFFSET, DEFAULT_HEAT_OFFSET),
			): NumberSelector(
				NumberSelectorConfig(
					min=-10.0,
					max=10.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_COOL_OFFSET,
				default=defaults.get(CONF_COOL_OFFSET, DEFAULT_COOL_OFFSET),
			): NumberSelector(
				NumberSelectorConfig(
					min=-10.0,
					max=10.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_BASE_STOP_HEAT_OFFSET,
				default=defaults.get(
					CONF_BASE_STOP_HEAT_OFFSET, DEFAULT_BASE_STOP_HEAT_OFFSET
				),
			): NumberSelector(
				NumberSelectorConfig(
					min=-10.0,
					max=0.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_MAX_STOP_HEAT_OFFSET,
				default=defaults.get(CONF_MAX_STOP_HEAT_OFFSET, DEFAULT_MAX_STOP_HEAT_OFFSET),
			): NumberSelector(
				NumberSelectorConfig(
					min=-20.0,
					max=0.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_TEMP_TOLERANCE,
				default=defaults.get(CONF_TEMP_TOLERANCE, DEFAULT_TEMP_TOLERANCE),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=5.0,
					step=0.1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_FAN_ONLY_DIFF,
				default=defaults.get(CONF_FAN_ONLY_DIFF, DEFAULT_FAN_ONLY_DIFF),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=10.0,
					step=0.5,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_COOL_INDOOR_THRESHOLD,
				default=defaults.get(
					CONF_COOL_INDOOR_THRESHOLD, DEFAULT_COOL_INDOOR_THRESHOLD
				),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=40.0,
					step=0.5,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_COOL_OUTDOOR_THRESHOLD,
				default=defaults.get(
					CONF_COOL_OUTDOOR_THRESHOLD, DEFAULT_COOL_OUTDOOR_THRESHOLD
				),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=40.0,
					step=0.5,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_COOL_INDOOR_MIN,
				default=defaults.get(CONF_COOL_INDOOR_MIN, DEFAULT_COOL_INDOOR_MIN),
			): NumberSelector(
				NumberSelectorConfig(
					min=0.0,
					max=30.0,
					step=0.5,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="°C",
				)
			),
			vol.Optional(
				CONF_ENABLE_FAN_ONLY_MODE,
				default=defaults.get(CONF_ENABLE_FAN_ONLY_MODE, DEFAULT_ENABLE_FAN_ONLY_MODE),
			): BooleanSelector(),
			vol.Optional(
				CONF_ALLOW_HVAC_MODE_CHANGES,
				default=defaults.get(
					CONF_ALLOW_HVAC_MODE_CHANGES, DEFAULT_ALLOW_HVAC_MODE_CHANGES
				),
			): BooleanSelector(),
			vol.Optional(
				CONF_ENABLE_DIAGNOSTIC_LOGGING,
				default=defaults.get(
					CONF_ENABLE_DIAGNOSTIC_LOGGING, DEFAULT_ENABLE_DIAGNOSTIC_LOGGING
				),
			): BooleanSelector(),
			vol.Optional(
				CONF_LOOKAHEAD_HOURS,
				default=defaults.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS),
			): NumberSelector(
				NumberSelectorConfig(
					min=1,
					max=24,
					step=1,
					mode=NumberSelectorMode.BOX,
					unit_of_measurement="hours",
				)
			),
			vol.Optional(
				CONF_PRECONDITIONING_ENABLED,
				default=defaults.get(
					CONF_PRECONDITIONING_ENABLED, DEFAULT_PRECONDITIONING_ENABLED
				),
			): BooleanSelector(),
		}
	)


def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
	"""Validate user input."""
	errors: dict[str, str] = {}
	control_mode = data.get(CONF_CONTROL_MODE, DEFAULT_CONTROL_MODE)

	price_sensor = data.get(CONF_PRICE_SENSOR)
	if not price_sensor or not hass.states.get(price_sensor):
		errors[CONF_PRICE_SENSOR] = "entity_not_found"
	else:
		price_state = hass.states.get(price_sensor)
		if not price_state or not price_state.attributes.get("raw_today"):
			errors[CONF_PRICE_SENSOR] = "invalid_price_sensor"

	remote_sensor = data.get(CONF_TARGET_SENSOR)
	if not remote_sensor or not hass.states.get(remote_sensor):
		errors[CONF_TARGET_SENSOR] = "entity_not_found"

	if control_mode == CONTROL_MODE_TOLERANCE:
		if not data.get(CONF_HEATER) and not data.get(CONF_COOLER):
			errors["base"] = "missing_output_device"
	elif control_mode == CONTROL_MODE_TEMPERATURE:
		target_climate = data.get(CONF_TARGET_CLIMATE)
		if not target_climate or not hass.states.get(target_climate):
			errors[CONF_TARGET_CLIMATE] = "entity_not_found"
	else:
		errors[CONF_CONTROL_MODE] = "invalid_control_mode"

	return errors


class SmartmostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
	"""Handle a config flow for Smart Thermostat."""

	VERSION = 2

	async def async_step_user(
		self, user_input: dict[str, Any] | None = None
	) -> config_entries.FlowResult:
		"""Handle the initial step."""
		errors: dict[str, str] = {}
		suggested_sensor = self._find_nordpool_sensor()

		if user_input is not None:
			errors = _validate_input(self.hass, user_input)
			if not errors:
				return self.async_create_entry(
					title=user_input[CONF_NAME],
					data=user_input,
				)

		defaults: dict[str, Any] = {
			CONF_NAME: user_input.get(CONF_NAME) if user_input else "Smart Thermostat",
			CONF_CONTROL_MODE: user_input.get(CONF_CONTROL_MODE, DEFAULT_CONTROL_MODE)
			if user_input
			else DEFAULT_CONTROL_MODE,
			CONF_TARGET_SENSOR: user_input.get(CONF_TARGET_SENSOR) if user_input else None,
			CONF_INTERNAL_SENSOR: user_input.get(CONF_INTERNAL_SENSOR) if user_input else None,
			CONF_OUTDOOR_SENSOR: user_input.get(CONF_OUTDOOR_SENSOR) if user_input else None,
			CONF_TARGET_CLIMATE: user_input.get(CONF_TARGET_CLIMATE) if user_input else None,
			CONF_PRICE_SENSOR: user_input.get(CONF_PRICE_SENSOR, suggested_sensor)
			if user_input
			else suggested_sensor,
			CONF_HEATER: user_input.get(CONF_HEATER) if user_input else None,
			CONF_COOLER: user_input.get(CONF_COOLER) if user_input else None,
			CONF_MAX_TOLERANCE: user_input.get(CONF_MAX_TOLERANCE, DEFAULT_MAX_TOLERANCE)
			if user_input
			else DEFAULT_MAX_TOLERANCE,
			CONF_MIN_TOLERANCE: user_input.get(CONF_MIN_TOLERANCE, DEFAULT_MIN_TOLERANCE)
			if user_input
			else DEFAULT_MIN_TOLERANCE,
			CONF_MAX_OFFSET: user_input.get(CONF_MAX_OFFSET, DEFAULT_MAX_OFFSET)
			if user_input
			else DEFAULT_MAX_OFFSET,
			CONF_MIN_OFFSET: user_input.get(CONF_MIN_OFFSET, DEFAULT_MIN_OFFSET)
			if user_input
			else DEFAULT_MIN_OFFSET,
			CONF_HEAT_OFFSET: user_input.get(CONF_HEAT_OFFSET, DEFAULT_HEAT_OFFSET)
			if user_input
			else DEFAULT_HEAT_OFFSET,
			CONF_COOL_OFFSET: user_input.get(CONF_COOL_OFFSET, DEFAULT_COOL_OFFSET)
			if user_input
			else DEFAULT_COOL_OFFSET,
			CONF_BASE_STOP_HEAT_OFFSET: user_input.get(
				CONF_BASE_STOP_HEAT_OFFSET, DEFAULT_BASE_STOP_HEAT_OFFSET
			)
			if user_input
			else DEFAULT_BASE_STOP_HEAT_OFFSET,
			CONF_MAX_STOP_HEAT_OFFSET: user_input.get(
				CONF_MAX_STOP_HEAT_OFFSET, DEFAULT_MAX_STOP_HEAT_OFFSET
			)
			if user_input
			else DEFAULT_MAX_STOP_HEAT_OFFSET,
			CONF_TEMP_TOLERANCE: user_input.get(CONF_TEMP_TOLERANCE, DEFAULT_TEMP_TOLERANCE)
			if user_input
			else DEFAULT_TEMP_TOLERANCE,
			CONF_FAN_ONLY_DIFF: user_input.get(CONF_FAN_ONLY_DIFF, DEFAULT_FAN_ONLY_DIFF)
			if user_input
			else DEFAULT_FAN_ONLY_DIFF,
			CONF_COOL_INDOOR_THRESHOLD: user_input.get(
				CONF_COOL_INDOOR_THRESHOLD, DEFAULT_COOL_INDOOR_THRESHOLD
			)
			if user_input
			else DEFAULT_COOL_INDOOR_THRESHOLD,
			CONF_COOL_OUTDOOR_THRESHOLD: user_input.get(
				CONF_COOL_OUTDOOR_THRESHOLD, DEFAULT_COOL_OUTDOOR_THRESHOLD
			)
			if user_input
			else DEFAULT_COOL_OUTDOOR_THRESHOLD,
			CONF_COOL_INDOOR_MIN: user_input.get(
				CONF_COOL_INDOOR_MIN, DEFAULT_COOL_INDOOR_MIN
			)
			if user_input
			else DEFAULT_COOL_INDOOR_MIN,
			CONF_ENABLE_FAN_ONLY_MODE: user_input.get(
				CONF_ENABLE_FAN_ONLY_MODE, DEFAULT_ENABLE_FAN_ONLY_MODE
			)
			if user_input
			else DEFAULT_ENABLE_FAN_ONLY_MODE,
			CONF_ALLOW_HVAC_MODE_CHANGES: user_input.get(
				CONF_ALLOW_HVAC_MODE_CHANGES, DEFAULT_ALLOW_HVAC_MODE_CHANGES
			)
			if user_input
			else DEFAULT_ALLOW_HVAC_MODE_CHANGES,
			CONF_ENABLE_DIAGNOSTIC_LOGGING: user_input.get(
				CONF_ENABLE_DIAGNOSTIC_LOGGING, DEFAULT_ENABLE_DIAGNOSTIC_LOGGING
			)
			if user_input
			else DEFAULT_ENABLE_DIAGNOSTIC_LOGGING,
			CONF_LOOKAHEAD_HOURS: user_input.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)
			if user_input
			else DEFAULT_LOOKAHEAD_HOURS,
			CONF_PRECONDITIONING_ENABLED: user_input.get(
				CONF_PRECONDITIONING_ENABLED, DEFAULT_PRECONDITIONING_ENABLED
			)
			if user_input
			else DEFAULT_PRECONDITIONING_ENABLED,
		}

		return self.async_show_form(
			step_id="user",
			data_schema=_build_schema(defaults),
			errors=errors,
		)

	@staticmethod
	@callback
	def async_get_options_flow(
		config_entry: config_entries.ConfigEntry,
	) -> SmartmostatOptionsFlowHandler:
		"""Get the options flow for this handler."""
		return SmartmostatOptionsFlowHandler(config_entry)

	def _find_nordpool_sensor(self) -> str | None:
		"""Try to find a suitable Nordpool sensor."""
		for state in self.hass.states.async_all("sensor"):
			if "nordpool" in state.entity_id and "kwh" in state.entity_id:
				if state.attributes.get("raw_today") and state.attributes.get("average"):
					return state.entity_id
		return None


class SmartmostatOptionsFlowHandler(config_entries.OptionsFlow):
	"""Handle options flow for Smart Thermostat."""

	def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
		"""Initialise options flow."""
		self.config_entry = config_entry

	async def async_step_init(
		self, user_input: dict[str, Any] | None = None
	) -> config_entries.FlowResult:
		"""Manage the options."""
		current = {**self.config_entry.data, **self.config_entry.options}

		if user_input is not None:
			merged = {**current, **user_input}
			errors = _validate_input(self.hass, merged)
			if not errors:
				return self.async_create_entry(title="", data=user_input)
		else:
			errors = {}

		defaults = {**current, **(user_input or {})}

		return self.async_show_form(
			step_id="init",
			data_schema=_build_schema(defaults),
			errors=errors,
		)

