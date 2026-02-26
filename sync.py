from __future__ import annotations

import logging
import signal
import sys
import time

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


def main() -> int:
    setup_logging()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        app_config = build_config()
        engines = []
        for sync_config in app_config.syncs:
            state = SyncState(sync_config.state_file)
            fetcher = ICSFetcher(sync_config, state)
            mirror = CalDAVMirror(sync_config)
            engines.append((sync_config, MirrorSyncEngine(fetcher, mirror, state, sync_config.timezone)))

        if not app_config.daemon_mode:
            for sync_config, engine in engines:
                logger.info("Running one-shot sync", extra={"extra": {"sync": sync_config.sync_name}})
                engine.run_once()
            return 0

        logger.info(
            "Starting daemon loop",
            extra={"extra": {"interval_seconds": app_config.interval_seconds, "sync_count": len(engines)}},
        )
        while RUNNING:
            for sync_config, engine in engines:
                try:
                    engine.run_once()
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Sync round crashed",
                        extra={"extra": {"operation": "sync_round", "sync": sync_config.sync_name, "error": str(exc)}},
                    )
            for _ in range(app_config.interval_seconds):
                if not RUNNING:
                    break
                time.sleep(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error", extra={"extra": {"error": str(exc)}})
        return 1

    logger.info("Stopped daemon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
