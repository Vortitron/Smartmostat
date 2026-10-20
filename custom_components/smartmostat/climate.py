"""Smartmostat climate entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
	ClimateEntity,
	ClimateEntityFeature,
	HVACAction,
	HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, ServiceResponse
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SmartmostatConfigEntry
from .const import (
	ATTR_AVERAGE_PRICE,
	ATTR_BASE_TEMPERATURE,
	ATTR_CONTROL_MODE,
	ATTR_CONTROL_TARGET,
	ATTR_CURRENT_ADJUSTMENT,
	ATTR_CURRENT_PRICE,
	ATTR_HEADLINE,
	ATTR_INTERNAL_TEMPERATURE,
	ATTR_MAX_PRICE,
	ATTR_MIN_PRICE,
	ATTR_MINUTES,
	ATTR_NEXT_HIGH_PRICE,
	ATTR_NEXT_LOW_PRICE,
	ATTR_OUTDOOR_TEMPERATURE,
	ATTR_OVERRIDE_UNTIL,
	ATTR_PAUSED_UNTIL,
	ATTR_PRICE_LEVEL,
	ATTR_PRICE_POSITION,
	ATTR_PRICE_RATIO,
	ATTR_REASON,
	ATTR_REMOTE_TEMPERATURE,
	ATTR_WRAPPED_CLIMATE,
	HVAC_OFF,
	MODE_SWITCH,
	PRESETS,
)
from .coordinator import SmartmostatController
from .entity import SmartmostatEntity, build_device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
	hass: HomeAssistant,
	entry: SmartmostatConfigEntry,
	async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
	"""Add the climate entity."""
	controller = entry.runtime_data
	async_add_entities([SmartmostatClimate(controller, build_device_info(hass, controller))])


class SmartmostatClimate(SmartmostatEntity, ClimateEntity, RestoreEntity):
	"""The thermostat people use. Smartmostat decides what the device is told."""

	_attr_name = None
	_attr_translation_key = "smartmostat"
	_attr_temperature_unit = UnitOfTemperature.CELSIUS
	_attr_preset_modes = list(PRESETS)
	_attr_supported_features = (
		ClimateEntityFeature.TARGET_TEMPERATURE
		| ClimateEntityFeature.PRESET_MODE
		| ClimateEntityFeature.TURN_ON
		| ClimateEntityFeature.TURN_OFF
	)

	def __init__(self, controller: SmartmostatController, device_info: DeviceInfo) -> None:
		"""Unique id kept from 0.1.0/0.2.0: ``{entry_id}_climate``."""
		super().__init__(controller, "climate", device_info)

	async def async_added_to_hass(self) -> None:
		"""Restore the 0.1.0/0.2.0 entity's state on first start after upgrade."""
		await super().async_added_to_hass()
		self.controller.apply_restored_state(await self.async_get_last_state())

	# --- state ------------------------------------------------------------

	@property
	def hvac_modes(self) -> list[HVACMode]:
		"""Modes offered."""
		return [HVACMode(mode) for mode in self.controller.hvac_modes]

	@property
	def hvac_mode(self) -> HVACMode:
		"""Smartmostat's own mode."""
		return HVACMode(self.controller.hvac_mode)

	@property
	def preset_mode(self) -> str:
		"""Current preset ("none" is shown as Schedule)."""
		return self.controller.preset

	@property
	def target_temperature(self) -> float | None:
		"""The base target: what the person asked for, or the schedule's value."""
		plan = self.controller.plan
		if plan is not None:
			return plan.base_target
		return self.controller.settings.planner.comfort_temperature

	@property
	def current_temperature(self) -> float | None:
		"""Room aggregate, or the device reading without room sensors."""
		readings = self.controller.readings
		if readings is None:
			return None
		return readings.room if readings.room is not None else readings.internal

	@property
	def min_temp(self) -> float:
		"""Lowest target."""
		return self.controller.settings.planner.min_target

	@property
	def max_temp(self) -> float:
		"""Highest target."""
		return self.controller.settings.planner.max_target

	@property
	def target_temperature_step(self) -> float:
		"""Device step, else 0.5."""
		entity_id = self.controller.settings.target_climate
		if entity_id and (state := self.hass.states.get(entity_id)) is not None:
			step = state.attributes.get("target_temp_step")
			if isinstance(step, (int, float)) and step > 0:
				return float(step)
		return 0.5

	@property
	def hvac_action(self) -> HVACAction | None:
		"""From the device, or the relay states in switch mode."""
		controller = self.controller
		if controller.settings.mode == MODE_SWITCH:
			state = controller.switch_state()
			if state.heater_on:
				return HVACAction.HEATING
			if state.cooler_on:
				return HVACAction.COOLING
			return HVACAction.OFF if controller.hvac_mode == HVAC_OFF else HVACAction.IDLE
		entity_id = controller.settings.target_climate
		state = self.hass.states.get(entity_id) if entity_id else None
		if state is None:
			return None
		action = state.attributes.get("hvac_action")
		if action in {member.value for member in HVACAction}:
			return HVACAction(action)
		if state.state == HVAC_OFF:
			return HVACAction.OFF
		return None

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Attribute names kept from 0.1.0 and 0.2.0."""
		c = self.controller
		plan = c.plan
		price = c.price
		readings = c.readings
		decision = c.decision
		attrs: dict[str, Any] = {
			ATTR_CONTROL_MODE: c.settings.mode,
			ATTR_WRAPPED_CLIMATE: c.settings.target_climate,
			ATTR_CONTROL_TARGET: plan.control_target if plan else None,
			ATTR_BASE_TEMPERATURE: plan.base_target if plan else None,
			ATTR_CURRENT_ADJUSTMENT: plan.current_adjustment if plan else None,
			ATTR_REASON: decision.reason if decision else None,
			ATTR_HEADLINE: decision.headline if decision else None,
			ATTR_REMOTE_TEMPERATURE: readings.room if readings else None,
			ATTR_INTERNAL_TEMPERATURE: readings.internal if readings else None,
			ATTR_OUTDOOR_TEMPERATURE: readings.outdoor if readings else None,
			ATTR_OVERRIDE_UNTIL: c.override.until.isoformat() if c.override and c.override.until else None,
			ATTR_PAUSED_UNTIL: c.paused_until.isoformat() if c.paused_until else None,
		}
		if price is not None:
			attrs.update(
				{
					ATTR_CURRENT_PRICE: price.price_now,
					ATTR_AVERAGE_PRICE: _r(price.day_average),
					ATTR_MIN_PRICE: _r(price.min_price_24h),
					ATTR_MAX_PRICE: _r(price.max_price_24h),
					ATTR_PRICE_POSITION: _r(price.price_position),
					ATTR_NEXT_HIGH_PRICE: price.next_high_price_in_hours,
					ATTR_NEXT_LOW_PRICE: price.next_low_price_in_hours,
					ATTR_PRICE_LEVEL: price.level,
				}
			)
			if price.price_now is not None and price.day_average is not None and price.day_average > 0:
				attrs[ATTR_PRICE_RATIO] = round(price.price_now / price.day_average, 3)
		return attrs

	# --- commands -----------------------------------------------------------

	async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
		"""Change Smartmostat's mode."""
		await self.controller.async_set_hvac_mode(str(hvac_mode))

	async def async_turn_on(self) -> None:
		"""Turn on (last mode)."""
		await self.controller.async_turn_on()

	async def async_turn_off(self) -> None:
		"""Turn off."""
		await self.controller.async_set_hvac_mode(HVAC_OFF)

	async def async_set_preset_mode(self, preset_mode: str) -> None:
		"""Change preset (clears overrides)."""
		await self.controller.async_set_preset(preset_mode)

	async def async_set_temperature(self, **kwargs: Any) -> None:
		"""Set a target (override with a schedule, comfort without)."""
		mode = kwargs.get("hvac_mode")
		temperature = kwargs.get(ATTR_TEMPERATURE)
		await self.controller.async_set_temperature(
			None if temperature is None else float(temperature),
			None if mode is None else str(mode),
		)

	# --- entity services ----------------------------------------------------

	async def async_service_set_override(self, temperature: float, **kwargs: Any) -> None:
		"""smartmostat.set_override."""
		await self.controller.async_set_override(temperature, kwargs.get(ATTR_MINUTES))

	async def async_service_clear_override(self) -> None:
		"""smartmostat.clear_override."""
		await self.controller.async_clear_override()

	async def async_service_resume(self) -> None:
		"""smartmostat.resume."""
		await self.controller.async_resume()

	async def async_service_evaluate(self) -> ServiceResponse:
		"""smartmostat.evaluate: re-run now and return the decision."""
		await self.controller.async_evaluate(user_action=True)
		return self.controller.decision_dict()


def _r(value: float | None) -> float | None:
	return None if value is None else round(value, 4)

