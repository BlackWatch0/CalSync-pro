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
        config = build_config()
        state = SyncState(config.state_file)
        engines = []
        for job in config.jobs.values():
            source = config.sources[job.source_id]
            client = config.clients[job.client_id]
            fetcher = ICSFetcher(config, source, job, state)
            mirror = CalDAVMirror(config, client, job)
            engines.append(MirrorSyncEngine(fetcher, mirror, state, job))

        if not config.daemon_mode:
            for engine in engines:
                engine.run_once()
            return 0

        logger.info("Starting daemon loop", extra={"extra": {"interval_seconds": config.interval_seconds, "job_count": len(engines)}})
        while RUNNING:
            for engine in engines:
                try:
                    engine.run_once()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Sync round crashed", extra={"extra": {"operation": "sync_round", "error": str(exc)}})
            for _ in range(config.interval_seconds):
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
