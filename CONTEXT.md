# Copilot Context

## Project goal

Prometheus exporter that periodically runs `mtr` for configured targets and publishes hop-level metrics on `/metrics`.

## Current stack

- Language: Python 3.12
- Runtime: single process + background thread scheduler
- Metrics: `prometheus_client`
- Config: YAML via `PyYAML`
- Probe engine: external `mtr` command in report+json mode
- Deployment: Docker (Debian slim base)

## Core files

- `app.py`: main app, config parsing, scheduler, mtr execution, metric updates
- `config.example.yml`: sample targets and defaults
- `Dockerfile`: runtime image with `mtr-tiny`
- `docker-compose.yaml`: local deployment helper

## Important behavior

- Exporter owns probing schedule (`interval_seconds`) per target.
- Prometheus scrape is passive and only reads latest values.
- Hop labels include `target`, `hop`, `hop_number`.
- Stale hop series are removed when route changes.

## Non-goals

- No active HTTP API to mutate config at runtime.
- No built-in config hot-reload.
