#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import yaml
from prometheus_client import Counter, Gauge, start_http_server


LOGGER = logging.getLogger("prometheus-traceroute-exporter")


# Hop-level metrics inspired by mtr fields
PING = Gauge(
    "prometheus_traceroute_exporter_ping",
    "Last ping in milliseconds for a hop",
    ["target", "hop", "hop_number"],
)
AVG = Gauge(
    "prometheus_traceroute_exporter_avg",
    "Average ping in milliseconds for a hop",
    ["target", "hop", "hop_number"],
)
BEST = Gauge(
    "prometheus_traceroute_exporter_best",
    "Best ping in milliseconds for a hop",
    ["target", "hop", "hop_number"],
)
WORST = Gauge(
    "prometheus_traceroute_exporter_worst",
    "Worst ping in milliseconds for a hop",
    ["target", "hop", "hop_number"],
)
STDEV = Gauge(
    "prometheus_traceroute_exporter_stdev",
    "Standard deviation of ping in milliseconds for a hop",
    ["target", "hop", "hop_number"],
)
LOSS_RATIO = Gauge(
    "prometheus_traceroute_exporter_loss_ratio",
    "Packet loss ratio for a hop in range 0..1",
    ["target", "hop", "hop_number"],
)
SENT = Gauge(
    "prometheus_traceroute_exporter_sent",
    "Number of probes sent to a hop",
    ["target", "hop", "hop_number"],
)

# Target-level metrics
TARGET_UP = Gauge(
    "prometheus_traceroute_exporter_target_up",
    "1 if target scrape was successful, 0 otherwise",
    ["target"],
)
TARGET_LAST_SUCCESS_UNIX = Gauge(
    "prometheus_traceroute_exporter_target_last_success_unix",
    "Unix timestamp of the last successful scrape per target",
    ["target"],
)
TARGET_LAST_DURATION_SECONDS = Gauge(
    "prometheus_traceroute_exporter_target_last_duration_seconds",
    "Duration of the last scrape in seconds per target",
    ["target"],
)
TARGET_HOP_COUNT = Gauge(
    "prometheus_traceroute_exporter_target_hop_count",
    "Number of hops seen in the latest scrape per target",
    ["target"],
)
SCRAPE_ERRORS_TOTAL = Counter(
    "prometheus_traceroute_exporter_scrape_errors_total",
    "Total number of scrape errors per target",
    ["target"],
)


@dataclass
class MTRSettings:
    report_cycles: int = 5
    max_hops: int = 30
    timeout_seconds: int = 2
    no_dns: bool = True


@dataclass
class TargetConfig:
    name: str
    host: str
    interval_seconds: int = 60
    mtr: MTRSettings = field(default_factory=MTRSettings)


@dataclass
class ExporterConfig:
    default_interval_seconds: int = 60
    default_mtr: MTRSettings = field(default_factory=MTRSettings)
    targets: list[TargetConfig] = field(default_factory=list)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    text = str(value).strip().replace("%", "")
    if text == "":
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _pick(dct: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in dct:
            return dct[key]
    return default


def _load_mtr(raw: dict[str, Any] | None, defaults: MTRSettings) -> MTRSettings:
    raw = raw or {}
    return MTRSettings(
        report_cycles=max(1, _as_int(raw.get("report_cycles"), defaults.report_cycles)),
        max_hops=max(1, _as_int(raw.get("max_hops"), defaults.max_hops)),
        timeout_seconds=max(1, _as_int(raw.get("timeout_seconds"), defaults.timeout_seconds)),
        no_dns=bool(raw.get("no_dns", defaults.no_dns)),
    )


def load_config(path: str) -> ExporterConfig:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    global_cfg = data.get("global", {})
    default_interval = max(1, _as_int(global_cfg.get("default_interval_seconds"), 60))
    default_mtr = _load_mtr(global_cfg.get("mtr"), MTRSettings())

    targets: list[TargetConfig] = []
    for idx, item in enumerate(data.get("targets", []) or []):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid target at index {idx}: expected object")

        name = str(item.get("name") or item.get("host") or "").strip()
        host = str(item.get("host") or "").strip()
        if not name:
            raise ValueError(f"Target at index {idx} has no name")
        if not host:
            raise ValueError(f"Target '{name}' has no host")

        interval = max(1, _as_int(item.get("interval_seconds"), default_interval))
        mtr = _load_mtr(item.get("mtr"), default_mtr)
        targets.append(TargetConfig(name=name, host=host, interval_seconds=interval, mtr=mtr))

    if not targets:
        raise ValueError("Configuration contains no targets")

    return ExporterConfig(
        default_interval_seconds=default_interval,
        default_mtr=default_mtr,
        targets=targets,
    )


def build_mtr_command(target: TargetConfig) -> list[str]:
    command = [
        "mtr",
        "--report",
        "--json",
        "--report-cycles",
        str(target.mtr.report_cycles),
        "--max-ttl",
        str(target.mtr.max_hops),
        "--gracetime",
        str(target.mtr.timeout_seconds),
    ]
    if target.mtr.no_dns:
        command.append("--no-dns")
    command.append(target.host)
    return command


def parse_hops(raw: dict[str, Any]) -> list[dict[str, Any]]:
    hubs = _pick(raw, ["report"], {})
    if isinstance(hubs, dict):
        hops = _pick(hubs, ["hubs"], [])
    else:
        hops = []

    parsed: list[dict[str, Any]] = []
    for index, hop in enumerate(hops, start=1):
        if not isinstance(hop, dict):
            continue

        hop_number = _as_int(_pick(hop, ["count", "Count", "hop", "Hop"], index), index)
        host = str(_pick(hop, ["host", "Host"], "unknown")).strip() or "unknown"

        loss_percent = _as_float(_pick(hop, ["Loss%", "loss", "loss%"]), 0.0)
        last = _as_float(_pick(hop, ["Last", "last"]))
        avg = _as_float(_pick(hop, ["Avg", "avg"]))
        best = _as_float(_pick(hop, ["Best", "best"]))
        worst = _as_float(_pick(hop, ["Wrst", "Worst", "worst"]))
        stdev = _as_float(_pick(hop, ["StDev", "stdev", "StdDev"]))
        sent = _as_float(_pick(hop, ["Snt", "sent"]), 0.0)

        parsed.append(
            {
                "hop_number": hop_number,
                "hop": host,
                "loss_ratio": (loss_percent or 0.0) / 100.0,
                "last": last,
                "avg": avg,
                "best": best,
                "worst": worst,
                "stdev": stdev,
                "sent": sent,
            }
        )

    return parsed


class TracerouteCollector:
    def __init__(self, config: ExporterConfig):
        self.config = config
        self.stop_event = threading.Event()
        self._seen_labels: dict[str, set[tuple[str, str]]] = {}
        self._next_run: dict[str, float] = {
            target.name: 0.0 for target in self.config.targets
        }

    def run(self) -> None:
        LOGGER.info("Starting collection loop for %d target(s)", len(self.config.targets))
        while not self.stop_event.is_set():
            now = time.time()
            for target in self.config.targets:
                if now >= self._next_run[target.name]:
                    self.scrape_target(target)
                    self._next_run[target.name] = now + target.interval_seconds
            self.stop_event.wait(0.5)

    def stop(self) -> None:
        self.stop_event.set()

    def scrape_target(self, target: TargetConfig) -> None:
        start = time.time()
        command = build_mtr_command(target)
        LOGGER.debug("Running for target=%s command=%s", target.name, command)

        try:
            proc = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=(target.mtr.report_cycles * target.mtr.timeout_seconds) + 10,
            )
            data = yaml.safe_load(proc.stdout)
            if not isinstance(data, dict):
                raise ValueError("mtr output did not produce a valid JSON object")

            hops = parse_hops(data)
            self._update_hop_metrics(target.name, hops)

            TARGET_UP.labels(target=target.name).set(1)
            TARGET_HOP_COUNT.labels(target=target.name).set(len(hops))
            TARGET_LAST_SUCCESS_UNIX.labels(target=target.name).set(time.time())
        except Exception as exc:
            LOGGER.warning("Failed to scrape target=%s error=%s", target.name, exc)
            TARGET_UP.labels(target=target.name).set(0)
            TARGET_HOP_COUNT.labels(target=target.name).set(0)
            SCRAPE_ERRORS_TOTAL.labels(target=target.name).inc()
            self._clear_hop_metrics(target.name)
        finally:
            TARGET_LAST_DURATION_SECONDS.labels(target=target.name).set(time.time() - start)

    def _clear_hop_metrics(self, target: str) -> None:
        previous = self._seen_labels.get(target, set())
        for hop, hop_number in previous:
            PING.remove(target, hop, hop_number)
            AVG.remove(target, hop, hop_number)
            BEST.remove(target, hop, hop_number)
            WORST.remove(target, hop, hop_number)
            STDEV.remove(target, hop, hop_number)
            LOSS_RATIO.remove(target, hop, hop_number)
            SENT.remove(target, hop, hop_number)
        self._seen_labels[target] = set()

    def _update_hop_metrics(self, target: str, hops: list[dict[str, Any]]) -> None:
        active_labels: set[tuple[str, str]] = set()

        for hop in hops:
            hop_label = str(hop["hop"])
            hop_number_label = str(hop["hop_number"])
            labels = (hop_label, hop_number_label)
            active_labels.add(labels)

            label_args = {
                "target": target,
                "hop": hop_label,
                "hop_number": hop_number_label,
            }
            if hop["last"] is not None:
                PING.labels(**label_args).set(hop["last"])
            if hop["avg"] is not None:
                AVG.labels(**label_args).set(hop["avg"])
            if hop["best"] is not None:
                BEST.labels(**label_args).set(hop["best"])
            if hop["worst"] is not None:
                WORST.labels(**label_args).set(hop["worst"])
            if hop["stdev"] is not None:
                STDEV.labels(**label_args).set(hop["stdev"])
            if hop["loss_ratio"] is not None:
                LOSS_RATIO.labels(**label_args).set(hop["loss_ratio"])
            if hop["sent"] is not None:
                SENT.labels(**label_args).set(hop["sent"])

        previous = self._seen_labels.get(target, set())
        stale = previous - active_labels
        for hop_label, hop_number_label in stale:
            PING.remove(target, hop_label, hop_number_label)
            AVG.remove(target, hop_label, hop_number_label)
            BEST.remove(target, hop_label, hop_number_label)
            WORST.remove(target, hop_label, hop_number_label)
            STDEV.remove(target, hop_label, hop_number_label)
            LOSS_RATIO.remove(target, hop_label, hop_number_label)
            SENT.remove(target, hop_label, hop_number_label)

        self._seen_labels[target] = active_labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prometheus Traceroute Exporter")
    parser.add_argument(
        "--config",
        default=os.environ.get("CONFIG_PATH", "/etc/prometheus-traceroute-exporter/config.yml"),
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--listen-address",
        default=os.environ.get("LISTEN_ADDRESS", "0.0.0.0"),
        help="Address where metrics HTTP server listens",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=int(os.environ.get("LISTEN_PORT", "9888")),
        help="Port where metrics HTTP server listens",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config(args.config)

    collector = TracerouteCollector(config)
    worker = threading.Thread(target=collector.run, daemon=True)

    LOGGER.info(
        "Starting metrics endpoint on %s:%s for %d target(s)",
        args.listen_address,
        args.listen_port,
        len(config.targets),
    )
    start_http_server(port=args.listen_port, addr=args.listen_address)
    worker.start()

    def _shutdown_handler(signum: int, frame: Any) -> None:
        LOGGER.info("Received signal %s, shutting down", signum)
        collector.stop()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    while worker.is_alive():
        worker.join(timeout=0.5)


if __name__ == "__main__":
    main()
