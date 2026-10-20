"""Config, reconfigure and options flows for Smartmostat."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
	SOURCE_RECONFIGURE,
	ConfigEntry,
	ConfigFlow,
	ConfigFlowResult,
	OptionsFlow,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.selector import (
	BooleanSelector,
	EntitySelector,
	EntitySelectorConfig,
	NumberSelector,
	NumberSelectorConfig,
	NumberSelectorMode,
	SelectSelector,
	SelectSelectorConfig,
	SelectSelectorMode,
	TextSelector,
	TimeSelector,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
	AGGREGATE_FIRST,
	AGGREGATES,
	CONF_ALLOW_HVAC_MODE_CHANGES,
	CONF_AWAY_DEVICE_PRESET,
	CONF_AWAY_TEMPERATURE,
	CONF_BASE_STOP_HEAT_OFFSET,
	CONF_BOOST_SKIP_MARGIN,
	CONF_CHEAP_BOOST,
	CONF_CHEAP_PERCENTILE,
	CONF_CHEAP_RATIO,
	CONF_COLD_OUTDOOR,
	CONF_COMFORT_END,
	CONF_COMFORT_START,
	CONF_COMFORT_TEMPERATURE,
	CONF_CONTROL_MODE,
	CONF_COOL_COMPRESSOR_OUTDOOR,
	CONF_COOL_COMPRESSOR_ROOM,
	CONF_COOL_FAN_ROOM,
	CONF_COOL_OFFSET,
	CONF_COOL_OUTDOOR_GATE,
	CONF_COOLER,
	CONF_COOLING,
	CONF_DIAGNOSTIC_EVENTS,
	CONF_DRY_RUN,
	CONF_ECO_TEMPERATURE,
	CONF_EXPENSIVE_CUT,
	CONF_EXPENSIVE_RATIO,
	CONF_FALLBACK_OFFSET,
	CONF_FAN_ONLY_DIFF,
	CONF_FORECAST_HOURS,
	CONF_FROST_PROTECTION,
	CONF_FROST_TEMPERATURE,
	CONF_HEAT_OFFSET,
	CONF_HEATER,
	CONF_HOT_DAY_MAX,
	CONF_HYSTERESIS,
	CONF_IDLE_MODE,
	CONF_INTERNAL_SENSOR,
	CONF_LOOKAHEAD_HOURS,
	CONF_MAX_STOP_HEAT_OFFSET,
	CONF_MAX_TARGET,
	CONF_MIN_CYCLE_MINUTES,
	CONF_MIN_TARGET,
	CONF_MORNING_END,
	CONF_NAME,
	CONF_OUTDOOR_SENSOR,
	CONF_OVERRIDE_MINUTES,
	CONF_PREWARM_HOURS,
	CONF_PREWARM_HOURS_COLD,
	CONF_PRICE_OPTIMISATION,
	CONF_PRICE_SENSOR,
	CONF_RELATIVE_MARGIN,
	CONF_ROOM_AGGREGATE,
	CONF_ROOM_MAX,
	CONF_ROOM_SENSORS,
	CONF_SHED_FLOOR,
	CONF_SHED_HYSTERESIS,
	CONF_SHED_PRICE,
	CONF_STALE_MINUTES,
	CONF_TARGET_CLIMATE,
	CONF_TEMP_TOLERANCE,
	CONF_THERMAL_H,
	CONF_THERMAL_H_ENTITY,
	CONF_THERMAL_K,
	CONF_THERMAL_K_ENTITY,
	CONF_WEATHER_ENTITY,
	CONFIG_MINOR_VERSION,
	CONFIG_VERSION,
	CONTROL_MODES,
	DEFAULTS,
	DOMAIN,
	IDLE_MODES,
	MODE_REMOTE_SENSOR,
	MODE_SETPOINT,
	MODE_SWITCH,
)
from .price import find_price_slots

SWITCH_DOMAINS = ["switch", "input_boolean", "fan", "climate"]


def _num(minimum: float, maximum: float, step: float | str, unit: str | None = None) -> NumberSelector:
	config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
	if unit is not None:
		config["unit_of_measurement"] = unit
	return NumberSelector(config)


TEMP = "°C"


def _temp(minimum: float = 0, maximum: float = 35) -> NumberSelector:
	return _num(minimum, maximum, 0.1, TEMP)


def _offset(minimum: float = -15, maximum: float = 15) -> NumberSelector:
	return _num(minimum, maximum, 0.1, TEMP)


def _sensor(multiple: bool = False) -> EntitySelector:
	return EntitySelector(EntitySelectorConfig(domain="sensor", multiple=multiple))


def _select(options: list[str], key: str) -> SelectSelector:
	return SelectSelector(
		SelectSelectorConfig(options=options, translation_key=key, mode=SelectSelectorMode.DROPDOWN)
	)


# Each options step: (key, selector, nullable). Nullable keys may be cleared.
OptionField = tuple[str, Any, bool]

COMFORT_FIELDS: list[OptionField] = [
	(CONF_COMFORT_TEMPERATURE, _temp(5, 30), False),
	(CONF_ECO_TEMPERATURE, _temp(5, 30), True),
	(CONF_COMFORT_START, TimeSelector(), True),
	(CONF_COMFORT_END, TimeSelector(), True),
	(CONF_AWAY_TEMPERATURE, _temp(5, 20), False),
	(CONF_OVERRIDE_MINUTES, _num(0, 1440, 1, "min"), False),
	(CONF_AWAY_DEVICE_PRESET, TextSelector(), True),
	(CONF_MIN_TARGET, _temp(0, 20), False),
	(CONF_MAX_TARGET, _temp(15, 35), False),
]

PRICE_FIELDS: list[OptionField] = [
	(CONF_PRICE_OPTIMISATION, BooleanSelector(), False),
	(CONF_LOOKAHEAD_HOURS, _num(1, 24, 1, "h"), False),
	(CONF_RELATIVE_MARGIN, _num(0, 10, 0.01), False),
	(CONF_CHEAP_RATIO, _num(0, 2, 0.01), False),
	(CONF_CHEAP_PERCENTILE, _num(0, 1, 0.01), False),
	(CONF_EXPENSIVE_RATIO, _num(0, 5, 0.01), False),
	(CONF_CHEAP_BOOST, _offset(0, 10), False),
	(CONF_BOOST_SKIP_MARGIN, _offset(-1, 5), False),
	(CONF_EXPENSIVE_CUT, _offset(0, 10), False),
	(CONF_PREWARM_HOURS, _num(0, 12, 0.5, "h"), False),
	(CONF_PREWARM_HOURS_COLD, _num(0, 12, 0.5, "h"), False),
	(CONF_COLD_OUTDOOR, _temp(-30, 25), False),
	(CONF_HOT_DAY_MAX, _temp(10, 45), False),
	(CONF_MORNING_END, TimeSelector(), False),
	(CONF_SHED_PRICE, _num(-100, 1000, 0.01), True),
	(CONF_SHED_HYSTERESIS, _num(0, 100, 0.01), False),
	(CONF_SHED_FLOOR, _temp(5, 30), False),
]

REMOTE_FIELDS: list[OptionField] = [
	(CONF_TEMP_TOLERANCE, _offset(0, 5), False),
	(CONF_HEAT_OFFSET, _offset(0, 10), False),
	(CONF_BASE_STOP_HEAT_OFFSET, _offset(-15, 0), False),
	(CONF_MAX_STOP_HEAT_OFFSET, _offset(-15, 0), False),
	(CONF_ROOM_MAX, _temp(15, 35), False),
	(CONF_FAN_ONLY_DIFF, _offset(0, 10), False),
	(CONF_IDLE_MODE, _select(IDLE_MODES, "idle_mode"), False),
	(CONF_FALLBACK_OFFSET, _offset(-5, 5), False),
	(CONF_ALLOW_HVAC_MODE_CHANGES, BooleanSelector(), False),
]

SETPOINT_FIELDS: list[OptionField] = [
	(CONF_ALLOW_HVAC_MODE_CHANGES, BooleanSelector(), False),
]

SWITCH_FIELDS: list[OptionField] = [
	(CONF_HYSTERESIS, _offset(0.05, 5), False),
	(CONF_MIN_CYCLE_MINUTES, _num(0, 60, 1, "min"), False),
]

COOLING_FIELDS: list[OptionField] = [
	(CONF_COOLING, BooleanSelector(), False),
	(CONF_COOL_FAN_ROOM, _temp(15, 35), False),
	(CONF_COOL_OUTDOOR_GATE, _temp(0, 45), False),
	(CONF_COOL_COMPRESSOR_ROOM, _temp(15, 35), False),
	(CONF_COOL_COMPRESSOR_OUTDOOR, _temp(0, 45), False),
	(CONF_COOL_OFFSET, _offset(-10, 0), False),
]

SAFETY_FIELDS: list[OptionField] = [
	(CONF_FROST_PROTECTION, BooleanSelector(), False),
	(CONF_FROST_TEMPERATURE, _temp(0, 12), False),
	(CONF_STALE_MINUTES, _num(0, 1440, 1, "min"), False),
	(CONF_DIAGNOSTIC_EVENTS, BooleanSelector(), False),
]

ADVANCED_FIELDS: list[OptionField] = [
	(CONF_WEATHER_ENTITY, EntitySelector(EntitySelectorConfig(domain="weather")), True),
	(CONF_FORECAST_HOURS, _num(1, 24, 1, "h"), False),
	(CONF_THERMAL_K, _num(0, 5, "any"), True),
	(CONF_THERMAL_K_ENTITY, EntitySelector(EntitySelectorConfig(domain=["input_number", "sensor"])), True),
	(CONF_THERMAL_H, _num(0, 20, "any"), True),
	(CONF_THERMAL_H_ENTITY, EntitySelector(EntitySelectorConfig(domain=["input_number", "sensor"])), True),
	(CONF_DRY_RUN, BooleanSelector(), False),
]


def _options_schema(fields: list[OptionField], current: dict[str, Any]) -> vol.Schema:
	schema: dict[Any, Any] = {}
	for key, selector, nullable in fields:
		value = current.get(key, DEFAULTS[key])
		if nullable:
			marker = vol.Optional(key, description={"suggested_value": value}) if value is not None else vol.Optional(key)
		else:
			if value is None:
				value = DEFAULTS[key]
			marker = vol.Required(key, default=value) if value is not None else vol.Required(key)
		schema[marker] = selector
	return vol.Schema(schema)


def _clean(fields: list[OptionField], user_input: dict[str, Any]) -> dict[str, Any]:
	"""Normalise one step's answers; cleared nullable fields become None."""
	cleaned: dict[str, Any] = {}
	for key, _selector, nullable in fields:
		value = user_input.get(key)
		if value in ("", []) or (value is None and nullable):
			cleaned[key] = None
			continue
		if value is None:
			continue
		if key in (CONF_OVERRIDE_MINUTES, CONF_LOOKAHEAD_HOURS, CONF_STALE_MINUTES, CONF_FORECAST_HOURS, CONF_MIN_CYCLE_MINUTES):
			value = int(value)
		cleaned[key] = value
	return cleaned


def _comfort_errors(values: dict[str, Any]) -> dict[str, str]:
	errors: dict[str, str] = {}
	if bool(values.get(CONF_COMFORT_START)) != bool(values.get(CONF_COMFORT_END)):
		errors["base"] = "schedule_incomplete"
	minimum = values.get(CONF_MIN_TARGET, DEFAULTS[CONF_MIN_TARGET])
	maximum = values.get(CONF_MAX_TARGET, DEFAULTS[CONF_MAX_TARGET])
	if minimum is not None and maximum is not None and float(minimum) >= float(maximum):
		errors["base"] = "min_above_max"
	return errors


class SmartmostatConfigFlow(ConfigFlow, domain=DOMAIN):
	"""Set up a Smartmostat zone."""

	VERSION = CONFIG_VERSION
	MINOR_VERSION = CONFIG_MINOR_VERSION

	def __init__(self) -> None:
		"""Start a flow."""
		self._data: dict[str, Any] = {}
		self._price_note = ""

	@staticmethod
	@callback
	def async_get_options_flow(config_entry: ConfigEntry) -> SmartmostatOptionsFlow:
		"""Options flow (HA sets ``self.config_entry`` itself)."""
		return SmartmostatOptionsFlow()

	# --- helpers ---------------------------------------------------------

	def _devices_schema(self, mode: str, defaults: dict[str, Any]) -> vol.Schema:
		def opt(key: str) -> vol.Optional:
			value = defaults.get(key)
			if value:
				return vol.Optional(key, description={"suggested_value": value})
			return vol.Optional(key)

		def req(key: str) -> vol.Required:
			value = defaults.get(key)
			if value:
				return vol.Required(key, default=value)
			return vol.Required(key)

		schema: dict[Any, Any] = {}
		if mode in (MODE_REMOTE_SENSOR, MODE_SETPOINT):
			schema[req(CONF_TARGET_CLIMATE)] = EntitySelector(EntitySelectorConfig(domain="climate"))
		else:
			schema[opt(CONF_HEATER)] = EntitySelector(EntitySelectorConfig(domain=SWITCH_DOMAINS))
			schema[opt(CONF_COOLER)] = EntitySelector(EntitySelectorConfig(domain=SWITCH_DOMAINS))
		rooms_key = req(CONF_ROOM_SENSORS) if mode != MODE_SETPOINT else opt(CONF_ROOM_SENSORS)
		schema[rooms_key] = _sensor(multiple=True)
		schema[vol.Required(CONF_ROOM_AGGREGATE, default=defaults.get(CONF_ROOM_AGGREGATE) or AGGREGATE_FIRST)] = _select(
			AGGREGATES, "room_aggregate"
		)
		if mode == MODE_REMOTE_SENSOR:
			schema[opt(CONF_INTERNAL_SENSOR)] = _sensor()
		schema[opt(CONF_OUTDOOR_SENSOR)] = _sensor()
		return vol.Schema(schema)

	def _validate_devices(self, mode: str, user_input: dict[str, Any]) -> dict[str, str]:
		errors: dict[str, str] = {}
		if mode == MODE_SWITCH and not user_input.get(CONF_HEATER) and not user_input.get(CONF_COOLER):
			errors["base"] = "need_heater_or_cooler"
		for key in (CONF_TARGET_CLIMATE, CONF_HEATER, CONF_COOLER, CONF_INTERNAL_SENSOR, CONF_OUTDOOR_SENSOR):
			entity_id = user_input.get(key)
			if entity_id and self.hass.states.get(entity_id) is None:
				errors[key] = "entity_not_found"
		rooms = user_input.get(CONF_ROOM_SENSORS) or []
		if mode != MODE_SETPOINT and not rooms:
			errors[CONF_ROOM_SENSORS] = "room_sensor_required"
		for entity_id in rooms:
			if self.hass.states.get(entity_id) is None:
				errors[CONF_ROOM_SENSORS] = "entity_not_found"
		if not errors:
			ignore = self._editing_entry_id()
			devices = {user_input.get(CONF_TARGET_CLIMATE), user_input.get(CONF_HEATER), user_input.get(CONF_COOLER)} - {None, ""}
			for entry in self._async_current_entries(include_ignore=False):
				if entry.entry_id == ignore:
					continue
				used = {entry.data.get(CONF_TARGET_CLIMATE), entry.data.get(CONF_HEATER), entry.data.get(CONF_COOLER)}
				if devices & used:
					errors["base"] = "already_controlled"
		return errors

	def _editing_entry_id(self) -> str | None:
		if self.source == SOURCE_RECONFIGURE:
			return self._get_reconfigure_entry().entry_id
		return None

	def _detect_price_sensor(self) -> str | None:
		now = dt_util.now()
		for state in self.hass.states.async_all("sensor"):
			if "raw_today" in state.attributes and find_price_slots(state.attributes, now):
				return state.entity_id
		for state in self.hass.states.async_all("sensor"):
			if "raw_today" in state.attributes:
				return state.entity_id
		return None

	# --- steps -------------------------------------------------------------

	async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Name and control mode."""
		if user_input is not None:
			self._data = {CONF_NAME: user_input[CONF_NAME].strip() or "Smartmostat", CONF_CONTROL_MODE: user_input[CONF_CONTROL_MODE]}
			return await self.async_step_devices()
		return self.async_show_form(
			step_id="user",
			data_schema=vol.Schema(
				{
					vol.Required(CONF_NAME, default="Smartmostat"): str,
					vol.Required(CONF_CONTROL_MODE, default=MODE_REMOTE_SENSOR): _select(CONTROL_MODES, "control_mode"),
				}
			),
		)

	async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Change entities and control mode."""
		entry = self._get_reconfigure_entry()
		if user_input is not None:
			self._data = {**entry.data, CONF_CONTROL_MODE: user_input[CONF_CONTROL_MODE]}
			return await self.async_step_devices()
		return self.async_show_form(
			step_id="reconfigure",
			data_schema=vol.Schema(
				{
					vol.Required(CONF_CONTROL_MODE, default=entry.data.get(CONF_CONTROL_MODE, MODE_REMOTE_SENSOR)): _select(
						CONTROL_MODES, "control_mode"
					),
				}
			),
		)

	async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Device and sensors for the chosen mode."""
		mode = self._data[CONF_CONTROL_MODE]
		errors: dict[str, str] = {}
		if user_input is not None:
			errors = self._validate_devices(mode, user_input)
			if errors.get("base") == "already_controlled" and self.source != SOURCE_RECONFIGURE:
				return self.async_abort(reason="already_controlled")
			if not errors:
				for key in (CONF_TARGET_CLIMATE, CONF_HEATER, CONF_COOLER, CONF_INTERNAL_SENSOR, CONF_OUTDOOR_SENSOR):
					self._data.pop(key, None)
				self._data.update({key: value for key, value in user_input.items() if value not in (None, "", [])})
				self._data[CONF_ROOM_SENSORS] = list(user_input.get(CONF_ROOM_SENSORS) or [])
				return await self.async_step_price()
		defaults = user_input or self._data
		return self.async_show_form(
			step_id="devices",
			data_schema=self._devices_schema(mode, defaults),
			errors=errors,
			description_placeholders={"mode": mode},
		)

	async def async_step_price(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Price sensor (HACS Nordpool or compatible)."""
		errors: dict[str, str] = {}
		if user_input is not None:
			entity_id = user_input[CONF_PRICE_SENSOR]
			state = self.hass.states.get(entity_id)
			if state is None:
				errors[CONF_PRICE_SENSOR] = "entity_not_found"
			elif state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
				# Nordpool restarts slowly: a warning, not an error.
				self._price_note = "The price sensor is unavailable right now. Smartmostat will act as a plain thermostat until prices arrive."
			elif not find_price_slots(state.attributes, dt_util.now()):
				errors[CONF_PRICE_SENSOR] = "invalid_price_sensor"
			if not errors:
				self._data[CONF_PRICE_SENSOR] = entity_id
				if self.source == SOURCE_RECONFIGURE:
					entry = self._get_reconfigure_entry()
					# The update listener in __init__.py reloads on a data change.
					# (async_update_reload_and_abort would reload a second time, which
					# HA 2026.10 reports and 2026.12 rejects; ConfigFlow only gained
					# async_update_and_abort after 2025.10, the minimum we support.)
					self.hass.config_entries.async_update_entry(entry, data=self._data)
					return self.async_abort(reason="reconfigure_successful")
				return await self.async_step_comfort()
		default = self._data.get(CONF_PRICE_SENSOR) or self._detect_price_sensor()
		key = vol.Required(CONF_PRICE_SENSOR, default=default) if default else vol.Required(CONF_PRICE_SENSOR)
		return self.async_show_form(
			step_id="price",
			data_schema=vol.Schema({key: _sensor()}),
			errors=errors,
		)

	async def async_step_comfort(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Comfort, eco and away temperatures and the comfort period."""
		fields = COMFORT_FIELDS[:5]
		errors: dict[str, str] = {}
		if user_input is not None:
			options = _clean(fields, user_input)
			errors = _comfort_errors(options)
			if not errors:
				return self.async_create_entry(title=self._data[CONF_NAME], data=self._data, options=options)
		return self.async_show_form(
			step_id="comfort",
			data_schema=_options_schema(fields, user_input or {}),
			errors=errors,
			description_placeholders={"price_note": self._price_note},
		)


class SmartmostatOptionsFlow(OptionsFlow):
	"""Options as a menu. Saving reloads the entry."""

	def _mode(self) -> str:
		return self.config_entry.data.get(CONF_CONTROL_MODE, MODE_REMOTE_SENSOR)

	async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Menu."""
		menu = ["comfort", "price", "actuator"]
		if self._mode() == MODE_REMOTE_SENSOR:
			menu.append("cooling")
		menu += ["safety", "advanced"]
		return self.async_show_menu(step_id="init", menu_options=menu)

	async def _step(
		self,
		step_id: str,
		fields: list[OptionField],
		user_input: dict[str, Any] | None,
		validate: Any = None,
	) -> ConfigFlowResult:
		current = dict(self.config_entry.options)
		errors: dict[str, str] = {}
		if user_input is not None:
			values = _clean(fields, user_input)
			if validate is not None:
				errors = validate(values)
			if not errors:
				return self.async_create_entry(data={**current, **values})
		return self.async_show_form(
			step_id=step_id,
			data_schema=_options_schema(fields, {**current, **(user_input or {})}),
			errors=errors,
		)

	async def async_step_comfort(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Comfort and schedule."""
		return await self._step("comfort", COMFORT_FIELDS, user_input, _comfort_errors)

	async def async_step_price(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Price behaviour."""
		return await self._step("price", PRICE_FIELDS, user_input)

	async def async_step_actuator(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Fields for this entry's control mode only."""
		mode = self._mode()
		fields = REMOTE_FIELDS if mode == MODE_REMOTE_SENSOR else SWITCH_FIELDS if mode == MODE_SWITCH else SETPOINT_FIELDS
		return await self._step("actuator", fields, user_input)

	async def async_step_cooling(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Basic cooling (remote-sensor only)."""
		return await self._step("cooling", COOLING_FIELDS, user_input)

	async def async_step_safety(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Safety."""
		return await self._step("safety", SAFETY_FIELDS, user_input)

	async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
		"""Weather, thermal model, events, dry run."""
		return await self._step("advanced", ADVANCED_FIELDS, user_input)
