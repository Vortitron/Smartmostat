# Superseded design notes

These files describe earlier designs of Smartmostat and are kept for reference only. They do
**not** describe how 0.3.0 works; see the main [README](../../README.md) and
[docs/SPEC.md](../SPEC.md) for that.

| File | Describes | Status |
|---|---|---|
| `project_outline.md` | The 0.1.0 plan: wrap a climate entity and shift its set-point by price ratio | Became *Set-point* mode |
| `PRICE_ANALYSIS.md` | 0.1.0 price-ratio decisions and look-ahead | Replaced by the two-signal price gate (relative and absolute) |
| `IMPROVEMENTS_V2.md`, `SUMMARY.md` | A "max variance" curve on price position | Never implemented |
| `TOLERANCE_APPROACH.md`, `TOLERANCE_IMPLEMENTATION.md` | 0.2.0 tolerance mode: price-dependent asymmetric hysteresis | Became *Switch* mode; migrated entries keep the same thresholds at the price extremes. Note: these files say the bands cross at `min_tolerance`; the 0.2.0 code crossed at `(min + max) / 2` |

Useful ideas from them that live on in 0.3.0:

- the control target stays invisible: the thermostat shows what you asked for, the price
  adjustment is an attribute and a sensor;
- `price_position` (0 cheapest to 1 dearest over the next 24 hours) is still published;
- the auto-detection of a Nordpool sensor by its `raw_today` attribute in the config flow.
