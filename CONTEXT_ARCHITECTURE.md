# Architecture Context

## High-level flow

1. App starts and loads YAML config.
2. HTTP metrics endpoint starts on configured address/port.
3. Background scheduler loop checks due targets.
4. For each due target:
   - runs `mtr --report --json ...`
   - parses hop stats
   - updates Prometheus gauges/counters
5. Prometheus scrapes `/metrics`.

## Components

- `load_config()`
  - validates targets
  - applies global defaults + per-target overrides

- `build_mtr_command()`
  - creates command from target config

- `parse_hops()`
  - maps mtr report fields to normalized hop structure

- `TracerouteCollector`
  - scheduler (`run()`)
  - per-target scrape (`scrape_target()`)
  - stale-label cleanup for changing routes

## Operational considerations

- Requires raw network capability in container.
- Probe duration depends on `report_cycles` and timeout.
- Large target lists may increase CPU/network usage.
