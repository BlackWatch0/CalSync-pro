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

from .config import SyncConfig
from .normalizer import (
    build_bundle,
    compute_timerange,
    event_overlaps_range,
    fallback_uid,
    fingerprint_calendar_event_bundle,
)

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

    def source_headers(self, url: str) -> Dict[str, str]:
        item = self.data.get("sources", {}).get(url, {})
        headers: Dict[str, str] = {}
        if item.get("etag"):
            headers["If-None-Match"] = item["etag"]
        if item.get("last_modified"):
            headers["If-Modified-Since"] = item["last_modified"]
        return headers

    def update_source_cache(self, url: str, etag: Optional[str], last_modified: Optional[str]) -> None:
        self.data.setdefault("sources", {}).setdefault(url, {})
        self.data["sources"][url].update({"etag": etag, "last_modified": last_modified})

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


class ICSFetcher:
    def __init__(self, config: SyncConfig, state: SyncState):
        self.config = config
        self.state = state

    def _request_with_retry(self, session: requests.Session, url: str, headers: Dict[str, str]) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                return session.get(url, headers=headers, timeout=self.config.request_timeout)
            except requests.RequestException as exc:
                last_exc = exc
                wait_s = self.config.retry_base_seconds * (2 ** attempt)
                logger.warning("ICS fetch failed, retrying", extra={"extra": {"url": url, "attempt": attempt + 1, "wait_s": wait_s}})
                time.sleep(wait_s)
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}")

    def _parse(self, body: str, source_url: str) -> Dict[str, str]:
        cal = Calendar.from_ical(body)
        vtimezones = [comp for comp in cal.subcomponents if comp.name == "VTIMEZONE"]

        range_start, range_end = compute_timerange(
            self.config.timezone,
            self.config.range_past_days,
            self.config.range_future_days,
        )

        grouped: Dict[str, List[Component]] = {}
        for comp in cal.subcomponents:
            if comp.name != "VEVENT":
                continue
            if not event_overlaps_range(comp, range_start, range_end, self.config.timezone):
                continue
            uid = str(comp.get("UID") or fallback_uid(comp, self.config.fallback_uid_strategy, source_url))
            grouped.setdefault(uid, []).append(comp)

        bundles: Dict[str, str] = {}
        for uid, events in grouped.items():
            bundle = build_bundle(uid, events, vtimezones)
            bundles[uid] = bundle.raw_ical
        return bundles

    def fetch(self) -> SourceFetchResult:
        session = requests.Session()
        if self.config.ics_basic_user and self.config.ics_basic_password:
            session.auth = (self.config.ics_basic_user, self.config.ics_basic_password)

        headers_base = dict(self.config.ics_headers)
        if self.config.ics_bearer_token:
            headers_base["Authorization"] = f"Bearer {self.config.ics_bearer_token}"

        all_bundles: Dict[str, str] = {}
        unchanged_all = True
        for url in self.config.ics_urls:
            headers = dict(headers_base)
            headers.update(self.state.source_headers(url))
            response = self._request_with_retry(session, url, headers)
            if response.status_code == 304:
                logger.info("ICS not modified", extra={"extra": {"url": url}})
                continue
            response.raise_for_status()
            unchanged_all = False
            self.state.update_source_cache(url, response.headers.get("ETag"), response.headers.get("Last-Modified"))
            parsed = self._parse(response.text, url)
            all_bundles.update(parsed)

        if unchanged_all:
            return SourceFetchResult(bundles={}, unchanged=True)

        with_fingerprints = {
            uid: fingerprint_calendar_event_bundle(raw, self.config.timezone) + "\n" + raw for uid, raw in all_bundles.items()
        }
        return SourceFetchResult(bundles=with_fingerprints, unchanged=False)
