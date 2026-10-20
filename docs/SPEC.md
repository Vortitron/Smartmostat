# Smartmostat 0.3.0 ("finished") - specification

Status: draft for implementation, October 2026.
Scope: one release that can be built, tested and shipped in a single pass.

## 0. Why this document exists

The repository currently holds three different designs that contradict each other:

| Where | Design | Notes |
|---|---|---|
| 0.1.0 (installed copy at `/var/www/ha-shared-components/smartmostat`, `VERSION = 1`) | Wrap a `climate` entity and shift its set-point by price ratio (current / `average`). | Tests in `tests/test_climate.py` still target this. |
| `IMPROVEMENTS_V2.md`, `SUMMARY.md` | "Max variance" linear curve on price position. | Never implemented: `CONF_MAX_VARIANCE` exists nowhere in the code. |
| 0.2.0 code (`VERSION = 2`), `TOLERANCE_*.md`, README | Two modes: "tolerance" (switch a heater with price-dependent hysteresis) and "temperature" (a copy of the old `remote_temperature_hvac_control` YAML). | No config entry migration, broken translations, tests not updated. |

Meanwhile the owner's real heat pump ("Sam", `climate.sam`, `panasonic_cc`) is run successfully by
hand-built automations (`sam.yaml`, `DaytimeCheapHeat.yaml`, `ElectricityPriceRank.yaml`,
`CheapLeccy.yaml`, `HouseThermalModel.yaml`, `forecast_sensors.yaml`, `SuperExpensive.yaml`) that
have accumulated a year of hard-won fixes. Smartmostat was meant to be the reusable version of
that. This spec decides what 0.3.0 is: **the Sam automations, generalised, as one integration,
with 0.1.0 and 0.2.0 entries migrated.**

### 0.1 Facts gathered (20 Oct 2026)

- **GamlaBio (HA 2026.10.0) has no `smartmostat` config entries, no `smartmostat` entities and no
  `custom_components/smartmostat` folder.** 0.1.0 is in the shared-components copy only. So no
  production entry can break, but migration is still specified for anyone else who installed
  0.1.0 or 0.2.0 from HACS.
- The live Nordpool sensor (`sensor.nordpool_kwh_se4_sek_3_10_025`, HACS Nordpool) now publishes
  **96 fifteen-minute slots** per day in `raw_today` / `raw_tomorrow`, each
  `{"start": "2026-10-20T00:00:00+02:00", "end": ..., "value": 2.336}`. Over the API `start` is an
  ISO string with an offset; inside HA it can be a `datetime`. `today` is a list of 96 floats.
  `average` (2.482) differs from `mean` (2.352) on the same day.
- `climate.sam`: modes `off, heat_cool, cool, dry, fan_only, heat`, `min_temp` 16, `max_temp` 30,
  step 0.5, presets `none, quiet, powerful, heat_8_15`. Seen at `current_temperature` 20 (its own
  ceiling sensor) with target 28.5: the remote-sensor "boost" behaviour working as intended.

### 0.2 Why CI failed on the last push (run 19240340105 / 19240340002, 10 Nov 2025)

**Python Tests (exit code 2, 3.11 job failed, 3.12 cancelled).** Exit code 2 is pytest's
"errors during collection". `tests/test_climate.py` imports `CONF_MAX_INCREASE`,
`CONF_MAX_DECREASE`, `CONF_PRICE_THRESHOLD_HIGH`, `CONF_PRICE_THRESHOLD_LOW`,
`CONF_PREHEATING_ENABLED`, `CONF_PREHEATING_HOURS` and the matching `DEFAULT_*` names from
`const.py`. 0.2.0 deleted all of them, so the module fails to import and nothing runs. (The step
logs have expired from GitHub, HTTP 410; the cause is confirmed statically: none of those names
exist in 0.2.0 `const.py`.) The tests also exercise 0.1.0 internals (`_current_adjustment`,
`_async_calculate_adjustment`, `_average_price`) that no longer exist.

**HACS Validation (3 of 8 checks failed):**

1. `hacsjson`: `extra keys not allowed @ data['domains']`. `hacs.json` still carries the long
   retired `domains` key.
2. `brands`: the domain is not in `home-assistant/brands`.
3. `topics`: the GitHub repository has no topics.

**Found while reading, not caught by CI:**

- `custom_components/smartmostat/translations/en.json` is truncated to two lines (`{` and
  `"config": {`): invalid JSON, so the config flow has no strings.
- 0.2.0 bumps `ConfigFlow.VERSION` to 2 but has no `async_migrate_entry`. HA refuses to set up a
  version 1 entry ("migration handler not found"), so upgrading 0.1.0 to 0.2.0 kills every entry.
  Even if it loaded, a v1 entry would fall into tolerance mode with no heater and do nothing.
- Both versions compare `datetime.fromisoformat(start)` (offset-aware, or a `TypeError` if
  `start` is already a `datetime`) with naive `datetime.now()`. The `TypeError` is caught and the
  slot skipped, so **look-ahead, price range and pre-heating have never worked** on a real
  Nordpool sensor. The 0.2.0 `price_position` is therefore always `None` and its tolerance mode
  always uses the minimum band.
- `if not self._current_price` (0.1.0) treats a price of exactly 0 as "no data". Zero and negative
  prices are routine in SE3/SE4.
- Options flow assigns `self.config_entry = config_entry`, which HA deprecated in 2024.11 and
  turned into an error in 2025.12. On HA 2026.10 opening Options would fail.
- `TOLERANCE_APPROACH.md` claims the bands cross at `min_tolerance`; the code crosses at
  `(min + max) / 2` (1.1 °C with defaults).
- `example_configuration.yaml` repeats the `automation:` key three times (invalid YAML) and refers
  to 0.1.0 attributes.

## 1. Goals and non-goals

### Goals

1. One climate entity per zone that a person can set like any thermostat, while Smartmostat
   decides what the real device is told, using price and (optionally) a remote room sensor.
2. Capture what Sam does well, without any Sam entity ids or hardware assumptions:
   - the **two-number architecture** (comfort target vs price-adjusted control target);
   - the **two-signal price gate** (relative *and* absolute) for both cheap and expensive calls;
   - **pre-warming in a window before a comfort period**, sized to need, widened when cold, never
     a flat overnight blast;
   - **remote-sensor control** of a heat pump through its own internal reading, with the
     dynamic "work harder when far off target" boost, the overheat guard and the room ceiling;
   - **fallbacks**: device acts as its own thermostat when the room sensor drops out; price logic
     switches itself off when price data is missing;
   - the **manual override lock** (a person's change sticks for 90 minutes, price ignored);
   - **holiday / frost** behaviour, and the **super-expensive shed** that never sheds blind;
   - the **headline / reason / status** diagnostics;
   - **send only on change** (no command churn).
3. Keep every 0.1.0 and 0.2.0 config entry loading after upgrade, with the same entity ids.
4. Be safe: never leave a house unheated in frost, behave sensibly with missing data, respect
   people.
5. Green CI (pytest, hassfest, HACS).

### Non-goals for 0.3.0

Listed with reasons in section 11. In short: no thermal-model learning, no occupancy/TV logic,
no Superchill or vendor presets, no circulation-fan control, no cheap pre-cool or scorcher logic,
no built-in-Nordpool service support, no multi-zone coordination.

## 2. Architecture

```
            inputs                          core (pure Python, no HA imports)                    actuator
  price sensor ──► PriceAnalyser ─┐
  room sensor(s) ─────────────────┤
  outdoor / weather ──────────────┼──► Planner ──► control target + reason ──► Actuator ──► device command
  presets, schedule, override ────┤                                              │            (only if changed)
  thermal params (optional) ──────┘                                    SafetyLayer (wraps every decision)
```

- `price.py`: `PriceAnalyser`, pure functions over a list of `PriceSlot(start, end, value)`.
- `planner.py`: `plan(inputs) -> Plan(base_target, control_target, reason, headline_reason, flags)`.
  Generalised `DaytimeCheapHeat.yaml`.
- `actuators.py`: three actuators, each `decide(plan, readings, device) -> Command | None`:
  - `RemoteSensorActuator` (generalised `sam.yaml` heating and basic cooling);
  - `SetpointActuator` (0.1.0 behaviour: tell the device the control target directly);
  - `SwitchActuator` (0.2.0 tolerance mode: switch a heater/cooler with hysteresis).
- `safety.py`: frost guard, stale-sensor handling, shed guard, command rate limit.
- `coordinator.py`: one `SmartmostatController` per entry: subscribes to state changes, runs a
  5-minute watchdog tick, evaluates core, applies commands, stores runtime state
  (`homeassistant.helpers.storage.Store`), and feeds the entities.
- Platforms: `climate`, `sensor`, `switch`.

All decision logic lives in the three pure modules, so the bulk of the test suite needs no HA
instance and can replay Sam's regression cases directly.

Evaluation triggers: any input state change (room/internal/outdoor sensors debounced 30 s, as
Sam does), price sensor state or attribute change, preset/target/mode change, override expiry,
the 5-minute watchdog, and HA start. Concurrency: one evaluation at a time per entry
(`asyncio.Lock`); a trigger arriving mid-run schedules exactly one follow-up run (Sam's
`mode: queued, max: 2`).

## 3. Control modes

Chosen at setup, changeable later only by reconfigure (because each needs different entities).

| Mode key | Name in UI | Device | What Smartmostat sends | Origin |
|---|---|---|---|---|
| `remote_sensor` | Remote sensor (heat pump / AC) | `climate` entity | hvac mode + set-point computed from the device's own reading so the device heats to the **room** sensor | `sam.yaml`, `remote_temperature_hvac_control`, 0.2.0 "temperature" |
| `setpoint` | Set-point (any thermostat) | `climate` entity | the control target as its set-point | 0.1.0 |
| `switch` | Switch (heater / cooler relay) | `switch`, `input_boolean`, `fan` (heater and/or cooler) | on / off with hysteresis around the control target | 0.2.0 "tolerance" |

The **Planner is the same for all three**: price, schedule, presets, override and safety behave
identically; only the last step differs.

## 4. Inputs

### 4.1 Entities (config flow, stored in `entry.data`)

| Key | Required | Modes | Notes |
|---|---|---|---|
| `name` | yes | all | Entity name prefix. |
| `control_mode` | yes | all | Section 3. |
| `target_climate` | yes | `remote_sensor`, `setpoint` | The real device. |
| `heater`, `cooler` | at least one | `switch` | Domains `switch`, `input_boolean`, `fan`. (0.2.0 also offered `climate` here; migrated entries keep it and get `climate.turn_on/off`.) |
| `price_sensor` | yes | all | Section 4.2. May be `unavailable` at setup time (a warning, not an error), because Nordpool restarts slowly. |
| `room_sensors` | yes for `remote_sensor` and `switch`; optional for `setpoint` | all | One or more `sensor` entities, `device_class: temperature`, in order of preference. |
| `room_aggregate` | no | all | `first_available` (default), `min`, `mean`. Sam's "min(living, bedroom) while the circulation fan runs" becomes `min` all the time if wanted. |
| `internal_sensor` | no | `remote_sensor` | Overrides the device's `current_temperature` (Sam: `sensor.sam_inside_temperature`). |
| `outdoor_sensor` | no | all | Used for the cold-weather pre-warm widening, mild coasting, cooling gates, frost fallback. |
| `weather_entity` | no | all | `weather.*`. Used only for (a) today's forecast maximum and (b) the mean of the next `forecast_hours` (4) hourly temperatures. Fetched with `weather.get_forecasts` every 30 minutes, cached; failures fall back to the outdoor sensor. |
| `thermal_k`, `thermal_h` | no | all | Either a number or an entity id (`input_number` / `sensor`). Lets Sam's existing `HouseThermalModel.yaml` keep learning and feed Smartmostat (`input_number.house_heat_loss_k`, `input_number.house_heat_rate`). |

### 4.2 Price sensor parsing

`PriceAnalyser.from_state(state, now)` accepts, in order of preference:

1. `raw_today` / `raw_tomorrow`: list of mappings with `start` (ISO string **or** `datetime`,
   offset-aware or naive-local), optional `end`, and `value`. Slot length is `end - start`, else
   the gap to the next slot, else `24 h / len`. 15-minute and 60-minute slots both work.
2. `today` / `tomorrow`: list of floats; starts are local midnight plus `i * (24 h / len)`.
3. Neither: current state only. Only the "super-expensive" absolute threshold can work; the
   relative and pre-warm logic reports `price_data: partial`.

Rules:

- All times converted with `dt_util.as_local`; `now` is always `dt_util.now()` (aware).
  Never compare naive and aware datetimes (the 0.1.0/0.2.0 bug).
- Unparsable slots are skipped and counted; if more than half are bad the data is "invalid".
- `0` and negative prices are valid values. No division by the price itself anywhere.
- The current price is the value of the slot containing `now`; the sensor state is the fallback.
- **Daily average**: mean of today's slots, computed by Smartmostat (not the `average`
  attribute, which disagrees with `mean` on the live sensor). The attribute is the fallback.
- **Hourly view**: slots are averaged into clock hours, as `ElectricityPriceRank.yaml` does,
  so 15-minute jitter does not flip decisions.

Derived signals (all in `PriceInfo`, all exposed as attributes):

| Signal | Definition | Sam equivalent |
|---|---|---|
| `price_now` | current slot value | sensor state |
| `day_average` | mean of today's slots | `average` attribute / CheapLeccy average |
| `forward_average` | mean over the next `lookahead_hours` (default 4) using today **and** tomorrow | `electricity_price_rank_4h` |
| `percentile_today` | rank of the current hour among today's 24 hourly means, 0 (cheapest) to 1 | `electricity_price_rank / 23` |
| `price_position` | (now - min) / (max - min) over the next 24 h, 0.5 if flat | 0.2.0 attribute, kept |
| `relatively_cheap` | `price_now < forward_average - relative_margin` | `rank < rank_4h` |
| `relatively_expensive` | `price_now > forward_average + relative_margin` | `rank > rank_4h` |
| `absolutely_cheap` | `price_now <= cheap_ratio * day_average` (when the average is > 0, else `price_now <= day_average`) **or** `percentile_today <= cheap_percentile` | `cheap_leccy` (ratio 0.5) or `rank <= 11` |
| `absolutely_expensive` | `price_now >= expensive_ratio * day_average` | `price >= average` |
| `cheap_now` | `relatively_cheap and absolutely_cheap` | `electricity_cheap_now and price_genuinely_cheap` |
| `expensive_now` | `relatively_expensive and absolutely_expensive` | `electricity_expensive_now` |
| `super_expensive` | `price_now >= shed_price` latching, releases below `shed_price - shed_hysteresis` | `SuperExpensive.yaml` |
| `level` | `super_expensive` > `expensive` > `cheap` > `normal`; `unknown` without data | headline wording |

**Deliberate simplification:** Sam compares two rank numbers computed over *today's hours only*
(and scales the 4 h rank to 0..23). That is opaque and breaks across midnight when tomorrow is
already known. Smartmostat compares the current price with the forward average directly, using
tomorrow's slots when present. The documented regressions (3 Sep 06:00 and 18:00 called cheap;
10 Sep 09:40 called expensive) must still come out right, and they do because the absolute gate,
not the relative test, is what fixed them.

### 4.3 Tunables (options flow, stored in `entry.options`)

Defaults are Sam's values, generalised. Temperatures in °C, using HA's unit system for display.

**Comfort and schedule**

| Key | Default | Meaning |
|---|---|---|
| `comfort_temperature` | 20 | Target in the comfort period and for the `comfort` preset. Also what the climate entity shows as target unless a preset or override says otherwise. |
| `eco_temperature` | none | Base target outside the comfort period. Unset means "comfort all day" (the 0.1.0/0.2.0 behaviour). Sam: 16. |
| `comfort_start`, `comfort_end` | none | Daily comfort period, local time. Sam: 19:00 to 23:00. Unset disables the schedule and pre-warming. |
| `away_temperature` | 10 | `away` preset (Sam's holiday mode). |
| `override_minutes` | 90 | Manual override lock length. 0 means "until the next schedule change". |
| `away_device_preset` | none | Device preset to set while `away` and clear afterwards (`remote_sensor`, `setpoint`). Sam needs `heat_8_15`: its `min_temp` is 16, so a 10 °C away target is otherwise clamped to 16. This is Sam's holiday-preset handling, generalised; it is the only vendor preset Smartmostat touches. |
| `min_target`, `max_target` | 7, 25 | Hard clamp on any control target (25 is Sam's `prewarm_max`). |

**Price behaviour**

| Key | Default | Meaning |
|---|---|---|
| `price_optimisation` | on | Master switch (also exposed as a switch entity). Off = Sam's fixed-price feed. |
| `lookahead_hours` | 4 | Forward window for the relative test. |
| `relative_margin` | 0 | Price units; a dead band for the relative test. |
| `cheap_ratio` | 0.5 | Absolute cheap bar vs day average. |
| `cheap_percentile` | 0.48 | Absolute cheap bar by rank (11 of 23). |
| `expensive_ratio` | 1.0 | Absolute expensive bar vs day average. |
| `cheap_boost` | 3 | Raise over base when cheap (outside pre-warm). |
| `boost_skip_margin` | 0.5 | Skip the boost if the room is already within this of the boosted value. |
| `expensive_cut` | 2 | Lower base by this when expensive, never below `eco_temperature` or `min_target`. |
| `prewarm_hours` | 4 | Pre-warm window length before `comfort_start` (Sam 15:00). |
| `prewarm_hours_cold` | 6 | Window length when outdoor < `cold_outdoor` (Sam 13:00). |
| `cold_outdoor` | 10 | See above. |
| `hot_day_max` | 25 | With a weather entity: no cheap boost before `morning_end` when today's forecast max is above this ... |
| `morning_end` | 12:00 | ... unless "really cold": room < `eco_temperature` (or `comfort - 4`), or outdoor < 5. |
| `shed_price` | none | Super-expensive threshold in the sensor's unit. Unset disables shedding. |
| `shed_hysteresis` | 0.15 | Release margin. |
| `shed_floor` | 19 | Only shed when the room is above this. Unknown room temperature = never shed. |

**Remote-sensor actuator** (names kept from 0.2.0 / rthc so migration is a copy)

| Key | Default | Meaning |
|---|---|---|
| `temperature_tolerance` | 0.5 | Dead band below target before active heating. |
| `heat_offset` | 1 | Minimum push above the internal reading when heating. |
| `base_stop_heat_offset` | -2 | Pull below the internal reading when at/above target. |
| `max_stop_heat_offset` | -5 | Most it will pull down. |
| `room_max` | 27 | Room ceiling: above this, idle regardless (Sam `heat_room_max`; fixes the 7-minute short cycle). |
| `fan_only_difference` | 3 | Idle if room exceeds target by this. |
| `idle_mode` | `fan_only` if the device has it, else `heat_low` | How to "not heat": `fan_only`, `heat_low` (heat mode, set-point at device minimum), or `off`. |
| `fallback_offset` | 0 | When no room sensor is available: device heats as its own thermostat at control + this. Sam: 2 (ceiling sensor reads warm). |
| `allow_hvac_mode_changes` | on | If off, only set-points are sent (0.2.0 option, kept). |
| `cooling` | off | Enable the cooling branch (section 6.3). |
| `cool_fan_room`, `cool_outdoor_gate` | 25, 22 | Fan-only cooling when room >= 25 and outdoor >= 22. |
| `cool_compressor_room`, `cool_compressor_outdoor` | 27, 27 | Compressor only when both are reached. |
| `cool_offset` | -1 | Compressor set-point = internal + this. |

**Switch actuator**

| Key | Default | Meaning |
|---|---|---|
| `hysteresis` | 0.5 | On at `control - hysteresis`, off at `control + hysteresis`. |
| `min_cycle_minutes` | 5 | Minimum on and off time (compressor / relay protection). |

**Safety**

| Key | Default | Meaning |
|---|---|---|
| `frost_protection` | on | Section 8. |
| `frost_temperature` | 5 | Room (or best available) reading at which heating is forced. |
| `stale_minutes` | 180 | A sensor not reported for this long counts as unavailable. 0 disables. |
| `diagnostic_events` | on | Fire `smartmostat_decision` events (0.2.0 `enable_diagnostic_logging`, renamed). |

## 5. Planner (generalised DaytimeCheapHeat)

Inputs: time, preset, schedule, override state, room temperature `R` (may be `None`), outdoor
`O` (may be `None`), forecast (may be `None`), thermal params (may be `None`), `PriceInfo`.

### 5.1 Base target (Sam's "desired")

Evaluated in order, first match wins:

1. preset `away` -> `away_temperature`.
2. override active -> override temperature.
3. preset `comfort` -> `comfort_temperature`.
4. preset `eco` -> `eco_temperature` (or `comfort - 2` if unset).
5. schedule configured and inside the comfort period -> `comfort_temperature`.
6. schedule configured -> `eco_temperature`.
7. otherwise `comfort_temperature`.

The preset `none` in HA terms is shown as "Schedule" (5 to 7).

### 5.2 Control target (Sam's "control")

Evaluated in order, first match wins. Each row also sets `reason` (a fixed key, translated) and
the headline fragment.

| # | Condition | Control | Reason key / headline |
|---|---|---|---|
| 1 | preset `away` | `away_temperature` | `away` / "Away {T}°C" |
| 2 | override active | override temperature, **price ignored** | `override` / "You set {T}°C ({m}m)" |
| 3 | price optimisation off, or price data invalid | base | `no_price` / "No price data" or `price_off` / "Price control off" |
| 4 | inside the comfort period | base; if `R < comfort - 1` then `max(base, comfort)` (no boost, no cut) | `comfort` / "Comfort {T}°C" or `comfort_hold` / "Evening warm {R}°C hold" when `R >= comfort` |
| 5 | pre-warm applies (5.3) | pre-warm target (5.3) | `prewarm` / "Pre-warm to {C}°C" (+ " (cold)") |
| 6 | `cheap_now` and not hot-day-morning | `min(base + cheap_boost, max_target)`, unless `R >= that - boost_skip_margin`, then base | `cheap_boost` / "Cheap power boost" |
| 7 | `expensive_now` | `max(base - expensive_cut, eco_temperature or min_target, min_target)` | `expensive` / "Electricity expensive" |
| 8 | otherwise | base | `economy` / "Economy {T}°C" or `comfort` |

Then clamp to `[min_target, max_target]`. The hot-day morning case reports `hot_day` / "Hot day,
no morning heat" when it suppressed a boost.

Exposed: `current_adjustment = control - base` (0.1.0 attribute name, kept).

### 5.3 Pre-warm before the comfort period

Only when `comfort_start` is set and `cheap_now` is true. Window: from
`comfort_start - prewarm_hours` (or `prewarm_hours_cold` when `O < cold_outdoor`) to
`comfort_start`. Never outside the window: that is the "no 03:00 blast" fix.

Let `floor = comfort - 1` (Sam: 19 for 20).

Skip (control falls to row 6 or below) when any holds:

- `R >= floor` (already comfortable), or `R` is unknown (a boost needs evidence);
- thermal params known and **on track**: `R >= comfort - 2.5` and
  `hours_to(comfort) <= hours_until(comfort_start) + 1`, where
  `T_eq = forecast_mean (or O) + h / k`, and
  `hours_to = (1/k) * ln((T_eq - R) / (T_eq - comfort))` when `R < comfort < T_eq - 0.5`,
  0 when `R >= comfort`, "unreachable" otherwise (unreachable never skips).

Target (Sam's `prewarm_control_target`):
`clamp(floor + 2 + 2 * (floor - R), comfort, max_target)`.

### 5.4 Override (Sam's 90-minute lock)

- `climate.set_temperature` on the Smartmostat entity, or `smartmostat.set_override`, sets
  `override = (temperature, until = now + minutes)`. Stored, survives restart.
- While active, price logic is bypassed (row 2). `away` still wins (Sam's holiday rule).
- `climate.set_preset_mode` clears any override. `smartmostat.clear_override` clears it.
- `override_minutes = 0`: lasts until the next comfort-period boundary.
- Sam's `sam_automation_set_value` trick is not needed: Smartmostat owns its own target, so it
  knows which writes are its own.

### 5.5 Changes made on the device itself (respecting people)

Smartmostat records the mode and set-point it last sent. If the device later reports a
**different** mode or target with no command from us in the previous 30 s (a person using the
remote or the vendor app):

- device set to `off` -> Smartmostat's climate follows to `off` and stops commanding (frost guard
  excepted). Turning the Smartmostat climate back on resumes.
- any other change -> **pause** for `override_minutes`: no commands, headline
  "Paused: changed on device ({m}m)". `smartmostat.resume` ends it early.

This is new relative to Sam (which simply overwrites every 15 minutes), and is the main thing
"respects manual overrides" adds for a generic integration.

## 6. Actuators

All actuators: never send a command whose effect equals what the device already reports
(mode equal and set-point within half a step). Round set-points to the device's
`target_temp_step` (default 0.5), clamp to its `min_temp` / `max_temp`. Send mode first, then
temperature (with `hvac_mode` included, as Sam does). Use `blocking=False` plus a 10 s timeout
task, so one slow cloud integration cannot stall HA.

### 6.1 Remote-sensor actuator, heating (generalised sam.yaml)

Notation: `D` = control target, `R` = room temperature (aggregate), `I` = internal reading,
`O` = outdoor, `tol` = `temperature_tolerance`.

| Order | Condition | Mode | Set-point | Action label |
|---|---|---|---|---|
| 1 | no usable `R` (all room sensors unavailable or stale) | heat | `D + fallback_offset` | "Device sensor only" |
| 2 | no usable `I` | heat | `D` (plain thermostat) | "No device reading" |
| 3 | `R >= room_max` | idle | `I + max_stop_heat_offset` | "Room at max" |
| 4 | `R > D` (overheat guard) | idle | `I + max(base_stop - (R - D), max_stop)` | "Warm enough" |
| 5 | `R < D - tol` and `O > D` | idle | `I + max(heat_offset, D - R)` | "Coasting (mild)" |
| 6 | `R < D - tol` | heat | `I + max(heat_offset, D - R)` (dynamic boost) | "Heating" |
| 7 | `R >= D` | heat | `I + max(base_stop - (R - D), max_stop)` | "Holding" |
| 8 | otherwise | heat | `I` | "Holding" |

"idle" means `idle_mode` (section 4.3). With `allow_hvac_mode_changes` off, idle is
expressed only through the low set-point. Row 5 keeps Sam's quirk of still computing a boost
set-point while in fan-only (behaviour-identical to the regression tests).

### 6.2 Set-point actuator (0.1.0)

`mode = heat` (if the device is off and Smartmostat is in heat), set-point `= D`. If room sensors
are configured they only feed the planner (comfort hold, boost skip, frost guard).

### 6.3 Remote-sensor actuator, cooling (only when `cooling` is on, Smartmostat mode `heat_cool`)

Evaluated before heating when `O >= cool_outdoor_gate`:

| Condition | Mode | Set-point |
|---|---|---|
| `R >= cool_compressor_room` and `O >= cool_compressor_outdoor` | cool | `I + cool_offset`, capped at 27 |
| `R >= cool_fan_room` | fan_only | `I` |
| otherwise | fall through to heating table | |

Cooling never runs when it is cold outside, so it cannot fight a pre-warm. This is Sam's June 2026
fix ("27 inside and 27 outside, fan only below that") without the pre-cool and scorcher extras.

### 6.4 Switch actuator (0.2.0 tolerance mode)

On when `R <= D - hysteresis`, off when `R >= D + hysteresis`, otherwise unchanged, subject to
`min_cycle_minutes`. Cooler mirrors it. With no usable room reading the switch keeps its last
state until the reading has been missing for `stale_minutes`, then safety rule 2 (section 8)
takes over. 0.2.0's price-dependent asymmetric band is replaced by moving `D`; section 9 shows
the mapping.

## 7. Outputs

### 7.1 Climate entity `climate.<name>` (unique id `{entry_id}_climate`, unchanged)

- `hvac_modes`: `off`, `heat`, plus `heat_cool` when cooling is enabled (switch mode: `cool` when
  only a cooler is configured).
- `target_temperature`: the base target (what the person asked for, or the schedule's value).
  The control target is an attribute and a sensor, not the displayed target: this is the
  "invisible to the user" goal from `TOLERANCE_APPROACH.md`, kept.
- `current_temperature`: room aggregate; device reading when no room sensor.
- `hvac_action`: from the device (`remote_sensor`, `setpoint`) or switch state.
- `preset_modes`: `none` (Schedule), `comfort`, `eco`, `away`.
- `min_temp` / `max_temp`: `min_target` / `max_target`. Step from device, else 0.5.
- Attributes (kept names from 0.1.0/0.2.0 in brackets): `control_target`, `base_temperature`
  [0.1.0], `current_adjustment` [0.1.0], `reason`, `headline`, `control_mode` [0.2.0],
  `wrapped_climate_entity` [0.1.0], `remote_temperature` [0.2.0], `internal_temperature` [0.2.0],
  `outdoor_temperature` [0.2.0], `current_price` [both], `average_price` [0.1.0],
  `price_ratio` [0.1.0, only when the average > 0], `min_price_24h`, `max_price_24h`,
  `price_position` [0.2.0], `next_high_price_in_hours`, `next_low_price_in_hours` [both, fixed so
  they actually work], `price_level`, `override_until`, `paused_until`.

### 7.2 Sensors

| Entity | Type | Content |
|---|---|---|
| `sensor.<name>_control_target` | temperature | The price-adjusted target (Sam's `sam_control_temperature`). |
| `sensor.<name>_headline` | text | "Reason · Action", e.g. `Pre-warm to 22°C · Heating`, `Electricity expensive · Warm enough`, `No price data · Holding`, `Frost guard · Heating`. Attribute `status`: the full diagnostic line (Sam's `sam_hvac_status`: mode, set-point, D, R and its source, I, O, need, boost, guards, price signals, pre-warm calc). Attributes have no 255-character limit, so no truncation bug. |
| `sensor.<name>_reason` | enum | `away`, `override`, `paused`, `no_price`, `price_off`, `comfort`, `comfort_hold`, `prewarm`, `cheap_boost`, `hot_day`, `expensive`, `shed`, `economy`, `frost`, `fallback`. Translated. Good for automations. |
| `sensor.<name>_price_level` | enum | `cheap`, `normal`, `expensive`, `super_expensive`, `unknown`. |
| `sensor.<name>_price_position` | % (diagnostic) | 0 to 100. |
| `sensor.<name>_override_until` | timestamp (diagnostic) | Unknown when no override or pause. |

### 7.3 Switch

`switch.<name>_price_optimisation`: master price switch (Sam's fixed-price feed toggle becomes an
automation that turns this off). Restores state.

### 7.4 Events

`smartmostat_decision` (when `diagnostic_events` is on) with the same fields as the status line,
fired only when the command or reason changes (0.2.0 fired one on every evaluation).

### 7.5 Device

All entities sit on one device per entry, `entry_type: service`, linked (`via_device`) to the
wrapped climate's device when it has one.

## 8. Safety rules (evaluated after planner and actuator, can only add heat or stop a shed)

1. **Frost guard.** If `frost_protection` is on and the best available reading (room, then
   internal, then nothing) is below `frost_temperature`: command heat at
   `max(control, frost_temperature + 3)` regardless of Smartmostat's mode (including `off`),
   presets, override, pause, price and shed. Release at `frost_temperature + 3`. Reason `frost`.
   Repairs issue raised while it is active and Smartmostat was `off`.
2. **No reading at all and cold outside.** If no room or internal reading is usable and
   `O < 3` (or `O` unknown in `switch` mode): `remote_sensor` / `setpoint` command heat at
   `D`; `switch` turns the heater on for 10 minutes in every 30 (duty cycle), reason
   `fallback`, and raises a repairs issue. Never leaves the last command standing indefinitely
   (Sam's "fan_only overnight while target was 23" incident).
3. **Shed only with evidence.** The super-expensive shed (device off) requires a usable room
   reading above `shed_floor`. Shed is released immediately if the room drops to `shed_floor`.
   `away` takes precedence over shed, and so does an active override: a person who asks for heat
   during a price spike gets it (Sam's "Superchill beats the shed" principle).
4. **Device unavailable.** No commands; headline "Device unavailable"; retry on next state.
5. **Price missing.** Covered by planner row 3: behave like a plain thermostat at base.
6. **Stale sensors** (`stale_minutes`) treated as unavailable, using `last_reported` (falls back
   to `last_updated`).
7. **Rate limit.** At most one command per device per 60 s except frost guard and user actions.
8. **Startup.** Do nothing until HA is running and the device state is known; restore preset,
   target, override, pause and last command from storage; first evaluation 30 s after start.
9. **Unload.** Leave the device as it is (do not switch it off).

## 9. Config entry migration (VERSION 3, MINOR_VERSION 1)

`async_migrate_entry` in `__init__.py`. Data holds entities, options hold tunables. Unique ids are
unchanged, so entity ids, history and dashboards survive. Unknown keys are dropped.

### 9.1 From version 1 (0.1.0)

| 0.1.0 key | 0.3.0 |
|---|---|
| (none) | `control_mode = setpoint` |
| `target_climate`, `price_sensor`, `name` | same keys in data |
| `max_increase` | `cheap_boost` |
| `max_decrease` | `expensive_cut` |
| `price_threshold_high` (1.2) | `expensive_ratio` |
| `price_threshold_low` (0.8) | `cheap_ratio` |
| `preheating_enabled` | `price_optimisation` stays on; no schedule so no pre-warm (0.1.0 pre-heat never worked, section 0.2) |
| `preheating_hours` | `lookahead_hours` |
| `precooling_*` | dropped |
| (none) | `comfort_temperature` left unset; at first start it is taken from the restored climate state's target, else from the wrapped device's target, else 20 (0.1.0's own behaviour) |

### 9.2 From version 2 (0.2.0)

| 0.2.0 key | 0.3.0 |
|---|---|
| `control_mode: temperature` | `remote_sensor` |
| `control_mode: tolerance` | `switch` |
| `target_sensor` | `room_sensors: [target_sensor]` |
| `internal_sensor`, `outdoor_sensor`, `target_climate`, `heater`, `cooler`, `price_sensor` | same |
| `heat_offset`, `cool_offset`, `base_stop_heat_offset`, `max_stop_heat_offset`, `temperature_tolerance`, `fan_only_difference`, `allow_hvac_mode_changes` | same |
| `cool_indoor_threshold`, `cool_outdoor_threshold`, `cool_indoor_min` | if equal to the 0.2.0 defaults (26, 25, 20, the over-eager rule Sam abandoned in June 2026), replaced by 0.3.0 defaults; otherwise mapped to `cool_compressor_room`, `cool_compressor_outdoor`, `cool_fan_room` |
| `enable_fan_only_mode` | `idle_mode = fan_only` if true, else `heat_low`; `cooling` on if a cooler or cooling thresholds were in use |
| `min_tolerance` (a), `max_tolerance` (b) | `hysteresis = (a + b) / 2`; `cheap_boost = expensive_cut = (b - a) / 2`. This reproduces 0.2.0's on/off thresholds at the price extremes (0.2.0: on at `T - a`, off at `T + b` when cheapest; 0.3.0: control `T + (b-a)/2`, band `(a+b)/2`, giving the same two numbers). |
| `lookahead_hours` | same |
| `preconditioning_enabled` | `price_optimisation` |
| `enable_diagnostic_logging` | `diagnostic_events` |

### 9.3 Downgrade

A version 3 entry cannot be loaded by 0.1.0 or 0.2.0 (HA refuses newer entry versions). README
says to back up before upgrading. No version-1-compatible keys are kept.

## 10. Config flow, options flow, services

### 10.1 Config flow (`VERSION = 3`)

1. `user`: name, control mode.
2. `devices` (form depends on mode): device / heater / cooler, room sensors (+ aggregate),
   internal sensor, outdoor sensor.
3. `price`: price sensor, pre-filled with the first sensor that has `raw_today` (the 0.2.0
   auto-detect, kept). Validation: entity exists; if it is available, `PriceAnalyser` must find
   slots, else error `invalid_price_sensor` with the HACS Nordpool hint. Unavailable = warning
   only.
4. `comfort`: comfort / eco / away temperatures, comfort period.

Unique id: none (multiple entries per device are the user's choice, as 0.2.0 allows), but abort
if another entry already controls the same `target_climate` / heater, because two controllers on
one device fight (Sam's "two automations with the same alias" incident).

Reconfigure flow (`async_step_reconfigure`) for changing entities and mode.

### 10.2 Options flow (menu, `OptionsFlow` without assigning `self.config_entry`)

`comfort` (section 4.3 comfort table), `price`, `actuator` (fields for the entry's mode only),
`cooling` (remote-sensor only), `safety`, `advanced` (weather entity, forecast hours,
thermal k/h as number or entity, diagnostic events). Saving reloads the entry.

### 10.3 Services (`services.yaml`, entity services on `climate.<name>` targets)

| Service | Fields | Effect |
|---|---|---|
| `smartmostat.set_override` | `temperature` (required), `minutes` (optional, default `override_minutes`) | Section 5.4. |
| `smartmostat.clear_override` | | Back to schedule. |
| `smartmostat.resume` | | End a device-side pause (5.5). |
| `smartmostat.evaluate` | | Re-run now; returns the decision as a service response (`SupportsResponse.OPTIONAL`), which is the debugging tool (replaces Sam's Developer Tools template recipe). |

Standard `climate.set_temperature`, `set_hvac_mode`, `set_preset_mode`, `turn_on`, `turn_off`
work as usual.

## 11. Sam features deliberately left out of 0.3.0

| Sam feature | Why left out | How Sam keeps it |
|---|---|---|
| **Thermal model learning** (`HouseThermalModel.yaml`: EMA of k and h every 10 min) | Needs persisted sampling state, hvac_action semantics per vendor and days of data to verify. Too much to test in one pass. | k and h are accepted as entities (4.1), so the existing YAML keeps learning and Smartmostat reads it. |
| **TV / occupancy comfort** (`media_player.lgnano_55`, `telia_tv`) | Occupancy is house-specific. | A two-line automation sets preset `comfort` (or an override). |
| **Mild-night pre-warm skip** (`forecast_outside_at_23`, `forecast_tonight_min`) | The sensor it depends on is not even deployed on GamlaBio (README, 3 Sep 2026), so the guard has never really run; the "on track" thermal skip covers most of it. | Not needed. |
| **Hourly `daytime` rank, `daytime_cheap_7_21`** | Used by other loads (pool pump), not Sam's heating maths. | Unchanged. |
| **Cheap pre-cool, scorcher override, cooling-trend baseline** | Need forecast plumbing and summer testing; rare in southern Sweden; easy to get wrong (Sam's own June history). | Remain in `sam.yaml` until 0.4; Sam can stay on YAML for cooling by leaving `cooling` off. |
| **Superchill and the `powerful` preset** | A manual blast-cool button with a vendor-specific preset; cooling extras are out of scope (row above). | `SamSuperchill.yaml` keeps working if `cooling` is off; otherwise a person's override covers "cool hard now". |
| **Circulation-fan control** (`switch.smart_plug_5_socket_1`) | House hardware. | Automation keyed on `sensor.<name>_headline` / hvac_action. |
| **`min(living, bedroom)` only while the fan runs** | Hardware-conditional. | `room_aggregate: min` gives the always-on version. |
| **Fixed-price feed detection** (`FeedDetect.yaml`) | House-specific meters. | Automation turns `switch.<name>_price_optimisation` off. |
| **Built-in HA Nordpool** (service-based prices) | Needs a service call per day and a different data path. | HACS Nordpool, as now. |
| **Logbook entries, MiniDisplay `input_text` helpers** | Entities and events replace them. | Template the headline sensor into the old helper if the MiniDisplay needs it. |

Also left out from the old docs: "machine learning", cost tracking, non-linear curves, energy
dashboard integration.

## 12. Repository and CI work in the same release

- `hacs.json`: remove `domains`; keep `name`, `render_readme`, `homeassistant: "2025.1.0"`.
- HACS workflow: add `ignore: brands` until a brands PR lands (or submit one). Repository
  topics (`home-assistant`, `hacs`, `integration`, `climate`, `nordpool`) must be set by the owner
  in GitHub settings: this cannot be done from a branch.
- Add a `hassfest` workflow (`home-assistant/actions/hassfest@master`).
- Tests: replace `requirements_test.txt` with `pytest-homeassistant-custom-component` pinned to
  a release matching the minimum HA version; Python 3.13 only (current HA requires it); add
  `pyproject.toml` with `asyncio_mode = auto`.
- Rewrite `translations/en.json` from `strings.json` (fixes the truncated file); add
  `icons.json`, `services.yaml`.
- `manifest.json`: version `0.3.0`, keys sorted as hassfest requires, `integration_type:
  helper`, `iot_class: calculated`.
- Docs: replace README, delete or move `IMPROVEMENTS_V2.md`, `SUMMARY.md`,
  `TOLERANCE_IMPLEMENTATION.md`, `PRICE_ANALYSIS.md` into `docs/history/` with a note that they
  describe superseded designs; fix `example_configuration.yaml`; CHANGELOG entries for 0.2.0 and
  0.3.0.

## 13. Test plan

### 13.1 Pure unit tests (no HA; `tests/core/`)

**Price (`test_price.py`)**

- 96 x 15-minute slots with ISO strings (the live format), with `datetime` objects, with naive
  strings; 24 x 60-minute slots; `today` float list only; empty / `None` / garbage.
- Current slot selection at slot boundaries, across midnight, on DST change days (23 and 25
  hour days).
- Forward average using tomorrow when present, truncated window when absent.
- Zero and negative prices; day average <= 0.
- Super-expensive latch and hysteresis.
- **Sam regressions replayed**: 3 Sep 2026 SE4 day: 06:00 (1.85 SEK) and 18:00 (2.14 SEK) are not
  `cheap_now`; 02:00 to 06:00 (0.32) and 13:00 to 15:00 (0.50) are. 10 Sep 2026 09:40 (0.66 SEK,
  average 1.23) is not `expensive_now`. `cheap_leccy` escape hatch (cheap now, cheaper later
  still: `today_cheap_leccy_even_cheaper_later`).

**Planner (`test_planner.py`)**, table-driven, porting `test_daytime_cheap_heat_templates.py`:

- every row of 5.1 and 5.2 including ordering (away beats override; override beats price; comfort
  period blocks boost and cut);
- `test_prewarm_window_widens_when_cold`, `test_no_overnight_25c_blast`,
  `test_cold_afternoon_still_respects_the_skip_guards`, `test_hot_day_morning_skip`,
  `test_new_prewarm_target_values` (floor/deficit sizing and clamps);
- thermal "on track" skip; unreachable T_eq never skips; missing k/h never skips;
- room unknown: no boost, no pre-warm, base still applied;
- price invalid or optimisation off: control = base, correct reason.

**Actuators (`test_actuators.py`)**, porting the cases from `test_sam_hvac_templates.py` by name:
`live_now_overheat_guard`, `very_cold_full_boost`, `at_target_nudge_down`,
`mild_coasting_fan_only`, `unit_overreads_keeps_heating`, `live_short_cycle_fixed`,
`half_degree_rounding`, `room_at_heat_max`, `strong_overheat_guard`, `warm_room_cool_out`,
`live_tuya_signed_out_fallback`, `fallback_internal_overreads`, `fallback_economy_target`,
`bedroom_down_uses_living`, `today_bug_no_cool`, `very_hot_both`, `hot_in_mild_out`,
`warm_room_not_27`, `winter_prewarm_not_cooling`. Each asserts mode and set-point exactly
as the YAML computes them (same inputs, Sam constants). Plus:

- `idle_mode` variants on a device without `fan_only`;
- `allow_hvac_mode_changes = off`;
- clamp to device min/max and step rounding (16..30, 0.5);
- "no change, no command";
- switch actuator hysteresis, min cycle time, cooler, missing reading;
- 0.2.0 tolerance equivalence: for min/max tolerance pairs, migrated switch thresholds equal
  0.2.0's at price position 0 and 1.

**Safety (`test_safety.py`)**: frost guard in every mode including `off`, override and pause;
release hysteresis; no-reading cold fallback and switch duty cycle; shed never without room
reading, released at floor, beaten by override and by away; stale sensor detection; rate limit
bypassed only by frost and user actions.

### 13.2 HA integration tests (`pytest-homeassistant-custom-component`)

- Config flow for each mode: happy path, missing entities, invalid price sensor, unavailable
  price sensor (warning), duplicate device abort, reconfigure.
- Options flow: each menu step saves and reloads; only fields for the mode are shown.
- **Migration**: fixtures of a real 0.1.0 entry (v1 data + options) and 0.2.0 entries in both
  modes, including one with options overriding data; assert version 3, mapped values, dropped
  keys, entity ids unchanged, entry loads. A v2 entry with the old cooling defaults gets new
  defaults; a customised one keeps its values.
- End to end with a fake `climate` (demo or `MockEntity`) and fake sensors: price change ->
  control target and device set-point; device-side change -> pause; device set off -> follows;
  frost -> heats even when off; restart restores override and pause.
- Services: `set_override`, `clear_override`, `resume`, `evaluate` response contents.
- Entities: unique ids, translations load (catches a broken `en.json`), diagnostics sensors
  update only on change, events fire only on change.
- `hassfest` and HACS validation in CI.

### 13.3 Manual acceptance on a test instance (not GamlaBio production)

1. Install on a non-production HA (or GamlaBio's standby once the owner agrees) with a copy of the
   SE4 Nordpool sensor and a demo climate.
2. Run side by side with `sam.yaml` in **shadow mode**: Smartmostat entry configured for
   `climate.sam` but with its price switch and a temporary `dry_run` advanced option that logs
   commands without sending them. Compare its headline and set-point with `sam_hvac_headline`
   and Sam's actual set-point for 48 hours, including one evening pre-warm. `dry_run` is the only
   addition this needs and is cheap: the actuator already returns commands rather than sending
   them.
3. Only after the owner reviews the comparison: disable `sam.yaml` and `DaytimeCheapHeat.yaml`,
   enable Smartmostat for real.

## 14. Definition of done

- All of section 13.1 and 13.2 green on CI with Python 3.13; hassfest and HACS (brands ignored)
  green.
- Migrations proven by tests for v1 and v2.
- README rewritten around the three modes, with a "Moving Sam to Smartmostat" section mapping
  each Sam helper to its Smartmostat option.
- Shadow run (13.3 step 2) done and reviewed before Sam is switched over.
