"""Tests for Smart Thermostat climate platform."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import pytest

from homeassistant.components.climate.const import HVACMode
from homeassistant.const import (
	ATTR_TEMPERATURE,
	STATE_UNAVAILABLE,
	STATE_UNKNOWN,
	UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from custom_components.smartmostat.climate import SmartThermostat
from custom_components.smartmostat.const import (
	CONF_TARGET_CLIMATE,
	CONF_PRICE_SENSOR,
	CONF_MAX_INCREASE,
	CONF_MAX_DECREASE,
	CONF_PRICE_THRESHOLD_HIGH,
	CONF_PRICE_THRESHOLD_LOW,
	CONF_PREHEATING_ENABLED,
	CONF_PREHEATING_HOURS,
	DEFAULT_MAX_INCREASE,
	DEFAULT_MAX_DECREASE,
	DEFAULT_PRICE_THRESHOLD_HIGH,
	DEFAULT_PRICE_THRESHOLD_LOW,
)


@pytest.fixture
def mock_hass():
	"""Create a mock Home Assistant instance."""
	hass = Mock(spec=HomeAssistant)
	hass.states = Mock()
	hass.services = Mock()
	hass.services.async_call = AsyncMock()
	return hass


@pytest.fixture
def basic_config():
	"""Create basic configuration."""
	return {
		"name": "Test Smart Thermostat",
		CONF_TARGET_CLIMATE: "climate.test_thermostat",
		CONF_PRICE_SENSOR: "sensor.electricity_price",
		CONF_MAX_INCREASE: DEFAULT_MAX_INCREASE,
		CONF_MAX_DECREASE: DEFAULT_MAX_DECREASE,
		CONF_PRICE_THRESHOLD_HIGH: DEFAULT_PRICE_THRESHOLD_HIGH,
		CONF_PRICE_THRESHOLD_LOW: DEFAULT_PRICE_THRESHOLD_LOW,
		CONF_PREHEATING_ENABLED: True,
		CONF_PREHEATING_HOURS: 2,
	}


@pytest.fixture
def mock_climate_state():
	"""Create a mock climate entity state."""
	state = Mock()
	state.state = HVACMode.HEAT
	state.attributes = {
		ATTR_TEMPERATURE: 20.0,
		"current_temperature": 19.0,
		"temperature_unit": UnitOfTemperature.CELSIUS,
		"hvac_modes": [HVACMode.HEAT, HVACMode.OFF],
		"min_temp": 7,
		"max_temp": 35,
		"target_temp_step": 0.5,
	}
	return state


@pytest.fixture
def mock_price_state():
	"""Create a mock price sensor state."""
	state = Mock()
	state.state = "1.5"
	state.attributes = {
		"average": 1.0,
		"raw_today": [
			{"start": "2025-10-21T00:00:00", "value": 0.8},
			{"start": "2025-10-21T01:00:00", "value": 0.9},
			{"start": "2025-10-21T02:00:00", "value": 1.5},
		],
		"raw_tomorrow": [],
	}
	return state


class TestSmartThermostatInit:
	"""Test Smart Thermostat initialisation."""

	def test_init_with_defaults(self, mock_hass, basic_config):
		"""Test initialisation with default values."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		assert thermostat.name == "Test Smart Thermostat"
		assert thermostat._target_climate_entity == "climate.test_thermostat"
		assert thermostat._price_sensor_entity == "sensor.electricity_price"
		assert thermostat._max_increase == DEFAULT_MAX_INCREASE
		assert thermostat._max_decrease == DEFAULT_MAX_DECREASE
		assert thermostat._current_adjustment == 0.0

	def test_init_with_custom_values(self, mock_hass):
		"""Test initialisation with custom configuration values."""
		config = {
			"name": "Custom Thermostat",
			CONF_TARGET_CLIMATE: "climate.custom",
			CONF_PRICE_SENSOR: "sensor.custom_price",
			CONF_MAX_INCREASE: 3.0,
			CONF_MAX_DECREASE: 1.5,
			CONF_PRICE_THRESHOLD_HIGH: 1.5,
			CONF_PRICE_THRESHOLD_LOW: 0.6,
		}
		
		thermostat = SmartThermostat(mock_hass, "test_entry", config)
		
		assert thermostat._max_increase == 3.0
		assert thermostat._max_decrease == 1.5
		assert thermostat._price_threshold_high == 1.5
		assert thermostat._price_threshold_low == 0.6


class TestPriceAnalysis:
	"""Test price analysis and adjustment calculation."""

	def test_high_price_adjustment(self, mock_hass, basic_config, mock_climate_state, mock_price_state):
		"""Test temperature adjustment during high prices."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		thermostat._base_target_temperature = 20.0
		
		# Set price 50% above average (1.5 / 1.0 = 1.5 ratio)
		thermostat._current_price = 1.5
		thermostat._average_price = 1.0
		
		# Calculate adjustment
		thermostat.hass.states.get = Mock(return_value=mock_price_state)
		
		# Manually trigger calculation
		import asyncio
		asyncio.run(thermostat._async_calculate_adjustment())
		
		# Should reduce temperature (negative adjustment)
		assert thermostat._current_adjustment < 0
		assert abs(thermostat._current_adjustment) <= thermostat._max_decrease

	def test_normal_price_no_adjustment(self, mock_hass, basic_config):
		"""Test no adjustment during normal prices."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		thermostat._base_target_temperature = 20.0
		
		# Price exactly at average
		thermostat._current_price = 1.0
		thermostat._average_price = 1.0
		
		import asyncio
		asyncio.run(thermostat._async_calculate_adjustment())
		
		# Should have no adjustment
		assert thermostat._current_adjustment == 0.0

	def test_price_ratio_calculation(self, mock_hass, basic_config):
		"""Test price ratio is correctly calculated."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		thermostat._current_price = 2.0
		thermostat._average_price = 1.0
		
		attrs = thermostat.extra_state_attributes
		assert attrs["price_ratio"] == 2.0


class TestTemperatureControl:
	"""Test temperature control functionality."""

	def test_target_temperature_with_adjustment(self, mock_hass, basic_config):
		"""Test target temperature includes adjustment."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		thermostat._base_target_temperature = 20.0
		thermostat._current_adjustment = 1.5
		
		assert thermostat.target_temperature == 21.5

	def test_target_temperature_without_base(self, mock_hass, basic_config):
		"""Test target temperature when base is not set."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		thermostat._base_target_temperature = None
		
		assert thermostat.target_temperature is None

	@pytest.mark.asyncio
	async def test_set_temperature(self, mock_hass, basic_config):
		"""Test setting temperature updates base temperature."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		await thermostat.async_set_temperature(temperature=22.0)
		
		assert thermostat._base_target_temperature == 22.0


class TestEntityProperties:
	"""Test climate entity properties."""

	def test_unique_id(self, mock_hass, basic_config):
		"""Test unique ID is correctly set."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		assert thermostat.unique_id == "test_entry_climate"

	def test_temperature_unit(self, mock_hass, basic_config, mock_climate_state):
		"""Test temperature unit from wrapped climate."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		mock_hass.states.get = Mock(return_value=mock_climate_state)
		
		assert thermostat.temperature_unit == UnitOfTemperature.CELSIUS

	def test_current_temperature(self, mock_hass, basic_config, mock_climate_state):
		"""Test current temperature from wrapped climate."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		mock_hass.states.get = Mock(return_value=mock_climate_state)
		
		assert thermostat.current_temperature == 19.0

	def test_hvac_mode(self, mock_hass, basic_config, mock_climate_state):
		"""Test HVAC mode from wrapped climate."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		mock_hass.states.get = Mock(return_value=mock_climate_state)
		
		assert thermostat.hvac_mode == HVACMode.HEAT


class TestStateAttributes:
	"""Test extra state attributes."""

	def test_extra_attributes_complete(self, mock_hass, basic_config):
		"""Test all extra attributes are present when data available."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		thermostat._base_target_temperature = 20.0
		thermostat._current_adjustment = -1.0
		thermostat._current_price = 1.5
		thermostat._average_price = 1.0
		thermostat._next_high_price_hours = 3
		
		attrs = thermostat.extra_state_attributes
		
		assert "base_temperature" in attrs
		assert "current_adjustment" in attrs
		assert "current_price" in attrs
		assert "average_price" in attrs
		assert "price_ratio" in attrs
		assert "next_high_price_in_hours" in attrs
		assert "wrapped_climate_entity" in attrs

	def test_extra_attributes_minimal(self, mock_hass, basic_config):
		"""Test attributes when minimal data available."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		attrs = thermostat.extra_state_attributes
		
		# Should always have these
		assert "wrapped_climate_entity" in attrs
		assert "base_temperature" in attrs
		assert "current_adjustment" in attrs


class TestErrorHandling:
	"""Test error handling scenarios."""

	def test_unavailable_price_sensor(self, mock_hass, basic_config):
		"""Test handling of unavailable price sensor."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		unavailable_state = Mock()
		unavailable_state.state = STATE_UNAVAILABLE
		mock_hass.states.get = Mock(return_value=unavailable_state)
		
		import asyncio
		asyncio.run(thermostat._async_update_prices())
		
		assert thermostat._current_price is None
		assert thermostat._average_price is None

	def test_invalid_price_value(self, mock_hass, basic_config):
		"""Test handling of invalid price values."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		invalid_state = Mock()
		invalid_state.state = "invalid"
		mock_hass.states.get = Mock(return_value=invalid_state)
		
		import asyncio
		# Should not raise exception
		asyncio.run(thermostat._async_update_prices())

	def test_missing_climate_entity(self, mock_hass, basic_config):
		"""Test handling of missing climate entity."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		mock_hass.states.get = Mock(return_value=None)
		
		import asyncio
		asyncio.run(thermostat._async_update_from_climate())
		
		# Should not crash, base temperature should remain None or unchanged


class TestPreheating:
	"""Test pre-heating/pre-cooling logic."""

	def test_preheating_upcoming_high_price(self, mock_hass, basic_config):
		"""Test pre-heating activates before high price period."""
		thermostat = SmartThermostat(mock_hass, "test_entry", basic_config)
		
		thermostat._base_target_temperature = 20.0
		thermostat._current_price = 1.0
		thermostat._average_price = 1.0
		thermostat._next_high_price_hours = 1
		thermostat._preheating_enabled = True
		thermostat._preheating_hours = 2
		
		import asyncio
		asyncio.run(thermostat._async_calculate_adjustment())
		
		# Should increase temperature (positive adjustment for pre-heating)
		assert thermostat._current_adjustment > 0
		assert thermostat._current_adjustment <= thermostat._max_increase

	def test_no_preheating_when_disabled(self, mock_hass, basic_config):
		"""Test pre-heating doesn't activate when disabled."""
		config = {**basic_config, CONF_PREHEATING_ENABLED: False}
		thermostat = SmartThermostat(mock_hass, "test_entry", config)
		
		thermostat._base_target_temperature = 20.0
		thermostat._current_price = 1.0
		thermostat._average_price = 1.0
		thermostat._next_high_price_hours = 1
		
		import asyncio
		asyncio.run(thermostat._async_calculate_adjustment())
		
		# Should not adjust when preheating disabled
		assert thermostat._current_adjustment == 0.0

