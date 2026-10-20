# Changelog

All notable changes to Smartmostat are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-20

A rewrite around the owner's working heat pump automations, generalised. See
`docs/SPEC.md` for the design.

### Added

- Three control modes sharing one planner: **remote sensor** (heat pumps steered through
  their own reading, with the dynamic boost, overheat guard, 27 °C room ceiling, mild
  coasting and device-sensor fallback), **set-point** (0.1.0 behaviour) and **switch**
  (0.2.0 tolerance mode as hysteresis around the control target).
- Two-number control: a base target (presets comfort, eco and away, plus an optional daily
  comfort period) and a price-adjusted control target.
- Two-signal price gate: cheap and expensive both need the relative test (against the
  average of the coming hours, using tomorrow's prices across midnight) **and** an absolute
  test against today's own computed average or rank.
- Pre-warming only in a window before the comfort period, wider when it is cold outside and
  sized to the room's deficit, with an optional "on track" skip from a thermal model (k and h
  as numbers or entities).
- Hot-day morning skip using a weather entity's forecast.
- 90-minute manual override lock; pause when someone changes the device itself; follow the
  device to off.
- Safety layer: frost guard (even when off), no-reading fallback with a switch duty cycle,
  super-expensive shed that needs a room reading, stale sensor detection, command rate
  limit, send-only-on-change, restore of runtime state across restarts.
- Sensors: control target, headline (with the full status line as an attribute), reason,
  price level, price position and override until. A price optimisation switch.
- `smartmostat_decision` event on decision changes only.
- Services `set_override`, `clear_override`, `resume` and `evaluate` (returns the decision).
- Options flow as a menu, reconfigure flow, diagnostics, repairs issues, icons, a dry-run
  (shadow) option.
- Basic cooling for remote-sensor mode: fan only from 25 °C, compressor only at 27 °C inside
  and out.
- A real test suite (pure unit tests porting the YAML regression cases, plus Home
  Assistant tests) and hassfest, HACS and pytest workflows.

### Changed

- Config entry version 3, with automatic migration from 0.1.0 (version 1) and 0.2.0
  (version 2). Entity ids and unique ids are kept.
- 0.2.0's default cooling rule (26 °C inside / 25 °C outside) is replaced by the 27 / 27
  rule; migrated temperature-mode entries with the old defaults start with cooling off.
- `hacs.json` no longer has the retired `domains` key; minimum Home Assistant is 2025.8.
- `manifest.json`: integration type `helper`, version 0.3.0.
- Planning notes moved to `docs/history/`.

### Fixed

- Price slot times are compared timezone-aware. In 0.1.0 and 0.2.0 the naive/aware mix
  raised an error that was swallowed, so look-ahead, price position and pre-heating never
  worked with a real Nordpool sensor.
- A price of 0 was treated as missing data; zero and negative prices now work.
- `translations/en.json` was truncated (invalid JSON), leaving the config flow without text.
- Upgrading 0.1.0 to 0.2.0 broke every entry (no migration handler).
- The options flow assigned `self.config_entry`, which fails on Home Assistant 2025.12 and
  later.
- `example_configuration.yaml` was invalid YAML.
- CI: the tests imported constants that 0.2.0 had removed; HACS rejected `hacs.json`.

## [0.2.0] - 2025-11-10

### Added

- "Tolerance" mode: switch a heater or cooler with price-dependent hysteresis.
- "Temperature" mode: remote-sensor set-point control adapted from
  `remote_temperature_hvac_control`.
- Price position, next high/low price attributes and diagnostic events.

### Known problems (fixed in 0.3.0)

- No config entry migration from 0.1.0; broken English translations; look-ahead never
  worked with real Nordpool data.

## [0.1.0] - 2025-10-21

### Added

- First version: wrap a climate entity and shift its set-point by the ratio of the current
  price to the daily average, with optional pre-heating.
- UI config and options flow.
