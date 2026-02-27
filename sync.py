from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from mirror_sync.caldav_client import CalDAVMirror
from mirror_sync.config import build_config
from mirror_sync.ics_source import ICSFetcher, SyncState
from mirror_sync.logging_utils import setup_logging
from mirror_sync.sync_engine import MirrorSyncEngine

logger = logging.getLogger(__name__)
RUNNING = True


def _stop(_signum, _frame):
    global RUNNING
    RUNNING = False


def _discover_json_config_path() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json-config")
    args, _ = parser.parse_known_args()
    raw = args.json_config or os.getenv("SYNC_JSON_CONFIG")
    return Path(raw) if raw else None


def _discover_related_config_paths(config_path: Path) -> list[Path]:
    paths = [config_path]
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        sources_file = str(payload.get("sources_file", "sources.json"))
        clients_file = str(payload.get("clients_file", "clients.json"))
        paths.append(config_path.parent / sources_file)
        paths.append(config_path.parent / clients_file)
    except Exception:  # noqa: BLE001
        pass
    return paths


def _config_signature(config_path: Path) -> tuple[tuple[str, bool, int, int], ...]:
    signature: list[tuple[str, bool, int, int]] = []
    for path in sorted(_discover_related_config_paths(config_path), key=lambda item: str(item)):
        try:
            stat = path.stat()
            signature.append((str(path), True, stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            signature.append((str(path), False, 0, 0))
    return tuple(signature)


def _build_engines(app_config):
    engines = []
    for sync_config in app_config.syncs:
        logger.info(
            "Sync mapping loaded",
            extra={
                "extra": {
                    "sync": sync_config.sync_name,
                    "source_count": len(sync_config.ics_urls),
                    "calendar_name": sync_config.calendar_name,
                    "calendar_url": sync_config.calendar_url,
                    "state_file": str(sync_config.state_file),
                    "interval_seconds": sync_config.interval_seconds,
                }
            },
        )
        state = SyncState(sync_config.state_file)
        fetcher = ICSFetcher(sync_config, state)
        mirror = CalDAVMirror(sync_config)
        engine = MirrorSyncEngine(fetcher, mirror, state, sync_config.timezone)
        engines.append({"sync": sync_config, "engine": engine, "next_run_at": 0.0})
    return engines


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        app_config = build_config()
        setup_logging(app_config.debug_level)
        json_config_path = _discover_json_config_path()
        config_signature = _config_signature(json_config_path) if json_config_path else None
        hot_reload_enabled = json_config_path is not None
        logger.info(
            "Runtime settings loaded",
            extra={
                "extra": {
                    "debug_level": app_config.debug_level,
                    "daemon_mode": app_config.daemon_mode,
                    "interval_seconds": app_config.interval_seconds,
                    "sync_count": len(app_config.syncs),
                    "hot_reload_enabled": hot_reload_enabled,
                }
            },
        )
        engines = _build_engines(app_config)

        if not app_config.daemon_mode:
            for item in engines:
                sync_config = item["sync"]
                engine = item["engine"]
                logger.info("Running one-shot sync", extra={"extra": {"sync": sync_config.sync_name}})
                engine.run_once()
            return 0

        logger.info(
            "Starting daemon loop",
            extra={"extra": {"sync_count": len(engines), "hot_reload_enabled": hot_reload_enabled}},
        )
        while RUNNING:
            if json_config_path:
                current_signature = _config_signature(json_config_path)
                if current_signature != config_signature:
                    logger.info("Config change detected, reloading")
                    try:
                        app_config = build_config()
                        setup_logging(app_config.debug_level)
                        engines = _build_engines(app_config)
                        config_signature = current_signature
                        logger.info(
                            "Config reloaded",
                            extra={"extra": {"sync_count": len(engines), "debug_level": app_config.debug_level}},
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Config reload failed", extra={"extra": {"error": str(exc)}})
                        config_signature = current_signature

            now = time.time()
            for item in engines:
                sync_config = item["sync"]
                engine = item["engine"]
                if now < item["next_run_at"]:
                    continue
                interval_seconds = max(1, int(sync_config.interval_seconds))
                try:
                    engine.run_once()
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Sync round crashed",
                        extra={"extra": {"operation": "sync_round", "sync": sync_config.sync_name, "error": str(exc)}},
                    )
                finally:
                    base_ts = max(float(item["next_run_at"]), now)
                    item["next_run_at"] = base_ts + interval_seconds

            time.sleep(1)
    except Exception as exc:  # noqa: BLE001
        setup_logging()
        logger.error("Fatal error", extra={"extra": {"error": str(exc)}})
        return 1

    logger.info("Stopped daemon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
