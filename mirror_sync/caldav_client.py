from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import caldav
from caldav.objects import CalendarObjectResource
from icalendar import Calendar

from .config import AppConfig, CalDAVClientConfig, SyncJobConfig
from .normalizer import compute_timerange, fallback_uid, fingerprint_calendar_event_bundle

logger = logging.getLogger(__name__)


@dataclass
class ServerObject:
    uid: str
    href: str
    raw: str
    fingerprint: str
    object_ref: CalendarObjectResource


class CalDAVMirror:
    def __init__(self, app_config: AppConfig, client_config: CalDAVClientConfig, job_config: SyncJobConfig):
        self.app_config = app_config
        self.client_config = client_config
        self.job_config = job_config
        self.client = caldav.DAVClient(
            url=client_config.caldav_url,
            username=client_config.username,
            password=client_config.password,
        )
        self.calendar = self._resolve_calendar()

    def _retry(self, func, op: str):
        last_exc = None
        for attempt in range(self.app_config.max_retries):
            try:
                return func()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait_s = self.app_config.retry_base_seconds * (2 ** attempt)
                logger.warning("CalDAV operation failed, retrying", extra={"extra": {"op": op, "job_id": self.job_config.job_id, "attempt": attempt + 1, "wait_s": wait_s}})
                time.sleep(wait_s)
        raise RuntimeError(f"CalDAV operation {op} failed: {last_exc}")

    def _resolve_calendar(self):
        principal = self.client.principal()
        if self.job_config.calendar_url:
            return caldav.Calendar(client=self.client, url=self.job_config.calendar_url)
        for cal in principal.calendars():
            if cal.name == self.job_config.calendar_name:
                return cal
        raise ValueError(f"Calendar not found: {self.job_config.calendar_name}")

    def list_server_objects(self) -> Dict[str, ServerObject]:
        start, end = compute_timerange(self.job_config.timezone, self.job_config.range_past_days, self.job_config.range_future_days)
        events = self._retry(lambda: self.calendar.date_search(start=start, end=end, expand=False), "date_search")
        result: Dict[str, ServerObject] = {}
        for item in events:
            raw = item.data
            cal = Calendar.from_ical(raw)
            uids: List[str] = []
            for comp in cal.subcomponents:
                if comp.name != "VEVENT":
                    continue
                uid = str(comp.get("UID") or fallback_uid(comp, self.job_config.fallback_uid_strategy, item.url))
                if uid not in uids:
                    uids.append(uid)
            if len(uids) != 1:
                logger.warning("Skipping server object with non-single UID", extra={"extra": {"href": item.url, "uids": uids, "job_id": self.job_config.job_id}})
                continue
            uid = uids[0]
            result[uid] = ServerObject(uid=uid, href=item.url, raw=raw, fingerprint=fingerprint_calendar_event_bundle(raw, self.job_config.timezone), object_ref=item)
        return result

    def create_or_update(self, raw_ical: str, existing: Optional[ServerObject]) -> None:
        if existing is None:
            self._retry(lambda: self.calendar.save_event(raw_ical), "save_event")
        else:
            self._retry(lambda: existing.object_ref.save(data=raw_ical), "update_event")

    def delete(self, obj: ServerObject) -> None:
        self._retry(lambda: obj.object_ref.delete(), "delete_event")
