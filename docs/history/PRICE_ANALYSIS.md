# How Price Analysis Works

This document explains exactly how the Smart Thermostat analyses electricity prices and makes decisions.

## Data Sources

### What the Integration Reads

From your Nordpool sensor (e.g., `sensor.nordpool_kwh_no1_nok`):

1. **Current Price** (sensor state)
   - Example: `1.85` NOK/kWh
   - Updated every hour

2. **Average Price** (attribute: `average`)
   - Example: `1.50` NOK/kWh
   - Average of all today's prices

3. **Today's Hourly Prices** (attribute: `raw_today`)
   ```json
   [
     {"start": "2025-10-21T00:00:00", "value": 1.20},
     {"start": "2025-10-21T01:00:00", "value": 1.15},
     ...
     {"start": "2025-10-21T23:00:00", "value": 1.80}
   ]
   ```

4. **Tomorrow's Hourly Prices** (attribute: `raw_tomorrow`)
   - Same format as `raw_today`
   - Available after ~13:00 CET
   - Empty before tomorrow's prices are published

## Decision Logic

### Step 1: Calculate Price Ratio

```
Price Ratio = Current Price / Average Price
```

Example:
- Current: 2.10 NOK/kWh
- Average: 1.50 NOK/kWh
- **Ratio: 1.40** (40% above average)

### Step 2: Determine Action

The integration uses your configured thresholds (defaults shown):

#### Scenario A: High Price (Ratio ≥ 1.2)

**When**: Current price is 20%+ above average  
**Action**: Reduce heating to save money  
**Adjustment**: Negative (reduce target temperature)

```
Current: 2.10 NOK/kWh
Average: 1.50 NOK/kWh
Ratio: 1.40 (above 1.2 threshold)

→ REDUCE TEMPERATURE by up to 2.0°C
→ Example: 21°C → 19°C
```

#### Scenario B: Normal Price (0.8 < Ratio < 1.2)

**When**: Price is within ±20% of average  
**Action**: Maintain comfort temperature  
**Adjustment**: Zero (no change)

```
Current: 1.45 NOK/kWh
Average: 1.50 NOK/kWh
Ratio: 0.97 (within normal range)

→ NO ADJUSTMENT
→ Example: 21°C → 21°C
```

#### Scenario C: Pre-heating (High Price Coming Soon)

**When**: Normal price now, BUT high price detected within look-ahead window  
**Action**: Pre-heat to build thermal mass  
**Adjustment**: Positive (increase target temperature)

```
Current Time: 10:00
Current Price: 1.30 NOK/kWh (normal)
Price at 12:00: 2.20 NOK/kWh (high!)
Look-ahead: 2 hours

→ INCREASE TEMPERATURE by up to 2.0°C NOW
→ Example: 21°C → 23°C
→ Home will be warm when expensive period starts
```

#### Scenario D: Low Price (Ratio ≤ 0.8)

**When**: Price is 20%+ below average  
**Action**: Currently: no special action (future: could increase comfort)  
**Adjustment**: Zero

## Look-Ahead Analysis

### How It Works

Every hour (or when prices update), the integration:

1. **Combines price data**: Today + Tomorrow = up to 48 hours
2. **Scans future hours**: Looks at each upcoming hour
3. **Identifies expensive periods**: Finds hours above high threshold
4. **Calculates time until**: "High price in 3 hours"
5. **Decides pre-heating**: If within look-ahead window, start now

### Example Timeline

```
Configuration:
- High Threshold: 1.2 (20% above average)
- Pre-heating Look-ahead: 2 hours
- Max Increase: 2.0°C

Time:     08:00  09:00  10:00  11:00  12:00  13:00  14:00
Price:    1.0    1.1    1.2    1.4    2.2    2.5    2.0   NOK/kWh
Average:  1.5 NOK/kWh
High Threshold: 1.8 NOK/kWh (1.5 × 1.2)

=== At 10:00 ===
Current Price: 1.2 NOK/kWh (normal, below 1.8)
Scanning ahead...
  11:00 → 1.4 NOK/kWh (normal)
  12:00 → 2.2 NOK/kWh (HIGH! Above 1.8)
  Hours until: 2 hours
  
Decision: START PRE-HEATING NOW
Reason: High price in 2 hours (within look-ahead window)
Adjustment: +2.0°C (21°C → 23°C)

=== At 11:00 ===
Current Price: 1.4 NOK/kWh (normal)
High price detected in 1 hour
Adjustment: +2.0°C (continuing pre-heat)

=== At 12:00 ===
Current Price: 2.2 NOK/kWh (HIGH!)
Price Ratio: 2.2 / 1.5 = 1.47 (47% above average)
Home is already warm from pre-heating

Decision: REDUCE HEATING
Adjustment: -1.8°C (23°C → 21.2°C)
Note: Even though we reduce, house stays comfortable
      due to thermal mass from pre-heating

=== At 14:00 ===
Current Price: 2.0 NOK/kWh (still elevated)
Price Ratio: 2.0 / 1.5 = 1.33 (33% above average)
Adjustment: -1.2°C (21°C → 19.8°C)
```

### Why This Works

1. **Pre-heating builds thermal mass**
   - Walls, furniture, air all warmed up
   - Takes time to cool down
   - Provides "free" heating during expensive period

2. **Reduces heating during expensive hours**
   - System runs less when prices are high
   - Still comfortable due to pre-heating
   - Maximum savings achieved

3. **Scales with price magnitude**
   - Small price increase = small adjustment
   - Large price spike = larger adjustment
   - Never exceeds your configured maximums

## Configuration Impact

### Max Increase/Decrease (Default: 2.0°C)

Controls how much temperature can change:
- **Conservative** (1.0°C): Smaller adjustments, less savings, more comfort
- **Moderate** (2.0°C): Balanced approach (recommended)
- **Aggressive** (3.0°C): Maximum savings, may affect comfort

### Price Thresholds

**High Threshold** (Default: 1.2 = 20% above average)
- **Lower** (1.1): React to smaller price increases
- **Higher** (1.5): Only react to major price spikes

**Low Threshold** (Default: 0.8 = 20% below average)
- Currently used for analysis only
- Future: could trigger comfort increases

### Pre-heating Look-ahead (Default: 2 hours)

How far ahead to check for expensive periods:
- **Short** (1 hour): Less anticipation, more reactive
- **Medium** (2-3 hours): Good balance (recommended)
- **Long** (4-6 hours): Maximum anticipation, more pre-heating

**Note**: Look-ahead effectiveness depends on:
- Home insulation quality
- Thermal mass
- Heating system response time

## Real-World Example

**Norway, Winter Day (NO2 region)**

```
Average Price: 1.20 NOK/kWh
Configuration:
- High Threshold: 1.3 (30% above = 1.56 NOK/kWh)
- Pre-heating: 3 hours look-ahead
- Max Adjustment: ±2.5°C
- Base Temperature: 21°C

Hour  Price   Ratio   Action                  Target Temp
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
06:00 0.80    0.67    Normal                  21.0°C
07:00 0.90    0.75    Normal                  21.0°C
08:00 1.00    0.83    Normal                  21.0°C
09:00 1.10    0.92    PRE-HEAT (peak at 12:00) 23.0°C 🔥
10:00 1.20    1.00    PRE-HEAT (peak at 13:00) 23.5°C 🔥
11:00 1.40    1.17    PRE-HEAT (peak at 14:00) 23.5°C 🔥
12:00 1.80    1.50    REDUCE (high price)     19.5°C ❄️
13:00 2.20    1.83    REDUCE (high price)     18.5°C ❄️
14:00 2.50    2.08    REDUCE (high price)     18.5°C ❄️
15:00 1.90    1.58    REDUCE (still high)     19.0°C ❄️
16:00 1.50    1.25    Normal                  21.0°C
17:00 1.60    1.33    REDUCE (slightly high)  20.0°C
18:00 1.30    1.08    Normal                  21.0°C
19:00 1.10    0.92    Normal                  21.0°C

Estimated savings: 15-25% during peak hours
Comfort maintained: ✅ (thanks to pre-heating)
```

## Monitoring Your Integration

### Useful Attributes to Watch

Check `climate.smart_thermostat` attributes in Developer Tools:

- **`base_temperature`**: Your desired temp (e.g., 21°C)
- **`current_adjustment`**: What's being added/removed (e.g., -1.5°C)
- **`current_price`**: Right now (e.g., 2.10 NOK/kWh)
- **`average_price`**: Today's average (e.g., 1.50 NOK/kWh)
- **`price_ratio`**: Current/Average (e.g., 1.40)
- **`next_high_price_in_hours`**: When next spike occurs (e.g., 3)

### Create a Dashboard Card

```yaml
type: entities
title: Smart Thermostat Price Analysis
entities:
  - entity: climate.smart_thermostat
  - type: attribute
    entity: climate.smart_thermostat
    attribute: price_ratio
    name: Price vs Average
  - type: attribute
    entity: climate.smart_thermostat
    attribute: current_adjustment
    name: Temperature Adjustment
  - type: attribute
    entity: climate.smart_thermostat
    attribute: next_high_price_in_hours
    name: Next Expensive Period
```

## Summary

✅ **Current Price Aware**: Always considers what prices are RIGHT NOW  
✅ **Future Looking**: Scans up to 24+ hours ahead  
✅ **Direction Aware**: Detects if prices are going up or down  
✅ **Magnitude Aware**: Scales adjustments based on how much prices change  
✅ **Proactive**: Pre-heats before expensive periods  
✅ **Reactive**: Reduces immediately when prices spike  

The integration gives you the best of both worlds: smart anticipation AND immediate reaction!

