"""Pytest configuration and fixtures for Smart Thermostat tests."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, AsyncMock

from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass():
	"""Create a mock Home Assistant instance for testing."""
	hass = Mock(spec=HomeAssistant)
	hass.states = Mock()
	hass.services = Mock()
	hass.services.async_call = AsyncMock()
	hass.config_entries = Mock()
	hass.data = {}
	hass.async_create_task = Mock()
	return hass

