# Contributing to Smart Thermostat

Thank you for considering contributing to the Smart Thermostat integration! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Home Assistant development environment
- Git

### Setting Up Development Environment

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/smartmostat.git
   cd smartmostat
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements_test.txt
   ```

4. Create a symlink in your Home Assistant installation:
   ```bash
   ln -s $(pwd)/custom_components/smartmostat ~/.homeassistant/custom_components/smartmostat
   ```

## Development Guidelines

### Code Style

- Follow PEP 8 style guidelines
- Use tabs for indentation (project preference)
- Use British English in comments and documentation
- Use type hints for all function parameters and return values

### Best Practices

1. **Reuse functions** - Keep code DRY (Don't Repeat Yourself)
2. **Avoid exports** - Never use `export let` or export objects/arrays; pass through function parameters
3. **ES Modules** - Use modern ES module syntax where appropriate
4. **File size** - Files over 1500 lines should be refactored
5. **Constants** - Replace hardcoded values with named constants
6. **Edge cases** - Always consider and handle potential edge cases
7. **Error handling** - Implement robust error handling and logging
8. **Assertions** - Include assertions to validate assumptions

### Testing

All new features and bug fixes must include tests.

#### Running Tests

```bash
pytest tests/ -v
```

#### Running Tests with Coverage

```bash
pytest tests/ -v --cov=custom_components/smartmostat --cov-report=term-missing
```

#### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names: `test_<functionality>_<scenario>`
- Mock external dependencies (Home Assistant entities)
- Test both success and error cases
- Include edge case tests

Example test structure:
```python
def test_temperature_adjustment_during_high_prices():
	"""Test that temperature is reduced when prices are high."""
	# Arrange
	thermostat = create_test_thermostat()
	set_high_price_state()
	
	# Act
	thermostat.calculate_adjustment()
	
	# Assert
	assert thermostat.current_adjustment < 0
```

### Committing Changes

1. Make sure tests pass:
   ```bash
   pytest tests/
   ```

2. Commit with descriptive messages:
   ```bash
   git commit -m "Add feature: pre-cooling logic for summer periods"
   ```

3. Use conventional commit format:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `test:` - Test additions or changes
   - `refactor:` - Code refactoring
   - `chore:` - Maintenance tasks

## Pull Request Process

1. **Update documentation** - Update README.md, project_outline.md if needed
2. **Add tests** - Ensure your changes are covered by tests
3. **Test thoroughly** - Manually test in a Home Assistant instance
4. **Update CHANGELOG** - Add entry describing your changes
5. **Create PR** - Submit pull request with clear description

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] Manually tested in Home Assistant
- [ ] All tests passing

## Checklist
- [ ] Code follows project style guidelines
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] No breaking changes (or clearly documented)
```

## Reporting Bugs

Use GitHub Issues to report bugs. Please include:

1. **Description** - Clear description of the bug
2. **Steps to Reproduce** - Detailed steps to reproduce the issue
3. **Expected Behaviour** - What you expected to happen
4. **Actual Behaviour** - What actually happened
5. **Environment**:
   - Home Assistant version
   - Smart Thermostat version
   - Price sensor integration (e.g., Nordpool)
6. **Logs** - Relevant log entries (enable debug logging)

### Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.smartmostat: debug
```

## Feature Requests

Feature requests are welcome! Please:

1. Check existing issues first
2. Describe the feature and use case
3. Explain expected behaviour
4. Consider backwards compatibility

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome newcomers
- Accept constructive criticism
- Focus on what's best for the community

### Enforcement

Project maintainers will address violations. Consequences may include:
- Warning
- Temporary ban
- Permanent ban

## Questions?

Feel free to:
- Open a GitHub Discussion
- Comment on related issues
- Ask in Home Assistant Community forums

## Licence

By contributing, you agree that your contributions will be licenced under the MIT Licence.

## Recognition

Contributors will be recognised in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing! 🎉

