# Changelog

All notable changes to the Smart Thermostat integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of Smart Thermostat integration
- Dynamic temperature adjustment based on electricity prices
- Pre-heating/pre-cooling before expensive periods
- UI-based configuration flow
- Options flow for reconfiguration
- Support for Nordpool and other price sensors
- Comprehensive state attributes for monitoring
- HACS compatibility
- Unit tests for core functionality
- GitHub Actions CI/CD workflows
- Documentation and contributing guidelines

### Features
- Wraps existing Home Assistant climate entities
- Monitors electricity price sensors (e.g., Nordpool)
- Reduces heating/cooling during expensive periods
- Pre-conditions home before price spikes
- Configurable maximum temperature variance
- Configurable price thresholds
- State restoration after restarts
- Rich entity attributes for automation

## [0.1.0] - 2025-10-21

### Added
- Initial development version
- Core climate platform implementation
- Configuration flow
- Basic documentation

