# Smart Thermostat with Price-Based Control

{% if installed %}
## Installed!

Your Smart Thermostat integration is now installed. To start using it:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Smart Thermostat**
4. Follow the configuration steps

You'll need:
- An existing thermostat (climate entity)
- An electricity price sensor (like Nordpool)

{% endif %}

## Features

✨ **Dynamic Temperature Adjustment** - Automatically adjusts your thermostat based on electricity prices

🔮 **Pre-heating Intelligence** - Pre-conditions your home before expensive periods

💰 **Cost Savings** - Reduce heating/cooling costs by 10-20% in well-insulated homes

⚙️ **Fully Configurable** - Set your own limits and thresholds

🔌 **Universal Compatibility** - Works with any Home Assistant climate entity

📊 **Rich Attributes** - Monitor price ratios, adjustments, and forecasts

## Quick Start

1. Install a price sensor integration (e.g., [Nordpool](https://github.com/custom-components/nordpool))
2. Add this integration and select your existing thermostat
3. **Important**: Choose the **main Nordpool sensor** (e.g., `sensor.nordpool_kwh_no1_nok`), NOT "next_price"
4. Configure your maximum temperature variance
5. Let it run and monitor the savings!

### Which Sensor?

✅ Use: `sensor.nordpool_kwh_<region>_<currency>`  
❌ Don't use: `sensor.nordpool_next_price`

The main sensor contains all hourly price data needed for intelligent look-ahead analysis.

## How It Works

The integration monitors electricity prices and adjusts your thermostat's target temperature:

- **High prices** → Reduces heating/increases cooling tolerance
- **Before high prices** → Pre-heats/pre-cools to build thermal mass
- **Normal prices** → Maintains your desired temperature

## Configuration Tips

Start conservative:
- Max adjustment: 2°C
- Price threshold: 1.2 (20% above average)
- Pre-heating: 2-3 hours look-ahead

Fine-tune based on:
- Your home's insulation
- Local price volatility
- Personal comfort preferences

## Support

📚 [Documentation](https://github.com/vortitron/smartmostat/blob/main/README.md)  
🐛 [Report Issues](https://github.com/vortitron/smartmostat/issues)  
💬 [Community Forum](https://community.home-assistant.io/)

---

**Note**: This integration requires an electricity price sensor that provides hourly prices and average calculations (like Nordpool).

