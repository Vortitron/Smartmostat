# Tolerance-Based Temperature Control

## The Correct Approach

Instead of changing the target temperature, we **adjust the heating/cooling tolerances** to make the thermostat more or less aggressive based on electricity prices.

## How Generic Thermostat Works

According to the [generic_thermostat documentation](https://www.home-assistant.io/integrations/generic_thermostat):

- **cold_tolerance**: How far below target before turning ON heater
- **hot_tolerance**: How far above target before turning OFF heater

Example with target temp 20°C:
- `cold_tolerance: 0.3` → turns ON at 19.7°C
- `hot_tolerance: 0.3` → turns OFF at 20.3°C

## Smart Thermostat Strategy

### During Expensive Prices
**Goal**: Reduce heating, save money

- **Large cold_tolerance** (e.g., 2.0°C) → Won't turn on until much colder
- **Small hot_tolerance** (e.g., 0°C) → Turns off quickly

Example: Target 20°C, expensive prices:
- Turn ON at: 20 - 2.0 = **18.0°C** (let it get cold!)
- Turn OFF at: 20 + 0.0 = **20.0°C** (turn off immediately)

### During Cheap Prices
**Goal**: Take advantage of cheap electricity

- **Small cold_tolerance** (e.g., 0°C) → Turns on sooner
- **Large hot_tolerance** (e.g., 2.0°C) → Stays on longer, gets warmer

Example: Target 20°C, cheap prices:
- Turn ON at: 20 - 0.0 = **20.0°C** (turn on immediately!)
- Turn OFF at: 20 + 2.0 = **22.0°C** (keep heating, get warm!)

### During Average Prices
**Goal**: Normal comfort

- **Both tolerances** at crossover point (e.g., 0.2°C)

Example: Target 20°C, average prices:
- Turn ON at: 20 - 0.2 = **19.8°C**
- Turn OFF at: 20 + 0.2 = **20.2°C**

## The Curve

Tolerances adjust on a curve that **crosses in the middle**:

```
Price Position:  0.0    0.25   0.50   0.75   1.0
                (min)          (avg)         (max)

Cold Tolerance:  0.0    0.5    0.2    1.5    2.0  °C
Hot Tolerance:   2.0    1.5    0.2    0.5    0.0  °C

At min price: cold=0, hot=2.0 → turns on immediately, stays on long
At avg price: cold=0.2, hot=0.2 → normal behavior (CROSSOVER)
At max price: cold=2.0, hot=0 → waits to turn on, turns off quickly
```

Formula:
```python
# At position 0 (cheapest): cold=min, hot=max
# At position 1 (expensive): cold=max, hot=min
# They cross at position 0.5 (average)

cold_tolerance = min_tolerance + (max_tolerance - min_tolerance) * price_position
hot_tolerance = max_tolerance - (max_tolerance - min_tolerance) * price_position
```

## Pre-conditioning

When expensive period is coming within look-ahead window:
- **Manually turn ON heater** even if within tolerance zone
- Builds thermal mass before prices spike
- Example: Currently 21°C, target 20°C, tolerance zone 19.8-20.2°C
  - Normally wouldn't heat (already warm)
  - But expensive period in 2 hours → turn on anyway!
  - Get to 22°C while cheap, then coast through expensive period

## Implementation Modes

### Mode 1: Tolerance Control (Primary)
For thermostats like `generic_thermostat`:
- Monitor heater/cooler switches
- Control switches directly based on:
  - Current temp vs (target ± dynamic tolerances)
  - Pre-conditioning override
- **User sees**: Normal target temp (20°C), tolerance varies invisibly

### Mode 2: Temperature Adjustment (Fallback)
For smart thermostats without tolerance access:
- Adjust target temperature instead
- Less elegant but works
- **User sees**: Target temp changing (19°C → 21°C)

## Configuration

Users configure:
1. **Heater** switch (e.g., `switch.living_room_heater`)
2. **Temperature sensor** (e.g., `sensor.living_room_temperature`)
3. **Price sensor** (e.g., `sensor.nordpool_kwh_no1_nok`)
4. **Max tolerance**: How much variance to allow (default: 2.0°C)
5. **Min tolerance**: Crossover point (default: 0.2°C)
6. **Look-ahead**: Hours to check for expensive periods (default: 3)
7. **Pre-conditioning**: Enable/disable (default: enabled)

## Example Scenario

**Setup:**
- Target: 20°C
- Max tolerance: 2.0°C
- Min tolerance: 0.2°C
- Current temp: 19.5°C

**Scenario 1: Expensive Prices (position=0.9)**
```
cold_tolerance = 0.2 + (2.0-0.2) * 0.9 = 1.82°C
hot_tolerance = 2.0 - (2.0-0.2) * 0.9 = 0.18°C

Turn ON at: 20 - 1.82 = 18.18°C
Turn OFF at: 20 + 0.18 = 20.18°C

Current: 19.5°C → Within zone (18.18-20.18), don't heat!
Result: Saves money, lets house cool down
```

**Scenario 2: Cheap Prices (position=0.1)**
```
cold_tolerance = 0.2 + (2.0-0.2) * 0.1 = 0.38°C
hot_tolerance = 2.0 - (2.0-0.2) * 0.1 = 1.82°C

Turn ON at: 20 - 0.38 = 19.62°C
Turn OFF at: 20 + 1.82 = 21.82°C

Current: 19.5°C → Below 19.62°C, HEAT!
Result: Takes advantage of cheap prices, gets warm
```

## Benefits

1. **Invisible to User**: Target temperature stays constant at user's preference
2. **Smooth Control**: Tolerances adjust on curve, not binary
3. **Comfortable**: At average prices, behaves like normal thermostat
4. **Cost Savings**: Reduces heating during expensive periods, increases during cheap
5. **Pre-conditioning**: Proactively warms before price spikes

## Compatibility

Works with:
- ✅ `generic_thermostat` - perfect match
- ✅ Any switch-based heater/cooler
- ✅ Smart thermostats (fallback to temperature mode)






