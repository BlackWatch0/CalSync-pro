from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SyncConfig:
    sync_name: str
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


@dataclass(frozen=True)
class AppConfig:
    syncs: List[SyncConfig]
    daemon_mode: bool
    interval_seconds: int
    debug_level: str


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


def _build_sync_config_from_json(item: Dict[str, object], defaults: Dict[str, object], name: str) -> SyncConfig:
    merged = dict(defaults)
    merged.update(item)

    ics_urls_raw = merged.get("ics_urls", [])
    if not isinstance(ics_urls_raw, list):
        raise ValueError(f"sync '{name}': ics_urls must be a list")
    ics_urls = [str(u).strip() for u in ics_urls_raw if str(u).strip()]
    if not ics_urls:
        raise ValueError(f"sync '{name}': no valid ics_urls provided")

    ics_headers = merged.get("ics_headers", {})
    if not isinstance(ics_headers, dict):
        raise ValueError(f"sync '{name}': ics_headers must be an object")

    if not merged.get("caldav_url") or not merged.get("caldav_username") or not merged.get("caldav_password"):
        raise ValueError(f"sync '{name}': caldav_url/caldav_username/caldav_password are required")

    if not merged.get("calendar_name") and not merged.get("calendar_url"):
        raise ValueError(f"sync '{name}': either calendar_name or calendar_url must be set")

    state_file = Path(str(merged.get("state_file", f".mirror_sync_state_{name}.json")))

    return SyncConfig(
        sync_name=name,
        ics_urls=ics_urls,
        ics_headers={str(k): str(v) for k, v in ics_headers.items()},
        ics_basic_user=merged.get("ics_basic_user"),
        ics_basic_password=merged.get("ics_basic_password"),
        ics_bearer_token=merged.get("ics_bearer_token"),
        caldav_url=str(merged.get("caldav_url", "")),
        caldav_username=str(merged.get("caldav_username", "")),
        caldav_password=str(merged.get("caldav_password", "")),
        calendar_name=merged.get("calendar_name"),
        calendar_url=merged.get("calendar_url"),
        interval_seconds=int(merged.get("interval_seconds", 600)),
        daemon_mode=bool(merged.get("daemon_mode", False)),
        state_file=state_file,
        timezone=str(merged.get("timezone", "Europe/London")),
        range_past_days=int(merged.get("range_past_days", 30)),
        range_future_days=int(merged.get("range_future_days", 365)),
        fallback_uid_strategy=str(merged.get("fallback_uid_strategy", "sha256")),
        request_timeout=int(merged.get("request_timeout", 30)),
        max_retries=int(merged.get("max_retries", 5)),
        retry_base_seconds=float(merged.get("retry_base_seconds", 1.5)),
    )


def _load_json_syncs(config_path: Path, debug_level: Optional[str] = None) -> AppConfig:
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    sources_path = config_path.parent / str(payload.get("sources_file", "sources.json"))
    clients_path = config_path.parent / str(payload.get("clients_file", "clients.json"))
    mappings = payload.get("mappings", [])
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("json config: mappings must be a non-empty array")

    sources_payload = json.loads(sources_path.read_text(encoding="utf-8"))
    clients_payload = json.loads(clients_path.read_text(encoding="utf-8"))
    sources = sources_payload.get("sources", {})
    clients = clients_payload.get("clients", {})

    global_defaults = payload.get("defaults", {})
    if not isinstance(global_defaults, dict):
        raise ValueError("json config: defaults must be an object")

    syncs: List[SyncConfig] = []
    for idx, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            raise ValueError(f"json config: mappings[{idx}] must be an object")
        source_name = mapping.get("source")
        client_name = mapping.get("client")
        if source_name not in sources:
            raise ValueError(f"json config: source '{source_name}' not found")
        if client_name not in clients:
            raise ValueError(f"json config: client '{client_name}' not found")

        sync_name = str(mapping.get("name") or f"{source_name}_to_{client_name}")

        merged = dict(global_defaults)
        merged.update(sources[source_name])
        merged.update(clients[client_name])
        merged.update(mapping.get("overrides", {}))
        merged.setdefault("state_file", f".mirror_sync_state_{sync_name}.json")

        syncs.append(_build_sync_config_from_json(merged, {}, sync_name))

    daemon_mode = bool(payload.get("daemon_mode", False))
    interval_seconds = int(payload.get("interval_seconds", 600))
    configured_level = str(payload.get("debug_level", "INFO"))
    return AppConfig(
        syncs=syncs,
        daemon_mode=daemon_mode,
        interval_seconds=interval_seconds,
        debug_level=(debug_level or configured_level).upper(),
    )


def build_config() -> AppConfig:
    parser = argparse.ArgumentParser(description="ICS -> CalDAV mirror sync")
    parser.add_argument("--json-config", default=env_default("SYNC_JSON_CONFIG"))
    parser.add_argument("--ics-urls", default=env_default("ICS_URLS"))
    parser.add_argument("--ics-headers", default=env_default("ICS_HEADERS", ""))
    parser.add_argument("--ics-basic-user", default=env_default("ICS_BASIC_USER"))
    parser.add_argument("--ics-basic-password", default=env_default("ICS_BASIC_PASSWORD"))
    parser.add_argument("--ics-bearer-token", default=env_default("ICS_BEARER_TOKEN"))
    parser.add_argument("--caldav-url", default=env_default("CALDAV_URL"))
    parser.add_argument("--caldav-username", default=env_default("CALDAV_USERNAME"))
    parser.add_argument("--caldav-password", default=env_default("CALDAV_PASSWORD"))
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
    parser.add_argument("--debug-level", default=env_default("DEBUG_LEVEL"))

    args = parser.parse_args()

    debug_level = str(args.debug_level or "INFO").upper()

    if args.json_config:
        return _load_json_syncs(Path(args.json_config), debug_level)

    if not args.ics_urls:
        raise ValueError("--ics-urls or SYNC_JSON_CONFIG must be set")
    if not args.caldav_url or not args.caldav_username or not args.caldav_password:
        raise ValueError("CalDAV credentials are required")

    if not args.calendar_name and not args.calendar_url:
        raise ValueError("Either --calendar-name or --calendar-url must be set")

    ics_urls = [u.strip() for u in args.ics_urls.split(",") if u.strip()]
    if not ics_urls:
        raise ValueError("No valid ICS URLs provided")

    sync = SyncConfig(
        sync_name="default",
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
    return AppConfig(
        syncs=[sync],
        daemon_mode=args.daemon,
        interval_seconds=args.interval_seconds,
        debug_level=debug_level,
    )
