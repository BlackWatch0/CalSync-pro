from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from dateutil import tz
from icalendar import Calendar
from icalendar.cal import Component


@dataclass
class SourceEventBundle:
    uid: str
    raw_ical: str
    fingerprint: str


def _serialize_primitive(value: object, default_tz: tz.tzfile) -> str:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz)
        return dt.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ",".join(_serialize_primitive(v, default_tz) for v in value) + "]"
    return str(value)


def fingerprint_calendar_event_bundle(raw_ical: str, default_timezone: str) -> str:
    cal = Calendar.from_ical(raw_ical)
    relevant: List[str] = []
    default_tz = tz.gettz(default_timezone)
    for comp in cal.subcomponents:
        if comp.name != "VEVENT":
            continue
        props = []
        for key, value in sorted(comp.property_items(), key=lambda x: x[0]):
            if key in ("DTSTAMP", "CREATED", "LAST-MODIFIED", "SEQUENCE"):
                continue
            props.append(f"{key}={_serialize_primitive(value, default_tz)}")
        relevant.append("|".join(props))
    normalized = "\n".join(sorted(relevant))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fallback_uid(component: Component, strategy: str, source_url: str) -> str:
    if strategy != "sha256":
        raise ValueError(f"Unsupported strategy: {strategy}")
    dtstart = component.get("DTSTART")
    summary = component.get("SUMMARY", "")
    recurid = component.get("RECURRENCE-ID", "")
    seed = f"{source_url}|{summary}|{dtstart}|{recurid}|{component.to_ical().decode('utf-8', errors='ignore')}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_bundle(uid: str, events: List[Component], vtimezones: List[Component]) -> SourceEventBundle:
    cal = Calendar()
    cal.add("PRODID", "-//CalSync Mirror//EN")
    cal.add("VERSION", "2.0")
    for tz_comp in vtimezones:
        cal.add_component(tz_comp)
    for event in events:
        cal.add_component(event.copy())
    raw_ical = cal.to_ical().decode("utf-8")
    return SourceEventBundle(uid=uid, raw_ical=raw_ical, fingerprint="")


def compute_timerange(default_timezone: str, past_days: int, future_days: int) -> Tuple[datetime, datetime]:
    zone = tz.gettz(default_timezone)
    now = datetime.now(zone)
    start = datetime.combine((now - timedelta(days=past_days)).date(), time.min, zone)
    end = datetime.combine((now + timedelta(days=future_days)).date(), time.max, zone)
    return start, end


def event_overlaps_range(event: Component, range_start: datetime, range_end: datetime, default_timezone: str) -> bool:
    default_tz = tz.gettz(default_timezone)
    dtstart = event.decoded("DTSTART", None)
    if dtstart is None:
        return False

    if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
        ev_start = datetime.combine(dtstart, time.min, default_tz)
    else:
        ev_start = dtstart if dtstart.tzinfo else dtstart.replace(tzinfo=default_tz)

    dtend = event.decoded("DTEND", None)
    if dtend is None:
        ev_end = ev_start
    elif isinstance(dtend, date) and not isinstance(dtend, datetime):
        ev_end = datetime.combine(dtend, time.max, default_tz)
    else:
        ev_end = dtend if dtend.tzinfo else dtend.replace(tzinfo=default_tz)

    return ev_end >= range_start and ev_start <= range_end
