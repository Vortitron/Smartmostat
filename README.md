# Smart Thermostat (Smartmostat)

A Home Assistant custom integration that dynamically adjusts thermostat temperature targets based on electricity prices, helping you save money whilst maintaining comfort.

## Features

- **Dual Control Modes**: Choose between tolerance-based switch control or smart set-point adjustments
- **Remote Sensor Support**: Combine internal, external, and outdoor sensors for accurate comfort management
- **Price-aware Comfort**: Reacts to live electricity prices and looks ahead to expensive periods
- **Pre-heating/Pre-cooling**: Build thermal mass before price spikes to coast through expensive hours
- **Granular Behaviour Tuning**: Configure offsets, fan-only behaviour, thresholds, logging, and more
- **Multiple Instances**: Run separate profiles for every room, thermostat, or heat pump
- **Nordpool Ready**: Built to work with the HACS Nordpool integration's hourly data
- **HACS Compatible**: Simple installation and updates via Home Assistant Community Store

## How It Works

Smartmostat supports two complementary control strategies. Pick the one that matches your hardware—or run multiple instances side by side.

### 1. Tolerance Mode (default)

Ideal for [`generic_thermostat`](https://www.home-assistant.io/integrations/generic_thermostat) style setups with a heater/cooler switch.

- **Target temperature never changes** – your thermostat stays at (say) 20 °C
- **Dynamic tolerances** expand or shrink based on price
- **Cheap prices** → small cold tolerance, large hot tolerance → heat sooner, stay warmer
- **Expensive prices** → large cold tolerance, tiny hot tolerance → wait longer, turn off faster
- **Average prices** → both tolerances cross at your minimum comfort tolerance

```
Target: 20 °C        Max tolerance: 2.0 °C        Min tolerance: 0.2 °C

Price position: 0.0 (cheap)   → ON at 20.0 °C · OFF at 22.0 °C  → maximise comfort
Price position: 0.5 (average) → ON at 19.8 °C · OFF at 20.2 °C  → normal behaviour
Price position: 1.0 (expensive) → ON at 18.0 °C · OFF at 20.0 °C → save energy
```

Pre-conditioning kicks in automatically: if an expensive period is less than `lookahead_hours` away Smartmostat turns the heater on even if you are still inside the tolerance band. The room warms while energy is cheap and coasts through the price spike.

### 2. Temperature Mode (set-point control)

Perfect for heat pumps and smart thermostats where you *nudge* the desired temperature rather than flipping a switch—just like the Sam HVAC automation in the prompt.

- Drives the thermostat using a **remote “truth” sensor** (e.g., Aqara probe)
- Reads the thermostat’s **internal** sensor to calculate offsets
- Optional **outdoor sensor** influences cooling and fan-only behaviour
- Applies configurable **heat/cool offsets** to fool the thermostat into heating/cooling sooner or later
- Supports **fan-only** mode to avoid unnecessary compressor cycles

Cooling branch (simplified):
```
if indoor > cool_indoor_threshold OR (outdoor >= cool_outdoor_threshold AND indoor > cool_indoor_min):
    if enable_fan_only AND indoor > desired + tolerance AND outdoor < desired:
        hvac_mode = FAN_ONLY
        target = internal_temp + cool_offset
    else:
        hvac_mode = COOL
        target = internal_temp + (cool_offset if indoor > desired + tolerance else 0)
```

Heating branch mirrors the logic with `heat_offset`, `base_stop_heat_offset`, and `max_stop_heat_offset`, just like the Sam script. All thresholds are configurable from the UI.

## Installation

### HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Go to HACS → Integrations
3. Click the three dots in the top right → Custom repositories
4. Add repository URL: `https://github.com/vortitron/smartmostat`
5. Category: Integration
6. Click "Add"
7. Search for "Smart Thermostat" and install
8. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy `custom_components/smartmostat` to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### Through the UI (Recommended)

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Smart Thermostat"
4. Fill in the configuration:

#### Common Settings

- **Name** – Friendly name shown in Home Assistant
- **Control Strategy** – `Tolerance (switch)` or `Temperature (set-point)`
- **Primary Temperature Sensor** – The “truth” sensor you trust (required)
- **Indoor/Outdoor Sensors** – Optional extras for advanced logic
- **Electricity Price Sensor** – Nordpool sensor (must be from HACS)
- **Look-ahead Hours** – How far ahead to scan for expensive periods
- **Pre-conditioning** – Enable to warm/cool before price spikes
- **Diagnostic Logging** – Enable detailed metrics and analytics events

#### Tolerance Mode Extras (Switch Control)

Designed for heaters/AC units you can toggle on/off.

- **Heater Switch** – Entity to turn on/off for heating (required unless cooling only)
- **Cooler Switch** – Entity for cooling control
- **Max / Min Tolerance** – Comfort envelope that expands with price

#### Temperature Mode Extras (Set-point Control)

Use this for smart thermostats and heat pumps (Sam HVAC style).

- **Thermostat to Control** – Climate entity receiving nudged set-points
- **Heat/Cool Offsets** – How much to nudge when remote temp deviates
- **Stop-heat Offsets** – How aggressively to back off once warmed
- **Fan-only Thresholds** – Automatically switch to fan-only to save energy
- **HVAC Mode Changes** – Allow Smartmostat to change HVAC modes, or keep current

### Configuration Examples

- **Tolerance Mode – Radiator with Shelly switch**
  - Remote sensor: `sensor.living_room_ecowitt`
  - Heater switch: `switch.living_room_radiator`
  - Price sensor: `sensor.nordpool_kwh_no2_nok`
  - Max tolerance 2.5 °C · Min tolerance 0.2 °C · Look-ahead 3h

- **Temperature Mode – Heat pump (Sam style)**
  - Remote sensor: `sensor.t_h_sensor_temperature`
  - Internal sensor: `sensor.sam_inside_temperature`
  - Outdoor sensor: `sensor.sam_outside_temperature`
  - Thermostat: `climate.sam`
  - Heat offset 1.0 °C · Cool offset −1.0 °C · Fan-only diff 3 °C

### Multiple Thermostats

Add as many instances as you like—one per zone, thermostat, or heater. Each can run a different strategy with custom thresholds.

## Nordpool Integration

⚠️ **IMPORTANT**: This integration requires the **[HACS Nordpool](https://github.com/custom-components/nordpool) custom component**, NOT the built-in Home Assistant Nordpool integration!

### Why HACS Nordpool?

The built-in HA `nordpool` integration doesn't provide the required hourly price data attributes (`raw_today`, `raw_tomorrow`). You **must** use the HACS custom component.

### Setting up Nordpool

1. Install Nordpool via HACS
2. Configure your region (e.g., NO1, NO2, SE1, DK1)
3. Wait for prices to populate (available around 13:00 CET daily)
4. Use the Nordpool sensor in Smart Thermostat configuration

### Which Nordpool Sensor to Choose?

**⚠️ Important**: Select the **main Nordpool sensor**, NOT the "Next Price" sensor!

The main sensor is typically named like:
- `sensor.nordpool_kwh_no1_nok` (Norway region 1, NOK currency)
- `sensor.nordpool_kwh_se3_sek` (Sweden region 3, SEK currency)
- `sensor.nordpool_kwh_dk1_dkk` (Denmark region 1, DKK currency)

**Don't use**:
- ❌ `sensor.nordpool_next_price` - Only shows next 15 minutes
- ❌ Any sensor with "next" or "current" in the name

### How the Integration Uses Price Data

The Smart Thermostat reads from the main Nordpool sensor to get:

1. **Current Price** (sensor state) - Used for immediate decisions
2. **Average Price** (attribute: `average`) - Baseline for comparison
3. **Today's Hourly Prices** (attribute: `raw_today`) - Look-ahead analysis
4. **Tomorrow's Hourly Prices** (attribute: `raw_tomorrow`) - Extended forecasting

The integration automatically:
- ✅ Analyses the **current** price vs. average
- ✅ Looks **several hours ahead** to detect upcoming expensive periods
- ✅ Calculates the **direction and magnitude** of price changes
- ✅ Pre-heats/pre-cools before price spikes to build thermal mass

**Example**: If it's 10:00 and prices will spike at 14:00, the integration will start pre-heating at 12:00 (with 2-hour look-ahead), even though current prices are normal.

### Price Analysis Example

```
Time:     10:00  11:00  12:00  13:00  14:00  15:00  16:00
Price:    1.0    1.1    1.2    1.5    2.0    2.2    1.8   (NOK/kWh)
Average:  1.5 NOK/kWh
Threshold High: 1.8 NOK/kWh (1.2 × average)

Action at 12:00:
├─ Current price: 1.2 NOK/kWh (below threshold, normal)
├─ Looking ahead: Detects spike at 14:00-16:00 (above 1.8)
├─ Decision: START PRE-HEATING NOW
└─ Adjustment: +2.0°C to build thermal mass

Action at 14:00:
├─ Current price: 2.0 NOK/kWh (high!)
├─ Already pre-heated, so home is warm
├─ Decision: REDUCE HEATING
└─ Adjustment: -1.5°C to save money
```

This way, your home stays comfortable during expensive hours whilst minimising energy costs!

**Want more details?** See [PRICE_ANALYSIS.md](PRICE_ANALYSIS.md) for a deep dive into how the price analysis works.

## Entity Attributes

The Smart Thermostat entity provides additional attributes for monitoring:

- `base_temperature`: Your desired temperature (before adjustments)
- `current_adjustment`: Current temperature adjustment being applied
- `current_price`: Current electricity price
- `min_price_24h`: Minimum price in next 24 hours
- `max_price_24h`: Maximum price in next 24 hours
- `price_position`: Where current price falls (0 = min, 1 = max)
- `next_high_price_in_hours`: Hours until next expensive period
- `next_low_price_in_hours`: Hours until next cheap period
- `wrapped_climate_entity`: The underlying thermostat being controlled

## Usage Tips

### Optimal Settings

1. **Conservative Start**: Begin with small variance (±1.5°C) and monitor results
2. **Adjust Based on Comfort**: Increase variance if comfortable, decrease if too variable
3. **Look-ahead Duration**: 3-4 hours works well for most homes
4. **Monitor Attributes**: Watch `price_position` and `current_adjustment` to understand behaviour
5. **Different Rooms**: Use different variance for different rooms (living room: ±2.5°C, bedroom: ±1.5°C)

### Automation Examples

**Disable during manual override:**
```yaml
automation:
  - alias: "Pause Smart Thermostat when manually adjusted"
    trigger:
      - platform: state
        entity_id: climate.smart_thermostat
        attribute: current_temperature
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.base_temperature != trigger.from_state.attributes.base_temperature }}"
    action:
      - service: climate.turn_off
        target:
          entity_id: climate.smart_thermostat
```

**Notification on high adjustments:**
```yaml
automation:
  - alias: "Notify on large temperature adjustment"
    trigger:
      - platform: state
        entity_id: climate.smart_thermostat
        attribute: current_adjustment
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.current_adjustment | abs > 2 }}"
    action:
      - service: notify.mobile_app
        data:
          message: "Smart Thermostat adjusted by {{ trigger.to_state.attributes.current_adjustment }}°C due to electricity prices"
```

## Frequently Asked Questions

### Which Nordpool sensor should I use?

Use the **main regional sensor** that contains all hourly prices:

✅ **Correct sensors:**
- `sensor.nordpool_kwh_no1_nok`
- `sensor.nordpool_kwh_no2_nok`
- `sensor.nordpool_kwh_se1_sek`
- `sensor.nordpool_kwh_dk1_dkk`
- etc. (pattern: `sensor.nordpool_kwh_<region>_<currency>`)

❌ **Wrong sensors (don't use these):**
- `sensor.nordpool_next_price` - Only 15 minutes ahead
- `sensor.nordpool_current_price` - No hourly data
- Any derivative sensors you've created

**How to verify**: Open Developer Tools → States, find your sensor, and check it has these attributes:
- `average` ✅
- `raw_today` ✅
- `raw_tomorrow` ✅

If all three are present, you've got the right sensor!

**Need help checking?** Use the validation helper in `check_nordpool_sensor.yaml` - it will tell you if your sensor is correct!

## Diagnostics & Metrics

Enable **diagnostic logging** when configuring the integration to capture rich analytics:

- Smartmostat fires a `smartmostat_metrics` event after every control decision.
- Payloads include remote/internal/outdoor temperatures, the commanded HVAC mode, price data, and tolerance/offset information.
- Use a Home Assistant automation to persist these events to the recorder, InfluxDB, or your own data pipeline for deeper analysis.

This telemetry is perfect for estimating heating and cooling coefficients, modelling heat retention, and planning forecast-driven heating schedules.

### Does it look ahead or just react to current prices?

**Both!** The integration is intelligent:

1. **Reacts to current high prices** - Reduces heating immediately when prices spike
2. **Looks ahead 2+ hours** - Detects upcoming expensive periods
3. **Pre-heats proactively** - Warms your home before prices spike
4. **Uses tomorrow's data** - When available (after ~13:00 CET), extends look-ahead to 24+ hours

### How much look-ahead time?

- **Configurable**: Set "Pre-heating Look-ahead" (default: 2 hours)
- **Data available**: Up to 24+ hours when tomorrow's prices are published
- **Practical range**: 1-4 hours works best for most homes

Example with 3-hour look-ahead:
- At 09:00, can detect expensive period at 12:00
- At 11:00, can detect expensive period at 14:00
- After 13:00 (when tomorrow's prices arrive), can detect tomorrow's peaks

## Troubleshooting

### Integration not appearing
- Ensure you've restarted Home Assistant after installation
- Check `custom_components/smartmostat/` exists and contains all files

### Price adjustments not working
- Verify your price sensor is working and has the `average` attribute
- Check the Smart Thermostat entity attributes for `current_price` and `average_price`
- Enable debug logging (see below)

### Temperature not changing
- Ensure your wrapped climate entity supports temperature changes
- Check Home Assistant logs for errors
- Verify the wrapped climate entity is responding to manual changes

### Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.smartmostat: debug
```

## Energy Savings

Typical savings depend on:
- Your electricity price volatility
- Home insulation quality
- Configured adjustment parameters
- Local climate

**Expected results:**
- Well-insulated homes: 10-20% heating cost reduction
- Average insulation: 5-15% reduction
- Best results with high price volatility (Nordic/Baltic regions)

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with appropriate tests
4. Submit a pull request

## Licence

This project is licenced under the MIT Licence - see the [LICENSE](LICENSE) file for details.

## Credits

- Inspired by the [generic_thermostat](https://www.home-assistant.io/integrations/generic_thermostat) integration
- Designed for use with [Nordpool](https://github.com/custom-components/nordpool) integration
- Built for the Home Assistant community

## Support

- **Issues**: [GitHub Issues](https://github.com/vortitron/smartmostat/issues)
- **Discussions**: [Home Assistant Community](https://community.home-assistant.io/)
- **Documentation**: [GitHub Wiki](https://github.com/vortitron/smartmostat/wiki)

## Roadmap

- [ ] Support for multiple price zones
- [ ] Advanced scheduling integration
- [ ] Machine learning for optimal adjustment prediction
- [ ] Energy dashboard integration
- [ ] Multi-room coordination
- [ ] Cost savings tracking and reporting
