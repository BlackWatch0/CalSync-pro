from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .caldav_client import CalDAVMirror
from .config import SyncJobConfig
from .ics_source import ICSFetcher, SyncState
from .normalizer import fingerprint_calendar_event_bundle

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0


class MirrorSyncEngine:
    def __init__(self, fetcher: ICSFetcher, mirror: CalDAVMirror, state: SyncState, job: SyncJobConfig):
        self.fetcher = fetcher
        self.mirror = mirror
        self.state = state
        self.job = job

    def run_once(self) -> SyncStats:
        started = time.monotonic()
        stats = SyncStats()

        fetch = self.fetcher.fetch()
        if fetch.unchanged:
            logger.info("ICS unchanged, skipping job", extra={"extra": {"job_id": self.job.job_id, "source_id": self.job.source_id}})
            return stats

        source_map = fetch.bundles
        server_map = self.mirror.list_server_objects()

        for uid, raw in source_map.items():
            try:
                src_fp = fingerprint_calendar_event_bundle(raw, self.job.timezone)
                existing = server_map.get(uid)
                if existing and existing.fingerprint == src_fp:
                    stats.skipped += 1
                    continue
                self.mirror.create_or_update(raw, existing)
                if existing:
                    stats.updated += 1
                else:
                    stats.created += 1
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                logger.error("Failed to upsert event", extra={"extra": {"job_id": self.job.job_id, "uid": uid, "operation": "upsert", "error": str(exc)}})

        for uid, server_event in server_map.items():
            if uid in source_map:
                continue
            try:
                self.mirror.delete(server_event)
                stats.deleted += 1
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                logger.error("Failed to delete event", extra={"extra": {"job_id": self.job.job_id, "uid": uid, "operation": "delete", "error": str(exc)}})

        self.state.save()
        elapsed = round(time.monotonic() - started, 3)
        logger.info("Sync round completed", extra={"extra": {"job_id": self.job.job_id, "source_id": self.job.source_id, "client_id": self.job.client_id, "created": stats.created, "updated": stats.updated, "deleted": stats.deleted, "skipped": stats.skipped, "failed": stats.failed, "duration_s": elapsed}})
        return stats
