# Copilot Quickstart Context

## Typical commands

- Build image:
  - `docker build -t prometheus-traceroute-exporter:latest .`
- Run:
  - `docker run --rm -p 9888:9888 --cap-add NET_RAW -v $(pwd)/config.yml:/etc/prometheus-traceroute-exporter/config.yml:ro prometheus-traceroute-exporter:latest`
- Compose:
  - `docker compose up -d --build`

## Files to edit first

1. `config.yml` for targets/intervals
2. `app.py` for new metrics or parsing logic
3. `README.md` for user-facing changes

## Extension ideas

- Add config hot-reload (SIGHUP or polling hash).
- Add metric for next scheduled run per target.
- Add optional DNS lookup mode toggle per target.
- Add unit tests for parsing and config validation.
