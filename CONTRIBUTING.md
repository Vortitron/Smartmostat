# Contributing to Smartmostat

Thank you for helping. Please read [docs/SPEC.md](docs/SPEC.md) first: it explains what
Smartmostat does and why.

## Development set-up

Smartmostat is tested with Python 3.13 and the Home Assistant release pinned by
`pytest-homeassistant-custom-component` in `requirements_test.txt`.

```bash
git clone https://github.com/Vortitron/Smartmostat.git
cd Smartmostat
uv venv -p 3.13 .venv          # or: python3.13 -m venv .venv
. .venv/bin/activate
uv pip install -r requirements_test.txt
pytest -q
```

To try it in a real instance, link or copy `custom_components/smartmostat` into your Home
Assistant `config/custom_components/` folder and restart. Please use a test instance, not a
production house.

## Code layout

| File | Role |
|---|---|
| `price.py` | Pure: parse price slots, derive the price signals |
| `planner.py` | Pure: base target and control target (presets, schedule, pre-warm, override) |
| `actuators.py` | Pure: what to tell the device in each control mode |
| `safety.py`, `engine.py` | Pure: safety rules and the decision for one snapshot |
| `migration.py`, `settings.py` | Pure: config entry migration and typed settings |
| `coordinator.py` | The per-entry controller: reads Home Assistant state, runs the engine, sends commands |
| `climate.py`, `sensor.py`, `switch.py` | Entities |
| `config_flow.py` | Config, reconfigure and options flows |

Decision logic belongs in the pure modules so it can be tested without Home Assistant
(`tests/core/`). Home Assistant behaviour (flows, entities, migration, services) is tested in
`tests/test_*.py`.

## Style

- Tabs for indentation; type hints everywhere.
- UK English in comments, docs and user-facing strings. No em-dashes.
- Every user-facing string lives in `strings.json`; copy it to `translations/en.json`
  (a test checks they match).
- Run `ruff check custom_components tests` before committing.

## Pull requests

- One logical change per commit, with tests.
- Add a line to `CHANGELOG.md` under an *Unreleased* heading.
- CI runs pytest, hassfest and HACS validation.
