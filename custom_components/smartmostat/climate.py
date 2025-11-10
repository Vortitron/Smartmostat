"""Platform for Smart Thermostat climate integration."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
	ClimateEntityFeature,
	HVACAction,
	HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
	ATTR_TEMPERATURE,
	CONF_NAME,
	SERVICE_TURN_OFF,
	SERVICE_TURN_ON,
	STATE_ON,
	STATE_UNAVAILABLE,
	STATE_UNKNOWN,
	UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
	ATTR_CONTROL_MODE,
	ATTR_COOLER_ENTITY,
	ATTR_CURRENT_COLD_TOLERANCE,
	ATTR_CURRENT_HOT_TOLERANCE,
	ATTR_CURRENT_PRICE,
	ATTR_HEATER_ENTITY,
	ATTR_INTERNAL_TEMPERATURE,
	ATTR_LAST_HVAC_MODE,
	ATTR_MAX_PRICE,
	ATTR_MIN_PRICE,
	ATTR_NEXT_HIGH_PRICE,
	ATTR_NEXT_LOW_PRICE,
	ATTR_OUTDOOR_TEMPERATURE,
	ATTR_PRICE_POSITION,
	ATTR_REMOTE_TEMPERATURE,
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
	CONF_FAN_ONLY_DIFF,
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
)

_LOGGER = logging.getLogger(__name__)

METRIC_EVENT = f"{DOMAIN}_metrics"


async def async_setup_entry(
	hass: HomeAssistant,
	config_entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up the Smart Thermostat climate platform."""
	config = config_entry.data
	options = config_entry.options
	merged_config = {**config, **options}

	async_add_entities(
		[SmartThermostat(hass, config_entry.entry_id, merged_config)],
		True,
	)


class SmartThermostat(ClimateEntity, RestoreEntity):
	"""Representation of a Smart Thermostat capable of multiple control strategies."""

	def __init__(
		self,
		hass: HomeAssistant,
		entry_id: str,
		config: dict[str, Any],
	) -> None:
		self.hass = hass
		self._entry_id = entry_id
		self._config = config

		self._name = config[CONF_NAME]
		self._control_mode = config.get(CONF_CONTROL_MODE, DEFAULT_CONTROL_MODE)

		self._remote_sensor_id = config.get(CONF_TARGET_SENSOR)
		self._internal_sensor_id = config.get(CONF_INTERNAL_SENSOR)
		self._outdoor_sensor_id = config.get(CONF_OUTDOOR_SENSOR)
		self._target_climate_entity = config.get(CONF_TARGET_CLIMATE)
		self._heater_entity_id = config.get(CONF_HEATER)
		self._cooler_entity_id = config.get(CONF_COOLER)
		self._price_sensor_entity = config[CONF_PRICE_SENSOR]

		self._allow_hvac_mode_changes = config.get(
			CONF_ALLOW_HVAC_MODE_CHANGES, DEFAULT_ALLOW_HVAC_MODE_CHANGES
		)
		self._enable_fan_only_mode = config.get(
			CONF_ENABLE_FAN_ONLY_MODE, DEFAULT_ENABLE_FAN_ONLY_MODE
		)
		self._enable_logging = config.get(
			CONF_ENABLE_DIAGNOSTIC_LOGGING, DEFAULT_ENABLE_DIAGNOSTIC_LOGGING
		)

		self._max_tolerance = config.get(CONF_MAX_TOLERANCE, DEFAULT_MAX_TOLERANCE)
		self._min_tolerance = config.get(CONF_MIN_TOLERANCE, DEFAULT_MIN_TOLERANCE)

		self._max_offset = config.get(CONF_MAX_OFFSET, DEFAULT_MAX_OFFSET)
		self._min_offset = config.get(CONF_MIN_OFFSET, DEFAULT_MIN_OFFSET)
		self._heat_offset = config.get(CONF_HEAT_OFFSET, DEFAULT_HEAT_OFFSET)
		self._cool_offset = config.get(CONF_COOL_OFFSET, DEFAULT_COOL_OFFSET)
		self._base_stop_heat_offset = config.get(
			CONF_BASE_STOP_HEAT_OFFSET, DEFAULT_BASE_STOP_HEAT_OFFSET
		)
		self._max_stop_heat_offset = config.get(
			CONF_MAX_STOP_HEAT_OFFSET, DEFAULT_MAX_STOP_HEAT_OFFSET
		)
		self._temp_tolerance = config.get(CONF_TEMP_TOLERANCE, DEFAULT_TEMP_TOLERANCE)
		self._fan_only_diff = config.get(CONF_FAN_ONLY_DIFF, DEFAULT_FAN_ONLY_DIFF)
		self._cool_indoor_threshold = config.get(
			CONF_COOL_INDOOR_THRESHOLD, DEFAULT_COOL_INDOOR_THRESHOLD
		)
		self._cool_outdoor_threshold = config.get(
			CONF_COOL_OUTDOOR_THRESHOLD, DEFAULT_COOL_OUTDOOR_THRESHOLD
		)
		self._cool_indoor_min = config.get(
			CONF_COOL_INDOOR_MIN, DEFAULT_COOL_INDOOR_MIN
		)

		self._lookahead_hours = config.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)
		self._preconditioning_enabled = config.get(
			CONF_PRECONDITIONING_ENABLED, DEFAULT_PRECONDITIONING_ENABLED
		)

		self._target_temp: float | None = None
		self._remote_temp: float | None = None
		self._internal_temp: float | None = None
		self._outdoor_temp: float | None = None
		self._cur_temp: float | None = None

		self._hvac_mode: HVACMode = HVACMode.OFF
		self._hvac_action: HVACAction = HVACAction.OFF
		self._last_commanded_hvac_mode: HVACMode | None = None

		self._current_price: float | None = None
		self._min_price_24h: float | None = None
		self._max_price_24h: float | None = None
		self._price_position: float | None = None
		self._next_high_price_hours: int | None = None
		self._next_low_price_hours: int | None = None

		self._current_cold_tolerance: float | None = None
		self._current_hot_tolerance: float | None = None

		self._attr_unique_id = f"{entry_id}_climate"
		self._attr_temperature_unit = UnitOfTemperature.CELSIUS
		self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

		self._unsub_remote_sensor = None
		self._unsub_internal_sensor = None
		self._unsub_outdoor_sensor = None
		self._unsub_price = None
		self._unsub_heater = None
		self._unsub_cooler = None
		self._unsub_target_climate = None

	async def async_added_to_hass(self) -> None:
		await super().async_added_to_hass()
		await self._restore_state()
		self._initialise_listeners()
		await self._refresh_all_sensors()
		await self._update_prices()
		await self._run_control("startup")

	async def async_will_remove_from_hass(self) -> None:
		for unsub in (
			self._unsub_remote_sensor,
			self._unsub_internal_sensor,
			self._unsub_outdoor_sensor,
			self._unsub_price,
			self._unsub_heater,
			self._unsub_cooler,
			self._unsub_target_climate,
		):
			if unsub:
				unsub()

	async def _restore_state(self) -> None:
		last_state = await self.async_get_last_state()
		if last_state and last_state.attributes.get(ATTR_TEMPERATURE) is not None:
			try:
				self._target_temp = float(last_state.attributes[ATTR_TEMPERATURE])
			except (ValueError, TypeError):
				self._target_temp = 20.0
		else:
			self._target_temp = 20.0

		if last_state and last_state.state in HVACMode.__members__.values():
			try:
				self._hvac_mode = HVACMode(last_state.state)
			except ValueError:
				self._hvac_mode = HVACMode.HEAT
		else:
			self._hvac_mode = HVACMode.HEAT if self._heater_entity_id else HVACMode.COOL

	def _initialise_listeners(self) -> None:
		if self._remote_sensor_id:
			self._unsub_remote_sensor = async_track_state_change_event(
				self.hass,
				[self._remote_sensor_id],
				self._async_remote_sensor_changed,
			)

		if self._internal_sensor_id:
			self._unsub_internal_sensor = async_track_state_change_event(
				self.hass,
				[self._internal_sensor_id],
				self._async_internal_sensor_changed,
			)

		if self._outdoor_sensor_id:
			self._unsub_outdoor_sensor = async_track_state_change_event(
				self.hass,
				[self._outdoor_sensor_id],
				self._async_outdoor_sensor_changed,
			)

		self._unsub_price = async_track_state_change_event(
			self.hass,
			[self._price_sensor_entity],
			self._async_price_changed,
		)

		if self._heater_entity_id:
			self._unsub_heater = async_track_state_change_event(
				self.hass,
				[self._heater_entity_id],
				self._async_switch_changed,
			)

		if self._cooler_entity_id:
			self._unsub_cooler = async_track_state_change_event(
				self.hass,
				[self._cooler_entity_id],
				self._async_switch_changed,
			)

		if self._target_climate_entity:
			self._unsub_target_climate = async_track_state_change_event(
				self.hass,
				[self._target_climate_entity],
				self._async_target_climate_changed,
			)

	async def _refresh_all_sensors(self) -> None:
		await self._update_remote_temp()
		await self._update_internal_temp()
		await self._update_outdoor_temp()
		await self._refresh_target_climate_state()

	async def _update_remote_temp(self) -> None:
		self._remote_temp = self._get_float_state(self._remote_sensor_id)
		self._cur_temp = self._remote_temp

	async def _update_internal_temp(self) -> None:
		self._internal_temp = self._get_float_state(self._internal_sensor_id)
		if self._internal_temp is None and self._target_climate_entity:
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				self._internal_temp = self._get_attr_float(
					climate_state, "current_temperature"
				)

	async def _update_outdoor_temp(self) -> None:
		self._outdoor_temp = self._get_float_state(self._outdoor_sensor_id)

	async def _refresh_target_climate_state(self) -> None:
		if not self._target_climate_entity:
			return
		state = self.hass.states.get(self._target_climate_entity)
		if not state:
			return
		self._internal_temp = self._get_attr_float(state, "current_temperature")
		try:
			self._hvac_mode = HVACMode(state.state)
		except ValueError:
			pass

	def _get_float_state(self, entity_id: str | None) -> float | None:
		if not entity_id:
			return None
		state = self.hass.states.get(entity_id)
		if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
			return None
		try:
			return float(state.state)
		except (ValueError, TypeError):
			return None

	def _get_attr_float(self, state, attribute: str) -> float | None:
		if not state:
			return None
		value = state.attributes.get(attribute)
		if value in (STATE_UNKNOWN, STATE_UNAVAILABLE, None):
			return None
		try:
			return float(value)
		except (ValueError, TypeError):
			return None

	@callback
	def _async_remote_sensor_changed(self, event) -> None:
		self.hass.async_create_task(self._handle_remote_sensor())

	async def _handle_remote_sensor(self) -> None:
		await self._update_remote_temp()
		await self._run_control("remote_sensor")

	@callback
	def _async_internal_sensor_changed(self, event) -> None:
		self.hass.async_create_task(self._handle_internal_sensor())

	async def _handle_internal_sensor(self) -> None:
		await self._update_internal_temp()
		await self._run_control("internal_sensor")

	@callback
	def _async_outdoor_sensor_changed(self, event) -> None:
		self.hass.async_create_task(self._handle_outdoor_sensor())

	async def _handle_outdoor_sensor(self) -> None:
		await self._update_outdoor_temp()
		await self._run_control("outdoor_sensor")

	@callback
	def _async_target_climate_changed(self, event) -> None:
		self.hass.async_create_task(self._handle_target_climate_change())

	async def _handle_target_climate_change(self) -> None:
		await self._refresh_target_climate_state()
		await self._run_control("climate_state")

	@callback
	def _async_price_changed(self, event) -> None:
		self.hass.async_create_task(self._handle_price_change())

	async def _handle_price_change(self) -> None:
		await self._update_prices()
		await self._run_control("price_change")

	@callback
	def _async_switch_changed(self, event) -> None:
		self.hass.async_create_task(self._update_hvac_action())

	async def _update_prices(self) -> None:
		price_state = self.hass.states.get(self._price_sensor_entity)
		if not price_state or price_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
			self._current_price = None
			self._min_price_24h = None
			self._max_price_24h = None
			self._price_position = None
			return
		try:
			self._current_price = float(price_state.state)
		except (ValueError, TypeError):
			_LOGGER.warning("Could not parse current price from %s", price_state.state)
			return

		self._calculate_price_range(price_state)
		self._analyse_upcoming_prices(price_state)

	def _calculate_price_range(self, price_state) -> None:
		raw_today = price_state.attributes.get("raw_today", [])
		raw_tomorrow = price_state.attributes.get("raw_tomorrow", [])
		if not raw_today:
			self._min_price_24h = None
			self._max_price_24h = None
			self._price_position = None
			return

		all_prices = raw_today + (raw_tomorrow if raw_tomorrow else [])
		now = datetime.now()
		future_prices: list[float] = []

		for price_data in all_prices:
			try:
				price_time = datetime.fromisoformat(price_data.get("start", ""))
				price_value = float(price_data.get("value", 0))
				hours_from_now = (price_time - now).total_seconds() / 3600
				if -1 <= hours_from_now <= 24:
					future_prices.append(price_value)
			except (ValueError, KeyError, TypeError) as err:
				_LOGGER.debug("Error parsing price data: %s", err)
				continue

		if not future_prices:
			self._min_price_24h = None
			self._max_price_24h = None
			self._price_position = None
			return

		self._min_price_24h = min(future_prices)
		self._max_price_24h = max(future_prices)

		if (
			self._current_price is not None
			and self._max_price_24h != self._min_price_24h
		):
			self._price_position = (
				(self._current_price - self._min_price_24h)
				/ (self._max_price_24h - self._min_price_24h)
			)
			self._price_position = max(0.0, min(1.0, self._price_position))
		else:
			self._price_position = 0.5

	def _analyse_upcoming_prices(self, price_state) -> None:
		raw_today = price_state.attributes.get("raw_today", [])
		raw_tomorrow = price_state.attributes.get("raw_tomorrow", [])
		if (
			not raw_today
			or self._max_price_24h is None
			or self._min_price_24h is None
		):
			self._next_high_price_hours = None
			self._next_low_price_hours = None
			return

		all_prices = raw_today + (raw_tomorrow if raw_tomorrow else [])
		now = datetime.now()
		price_range = self._max_price_24h - self._min_price_24h
		high_threshold = self._max_price_24h - (price_range * 0.25)
		low_threshold = self._min_price_24h + (price_range * 0.25)

		self._next_high_price_hours = None
		self._next_low_price_hours = None

		for price_data in all_prices:
			try:
				price_time = datetime.fromisoformat(price_data.get("start", ""))
				price_value = float(price_data.get("value", 0))
				if price_time <= now:
					continue
				hours_until = int((price_time - now).total_seconds() / 3600)
				if (
					self._next_high_price_hours is None
					and price_value >= high_threshold
					and hours_until <= self._lookahead_hours * 2
				):
					self._next_high_price_hours = hours_until
				if (
					self._next_low_price_hours is None
					and price_value <= low_threshold
					and hours_until <= self._lookahead_hours * 2
				):
					self._next_low_price_hours = hours_until
			except (ValueError, KeyError, TypeError) as err:
				_LOGGER.debug("Error parsing price data: %s", err)
				continue

	async def _run_control(self, reason: str) -> None:
		if self._control_mode == CONTROL_MODE_TOLERANCE:
			await self._run_tolerance_control(reason)
		else:
			await self._run_temperature_control(reason)
		self.async_write_ha_state()

	async def _run_tolerance_control(self, reason: str) -> None:
		if self._target_temp is None or self._remote_temp is None:
			return

		if self._price_position is None:
			self._current_cold_tolerance = self._min_tolerance
			self._current_hot_tolerance = self._min_tolerance
		else:
			tolerance_range = self._max_tolerance - self._min_tolerance
			self._current_cold_tolerance = self._min_tolerance + (
				tolerance_range * self._price_position
			)
			self._current_hot_tolerance = self._max_tolerance - (
				tolerance_range * self._price_position
			)

		preconditioning = (
			self._preconditioning_enabled
			and self._next_high_price_hours is not None
			and 1 <= self._next_high_price_hours <= self._lookahead_hours
		)

		if self._hvac_mode == HVACMode.OFF:
			if self._heater_entity_id:
				await self._async_turn_off(self._heater_entity_id)
			if self._cooler_entity_id:
				await self._async_turn_off(self._cooler_entity_id)
			await self._update_hvac_action()
			self._record_metrics(reason, self._hvac_mode, None)
			return

		if self._hvac_mode == HVACMode.HEAT and self._heater_entity_id:
			await self._control_heater(preconditioning)
		elif self._hvac_mode == HVACMode.COOL and self._cooler_entity_id:
			await self._control_cooler(preconditioning)

		await self._update_hvac_action()
		self._record_metrics(reason, self._hvac_mode, None)

	async def _control_heater(self, preconditioning: bool) -> None:
		if self._remote_temp is None or self._target_temp is None:
			return
		too_cold = self._remote_temp <= self._target_temp - (self._current_cold_tolerance or 0)
		too_hot = self._remote_temp >= self._target_temp + (self._current_hot_tolerance or 0)
		if too_cold or preconditioning:
			await self._async_turn_on(self._heater_entity_id)
		elif too_hot:
			await self._async_turn_off(self._heater_entity_id)

	async def _control_cooler(self, preconditioning: bool) -> None:
		if self._remote_temp is None or self._target_temp is None:
			return
		too_hot = self._remote_temp >= self._target_temp + (self._current_hot_tolerance or 0)
		too_cold = self._remote_temp <= self._target_temp - (self._current_cold_tolerance or 0)
		if too_hot or preconditioning:
			await self._async_turn_on(self._cooler_entity_id)
		elif too_cold:
			await self._async_turn_off(self._cooler_entity_id)

	async def _run_temperature_control(self, reason: str) -> None:
		if not self._target_climate_entity or self._target_temp is None:
			return

		remote = self._remote_temp
		internal = self._internal_temp or remote
		outdoor = self._outdoor_temp
		desired = self._target_temp

		if remote is None or internal is None:
			return

		diff = remote - desired

		target_temp_for_device = internal
		hvac_mode_to_set: HVACMode | None = None

		cooling_condition = (
			remote > self._cool_indoor_threshold
			or (
				outdoor is not None
				and outdoor >= self._cool_outdoor_threshold
				and remote > self._cool_indoor_min
			)
		)

		if cooling_condition:
			if (
				self._enable_fan_only_mode
				and remote > desired + self._temp_tolerance
				and (outdoor is not None and outdoor < desired)
			):
				hvac_mode_to_set = HVACMode.FAN_ONLY
			else:
				hvac_mode_to_set = HVACMode.COOL

			if remote > desired + self._temp_tolerance:
				target_temp_for_device = internal + self._cool_offset
			else:
				target_temp_for_device = internal
		else:
			fan_only_condition = (
				self._enable_fan_only_mode
				and (
					(remote < desired - self._temp_tolerance and outdoor is not None and outdoor > desired)
					or diff > self._fan_only_diff
				)
			)
			if fan_only_condition:
				hvac_mode_to_set = HVACMode.FAN_ONLY
			else:
				hvac_mode_to_set = HVACMode.HEAT

			if remote < desired - self._temp_tolerance:
				target_temp_for_device = internal + self._heat_offset
			elif remote >= desired:
				target_temp_for_device = internal + max(
					self._base_stop_heat_offset - diff,
					self._max_stop_heat_offset,
				)
			else:
				target_temp_for_device = internal

		clamped_target = self._clamp_offset(desired, target_temp_for_device)
		await self._apply_temperature_control(hvac_mode_to_set, clamped_target)
		self._record_metrics(reason, hvac_mode_to_set, clamped_target)

	def _clamp_offset(self, desired: float, target: float) -> float:
		min_allowed = desired + self._min_offset
		max_allowed = desired + self._max_offset
		return max(min_allowed, min(max_allowed, target))

	async def _apply_temperature_control(
		self, hvac_mode: HVACMode | None, target_temp: float
	) -> None:
		data = {
			"entity_id": self._target_climate_entity,
			"temperature": round(target_temp, 1),
		}
		if hvac_mode and self._allow_hvac_mode_changes:
			data["hvac_mode"] = hvac_mode.value
		await self.hass.services.async_call(
			"climate",
			"set_temperature",
			data,
			blocking=True,
		)
		if hvac_mode and self._allow_hvac_mode_changes:
			self._hvac_mode = hvac_mode
			self._last_commanded_hvac_mode = hvac_mode

	async def _async_turn_on(self, entity_id: str) -> None:
		await self.hass.services.async_call(
			"homeassistant",
			SERVICE_TURN_ON,
			{"entity_id": entity_id},
			blocking=True,
		)

	async def _async_turn_off(self, entity_id: str) -> None:
		await self.hass.services.async_call(
			"homeassistant",
			SERVICE_TURN_OFF,
			{"entity_id": entity_id},
			blocking=True,
		)

	async def _update_hvac_action(self) -> None:
		if self._control_mode == CONTROL_MODE_TEMPERATURE and self._target_climate_entity:
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				hvac_action = climate_state.attributes.get("hvac_action")
				if hvac_action:
					try:
						self._hvac_action = HVACAction(hvac_action)
					except ValueError:
						self._hvac_action = HVACAction.IDLE
				try:
					self._hvac_mode = HVACMode(climate_state.state)
				except ValueError:
					pass
			return

		if self._hvac_mode == HVACMode.OFF:
			self._hvac_action = HVACAction.OFF
		elif self._hvac_mode == HVACMode.HEAT and self._heater_entity_id:
			heater_state = self.hass.states.get(self._heater_entity_id)
			self._hvac_action = (
				HVACAction.HEATING
				if heater_state and heater_state.state == STATE_ON
				else HVACAction.IDLE
			)
		elif self._hvac_mode == HVACMode.COOL and self._cooler_entity_id:
			cooler_state = self.hass.states.get(self._cooler_entity_id)
			self._hvac_action = (
				HVACAction.COOLING
				if cooler_state and cooler_state.state == STATE_ON
				else HVACAction.IDLE
			)
		else:
			self._hvac_action = HVACAction.IDLE

	@property
	def name(self) -> str:
		return self._name

	@property
	def unique_id(self) -> str:
		return self._attr_unique_id

	@property
	def temperature_unit(self) -> str:
		if (
			self._control_mode == CONTROL_MODE_TEMPERATURE
			and self._target_climate_entity
		):
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				return climate_state.attributes.get(
					"temperature_unit", UnitOfTemperature.CELSIUS
				)
		return self._attr_temperature_unit

	@property
	def current_temperature(self) -> float | None:
		return self._remote_temp

	@property
	def target_temperature(self) -> float | None:
		return self._target_temp

	@property
	def hvac_mode(self) -> HVACMode:
		return self._hvac_mode

	@property
	def hvac_modes(self) -> list[HVACMode]:
		if (
			self._control_mode == CONTROL_MODE_TEMPERATURE
			and self._target_climate_entity
		):
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				return [
					HVACMode(mode) for mode in climate_state.attributes.get("hvac_modes", [])
				]
		modes = [HVACMode.OFF]
		if self._heater_entity_id:
			modes.append(HVACMode.HEAT)
		if self._cooler_entity_id:
			modes.append(HVACMode.COOL)
		if self._enable_fan_only_mode:
			modes.append(HVACMode.FAN_ONLY)
		return modes

	@property
	def hvac_action(self) -> HVACAction:
		return self._hvac_action

	@property
	def supported_features(self) -> int:
		return self._attr_supported_features

	@property
	def min_temp(self) -> float:
		if (
			self._control_mode == CONTROL_MODE_TEMPERATURE
			and self._target_climate_entity
		):
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				return climate_state.attributes.get("min_temp", 7.0)
		return 7.0

	@property
	def max_temp(self) -> float:
		if (
			self._control_mode == CONTROL_MODE_TEMPERATURE
			and self._target_climate_entity
		):
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				return climate_state.attributes.get("max_temp", 35.0)
		return 35.0

	@property
	def target_temperature_step(self) -> float:
		if (
			self._control_mode == CONTROL_MODE_TEMPERATURE
			and self._target_climate_entity
		):
			climate_state = self.hass.states.get(self._target_climate_entity)
			if climate_state:
				return climate_state.attributes.get("target_temp_step", 0.5)
		return 0.5

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		data: dict[str, Any] = {
			ATTR_CONTROL_MODE: self._control_mode,
			ATTR_REMOTE_TEMPERATURE: self._remote_temp,
			ATTR_INTERNAL_TEMPERATURE: self._internal_temp,
			ATTR_OUTDOOR_TEMPERATURE: self._outdoor_temp,
			ATTR_LAST_HVAC_MODE: self._last_commanded_hvac_mode.value
			if self._last_commanded_hvac_mode
			else None,
		}

		if self._control_mode == CONTROL_MODE_TOLERANCE:
			data.update(
				{
					ATTR_CURRENT_COLD_TOLERANCE: self._current_cold_tolerance,
					ATTR_CURRENT_HOT_TOLERANCE: self._current_hot_tolerance,
					ATTR_HEATER_ENTITY: self._heater_entity_id,
					ATTR_COOLER_ENTITY: self._cooler_entity_id,
				}
			)

		if self._current_price is not None:
			data[ATTR_CURRENT_PRICE] = self._current_price
		if self._min_price_24h is not None:
			data[ATTR_MIN_PRICE] = self._min_price_24h
		if self._max_price_24h is not None:
			data[ATTR_MAX_PRICE] = self._max_price_24h
		if self._price_position is not None:
			data[ATTR_PRICE_POSITION] = round(self._price_position, 3)
		if self._next_high_price_hours is not None:
			data[ATTR_NEXT_HIGH_PRICE] = self._next_high_price_hours
		if self._next_low_price_hours is not None:
			data[ATTR_NEXT_LOW_PRICE] = self._next_low_price_hours

		return data

	async def async_set_temperature(self, **kwargs) -> None:
		temperature = kwargs.get(ATTR_TEMPERATURE)
		if temperature is None:
			return
		self._target_temp = float(temperature)
		await self._run_control("user_set_temperature")

	async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
		if hvac_mode not in self.hvac_modes:
			_LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
			return

		if self._control_mode == CONTROL_MODE_TEMPERATURE and self._target_climate_entity:
			await self.hass.services.async_call(
				"climate",
				"set_hvac_mode",
				{"entity_id": self._target_climate_entity, "hvac_mode": hvac_mode.value},
				blocking=True,
			)
			self._last_commanded_hvac_mode = hvac_mode
		self._hvac_mode = hvac_mode
		await self._run_control("user_set_hvac_mode")

	async def async_update(self) -> None:
		await self._refresh_all_sensors()
		await self._update_prices()
		await self._run_control("manual_update")

	def _record_metrics(
		self,
		reason: str,
		hvac_mode: HVACMode | None,
		target_temp_for_device: float | None,
	) -> None:
		if not self._enable_logging:
			return

		metrics = {
			"entity_id": self.entity_id,
			"reason": reason,
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"control_mode": self._control_mode,
			"target_temperature": self._target_temp,
			"remote_temperature": self._remote_temp,
			"internal_temperature": self._internal_temp,
			"outdoor_temperature": self._outdoor_temp,
			"current_price": self._current_price,
			"price_position": self._price_position,
			"hvac_mode": hvac_mode.value if hvac_mode else self._hvac_mode.value,
			"target_device_temperature": target_temp_for_device,
			"cold_tolerance": self._current_cold_tolerance,
			"hot_tolerance": self._current_hot_tolerance,
		}

		_LOGGER.info("Smartmostat metrics: %s", metrics)
		self.hass.bus.async_fire(METRIC_EVENT, metrics)

