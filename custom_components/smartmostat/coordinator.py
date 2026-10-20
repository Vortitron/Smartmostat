"""The per-entry controller: gathers state, runs the engine, sends commands."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
	ATTR_ENTITY_ID,
	ATTR_TEMPERATURE,
	ATTR_UNIT_OF_MEASUREMENT,
	EVENT_HOMEASSISTANT_STARTED,
	STATE_ON,
	STATE_UNAVAILABLE,
	STATE_UNKNOWN,
	UnitOfTemperature,
)
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
	async_call_later,
	async_track_point_in_time,
	async_track_state_change_event,
	async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .actuators import ClimateCommand, DeviceState, Readings, SwitchCommand, SwitchState
from .const import (
	AGGREGATE_MEAN,
	AGGREGATE_MIN,
	ATTR_BASE_TEMPERATURE,
	ATTR_CURRENT_ADJUSTMENT,
	COMMAND_TIMEOUT_SECONDS,
	CONF_COMFORT_TEMPERATURE,
	CONF_PRICE_OPTIMISATION,
	DEFAULTS,
	DEVICE_CHANGE_GRACE_SECONDS,
	DOMAIN,
	EVENT_DECISION,
	HVAC_COOL,
	HVAC_HEAT,
	HVAC_HEAT_COOL,
	HVAC_OFF,
	LIVE_OPTION_KEYS,
	MODE_SWITCH,
	OWN_COMMAND_MEMORY_MINUTES,
	PRESET_SCHEDULE,
	PRESETS,
	REASON_FALLBACK,
	SENSOR_DEBOUNCE_SECONDS,
	STARTUP_DELAY_SECONDS,
	STORAGE_VERSION,
	WATCHDOG_MINUTES,
	WEATHER_REFRESH_MINUTES,
)
from .engine import Decision, EngineInputs, decide, status_line
from .planner import Override, Plan, PlannerInputs, next_schedule_change, plan
from .price import PriceInfo, analyse
from .safety import RateLimiter, is_stale
from .settings import Settings, build_settings

_LOGGER = logging.getLogger(__name__)

UNUSABLE = (STATE_UNAVAILABLE, STATE_UNKNOWN, None, "")


def _float(value: Any) -> float | None:
	if value is None or isinstance(value, bool):
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if number != number or number in (float("inf"), float("-inf")):
		return None
	return number


def _parse_dt(value: Any) -> datetime | None:
	if isinstance(value, datetime):
		return value
	if isinstance(value, str):
		return dt_util.parse_datetime(value)
	return None


class SmartmostatController:
	"""One controller per config entry."""

	def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
		"""Create the controller (no I/O)."""
		self.hass = hass
		self.entry = entry
		self.settings: Settings = build_settings(entry.data, entry.options)
		self._options_snapshot = dict(entry.options)
		self._data_snapshot = dict(entry.data)
		self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
		self._lock = asyncio.Lock()
		self._pending = False
		self._pending_user = False
		self._listeners: list[Callable[[], None]] = []
		self._unsubs: list[CALLBACK_TYPE] = []
		self._timer_unsubs: dict[str, CALLBACK_TYPE] = {}
		self._rate = RateLimiter()
		self._started = False

		# Runtime state (persisted).
		self.hvac_mode: str = self._default_on_mode()
		self.last_on_mode: str = self.hvac_mode
		self.preset: str = PRESET_SCHEDULE
		self.override: Override | None = None
		self.paused_until: datetime | None = None
		self.frost_latched = False
		self.shed_latched = False
		self.expected: dict[str, Any] = {}
		self.expected_at: datetime | None = None
		self.room_missing_since: datetime | None = None
		self.had_stored_state = False
		self.restored_target: float | None = None
		# Set when an upgrade restored a mode this entry cannot drive (section 9).
		self.hands_off: str | None = None
		# What we actually sent recently, so a late report of our own earlier
		# command is not mistaken for a person (section 5.5).
		self._sent: list[tuple[datetime, dict[str, Any]]] = []

		# Last evaluation.
		self.decision: Decision | None = None
		self.plan: Plan | None = None
		self.price: PriceInfo | None = None
		self.readings: Readings | None = None
		self.status: str = "Starting"
		self.last_evaluated: datetime | None = None
		self.last_command: dict[str, Any] | None = None
		self._last_event_key: tuple[Any, ...] | None = None

		self._forecast: tuple[float | None, float | None] = (None, None)
		self._forecast_at: datetime | None = None

	# --- set-up -----------------------------------------------------------

	def _default_on_mode(self) -> str:
		if self.settings.mode == MODE_SWITCH:
			return HVAC_HEAT if self.settings.heater else HVAC_COOL
		if self.settings.engine.remote.cooling:
			return HVAC_HEAT_COOL
		return HVAC_HEAT

	@property
	def hvac_modes(self) -> list[str]:
		"""Modes the Smartmostat climate entity offers."""
		if self.settings.mode == MODE_SWITCH:
			modes = [HVAC_OFF]
			if self.settings.heater:
				modes.append(HVAC_HEAT)
			if self.settings.cooler:
				modes.append(HVAC_COOL)
			return modes
		modes = [HVAC_OFF, HVAC_HEAT]
		if self.settings.engine.remote.cooling:
			modes.append(HVAC_HEAT_COOL)
		return modes

	async def async_setup(self) -> None:
		"""Load stored runtime state."""
		stored = await self._store.async_load()
		if stored:
			self.had_stored_state = True
			self._load_state(stored)

	def _load_state(self, stored: dict[str, Any]) -> None:
		mode = stored.get("hvac_mode")
		if mode in self.hvac_modes:
			self.hvac_mode = mode
		last_on = stored.get("last_on_mode")
		if last_on in self.hvac_modes and last_on != HVAC_OFF:
			self.last_on_mode = last_on
		if stored.get("preset") in PRESETS:
			self.preset = stored["preset"]
		override = stored.get("override")
		if isinstance(override, dict) and _float(override.get("temperature")) is not None:
			self.override = Override(float(override["temperature"]), _parse_dt(override.get("until")))
		self.paused_until = _parse_dt(stored.get("paused_until"))
		self.frost_latched = bool(stored.get("frost_latched", False))
		self.shed_latched = bool(stored.get("shed_latched", False))
		expected = stored.get("expected")
		if isinstance(expected, dict):
			self.expected = expected
		hands_off = stored.get("hands_off")
		if isinstance(hands_off, str) and self.hvac_mode == HVAC_OFF:
			self.hands_off = hands_off
		self.room_missing_since = _parse_dt(stored.get("room_missing_since"))

	def apply_restored_state(self, state: State | None) -> None:
		"""First start after an upgrade: take mode, preset and target from the old entity."""
		if state is None or self.had_stored_state:
			return
		if state.state in self.hvac_modes:
			self.hvac_mode = state.state
			if state.state != HVAC_OFF:
				self.last_on_mode = state.state
		elif state.state not in UNUSABLE:
			# 0.1.0 and 0.2.0 offered the device's own modes (cool, auto, ...).
			# Turning that into heat would change a working device on upgrade,
			# so start off, leave the device alone and say why.
			_LOGGER.warning(
				"%s: restored mode %s is not offered by this entry; not controlling the device until it is turned on",
				self.settings.name,
				state.state,
			)
			self.hvac_mode = HVAC_OFF
			self.hands_off = str(state.state)
		preset = state.attributes.get("preset_mode")
		if preset in PRESETS:
			self.preset = preset
		self.restored_target = self._restored_comfort(state)

	@staticmethod
	def _restored_comfort(state: State) -> float | None:
		"""The user's own target from the old entity.

		0.1.0's ``temperature`` was base + current_adjustment (the price-shifted
		value); the user's setting was published as ``base_temperature``.
		"""
		attrs = state.attributes
		base = _float(attrs.get(ATTR_BASE_TEMPERATURE))
		if base is not None:
			return base
		target = _float(attrs.get(ATTR_TEMPERATURE))
		adjustment = _float(attrs.get(ATTR_CURRENT_ADJUSTMENT))
		if target is not None and adjustment is not None:
			return round(target - adjustment, 2)
		return target

	def _state_to_save(self) -> dict[str, Any]:
		return {
			"hvac_mode": self.hvac_mode,
			"last_on_mode": self.last_on_mode,
			"preset": self.preset,
			"override": None
			if self.override is None
			else {
				"temperature": self.override.temperature,
				"until": self.override.until.isoformat() if self.override.until else None,
			},
			"paused_until": self.paused_until.isoformat() if self.paused_until else None,
			"frost_latched": self.frost_latched,
			"shed_latched": self.shed_latched,
			"expected": self.expected,
			"hands_off": self.hands_off,
			"room_missing_since": self.room_missing_since.isoformat() if self.room_missing_since else None,
		}

	def _save(self) -> None:
		self._store.async_delay_save(self._state_to_save, 1)

	async def async_start(self) -> None:
		"""Subscribe to inputs and schedule the first evaluation."""
		s = self.settings
		device_entities = list(s.device_entities)
		if device_entities:
			self._unsubs.append(async_track_state_change_event(self.hass, device_entities, self._on_device_event))
		if s.price_sensor:
			self._unsubs.append(async_track_state_change_event(self.hass, [s.price_sensor], self._on_price_event))
		sensors = list(s.sensor_entities)
		if sensors:
			self._unsubs.append(async_track_state_change_event(self.hass, sensors, self._on_sensor_event))
		self._unsubs.append(
			async_track_time_interval(self.hass, self._on_watchdog, timedelta(minutes=WATCHDOG_MINUTES))
		)
		if self.hass.is_running:
			self._started = True
			self.entry.async_create_task(self.hass, self.async_evaluate(), "smartmostat first evaluation")
		else:

			@callback
			def _on_started(_event: Event) -> None:
				self._schedule("startup", STARTUP_DELAY_SECONDS)

			self._unsubs.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started))

	async def async_shutdown(self) -> None:
		"""Unload: stop listening, save state, leave the device as it is."""
		for unsub in self._unsubs:
			unsub()
		self._unsubs.clear()
		for unsub in self._timer_unsubs.values():
			unsub()
		self._timer_unsubs.clear()
		await self._store.async_save(self._state_to_save())

	# --- listeners --------------------------------------------------------

	@callback
	def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
		"""Entities subscribe here; returns an unsubscribe callable."""
		self._listeners.append(listener)

		@callback
		def _remove() -> None:
			if listener in self._listeners:
				self._listeners.remove(listener)

		return _remove

	@callback
	def _notify(self) -> None:
		for listener in list(self._listeners):
			listener()

	# --- triggers ---------------------------------------------------------

	@callback
	def _schedule(self, key: str, delay: float) -> None:
		"""Run an evaluation after ``delay`` seconds unless one is already queued."""
		if key in self._timer_unsubs:
			return

		@callback
		def _fire(_now: datetime) -> None:
			self._timer_unsubs.pop(key, None)
			self._started = True
			self.entry.async_create_task(self.hass, self.async_evaluate(), f"smartmostat {key}")

		self._timer_unsubs[key] = async_call_later(self.hass, delay, _fire)

	@callback
	def _schedule_at(self, key: str, when: datetime | None) -> None:
		"""(Re)arm a point-in-time evaluation."""
		old = self._timer_unsubs.pop(key, None)
		if old:
			old()
		if when is None:
			return

		@callback
		def _fire(_now: datetime) -> None:
			self._timer_unsubs.pop(key, None)
			self.entry.async_create_task(self.hass, self.async_evaluate(), f"smartmostat {key}")

		self._timer_unsubs[key] = async_track_point_in_time(self.hass, _fire, when + timedelta(seconds=1))

	@callback
	def _on_sensor_event(self, _event: Event[EventStateChangedData]) -> None:
		if self._started:
			self._schedule("sensor", SENSOR_DEBOUNCE_SECONDS)

	@callback
	def _on_price_event(self, _event: Event[EventStateChangedData]) -> None:
		if self._started:
			self.entry.async_create_task(self.hass, self.async_evaluate(), "smartmostat price")

	@callback
	def _on_watchdog(self, _now: datetime) -> None:
		if self._started:
			self.entry.async_create_task(self.hass, self.async_evaluate(), "smartmostat watchdog")

	@callback
	def _on_device_event(self, event: Event[EventStateChangedData]) -> None:
		new = event.data["new_state"]
		old = event.data["old_state"]
		if self._started and new is not None and old is not None:
			self._detect_device_change(event.data["entity_id"], old, new)
		if self._started:
			self.entry.async_create_task(self.hass, self.async_evaluate(), "smartmostat device")

	def _detect_device_change(self, entity_id: str, old: State, new: State) -> None:
		"""Section 5.5: respect a person using the remote or the vendor app."""
		if self.settings.dry_run:
			# Shadow mode: something else (sam.yaml) drives the device.
			return
		if new.state in UNUSABLE or old.state in UNUSABLE or not self.expected:
			return
		now = dt_util.utcnow()
		if self.expected_at is not None and now - self.expected_at < timedelta(seconds=DEVICE_CHANGE_GRACE_SECONDS):
			return
		if self.hvac_mode == HVAC_OFF:
			return
		recent = self._recent_sent(now)
		if self.settings.mode == MODE_SWITCH:
			key = "heater" if entity_id == self.settings.heater else "cooler"
			want = self.expected.get(key)
			now_on = self._switch_is_on(new)
			if want is None or now_on == want or self._switch_is_on(old) == now_on:
				return
			if any(sent.get(key) == now_on for sent in recent):
				return  # a late report of our own command
			self._pause(now, f"{entity_id} switched {'on' if now_on else 'off'}")
			return
		want_mode = self.expected.get("hvac_mode")
		want_temp = self.expected.get("temperature")
		mode_changed = want_mode is not None and new.state != want_mode and new.state != old.state
		new_temp = self._device_temp(new.attributes.get(ATTR_TEMPERATURE))
		old_temp = self._device_temp(old.attributes.get(ATTR_TEMPERATURE))
		step = _float(new.attributes.get("target_temp_step")) or 0.5
		temp_changed = (
			want_temp is not None
			and new_temp is not None
			and abs(new_temp - float(want_temp)) >= step / 2
			and (old_temp is None or abs(new_temp - old_temp) >= step / 2)
		)
		# A late report of a command we sent earlier is not a person.
		if mode_changed and any(new.state in (sent.get("hvac_mode"), sent.get("target_mode")) for sent in recent):
			mode_changed = False
		if (
			temp_changed
			and new_temp is not None
			and any(
				sent.get("temperature") is not None and abs(new_temp - float(sent["temperature"])) < step / 2
				for sent in recent
			)
		):
			temp_changed = False
		if not (mode_changed or temp_changed):
			return
		if mode_changed and new.state == HVAC_OFF:
			_LOGGER.info("%s: device switched off by hand, Smartmostat follows", self.settings.name)
			self.hvac_mode = HVAC_OFF
			self.paused_until = None
			self._save()
			return
		self._pause(now, f"device changed to {new.state} {new_temp}")

	def _recent_sent(self, now: datetime) -> list[dict[str, Any]]:
		"""Commands sent within OWN_COMMAND_MEMORY_MINUTES (older ones are forgotten)."""
		cutoff = now - timedelta(minutes=OWN_COMMAND_MEMORY_MINUTES)
		self._sent = [(at, sent) for at, sent in self._sent if at >= cutoff]
		return [sent for _at, sent in self._sent]

	def _pause(self, now: datetime, why: str) -> None:
		minutes = self.settings.override_minutes
		until = None
		if minutes <= 0:
			until = next_schedule_change(dt_util.as_local(now), self.settings.planner)
		if until is None:
			until = now + timedelta(minutes=minutes if minutes > 0 else DEFAULTS["override_minutes"])
		_LOGGER.info("%s: %s, pausing until %s", self.settings.name, why, until)
		self.paused_until = until
		self._save()

	# --- user actions -----------------------------------------------------

	async def async_set_hvac_mode(self, mode: str) -> None:
		"""Climate entity hvac mode."""
		if mode not in self.hvac_modes:
			return
		self.hvac_mode = mode
		if mode != HVAC_OFF:
			self.last_on_mode = mode
			self.paused_until = None
			self._clear_hands_off()
		self._save()
		await self.async_evaluate(user_action=True)

	@callback
	def _clear_hands_off(self) -> None:
		if self.hands_off is None:
			return
		self.hands_off = None
		ir.async_delete_issue(self.hass, DOMAIN, f"restored_mode_unsupported_{self.entry.entry_id}")

	async def async_turn_on(self) -> None:
		"""Back to the last on mode."""
		await self.async_set_hvac_mode(self.last_on_mode if self.last_on_mode in self.hvac_modes else self._default_on_mode())

	async def async_set_preset(self, preset: str) -> None:
		"""Preset change clears any override (section 5.4)."""
		if preset not in PRESETS:
			return
		self.preset = preset
		self.override = None
		self._save()
		await self.async_evaluate(user_action=True)

	async def async_set_temperature(self, temperature: float | None, hvac_mode: str | None = None) -> None:
		"""Climate set_temperature.

		With a comfort schedule this is a temporary override (Sam's 90-minute
		lock). Without a schedule, on the Schedule preset, it simply changes
		the comfort temperature, like any thermostat, and price logic carries on.
		"""
		if hvac_mode is not None and hvac_mode in self.hvac_modes:
			self.hvac_mode = hvac_mode
			if hvac_mode != HVAC_OFF:
				self.last_on_mode = hvac_mode
				self.paused_until = None
				self._clear_hands_off()
			self._save()
		if temperature is None:
			await self.async_evaluate(user_action=True)
			return
		if self.preset == PRESET_SCHEDULE and not self.settings.planner.schedule_configured:
			self.override = None
			self.async_update_live_option(CONF_COMFORT_TEMPERATURE, float(temperature))
			await self.async_evaluate(user_action=True)
			return
		await self.async_set_override(temperature, None)

	async def async_set_override(self, temperature: float, minutes: int | None) -> None:
		"""smartmostat.set_override."""
		now = dt_util.now()
		minutes = self.settings.override_minutes if minutes is None else int(minutes)
		if minutes > 0:
			until: datetime | None = now + timedelta(minutes=minutes)
		else:
			until = next_schedule_change(now, self.settings.planner)
		self.override = Override(float(temperature), until)
		self._save()
		await self.async_evaluate(user_action=True)

	async def async_clear_override(self) -> None:
		"""smartmostat.clear_override."""
		self.override = None
		self._save()
		await self.async_evaluate(user_action=True)

	async def async_resume(self) -> None:
		"""smartmostat.resume: end a device-side pause."""
		self.paused_until = None
		self._save()
		await self.async_evaluate(user_action=True)

	async def async_set_price_optimisation(self, enabled: bool) -> None:
		"""Price optimisation switch."""
		self.async_update_live_option(CONF_PRICE_OPTIMISATION, bool(enabled))
		await self.async_evaluate(user_action=True)

	@callback
	def async_update_live_option(self, key: str, value: Any) -> None:
		"""Write an option that applies without a reload."""
		options = {**self.entry.options, key: value}
		self._options_snapshot = dict(options)
		self.settings = build_settings(self.entry.data, options)
		self.hass.config_entries.async_update_entry(self.entry, options=options)

	def only_live_changes(self, entry: ConfigEntry) -> bool:
		"""True when the entry changed only in live options (no reload needed)."""
		if dict(entry.data) != self._data_snapshot:
			return False
		new = dict(entry.options)
		old = self._options_snapshot
		changed = {key for key in set(new) | set(old) if new.get(key) != old.get(key)}
		return changed <= LIVE_OPTION_KEYS

	@callback
	def apply_live_options(self) -> None:
		"""Pick up live option changes."""
		self._options_snapshot = dict(self.entry.options)
		self.settings = build_settings(self.entry.data, self.entry.options)

	# --- reading Home Assistant state ------------------------------------

	def _ha_unit(self) -> str:
		return self.hass.config.units.temperature_unit

	def _device_temp(self, value: Any) -> float | None:
		number = _float(value)
		if number is None:
			return None
		unit = self._ha_unit()
		if unit == UnitOfTemperature.CELSIUS:
			return number
		return round(TemperatureConverter.convert(number, unit, UnitOfTemperature.CELSIUS), 2)

	def to_device_unit(self, celsius: float) -> float:
		"""Convert a °C set-point to Home Assistant's unit for service calls."""
		unit = self._ha_unit()
		if unit == UnitOfTemperature.CELSIUS:
			return celsius
		return round(TemperatureConverter.convert(celsius, UnitOfTemperature.CELSIUS, unit), 1)

	def _sensor_value(self, entity_id: str | None, now: datetime) -> float | None:
		if not entity_id:
			return None
		state = self.hass.states.get(entity_id)
		if state is None or state.state in UNUSABLE:
			return None
		last = getattr(state, "last_reported", None) or state.last_updated
		if is_stale(last, now, self.settings.engine.safety.stale_minutes):
			return None
		value = _float(state.state)
		if value is None:
			return None
		unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
		if unit in (UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN):
			return round(TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS), 2)
		return value

	def _read(self, now: datetime, device: DeviceState | None) -> Readings:
		s = self.settings
		values: list[tuple[str, float]] = []
		for entity_id in s.room_sensors:
			value = self._sensor_value(entity_id, now)
			if value is not None:
				values.append((entity_id, value))
		room = None
		source = None
		if values:
			if s.room_aggregate == AGGREGATE_MIN:
				source, room = min(values, key=lambda item: item[1])
			elif s.room_aggregate == AGGREGATE_MEAN:
				room = sum(v for _e, v in values) / len(values)
				source = "mean"
			else:
				source, room = values[0]
		internal = None
		if s.mode != MODE_SWITCH:
			internal = self._sensor_value(s.internal_sensor, now)
			if internal is None and device is not None and device.available:
				internal = device.current
		outdoor = self._sensor_value(s.outdoor_sensor, now)
		return Readings(
			room=room,
			room_max=max(v for _e, v in values) if values else None,
			internal=internal,
			outdoor=outdoor,
			room_source=source,
		)

	def _device_state(self) -> DeviceState | None:
		entity_id = self.settings.target_climate
		if not entity_id:
			return None
		state = self.hass.states.get(entity_id)
		if state is None:
			return None
		attrs = state.attributes
		step = _float(attrs.get("target_temp_step")) or 0.5
		if self._ha_unit() != UnitOfTemperature.CELSIUS:
			step = round(step * 5 / 9, 3)
		return DeviceState(
			available=state.state not in UNUSABLE,
			hvac_mode=state.state,
			target=self._device_temp(attrs.get(ATTR_TEMPERATURE)),
			current=self._device_temp(attrs.get("current_temperature")),
			hvac_modes=tuple(str(mode) for mode in attrs.get("hvac_modes") or ()),
			min_temp=self._device_temp(attrs.get("min_temp")) or 7.0,
			max_temp=self._device_temp(attrs.get("max_temp")) or 35.0,
			step=step,
			preset=attrs.get("preset_mode"),
			presets=tuple(attrs.get("preset_modes") or ()),
			hvac_action=attrs.get("hvac_action"),
		)

	@staticmethod
	def _switch_is_on(state: State | None) -> bool:
		if state is None:
			return False
		if state.domain == "climate":
			return state.state not in (HVAC_OFF, *UNUSABLE)
		return state.state == STATE_ON

	def switch_state(self) -> SwitchState:
		def one(entity_id: str | None) -> tuple[bool | None, datetime | None, bool]:
			if not entity_id:
				return None, None, False
			state = self.hass.states.get(entity_id)
			if state is None or state.state in UNUSABLE:
				return False, None, False
			return self._switch_is_on(state), state.last_changed, True

		heater_on, heater_changed, heater_ok = one(self.settings.heater)
		cooler_on, cooler_changed, cooler_ok = one(self.settings.cooler)
		return SwitchState(heater_on, cooler_on, heater_changed, cooler_changed, heater_ok, cooler_ok)

	def _thermal(self, entity_id: str | None, number: float | None, now: datetime) -> float | None:
		if entity_id:
			state = self.hass.states.get(entity_id)
			if state is not None:
				value = _float(state.state)
				if value is not None and value > 0:
					return value
		return number if number is not None and number > 0 else None

	async def _async_forecast(self, now: datetime) -> tuple[float | None, float | None]:
		"""(today's forecast max, mean of the next forecast_hours), cached 30 min."""
		weather = self.settings.weather_entity
		if not weather:
			return None, None
		if self._forecast_at is not None and now - self._forecast_at < timedelta(minutes=WEATHER_REFRESH_MINUTES):
			return self._forecast
		self._forecast_at = now
		state = self.hass.states.get(weather)
		unit = state.attributes.get("temperature_unit") if state else None

		def to_c(value: Any) -> float | None:
			number = _float(value)
			if number is None:
				return None
			if unit in (UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN):
				return TemperatureConverter.convert(number, unit, UnitOfTemperature.CELSIUS)
			return number

		async def fetch(kind: str) -> list[dict[str, Any]]:
			try:
				async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
					response = await self.hass.services.async_call(
						"weather",
						"get_forecasts",
						{ATTR_ENTITY_ID: weather, "type": kind},
						blocking=True,
						return_response=True,
					)
			except Exception as err:  # noqa: BLE001 - any failure falls back to the outdoor sensor
				_LOGGER.debug("%s: %s forecast unavailable: %s", self.settings.name, kind, err)
				return []
			if not isinstance(response, dict):
				return []
			forecast = (response.get(weather) or {}).get("forecast")
			return forecast if isinstance(forecast, list) else []

		hourly = await fetch("hourly")
		today = now.date()
		mean = None
		day_max = None
		upcoming = []
		today_temps = []
		for item in hourly:
			when = _parse_dt(item.get("datetime"))
			temp = to_c(item.get("temperature"))
			if when is None or temp is None:
				continue
			when = dt_util.as_local(when)
			if when >= now - timedelta(hours=1) and len(upcoming) < max(1, self.settings.forecast_hours):
				upcoming.append(temp)
			if when.date() == today:
				today_temps.append(temp)
		if upcoming:
			mean = sum(upcoming) / len(upcoming)
		daily = await fetch("daily")
		for item in daily:
			when = _parse_dt(item.get("datetime"))
			if when is not None and dt_util.as_local(when).date() == today:
				day_max = to_c(item.get("temperature"))
				break
		if day_max is None and today_temps:
			day_max = max(today_temps)
		self._forecast = (day_max, mean)
		return self._forecast

	# --- evaluation -------------------------------------------------------

	async def async_evaluate(self, user_action: bool = False) -> Decision | None:
		"""Evaluate now. A trigger arriving mid-run queues exactly one follow-up."""
		if self._lock.locked():
			self._pending = True
			self._pending_user = self._pending_user or user_action
			return self.decision
		async with self._lock:
			self._started = True
			decision = await self._evaluate_once(user_action)
			while self._pending:
				self._pending = False
				queued_user = self._pending_user
				self._pending_user = False
				decision = await self._evaluate_once(queued_user)
			return decision

	def _resolve_comfort(self, device: DeviceState | None) -> None:
		"""Migrated entries: comfort temperature from the old entity or device."""
		if self.settings.comfort_configured:
			return
		value = self.restored_target
		if value is None and device is not None and device.target is not None:
			value = device.target
		if value is None:
			value = float(DEFAULTS[CONF_COMFORT_TEMPERATURE])
		_LOGGER.info("%s: comfort temperature set to %s from previous state", self.settings.name, value)
		self.async_update_live_option(CONF_COMFORT_TEMPERATURE, float(value))

	async def _evaluate_once(self, user_action: bool) -> Decision:
		s = self.settings
		now = dt_util.now()
		device = self._device_state() if s.mode != MODE_SWITCH else None
		self._resolve_comfort(device)
		s = self.settings
		readings = self._read(now, device)
		if readings.room is None:
			if self.room_missing_since is None:
				self.room_missing_since = now
		else:
			self.room_missing_since = None

		price_state = self.hass.states.get(s.price_sensor) if s.price_sensor else None
		price = analyse(
			price_state.state if price_state is not None else None,
			price_state.attributes if price_state is not None else None,
			now,
			s.price,
			self.shed_latched,
		)
		self.shed_latched = price.super_expensive

		if self.override is not None and not self.override.active(now):
			self.override = None
		if self.paused_until is not None and now >= self.paused_until:
			self.paused_until = None

		forecast_max, forecast_mean = await self._async_forecast(now)
		planner_inputs = PlannerInputs(
			now=now,
			price=price,
			preset=self.preset,
			override=self.override,
			room=readings.room,
			outdoor=readings.outdoor,
			forecast_max=forecast_max,
			forecast_mean=forecast_mean,
			thermal_k=self._thermal(s.thermal_k_entity, s.thermal_k, now),
			thermal_h=self._thermal(s.thermal_h_entity, s.thermal_h, now),
		)
		the_plan = plan(planner_inputs, s.planner)
		inputs = EngineInputs(
			now=now,
			plan=the_plan,
			price=price,
			readings=readings,
			hvac_mode=self.hvac_mode,
			preset=self.preset,
			override_active=self.override is not None,
			paused_until=self.paused_until,
			device=device,
			switch_state=self.switch_state() if s.mode == MODE_SWITCH else None,
			frost_latched=self.frost_latched,
			room_missing_since=self.room_missing_since,
			hands_off=self.hands_off is not None and self.hvac_mode == HVAC_OFF,
		)
		decision = decide(inputs, s.engine)
		self.frost_latched = decision.frost

		await self._apply(decision, inputs, user_action, now)

		self.decision = decision
		self.plan = the_plan
		self.price = price
		self.readings = readings
		self.last_evaluated = now
		self.status = status_line(decision, inputs, self.hvac_mode)
		self._update_issues(decision)
		self._fire_event(decision, inputs)
		self._save()
		self._schedule_at("override", self.override.until if self.override else None)
		self._schedule_at("pause", self.paused_until)
		self._schedule_at("schedule", next_schedule_change(now, s.planner))
		self._notify()
		return decision

	async def _apply(self, decision: Decision, inputs: EngineInputs, user_action: bool, now: datetime) -> None:
		"""Send the command (rate limited), and remember what the device should be."""
		s = self.settings
		command = decision.command
		device_key = s.target_climate or s.heater or s.cooler or "device"
		if command is not None:
			bypass = user_action or decision.bypass_rate_limit
			if not self._rate.allowed(device_key, now, bypass):
				decision.details["rate_limited"] = True
				return
			self._rate.record(device_key, now)
			self.last_command = {"at": now.isoformat(), **command.as_dict()}
			if s.dry_run:
				_LOGGER.info("%s: dry run, would send %s (%s)", s.name, command.as_dict(), decision.headline)
			elif isinstance(command, ClimateCommand):
				self.entry.async_create_task(self.hass, self._send_climate(command), "smartmostat command")
			elif isinstance(command, SwitchCommand):
				self.entry.async_create_task(self.hass, self._send_switch(command), "smartmostat switch")
			if not s.dry_run:
				sent_at = dt_util.utcnow()
				self._recent_sent(sent_at)
				self._sent.append((sent_at, {**command.as_dict(), "target_mode": getattr(command, "target_mode", None)}))
			self.expected_at = dt_util.utcnow()

		# What the device should report from now on (for device-change detection).
		if decision.paused or decision.device_unavailable:
			return
		if s.mode == MODE_SWITCH:
			state = inputs.switch_state or SwitchState()
			heater = state.heater_on
			cooler = state.cooler_on
			if isinstance(command, SwitchCommand):
				heater = command.heater_on if command.heater_on is not None else heater
				cooler = command.cooler_on if command.cooler_on is not None else cooler
			self.expected = {"heater": heater, "cooler": cooler}
		elif decision.intent is not None and inputs.device is not None:
			mode = decision.intent.hvac_mode or inputs.device.hvac_mode
			temperature = decision.intent.temperature
			if temperature is None and mode != HVAC_OFF:
				temperature = inputs.device.target
			self.expected = {"hvac_mode": mode, "temperature": temperature}

	async def _call(self, domain: str, service: str, data: dict[str, Any]) -> bool:
		try:
			async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
				await self.hass.services.async_call(domain, service, data, blocking=True)
		except TimeoutError:
			_LOGGER.warning("%s: %s.%s timed out", self.settings.name, domain, service)
			return False
		except Exception as err:  # noqa: BLE001 - a failing device must not break the controller
			_LOGGER.warning("%s: %s.%s failed: %s", self.settings.name, domain, service, err)
			return False
		return True

	async def _send_climate(self, command: ClimateCommand) -> None:
		entity_id = self.settings.target_climate
		if command.preset is not None:
			await self._call("climate", "set_preset_mode", {ATTR_ENTITY_ID: entity_id, "preset_mode": command.preset})
		if command.hvac_mode is not None:
			await self._call("climate", "set_hvac_mode", {ATTR_ENTITY_ID: entity_id, "hvac_mode": command.hvac_mode})
		if command.temperature is not None:
			data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: self.to_device_unit(command.temperature)}
			if command.target_mode and self.settings.engine.remote.allow_hvac_mode_changes and command.hvac_mode is None:
				data["hvac_mode"] = command.target_mode
			await self._call("climate", "set_temperature", data)
		self.expected_at = dt_util.utcnow()

	async def _send_switch(self, command: SwitchCommand) -> None:
		for entity_id, on in ((self.settings.heater, command.heater_on), (self.settings.cooler, command.cooler_on)):
			if entity_id is None or on is None:
				continue
			domain = entity_id.split(".", 1)[0]
			if domain not in ("switch", "input_boolean", "fan", "climate"):
				domain = "homeassistant"
			await self._call(domain, "turn_on" if on else "turn_off", {ATTR_ENTITY_ID: entity_id})
		self.expected_at = dt_util.utcnow()

	@callback
	def _update_issues(self, decision: Decision) -> None:
		entry_id = self.entry.entry_id
		placeholders = {"name": self.settings.name}
		if decision.frost and self.hvac_mode == HVAC_OFF:
			ir.async_create_issue(
				self.hass,
				DOMAIN,
				f"frost_while_off_{entry_id}",
				is_fixable=False,
				severity=ir.IssueSeverity.WARNING,
				translation_key="frost_while_off",
				translation_placeholders=placeholders,
			)
		else:
			ir.async_delete_issue(self.hass, DOMAIN, f"frost_while_off_{entry_id}")
		if decision.reason == REASON_FALLBACK:
			ir.async_create_issue(
				self.hass,
				DOMAIN,
				f"no_readings_{entry_id}",
				is_fixable=False,
				severity=ir.IssueSeverity.WARNING,
				translation_key="no_readings",
				translation_placeholders=placeholders,
			)
		else:
			ir.async_delete_issue(self.hass, DOMAIN, f"no_readings_{entry_id}")
		if self.hands_off is not None and self.hvac_mode == HVAC_OFF:
			ir.async_create_issue(
				self.hass,
				DOMAIN,
				f"restored_mode_unsupported_{entry_id}",
				is_fixable=False,
				severity=ir.IssueSeverity.WARNING,
				translation_key="restored_mode_unsupported",
				translation_placeholders={**placeholders, "mode": self.hands_off},
			)

	@callback
	def _fire_event(self, decision: Decision, inputs: EngineInputs) -> None:
		key = decision.change_key()
		if key == self._last_event_key:
			return
		self._last_event_key = key
		if not self.settings.diagnostic_events:
			return
		self.hass.bus.async_fire(EVENT_DECISION, self.decision_dict())

	def decision_dict(self) -> dict[str, Any]:
		"""The decision as a plain dict (event data, evaluate response)."""
		decision = self.decision
		plan_ = self.plan
		readings = self.readings
		data: dict[str, Any] = {
			"entry_id": self.entry.entry_id,
			"name": self.settings.name,
			"control_mode": self.settings.mode,
			"hvac_mode": self.hvac_mode,
			"preset": self.preset,
			"evaluated": self.last_evaluated.isoformat() if self.last_evaluated else None,
			"status": self.status,
		}
		if decision is not None:
			data.update(
				{
					"reason": decision.reason,
					"headline": decision.headline,
					"action": decision.action,
					"command": decision.command.as_dict() if decision.command is not None else None,
					"intent": None
					if decision.intent is None
					else {"hvac_mode": decision.intent.hvac_mode, "temperature": decision.intent.temperature},
					"frost": decision.frost,
					"shed": decision.shed,
					"fallback": decision.fallback,
					"paused": decision.paused,
					"device_unavailable": decision.device_unavailable,
					"dry_run": self.settings.dry_run,
				}
			)
		if plan_ is not None:
			data.update(
				{
					"base_target": plan_.base_target,
					"control_target": plan_.control_target,
					"current_adjustment": plan_.current_adjustment,
					"plan_flags": {k: v for k, v in plan_.flags.items()},
				}
			)
		if readings is not None:
			data.update(
				{
					"room": readings.room,
					"room_source": readings.room_source,
					"internal": readings.internal,
					"outdoor": readings.outdoor,
				}
			)
		if self.price is not None:
			data["price"] = self.price.as_dict()
		return data

	def diagnostics(self) -> dict[str, Any]:
		"""Runtime state for diagnostics."""
		return {
			"state": self._state_to_save(),
			"last_command": self.last_command,
			"decision": self.decision_dict(),
			"forecast": {"max": self._forecast[0], "mean": self._forecast[1]},
		}
