from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SyncConfig:
    ics_urls: List[str]
    ics_headers: Dict[str, str]
    ics_basic_user: Optional[str]
    ics_basic_password: Optional[str]
    ics_bearer_token: Optional[str]
    caldav_url: str
    caldav_username: str
    caldav_password: str
    calendar_name: Optional[str]
    calendar_url: Optional[str]
    interval_seconds: int
    daemon_mode: bool
    state_file: Path
    timezone: str
    range_past_days: int
    range_future_days: int
    fallback_uid_strategy: str
    request_timeout: int
    max_retries: int
    retry_base_seconds: float


def parse_headers(raw: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not raw:
        return headers
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Invalid header format: {part}")
        key, value = part.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def env_default(name: str, fallback: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else fallback


def build_config() -> SyncConfig:
    parser = argparse.ArgumentParser(description="ICS -> CalDAV mirror sync")
    parser.add_argument("--ics-urls", default=env_default("ICS_URLS"), required=env_default("ICS_URLS") is None)
    parser.add_argument("--ics-headers", default=env_default("ICS_HEADERS", ""))
    parser.add_argument("--ics-basic-user", default=env_default("ICS_BASIC_USER"))
    parser.add_argument("--ics-basic-password", default=env_default("ICS_BASIC_PASSWORD"))
    parser.add_argument("--ics-bearer-token", default=env_default("ICS_BEARER_TOKEN"))
    parser.add_argument("--caldav-url", default=env_default("CALDAV_URL"), required=env_default("CALDAV_URL") is None)
    parser.add_argument("--caldav-username", default=env_default("CALDAV_USERNAME"), required=env_default("CALDAV_USERNAME") is None)
    parser.add_argument("--caldav-password", default=env_default("CALDAV_PASSWORD"), required=env_default("CALDAV_PASSWORD") is None)
    parser.add_argument("--calendar-name", default=env_default("CALENDAR_NAME"))
    parser.add_argument("--calendar-url", default=env_default("CALENDAR_URL"))
    parser.add_argument("--interval-seconds", type=int, default=int(env_default("SYNC_INTERVAL_SECONDS", "600")))
    parser.add_argument("--daemon", action="store_true", default=env_default("SYNC_DAEMON", "false").lower() == "true")
    parser.add_argument("--state-file", default=env_default("SYNC_STATE_FILE", ".mirror_sync_state.json"))
    parser.add_argument("--timezone", default=env_default("SYNC_TIMEZONE", "Europe/London"))
    parser.add_argument("--range-past-days", type=int, default=int(env_default("SYNC_RANGE_PAST_DAYS", "30")))
    parser.add_argument("--range-future-days", type=int, default=int(env_default("SYNC_RANGE_FUTURE_DAYS", "365")))
    parser.add_argument("--fallback-uid-strategy", default=env_default("FALLBACK_UID_STRATEGY", "sha256"), choices=["sha256"])
    parser.add_argument("--request-timeout", type=int, default=int(env_default("REQUEST_TIMEOUT", "30")))
    parser.add_argument("--max-retries", type=int, default=int(env_default("MAX_RETRIES", "5")))
    parser.add_argument("--retry-base-seconds", type=float, default=float(env_default("RETRY_BASE_SECONDS", "1.5")))

    args = parser.parse_args()

    if not args.calendar_name and not args.calendar_url:
        raise ValueError("Either --calendar-name or --calendar-url must be set")

    ics_urls = [u.strip() for u in args.ics_urls.split(",") if u.strip()]
    if not ics_urls:
        raise ValueError("No valid ICS URLs provided")

    return SyncConfig(
        ics_urls=ics_urls,
        ics_headers=parse_headers(args.ics_headers),
        ics_basic_user=args.ics_basic_user,
        ics_basic_password=args.ics_basic_password,
        ics_bearer_token=args.ics_bearer_token,
        caldav_url=args.caldav_url,
        caldav_username=args.caldav_username,
        caldav_password=args.caldav_password,
        calendar_name=args.calendar_name,
        calendar_url=args.calendar_url,
        interval_seconds=args.interval_seconds,
        daemon_mode=args.daemon,
        state_file=Path(args.state_file),
        timezone=args.timezone,
        range_past_days=args.range_past_days,
        range_future_days=args.range_future_days,
        fallback_uid_strategy=args.fallback_uid_strategy,
        request_timeout=args.request_timeout,
        max_retries=args.max_retries,
        retry_base_seconds=args.retry_base_seconds,
    )
