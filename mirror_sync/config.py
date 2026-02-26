from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class IcsSourceConfig:
    source_id: str
    url: str
    headers: Dict[str, str]
    basic_user: Optional[str]
    basic_password: Optional[str]
    bearer_token: Optional[str]


@dataclass(frozen=True)
class CalDAVClientConfig:
    client_id: str
    caldav_url: str
    username: str
    password: str


@dataclass(frozen=True)
class SyncJobConfig:
    job_id: str
    source_id: str
    client_id: str
    calendar_name: Optional[str]
    calendar_url: Optional[str]
    timezone: str
    range_past_days: int
    range_future_days: int
    fallback_uid_strategy: str


@dataclass(frozen=True)
class AppConfig:
    sources: Dict[str, IcsSourceConfig]
    clients: Dict[str, CalDAVClientConfig]
    jobs: Dict[str, SyncJobConfig]
    interval_seconds: int
    daemon_mode: bool
    state_file: Path
    request_timeout: int
    max_retries: int
    retry_base_seconds: float


def env_default(name: str, fallback: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value not in (None, "") else fallback


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_sources(path: Path) -> Dict[str, IcsSourceConfig]:
    raw = _load_json(path)
    out: Dict[str, IcsSourceConfig] = {}
    for item in raw.get("sources", []):
        source_id = item["id"]
        auth = item.get("auth", {})
        out[source_id] = IcsSourceConfig(
            source_id=source_id,
            url=item["url"],
            headers=item.get("headers", {}),
            basic_user=auth.get("username") if auth.get("type") == "basic" else None,
            basic_password=auth.get("password") if auth.get("type") == "basic" else None,
            bearer_token=auth.get("token") if auth.get("type") == "bearer" else None,
        )
    if not out:
        raise ValueError("No sources found in sources config")
    return out


def _parse_clients(path: Path) -> Dict[str, CalDAVClientConfig]:
    raw = _load_json(path)
    out: Dict[str, CalDAVClientConfig] = {}
    for item in raw.get("clients", []):
        client_id = item["id"]
        out[client_id] = CalDAVClientConfig(
            client_id=client_id,
            caldav_url=item["caldav_url"],
            username=item["username"],
            password=item["password"],
        )
    if not out:
        raise ValueError("No clients found in clients config")
    return out


def _parse_jobs(path: Path, sources: Dict[str, IcsSourceConfig], clients: Dict[str, CalDAVClientConfig]) -> Dict[str, SyncJobConfig]:
    raw = _load_json(path)
    jobs: Dict[str, SyncJobConfig] = {}
    for item in raw.get("jobs", []):
        job_id = item["id"]
        source_id = item["source_id"]
        client_id = item["client_id"]
        if source_id not in sources:
            raise ValueError(f"Job {job_id}: unknown source_id {source_id}")
        if client_id not in clients:
            raise ValueError(f"Job {job_id}: unknown client_id {client_id}")
        calendar_name = item.get("calendar_name")
        calendar_url = item.get("calendar_url")
        if not calendar_name and not calendar_url:
            raise ValueError(f"Job {job_id}: calendar_name or calendar_url required")
        jobs[job_id] = SyncJobConfig(
            job_id=job_id,
            source_id=source_id,
            client_id=client_id,
            calendar_name=calendar_name,
            calendar_url=calendar_url,
            timezone=item.get("timezone", "Europe/London"),
            range_past_days=int(item.get("range_past_days", 30)),
            range_future_days=int(item.get("range_future_days", 365)),
            fallback_uid_strategy=item.get("fallback_uid_strategy", "sha256"),
        )
    if not jobs:
        raise ValueError("No jobs found in jobs config")
    return jobs


def build_config() -> AppConfig:
    parser = argparse.ArgumentParser(description="ICS -> CalDAV mirror sync")
    parser.add_argument("--sources-config", default=env_default("SOURCES_CONFIG", "sources.json"))
    parser.add_argument("--clients-config", default=env_default("CLIENTS_CONFIG", "clients.json"))
    parser.add_argument("--jobs-config", default=env_default("JOBS_CONFIG", "jobs.json"))
    parser.add_argument("--interval-seconds", type=int, default=int(env_default("SYNC_INTERVAL_SECONDS", "600")))
    parser.add_argument("--daemon", action="store_true", default=env_default("SYNC_DAEMON", "false").lower() == "true")
    parser.add_argument("--state-file", default=env_default("SYNC_STATE_FILE", ".mirror_sync_state.json"))
    parser.add_argument("--request-timeout", type=int, default=int(env_default("REQUEST_TIMEOUT", "30")))
    parser.add_argument("--max-retries", type=int, default=int(env_default("MAX_RETRIES", "5")))
    parser.add_argument("--retry-base-seconds", type=float, default=float(env_default("RETRY_BASE_SECONDS", "1.5")))
    args = parser.parse_args()

    sources = _parse_sources(Path(args.sources_config))
    clients = _parse_clients(Path(args.clients_config))
    jobs = _parse_jobs(Path(args.jobs_config), sources, clients)

    return AppConfig(
        sources=sources,
        clients=clients,
        jobs=jobs,
        interval_seconds=args.interval_seconds,
        daemon_mode=args.daemon,
        state_file=Path(args.state_file),
        request_timeout=args.request_timeout,
        max_retries=args.max_retries,
        retry_base_seconds=args.retry_base_seconds,
    )
