from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import caldav
from caldav.objects import CalendarObjectResource
from icalendar import Calendar

from .config import SyncConfig
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
    def __init__(self, config: SyncConfig):
        self.config = config
        self.client = caldav.DAVClient(
            url=config.caldav_url,
            username=config.caldav_username,
            password=config.caldav_password,
        )
        self.calendar = self._resolve_calendar()

    def _retry(self, func, op: str):
        last_exc = None
        for attempt in range(self.config.max_retries):
            try:
                return func()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait_s = self.config.retry_base_seconds * (2 ** attempt)
                logger.warning("CalDAV operation failed, retrying", extra={"extra": {"op": op, "attempt": attempt + 1, "wait_s": wait_s}})
                time.sleep(wait_s)
        raise RuntimeError(f"CalDAV operation {op} failed: {last_exc}")

    def _resolve_calendar(self):
        principal = self.client.principal()
        if self.config.calendar_url:
            return caldav.Calendar(client=self.client, url=self.config.calendar_url)
        calendars = principal.calendars()
        for cal in calendars:
            if cal.name == self.config.calendar_name:
                return cal
        raise ValueError(f"Calendar not found: {self.config.calendar_name}")

    def list_server_objects(self) -> Dict[str, ServerObject]:
        start, end = compute_timerange(self.config.timezone, self.config.range_past_days, self.config.range_future_days)
        events = self._retry(lambda: self.calendar.search(start=start, end=end, event=True, expand=False), "search")
        result: Dict[str, ServerObject] = {}
        for item in events:
            raw = item.data
            cal = Calendar.from_ical(raw)
            uids: List[str] = []
            for comp in cal.subcomponents:
                if comp.name != "VEVENT":
                    continue
                uid = str(comp.get("UID") or fallback_uid(comp, self.config.fallback_uid_strategy, item.url))
                if uid not in uids:
                    uids.append(uid)
            if len(uids) != 1:
                logger.warning("Skipping server object with non-single UID", extra={"extra": {"href": item.url, "uids": uids}})
                continue
            uid = uids[0]
            result[uid] = ServerObject(
                uid=uid,
                href=item.url,
                raw=raw,
                fingerprint=fingerprint_calendar_event_bundle(raw, self.config.timezone),
                object_ref=item,
            )
        return result

    def create_or_update(self, raw_ical: str, existing: Optional[ServerObject]) -> None:
        if existing is None:
            self._retry(lambda: self.calendar.save_event(raw_ical), "save_event")
        else:
            self._retry(lambda: existing.object_ref.save(data=raw_ical), "update_event")

    def delete(self, obj: ServerObject) -> None:
        self._retry(lambda: obj.object_ref.delete(), "delete_event")
