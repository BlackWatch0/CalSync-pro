from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict

from .caldav_client import CalDAVMirror
from .ics_source import ICSFetcher, SourceFetchResult, SyncState
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
    def __init__(self, fetcher: ICSFetcher, mirror: CalDAVMirror, state: SyncState, timezone: str):
        self.fetcher = fetcher
        self.mirror = mirror
        self.state = state
        self.timezone = timezone

    def _decode_source(self, result: SourceFetchResult) -> Dict[str, str]:
        source: Dict[str, str] = {}
        for uid, packed in result.bundles.items():
            _, raw = packed.split("\n", 1)
            source[uid] = raw
        return source

    def run_once(self) -> SyncStats:
        started = time.monotonic()
        stats = SyncStats()

        fetch = self.fetcher.fetch()
        if fetch.unchanged:
            logger.info("All ICS sources unchanged, skipping sync")
            return stats

        source_map = self._decode_source(fetch)
        server_map = self.mirror.list_server_objects()

        for uid, raw in source_map.items():
            try:
                src_fp = fingerprint_calendar_event_bundle(raw, self.timezone)
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
                logger.error("Failed to upsert event", extra={"extra": {"uid": uid, "operation": "upsert", "error": str(exc)}})

        for uid, server_event in server_map.items():
            if uid in source_map:
                continue
            try:
                self.mirror.delete(server_event)
                stats.deleted += 1
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                logger.error("Failed to delete event", extra={"extra": {"uid": uid, "operation": "delete", "error": str(exc)}})

        self.state.save()
        elapsed = round(time.monotonic() - started, 3)
        logger.info(
            "Sync round completed",
            extra={
                "extra": {
                    "created": stats.created,
                    "updated": stats.updated,
                    "deleted": stats.deleted,
                    "skipped": stats.skipped,
                    "failed": stats.failed,
                    "duration_s": elapsed,
                }
            },
        )
        return stats
