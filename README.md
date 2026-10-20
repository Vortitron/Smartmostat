# Smartmostat

Price-aware heating for Home Assistant. Smartmostat gives you one thermostat per room that
you set like any other, while it decides what the real heat pump, thermostat or heater is
told, using your electricity price (HACS Nordpool) and, optionally, a room sensor.

It is the owner's year of hand-tuned heat pump automations, generalised into one
integration:

- **Two numbers.** The temperature you asked for (the *base target*) and a price-adjusted
  *control target*. You see the first; the device is steered by the second.
- **Cheap means cheap twice.** Power only counts as cheap when it is cheaper than the coming
  hours *and* genuinely cheap for the day (at most half the day's average, or in the cheaper
  half of the day's hours). Expensive likewise needs both. This stops the classic mistake of
  heating hard on the run-up into a price peak.
- **Pre-warm before you need it, not at 03:00.** With a daily comfort period (say 19:00 to
  23:00), cheap power before it is used to warm the house just enough, in a window that widens
  when it is cold outside.
- **Remote-sensor control of heat pumps.** Most heat pumps measure temperature at the ceiling
  unit. Smartmostat steers the unit's own set-point relative to its own reading so it heats to
  your *room* sensor, pushing harder the further off target the room is.
- **People win.** Set a temperature and it sticks for 90 minutes, price ignored. Change the
  device with its own remote and Smartmostat pauses instead of fighting you.
- **Safe.** A frost guard heats even when Smartmostat is off, missing sensors fall back to
  sensible behaviour, and the super-expensive shed never acts without a room reading.

## Requirements

- Home Assistant 2025.10 or newer.
- A price sensor with `raw_today` / `raw_tomorrow` (or `today` / `tomorrow`) attributes: the
  [HACS Nordpool](https://github.com/custom-components/nordpool) integration. The built-in
  Nord Pool integration does not expose these attributes. 15-minute and hourly prices both
  work; zero and negative prices are handled.
- Something to control: a `climate` entity, or a heater/cooler `switch`, `input_boolean` or
  `fan`.

## Installation

**HACS:** add `https://github.com/Vortitron/Smartmostat` as a custom repository (type
*Integration*), install **Smartmostat**, restart Home Assistant.

**Manual:** copy `custom_components/smartmostat` into your `config/custom_components/`
folder and restart.

Then go to **Settings > Devices & services > Add integration > Smartmostat**.

> Upgrading from 0.1.0 or 0.2.0? Entries are migrated automatically and keep their entity
> ids. Back up first: a migrated entry cannot be loaded by the older versions. See
> [Upgrading](#upgrading-from-010-or-020).

## Choosing a control mode

| Mode | Use it for | What Smartmostat sends |
|---|---|---|
| **Remote sensor** | Heat pumps and air conditioners whose own sensor is in the wrong place | Mode and a set-point computed from the unit's own reading, so it heats to the room sensor |
| **Set-point** | Any thermostat that measures the room well itself (radiator valves, underfloor) | The control target as its set-point while the device heats. It switches the device to heat only from off; a device someone put in cool, auto or another mode is left alone |
| **Switch** | A heater or cooler on a relay, smart plug or `input_boolean` | On and off with hysteresis around the control target |

Everything else (price logic, schedule, presets, overrides and safety) is the same in all
three modes.

## Setting up: a heat pump with a remote sensor

This is the set-up Smartmostat was built for: a Panasonic heat pump `climate.sam` in the
living room, a living-room temperature sensor, an outdoor sensor and the SE4 Nordpool sensor.

1. **Name and mode:** `Living room`, *Remote sensor*.
2. **Device and sensors:**
   - Climate device: `climate.sam`
   - Room temperature sensors: `sensor.living_room_temperature` (add more in order of
     preference; *Minimum* or *Mean* combine them)
   - Device internal sensor: leave empty to use the unit's own `current_temperature`
   - Outdoor temperature sensor: `sensor.outdoor_temperature`
3. **Price sensor:** `sensor.nordpool_kwh_se4_sek_3_10_025` (pre-filled when found).
4. **Comfort:** comfort 20 °C, eco 16 °C, comfort period 19:00 to 23:00, away 10 °C.

Then, in **Configure** (the options menu), the settings that matter for this unit:

| Menu | Option | Value | Why |
|---|---|---|---|
| Comfort | Device preset while away | `heat_8_15` | Panasonic units refuse set-points below 16 °C unless this preset is on |
| Device control | Fallback offset | `2` | The ceiling sensor reads warm; without a room reading the unit runs as its own thermostat at target + 2 |
| Device control | How to stop heating | Automatic | Uses `fan_only` when the unit has it |
| Price | Super-expensive price | e.g. `4.0` | Optional: switch off in extreme price spikes, only if the room is above 19 °C |
| Advanced | Weather entity | `weather.home` | Enables the hot-day morning skip |
| Advanced | Heat loss rate k / heating rate h from entity | `input_number.house_heat_loss_k` / `input_number.house_heat_rate` | Optional: lets an existing thermal model skip pre-warming when the house will reach comfort in time anyway |

What you get:

- `climate.living_room`: the thermostat you use. Its target is the base target (16 °C in the
  day, 20 °C in the evening); its current temperature is the room sensor.
- `sensor.living_room_control_target`: the price-adjusted target.
- `sensor.living_room_headline`: a one-line summary such as `Pre-warm to 22°C · Heating`,
  `Electricity expensive · Warm enough` or `Frost guard · Heating`. Its `status` attribute
  holds the full working: mode and set-point sent, targets, readings, price signals and the
  pre-warm calculation.
- `sensor.living_room_reason`: a fixed key (`prewarm`, `cheap_boost`, `expensive`,
  `override`, ...) for automations.
- `sensor.living_room_price_level`, `sensor.living_room_price_position`,
  `sensor.living_room_override_until` and `switch.living_room_price_optimisation`.

## How it decides

### Base target

First match wins:

1. **Away** preset: the away temperature.
2. **Override** active: what you set.
3. **Comfort** or **Eco** preset: the comfort or eco temperature.
4. **Schedule** (preset shown as *Schedule*): comfort inside the comfort period, eco outside.
   Without a comfort period the comfort temperature applies all day.

### Control target

First match wins, and each row sets the reason you see in the headline:

| # | When | Control target |
|---|---|---|
| 1 | Away | Away temperature |
| 2 | Override active | Your temperature, price ignored |
| 3 | Price optimisation off, or no usable price data | Base |
| 4 | Inside the comfort period | Base, raised to comfort if the room is more than 1 °C short. No boost, no cut |
| 5 | Cheap, in the pre-warm window, room below comfort - 1 | Pre-warm target (below) |
| 6 | Cheap | Base + cheap boost (3 °C), unless the room is already within 0.5 °C of that |
| 7 | Expensive | Base - expensive cut (2 °C), never below the eco temperature |
| 8 | Otherwise | Base |

**Cheap** = cheaper than the average of the next *look-ahead* hours (4) **and** genuinely
cheap: at most *cheap ratio* (0.5) times today's average, or in the cheapest *cheap
percentile* (48 %) of today's hours. **Expensive** = dearer than the next hours **and** at
least *expensive ratio* (1.0) times today's average. Prices are averaged per clock hour so
15-minute jitter does not flip decisions, and today's average is computed from the slots
(Nordpool's own `average` attribute can differ).

**Pre-warm window:** the *pre-warm hours* (4) before the comfort period starts, or 6 hours
when it is below 10 °C outside. Never outside that window. The target is sized to the
deficit: `floor + 2 + 2 × (floor - room)` with `floor = comfort - 1`, kept between comfort
and the maximum target (25 °C). With a thermal model (k and h) the pre-warm is skipped when
the house is on track to reach comfort in time anyway.

**Hot-day morning:** with a weather entity, no cheap heating before 12:00 when today's
forecast maximum is above 25 °C, unless the room is below the eco temperature or it is
below 5 °C outside.

### Remote-sensor mode: what the heat pump is told

`D` is the control target, `R` the room temperature and `I` the unit's own reading.

| When | Mode | Set-point |
|---|---|---|
| No room reading | heat | `D` + fallback offset (the unit is its own thermostat) |
| Any room sensor at or above the room ceiling (27 °C) | idle | `I - 5` |
| `R > D` (overheat guard) | idle | `I` pulled down by 2 °C plus the overshoot, at most 5 °C |
| `R < D - 0.5` and it is milder outside than `D` | idle (coasting) | `I + max(1, D - R)` |
| `R < D - 0.5` | heat | `I + max(1, D - R)`: works harder the further off target |
| `R = D` | heat | `I - 2` |
| otherwise | heat | `I` |

*Idle* means `fan_only` where the unit has it, otherwise heat at the unit's minimum
set-point (or *off*, if you choose that). Set-points are rounded to the unit's step and kept
inside its range, and nothing is sent when the unit already reports the same thing.

With **cooling** enabled (options, *Cooling*; adds a *Heat/Cool* mode) and at least 22 °C
outside: fan only from a 25 °C room; the compressor only when it is at least 27 °C both inside
and out.

### Switch mode

On at `D - hysteresis`, off at `D + hysteresis`, with a minimum on/off time (5 minutes). A
cooler mirrors it in *Cool* mode.

If the room sensor stops reporting, the relay keeps its state for the stale time (3 hours,
also when staleness is disabled). After that the heater runs 10 minutes in every 30 until a
reading returns, unless it is warmer outside than the target, in which case it stays off. A
dead sensor therefore never leaves the heater on, or the room unheated, indefinitely.

## Overrides and changes on the device

- Setting the temperature of the Smartmostat thermostat while a comfort period is configured
  (or a preset other than *Schedule* is active) creates an **override** for *override length* (90 minutes): price is ignored until it
  expires. Choosing a preset clears it. `smartmostat.set_override` sets one for any length;
  `smartmostat.clear_override` ends it.
- Without a comfort period, setting the temperature simply changes the comfort temperature
  (like any thermostat) and price logic carries on.
- If someone changes the **device itself** (its remote or app), Smartmostat **pauses** for the
  override length instead of overwriting them. `smartmostat.resume` ends the pause early. If
  the device is switched **off** by hand, Smartmostat turns itself off too; turn it back on to
  resume. A report that matches something Smartmostat itself sent in the last 15 minutes
  counts as its own command arriving late (slow cloud integrations), not as a person.

## Safety

- **Frost guard:** below the frost temperature (5 °C) Smartmostat heats to at least 8 °C,
  even when it is switched off, paused or shedding, and raises a repair notice if it was off.
- **No readings while it is cold:** with no room or device reading and below 3 °C outside,
  climate devices heat at the control target; switches run 10 minutes in every 30 (see
  [Switch mode](#switch-mode) for milder weather).
- **Super-expensive shed** (optional): turns the device off above a price you set, but only
  with a room reading above 19 °C. An override or the away preset beats it.
- **Stale sensors:** a sensor silent for 3 hours counts as unavailable.
- **Gentle:** at most one automatic command per device per minute; unloading the integration
  leaves the device as it is.

## Services

| Service | Fields | Effect |
|---|---|---|
| `smartmostat.set_override` | `temperature`, `minutes` (optional) | Hold a temperature, ignoring price |
| `smartmostat.clear_override` | | Back to the schedule |
| `smartmostat.resume` | | End a pause caused by a change on the device |
| `smartmostat.evaluate` | | Re-run now; returns the full decision (use *Return response* in Developer tools) |

Standard `climate.set_temperature`, `set_hvac_mode`, `set_preset_mode`, `turn_on` and
`turn_off` work as usual. Each decision change also fires a `smartmostat_decision` event
(can be turned off in *Safety*).

## Automation examples

```yaml
automation:
  - alias: "Comfort while the TV is on"
    triggers:
      - trigger: state
        entity_id: media_player.living_room_tv
        to: "on"
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.living_room
        data:
          preset_mode: comfort

  - alias: "Back to schedule when the TV goes off"
    triggers:
      - trigger: state
        entity_id: media_player.living_room_tv
        to: "off"
        for: "00:15:00"
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.living_room
        data:
          preset_mode: "none"

  - alias: "Fixed-price tariff: no price logic"
    triggers:
      - trigger: state
        entity_id: input_boolean.on_fixed_price_feed
    actions:
      - action: "switch.turn_{{ 'off' if trigger.to_state.state == 'on' else 'on' }}"
        target:
          entity_id: switch.living_room_price_optimisation

  - alias: "Circulation fan follows the heat pump"
    triggers:
      - trigger: state
        entity_id: sensor.living_room_headline
    actions:
      - action: "switch.turn_{{ 'on' if 'Heating' in states('sensor.living_room_headline') else 'off' }}"
        target:
          entity_id: switch.circulation_fan
```

## Moving Sam to Smartmostat

For the owner's own set-up, each helper in the old YAML maps to an option:

| Old helper or rule | Smartmostat |
|---|---|
| `input_number.sam_desired_temperature` | `climate.living_room` target (the base target) |
| `input_number.sam_control_temperature` | `sensor.living_room_control_target` |
| `sam_hvac_headline` / `sam_hvac_status` | `sensor.living_room_headline` and its `status` attribute |
| `input_datetime.sam_desired_lock_until` (90-minute lock) | Override length option; `sensor.living_room_override_until` |
| `input_boolean.holiday_mode` and `heat_8_15` | *Away* preset; *Device preset while away* = `heat_8_15` |
| Evening 19:00 to 23:00 at 20 °C, 16 °C otherwise | Comfort period, comfort 20, eco 16 |
| `prewarm_max` 25, window 15:00 (13:00 when < 10 °C) | Maximum target 25, pre-warm window 4 h / 6 h, cold outdoor 10 |
| `cheap_leccy` (50 %) and rank ≤ 11 | Cheap ratio 0.5, cheap percentile 0.48 |
| `price_genuinely_expensive` (≥ average) | Expensive ratio 1.0 |
| Cheap boost +3, skip within 0.5 | Cheap boost 3, boost skip margin 0.5 |
| `heat_room_max` 27, `heat_fallback_offset` 2 | Room ceiling 27, fallback offset 2 |
| `forecast_today_max` > 25 before 12:00 | Weather entity, hot day maximum 25, morning ends 12:00 |
| `HouseThermalModel.yaml` k and h | *Heat loss rate k / heating rate h from entity* |
| `SuperExpensive.yaml` | Super-expensive price, release margin, shed floor 19 |
| `min(living, bedroom)` while the fan runs | Two room sensors, combined with *Minimum* |
| TV comfort, fixed-price feed, circulation fan | Small automations (examples above) |

Kept in YAML for now: Superchill, cheap pre-cooling, the scorcher override and the cooling
trend baseline. Leave *Cooling* off in Smartmostat while those automations handle summer.

Before switching over, run Smartmostat in **shadow mode** (*Advanced > Dry run*) beside the
old automations for a couple of days, on a test instance or with the owner's agreement:
commands are logged instead of sent, so the headline and control target can be compared
with what the YAML did. In dry run Smartmostat does not watch for changes on the device (the
old automations are still driving it), so it never pauses or follows the device to off.

## Upgrading from 0.1.0 or 0.2.0

| Was | Becomes |
|---|---|
| 0.1.0 (wrap a climate, shift its set-point) | *Set-point* mode. `max_increase` becomes the cheap boost, `max_decrease` the expensive cut, the price thresholds the cheap and expensive ratios. The comfort temperature is your own setting from the old thermostat (its `base_temperature`, not the price-shifted target) |
| 0.2.0 *temperature* mode | *Remote sensor* mode with the same offsets. The old default cooling rule (26 °C inside / 25 °C outside) is replaced by the safer 27 / 27 rule and cooling starts switched off; customised cooling thresholds are kept and cooling stays on |
| 0.2.0 *tolerance* mode | *Switch* mode. Minimum and maximum tolerance `a` and `b` become hysteresis `(a + b) / 2` and boost/cut `(b - a) / 2`, which gives exactly the same on and off temperatures at the cheapest and dearest prices |

Entity ids, unique ids and history are kept.

0.1.0 and 0.2.0 offered the device's own modes. If the old thermostat was in a mode the new
entry does not offer (for example *Cool* on a set-point entry, or on a remote-sensor entry
with cooling off), Smartmostat starts **off** and leaves the device exactly as it is, with a
repair notice. Turn Smartmostat on when you want it to take control again.

## Troubleshooting

- **Reason is `no_price`:** check that the price sensor has a `raw_today` attribute in
  *Developer tools > States*. The built-in Nord Pool integration does not provide it.
- **The heat pump does not follow the room:** look at the headline sensor's `status`
  attribute: it shows the set-point sent, `R` and its source, `I`, `O`, the boost and any
  guards. `smartmostat.evaluate` returns the same as a service response.
- **Paused:** someone changed the device itself. Wait, or call `smartmostat.resume`.
- **Debug logging:**

  ```yaml
  logger:
    logs:
      custom_components.smartmostat: debug
  ```

- **Diagnostics:** *Settings > Devices & services > Smartmostat > ... > Download
  diagnostics* includes the last decision.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/SPEC.md](docs/SPEC.md) (the design this
release implements). Older design notes live in [docs/history](docs/history/).

## Licence

MIT. See [LICENSE](LICENSE).
