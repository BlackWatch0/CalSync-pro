from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from icalendar import Calendar
from icalendar.cal import Component

from .config import AppConfig, IcsSourceConfig, SyncJobConfig
from .normalizer import build_bundle, compute_timerange, event_overlaps_range, fallback_uid

logger = logging.getLogger(__name__)


@dataclass
class SourceFetchResult:
    bundles: Dict[str, str]
    unchanged: bool


class SyncState:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"sources": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def source_headers(self, source_id: str) -> Dict[str, str]:
        item = self.data.get("sources", {}).get(source_id, {})
        headers: Dict[str, str] = {}
        if item.get("etag"):
            headers["If-None-Match"] = item["etag"]
        if item.get("last_modified"):
            headers["If-Modified-Since"] = item["last_modified"]
        return headers

    def update_source_cache(self, source_id: str, etag: Optional[str], last_modified: Optional[str]) -> None:
        self.data.setdefault("sources", {}).setdefault(source_id, {})
        self.data["sources"][source_id].update({"etag": etag, "last_modified": last_modified})

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


class ICSFetcher:
    def __init__(self, app_config: AppConfig, source: IcsSourceConfig, job: SyncJobConfig, state: SyncState):
        self.app_config = app_config
        self.source = source
        self.job = job
        self.state = state

    def _request_with_retry(self, session: requests.Session, headers: Dict[str, str]) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.app_config.max_retries):
            try:
                return session.get(self.source.url, headers=headers, timeout=self.app_config.request_timeout)
            except requests.RequestException as exc:
                last_exc = exc
                wait_s = self.app_config.retry_base_seconds * (2 ** attempt)
                logger.warning("ICS fetch failed, retrying", extra={"extra": {"url": self.source.url, "attempt": attempt + 1, "wait_s": wait_s}})
                time.sleep(wait_s)
        raise RuntimeError(f"Failed to fetch {self.source.url}: {last_exc}")

    def _parse(self, body: str) -> Dict[str, str]:
        cal = Calendar.from_ical(body)
        vtimezones = [comp for comp in cal.subcomponents if comp.name == "VTIMEZONE"]
        range_start, range_end = compute_timerange(self.job.timezone, self.job.range_past_days, self.job.range_future_days)

        grouped: Dict[str, List[Component]] = {}
        for comp in cal.subcomponents:
            if comp.name != "VEVENT":
                continue
            if not event_overlaps_range(comp, range_start, range_end, self.job.timezone):
                continue
            uid = str(comp.get("UID") or fallback_uid(comp, self.job.fallback_uid_strategy, self.source.url))
            grouped.setdefault(uid, []).append(comp)

        bundles: Dict[str, str] = {}
        for uid, events in grouped.items():
            bundles[uid] = build_bundle(uid, events, vtimezones).raw_ical
        return bundles

    def fetch(self) -> SourceFetchResult:
        session = requests.Session()
        if self.source.basic_user and self.source.basic_password:
            session.auth = (self.source.basic_user, self.source.basic_password)

        headers = dict(self.source.headers)
        if self.source.bearer_token:
            headers["Authorization"] = f"Bearer {self.source.bearer_token}"
        headers.update(self.state.source_headers(self.source.source_id))

        response = self._request_with_retry(session, headers)
        if response.status_code == 304:
            logger.info("ICS not modified", extra={"extra": {"source_id": self.source.source_id, "url": self.source.url}})
            return SourceFetchResult(bundles={}, unchanged=True)

        response.raise_for_status()
        self.state.update_source_cache(self.source.source_id, response.headers.get("ETag"), response.headers.get("Last-Modified"))
        return SourceFetchResult(bundles=self._parse(response.text), unchanged=False)
