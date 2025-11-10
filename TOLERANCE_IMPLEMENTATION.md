# Tolerance-Based Implementation - The Correct Approach

## What Changed

I initially misunderstood the requirements and implemented a system that **changed the target temperature**. After clarification, I've now implemented the **correct tolerance-based approach**.

## Old (Wrong) Approach ❌

**What it did:**
- Wrapped an existing climate entity
- Changed the target temperature based on prices
- Example: Target 20°C → 18°C during expensive, → 22°C during cheap

**Problems:**
- User sees their temperature changing
- Doesn't work like a traditional thermostat
- Confusing UX

## New (Correct) Approach ✅

**What it does:**
- Works like `generic_thermostat` but smarter
- Controls heater/cooler switches directly  
- **Adjusts tolerances**, not target temperature
- Target stays constant (e.g., 20°C)
- Varies HOW aggressively it maintains that target

**Benefits:**
- Invisible to user (target never changes)
- Natural thermostat behaviour
- More intuitive

## How Tolerances Work

Based on Home Assistant's [generic_thermostat](https://www.home-assistant.io/integrations/generic_thermostat):

### Cold Tolerance
Distance below target before turning ON heater
- Example: Target 20°C, cold_tolerance 0.5°C → turns ON at 19.5°C

### Hot Tolerance  
Distance above target before turning OFF heater
- Example: Target 20°C, hot_tolerance 0.5°C → turns OFF at 20.5°C

## Dynamic Tolerance Strategy

### During Expensive Prices (position = 1.0)
```python
cold_tolerance = max_tolerance = 2.0°C
hot_tolerance = min_tolerance = 0.2°C

Target: 20°C
Turn ON at: 20 - 2.0 = 18.0°C  # Let it get cold!
Turn OFF at: 20 + 0.2 = 20.2°C # Turn off quickly

Result: Heater runs less, saves money
```

### During Average Prices (position = 0.5) 
```python
cold_tolerance = 0.2 + (2.0-0.2) * 0.5 = 1.1°C
hot_tolerance = 2.0 - (2.0-0.2) * 0.5 = 1.1°C  

Target: 20°C
Turn ON at: 20 - 1.1 = 18.9°C
Turn OFF at: 20 + 1.1 = 21.1°C

Result: Normal thermostat behaviour
```

### During Cheap Prices (position = 0.0)
```python
cold_tolerance = min_tolerance = 0.2°C
hot_tolerance = max_tolerance = 2.0°C

Target: 20°C
Turn ON at: 20 - 0.2 = 19.8°C  # Turn on immediately!
Turn OFF at: 20 + 2.0 = 22.0°C # Stay on longer, get warm

Result: Takes advantage of cheap electricity
```

## The Crossover

The tolerances **cross in the middle** at `min_tolerance`:

```
Price Position:  0.0    0.25   0.50   0.75   1.0
                (min)          (avg)         (max)

Cold Tolerance:  0.2    0.65   1.1    1.55   2.0  °C
Hot Tolerance:   2.0    1.55   1.1    0.65   0.2  °C

They cross at 0.5 (average price) where both = 1.1°C
```

## Pre-conditioning

When expensive period detected within look-ahead:

**Normal situation:**
- Current: 21°C, Target: 20°C
- Within tolerance zone (18.9-21.1°C)
- Heater would NOT turn on

**With pre-conditioning active:**
- Expensive period in 2 hours detected
- **Manually turn ON heater** anyway
- Heat to 22°C while prices are still reasonable
- Coast through expensive period using thermal mass

## Configuration

Users configure:

```yaml
heater: switch.living_room_heater
cooler: switch.living_room_ac  # optional
target_sensor: sensor.living_room_temperature
price_sensor: sensor.nordpool_kwh_no1_nok
max_tolerance: 2.0  # Maximum deviation allowed
min_tolerance: 0.2  # Crossover point at average prices
lookahead_hours: 3
preconditioning_enabled: true
```

## Code Structure

### Key Methods

**`_calculate_dynamic_tolerances()`**
```python
# At expensive prices: large cold, small hot
cold_tolerance = min + (max - min) * price_position
hot_tolerance = max - (max - min) * price_position

# Example at position=0.8 (expensive):
# cold = 0.2 + 1.8 * 0.8 = 1.64°C
# hot = 2.0 - 1.8 * 0.8 = 0.56°C
```

**`_async_control_heater()`**
```python
too_cold = cur_temp <= target - cold_tolerance
too_hot = cur_temp >= target + hot_tolerance
preconditioning = (expensive_period_coming and within_lookahead)

if too_cold or preconditioning:
    turn_on_heater()
elif too_hot:
    turn_off_heater()
```

## Comparison

| Aspect | Old Approach | New Approach |
|--------|--------------|--------------|
| **What changes** | Target temperature | Tolerances |
| **User sees** | Temperature changing | Constant target |
| **Cheap prices** | Target: 22°C | Target: 20°C, tolerances 0.2/2.0 |
| **Expensive prices** | Target: 18°C | Target: 20°C, tolerances 2.0/0.2 |
| **Comfort** | Confusing | Natural |
| **Integration** | Wraps climate entity | Controls switches |
| **Like** | Custom hack | generic_thermostat |

## User Experience

**Old way:**
```
User sets: 20°C
Cheap period: Display shows 22°C (confusing!)
User: "Why did my thermostat change?"
```

**New way:**
```
User sets: 20°C
Cheap period: Display still shows 20°C
But heater runs more aggressively (tolerances 0.2/2.0)
House gets to 22°C naturally
User: "It feels warm and cozy!" (doesn't notice)
```

## Implementation Files

- **`const.py`**: Updated with tolerance constants
- **`climate.py`**: Complete rewrite with tolerance-based control
- **`README.md`**: Updated with correct explanation
- **`TOLERANCE_APPROACH.md`**: Technical documentation
- **`TOLERANCE_IMPLEMENTATION.md`**: This file

## Next Steps

1. Update config_flow.py with correct parameters (heater, cooler, sensor)
2. Update translations/strings
3. Test with real generic_thermostat setup
4. Add fallback mode for thermostats without switch access
5. Document configuration examples

## Why This Is Better

✅ **Intuitive**: Works like a normal thermostat  
✅ **Invisible**: User doesn't see changes  
✅ **Effective**: Same energy savings  
✅ **Compatible**: Works with generic_thermostat pattern  
✅ **Elegant**: Clean implementation  

This is the correct approach! 🎯






