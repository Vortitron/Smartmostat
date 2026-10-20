# Version 2.0 Improvements

Based on user feedback, major improvements have been implemented to make the integration simpler and more intelligent.

## Key Improvements

### 1. ✅ Automatic Curve-Based Adjustment

**Before (v1.0):**
- User had to set confusing price thresholds (e.g., "1.2 = 20% above average")
- Separate "max increase" and "max decrease" settings
- Threshold-based: only reacted when prices crossed thresholds

**After (v2.0):**
- **Automatic min/max detection**: Finds cheapest and most expensive prices in next 24 hours
- **Single variance setting**: Just set ±2.0°C (how much comfort variance you allow)
- **Smooth curve**: Adjusts continuously based on where price falls in range
  ```
  At min price → +2.0°C (warmest)
  At mid price →  0.0°C (your normal temp)
  At max price → -2.0°C (coolest)
  ```
- **No more guessing**: The system figures out what's "expensive" and "cheap" automatically!

### 2. ✅ Simplified Configuration

**Merged Settings:**

| Old (v1.0) | New (v2.0) | Why Better |
|------------|------------|------------|
| Max Increase: 2.0°C<br>Max Decrease: 2.0°C | Max Variance: ±2.0°C | One setting instead of two |
| Pre-heating Hours: 2<br>Pre-cooling Hours: 2 | Look-ahead Hours: 3 | Combined into one |
| Pre-heating Enabled<br>Pre-cooling Enabled | Pre-conditioning Enabled | Single toggle |
| High Threshold: 1.2<br>Low Threshold: 0.8 | *(Automatic)* | No manual thresholds needed! |

**Before:** 8 configuration options  
**After:** 3 configuration options (62% reduction!)

### 3. ✅ HACS vs HA Nordpool Clarification

**Problem**: Users were confused about which Nordpool integration to use
- Home Assistant has a **built-in** `nordpool` integration
- HACS has a **custom component** Nordpool integration
- They're different! Built-in one lacks required attributes

**Solution**:
- ✅ Clear error message: "Use HACS Nordpool integration (sensor.nordpool_kwh_*), not built-in HA nordpool!"
- ✅ Validation: Checks for `raw_today` attribute during configuration
- ✅ Documentation: Explicit warnings throughout README
- ✅ Auto-detection: If HACS Nordpool sensor exists, pre-populates the field

### 4. ✅ Multiple Instances Supported

**Before (v1.0):**
- Could only add ONE Smart Thermostat
- Unique ID restriction prevented multiple instances
- Had to choose which thermostat to control

**After (v2.0):**
- ✅ Add unlimited Smart Thermostats
- ✅ One per room/zone
- ✅ Different variance settings for each
- ✅ Example:
  - Living Room: ±2.5°C variance (more tolerance)
  - Bedroom: ±1.5°C variance (keep comfortable)
  - Office: ±3.0°C variance (maximum savings)

### 5. ✅ Better Price Analysis

**New Attributes:**
- `min_price_24h`: Lowest price in next 24 hours
- `max_price_24h`: Highest price in next 24 hours  
- `price_position`: Where current price falls (0.0 = min, 1.0 = max)

**Example:**
```yaml
min_price_24h: 0.85 NOK/kWh
max_price_24h: 2.35 NOK/kWh
current_price: 1.60 NOK/kWh
price_position: 0.50  # Exactly in middle
```

This gives users clear insight into price context!

## Technical Changes

### Configuration Flow (`config_flow.py`)
- Removed unique_id restriction (line 70)
- Added `_find_nordpool_sensor()` method to auto-detect
- Added validation for `raw_today` attribute
- Simplified schema: 3 options instead of 8
- Added `invalid_price_sensor` error message

### Climate Platform (`climate.py`)
- New `_calculate_price_range()` method
  - Scans next 24 hours
  - Finds min/max prices
  - Calculates current position on curve
- Updated `_async_calculate_adjustment()` method
  - Automatic curve-based adjustment
  - Formula: `adjustment = max_variance - (2 * max_variance * price_position)`
  - Pre-conditioning boost still applies
- Removed threshold-based logic completely
- New state attributes: `min_price_24h`, `max_price_24h`, `price_position`

### Constants (`const.py`)
- Reduced from 12 constants to 6
- Simplified defaults
- Removed all threshold-related constants

### Translations (`strings.json`, `translations/en.json`)
- Simplified descriptions
- Added HACS Nordpool warning
- New error message for invalid sensor
- Clearer tooltips

## Migration Notes

For users upgrading from v1.0 to v2.0:

### Breaking Changes
- Configuration options changed (but options flow allows reconfiguration)
- Removed attributes: `average_price`, `price_ratio`
- New attributes: `min_price_24h`, `max_price_24h`, `price_position`

### Migration Steps
1. Note your current settings
2. Update integration
3. Go to Options
4. Set new simplified options:
   - Old "Max Increase: 2.0 + Max Decrease: 2.0" → New "Max Variance: 2.0"
   - Old "Pre-heating Hours: 3" → New "Look-ahead Hours: 3"
5. Remove any automations that used `average_price` or `price_ratio`
6. Update automations to use new `price_position` attribute if needed

### Automation Updates

**Old automation:**
```yaml
trigger:
  - platform: template
    value_template: >
      {{ state_attr('climate.smart_thermostat', 'price_ratio') > 1.3 }}
```

**New automation:**
```yaml
trigger:
  - platform: template
    value_template: >
      {{ state_attr('climate.smart_thermostat', 'price_position') > 0.75 }}
```

## User Benefits

1. **Simpler Setup**: 3 settings instead of 8
2. **No Math Required**: No need to understand "price ratio multipliers"
3. **More Intelligent**: Automatic adjustment based on actual price range
4. **More Flexible**: Multiple instances for different rooms
5. **Fewer Errors**: Validates sensor at configuration time
6. **Clearer Feedback**: Better attributes for monitoring

## Example Comparison

### Old System (v1.0)
```
User thinks: "What does threshold 1.2 mean? Is that good?"
User sets: Max Increase: 2°C, Max Decrease: 1.5°C, Thresholds: ???
Result: Maybe works, maybe doesn't react enough, user confused
```

### New System (v2.0)
```
User thinks: "I'm okay with ±2°C temperature change for savings"
User sets: Max Variance: ±2°C
Result: System automatically finds min/max and adjusts smoothly!
```

## Performance Impact

- **Similar**: No significant performance difference
- **Slightly Better**: Removed some redundant calculations
- **Same Update Frequency**: Still updates when prices change

## Future Enhancements

With this solid foundation, future additions could include:
- Non-linear curves (exponential, logarithmic)
- User-defined comfort profiles
- Machine learning for optimal variance
- Integration with weather forecasts
- Energy cost tracking and reporting

## Feedback Welcome!

These improvements were made based on user feedback. Please continue to report:
- Configuration confusion
- Unexpected behaviour
- Feature requests
- Documentation improvements

Together we make it better! 🚀

