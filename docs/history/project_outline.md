# Smart Thermostat Project Outline

## Project Purpose

Create a Home Assistant custom integration that dynamically adjusts thermostat temperature targets based on electricity prices to:
1. Reduce energy costs during expensive periods
2. Pre-condition homes before expensive periods
3. Maintain comfort whilst optimising energy usage

## Architecture

### Components

1. **Climate Platform (`climate.py`)**
   - Main entity that wraps existing thermostats
   - Monitors price sensors and calculates adjustments
   - Applies temperature changes to wrapped entities

2. **Configuration Flow (`config_flow.py`)**
   - UI-based configuration
   - Entity selection (climate + price sensor)
   - Parameter configuration (thresholds, limits)
   - Options flow for reconfiguration

3. **Constants (`const.py`)**
   - Domain and configuration keys
   - Default values
   - Attribute names

4. **Integration Setup (`__init__.py`)**
   - Entry point for Home Assistant
   - Platform forwarding
   - Entry management

### Key Algorithms

#### Price Analysis
- Compares current price to average price
- Calculates price ratio (current / average)
- Identifies upcoming expensive periods
- Uses Nordpool's `raw_today` and `raw_tomorrow` attributes

#### Temperature Adjustment Logic

1. **High Price Scenario** (price_ratio >= high_threshold)
   - Reduces temperature (heating) or increases (cooling)
   - Scales adjustment based on how far above threshold
   - Formula: `adjustment = -max_decrease * excess_ratio`

2. **Pre-heating Scenario** (upcoming high prices)
   - Increases temperature before expensive period
   - Builds thermal mass in structure
   - Formula: `adjustment = max_increase * hours_factor`

3. **Normal Scenario**
   - No adjustment applied
   - Maintains user's desired temperature

#### State Management
- Tracks base temperature (user's desired temp)
- Tracks current adjustment being applied
- Restores state after restarts
- Monitors wrapped entity for external changes

## Configuration Parameters

### Required
- `target_climate`: Climate entity to wrap/control
- `price_sensor`: Sensor providing electricity prices

### Optional
- `max_increase`: Maximum temp increase (default: 2.0°C)
- `max_decrease`: Maximum temp decrease (default: 2.0°C)
- `price_threshold_high`: High price multiplier (default: 1.2)
- `price_threshold_low`: Low price multiplier (default: 0.8)
- `preheating_enabled`: Enable pre-conditioning (default: true)
- `preheating_hours`: Look-ahead period (default: 2 hours)

## Integration Points

### Nordpool Integration
- Uses `current_price` (state)
- Uses `average` attribute
- Uses `raw_today` array for today's hourly prices
- Uses `raw_tomorrow` array for tomorrow's hourly prices
- Each price entry has: `start` (ISO datetime), `value` (price)

### Generic Thermostat
- Reads `current_temperature`
- Reads `temperature` (target)
- Sets temperature via `climate.set_temperature`
- Sets HVAC mode via `climate.set_hvac_mode`
- Mirrors all HVAC modes and features

## Design Decisions

### Why Wrap Instead of Replace?
- Preserves existing thermostat logic (hysteresis, etc.)
- Works with any climate entity
- Simpler implementation
- Easier debugging

### Why Not Use Climate Presets?
- Limited to predefined modes
- Less granular control
- Doesn't support dynamic calculation
- Harder to visualise adjustments

### Price Threshold Approach
- Relative to average (not absolute prices)
- Adapts to seasonal price changes
- Works across different currencies
- User-friendly configuration

### State Tracking
- Separates base temp from adjusted temp
- Allows user overrides
- Enables proper restoration
- Clear attribution of changes

## Future Enhancements

### Planned
- [ ] Support for multiple price zones
- [ ] Machine learning for adjustment optimisation
- [ ] Energy dashboard integration
- [ ] Cost savings calculation and tracking

### Considered
- [ ] Integration with weather forecasts
- [ ] Room-by-room coordination
- [ ] Advanced scheduling integration
- [ ] Support for dynamic tariffs

## Testing Strategy

### Unit Tests
- Price calculation logic
- Temperature adjustment algorithms
- State management
- Configuration validation

### Integration Tests
- Interaction with wrapped climate entities
- Price sensor monitoring
- State persistence
- Event handling

### Manual Testing Checklist
- [ ] Installation via HACS
- [ ] UI configuration
- [ ] Price sensor integration
- [ ] Temperature adjustments during high prices
- [ ] Pre-heating before expensive periods
- [ ] User overrides respected
- [ ] State restoration after restart
- [ ] Options flow changes

## Known Limitations

1. **Price Sensor Requirements**
   - Requires `average` attribute (Nordpool provides this)
   - Requires hourly price data
   - Some sensors may need adaptation

2. **Climate Entity Compatibility**
   - Target entity must support temperature setting
   - Must support reading current temperature
   - Some entities may have conflicts with external control

3. **Timing**
   - Tomorrow's prices available ~13:00 CET
   - Limited look-ahead before prices available
   - Relies on system time accuracy

## Performance Considerations

- State updates triggered by price/climate changes only
- No polling loops
- Efficient event subscription
- Minimal computational overhead
- No external API calls (uses existing sensors)

## Security Considerations

- No external network access
- No sensitive data storage
- Uses Home Assistant's authentication
- Config flow validates entity existence
- No code execution from configuration

