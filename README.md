# Prometheus Traceroute Exporter

[![GitHub Build](https://img.shields.io/github/actions/workflow/status/ownercz/prometheus-traceroute-exporter/docker-image.yml?branch=main&label=github%20build)](https://github.com/ownercz/prometheus-traceroute-exporter/actions/workflows/docker-image.yml)
[![Gitea Workflow](https://img.shields.io/badge/gitea-workflow%20enabled-609926?logo=gitea&logoColor=white)](https://git.lipovcan.cz/Ownercz/prometheus-traceroute-exporter)
[![Docker Image](https://img.shields.io/badge/docker-ownercz%2Fprometheus--traceroute--exporter-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/ownercz/prometheus-traceroute-exporter)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Prometheus](https://img.shields.io/badge/prometheus-exporter-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This is a Prometheus exporter that runs periodic traceroute-like checks using `mtr` and exposes hop metrics on `/metrics`.

> Disclosure: This project was LLM-created by Ownercz - Radim Lipovčan.

## Features

- YAML configuration for target list and scrape interval.
- Per-target interval override.
- `mtr`-inspired hop metrics with labels:
  - `target`
  - `hop`
  - `hop_number`
- Docker-first deployment for Prometheus scraping.

## Exposed metrics

Hop-level metrics:

- `prometheus_traceroute_exporter_ping{target,hop,hop_number}` — last RTT in ms
- `prometheus_traceroute_exporter_avg{target,hop,hop_number}` — average RTT in ms
- `prometheus_traceroute_exporter_best{target,hop,hop_number}` — best RTT in ms
- `prometheus_traceroute_exporter_worst{target,hop,hop_number}` — worst RTT in ms
- `prometheus_traceroute_exporter_stdev{target,hop,hop_number}` — stdev RTT in ms
- `prometheus_traceroute_exporter_loss_ratio{target,hop,hop_number}` — loss ratio in range 0..1
- `prometheus_traceroute_exporter_sent{target,hop,hop_number}` — sent probe count

Target-level metrics:

- `prometheus_traceroute_exporter_target_up{target}` — success state of latest run
- `prometheus_traceroute_exporter_target_hop_count{target}` — hop count from latest run
- `prometheus_traceroute_exporter_target_last_success_unix{target}` — timestamp of latest successful run
- `prometheus_traceroute_exporter_target_last_duration_seconds{target}` — duration of latest run
- `prometheus_traceroute_exporter_scrape_errors_total{target}` — cumulative scrape errors

## Configuration

Create `config.yml` (you can copy `config.example.yml`):

```yaml
global:
  default_interval_seconds: 60
  mtr:
    report_cycles: 5
    max_hops: 30
    timeout_seconds: 2
    no_dns: true

targets:
  - name: cloudflare_dns
    host: 1.1.1.1
    interval_seconds: 30
    mtr:
      report_cycles: 5
      max_hops: 30
      timeout_seconds: 2
      no_dns: true
```

### Config keys

- `global.default_interval_seconds`: default frequency per target
- `global.mtr.report_cycles`: number of probes per target run
- `global.mtr.max_hops`: max TTL/hops
- `global.mtr.timeout_seconds`: timeout/grace per probe
- `global.mtr.no_dns`: disable reverse DNS lookups
- `targets[].name`: label-safe target identifier
- `targets[].host`: destination hostname/IP
- `targets[].interval_seconds`: optional per-target interval override
- `targets[].mtr.*`: optional per-target mtr settings

## Run with Docker

1. Prepare config:
   - `cp config.example.yml config.yml`
2. Build image:
   - `docker build -t prometheus-traceroute-exporter:latest .`
3. Run container:
   - `docker run --rm -p 9888:9888 --cap-add NET_RAW -v $(pwd)/config.yml:/etc/prometheus-traceroute-exporter/config.yml:ro prometheus-traceroute-exporter:latest`

Or use compose:

- `docker compose up -d --build`

Then open:

- `http://localhost:9888/metrics`

## Prometheus scrape config example

```yaml
scrape_configs:
  - job_name: traceroute_exporter
    static_configs:
      - targets:
          - prometheus-traceroute-exporter:9888
```

## Notes

- Container needs raw network capabilities to run `mtr`; use `--cap-add NET_RAW`.
- If target path/hops change, stale hop label series from previous run are removed.
- Exporter runs periodic checks itself; Prometheus only scrapes current state.

## Development

Local run (without Docker) requires `mtr` binary and Python dependencies:

- `pip install -r requirements.txt`
- `python app.py --config ./config.yml --listen-address 0.0.0.0 --listen-port 9888`
