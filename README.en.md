# CalSync-pro (ICS -> CalDAV Mirror Sync)

[中文](README.md) | [English](README.en.md)

CalSync-pro is a production-ready calendar mirror sync service. It treats one or more ICS feeds as the single source of truth and continuously syncs them into CalDAV calendars.

Typical use cases:
- A team manages schedules in ICS and wants automatic delivery to personal/shared CalDAV calendars.
- An upstream system only provides ICS subscriptions, but you want native CalDAV usage in clients like Apple Calendar, Thunderbird, or DAVx5.
- You need a long-running, observable sync service with hot-reloadable configuration.

## Features

- ICS -> CalDAV mirror sync: create, update, and delete events automatically.
- Multi-source aggregation: one sync task can read multiple `ics_urls`.
- Multi-mapping architecture: connect different source/client pairs using `mappings`.
- Per-task sync interval:
  - Global `interval_seconds` is the default.
  - `overrides.interval_seconds` can override interval for each mapping.
- Config hot reload in daemon mode (`daemon_mode=true`):
  - `sync-config.json`
  - `sources.json`
  - `clients.json`
- Reliability controls: timeout, retry, exponential backoff.
- Structured logging with levels: `DEBUG/INFO/WARNING/ERROR/CRITICAL`.

## Sync Model

This is a mirror model: target CalDAV calendars are aligned to current ICS content.

Important: events that are not present in ICS may be removed from target calendars.
Use dedicated target calendars instead of mixing with manually managed personal calendars.

## Project Structure

```text
.
├── mirror_sync/
│   ├── caldav_client.py
│   ├── config.py
│   ├── ics_source.py
│   ├── logging_utils.py
│   ├── normalizer.py
│   └── sync_engine.py
├── config/
│   ├── sync-config.json
│   ├── sources.json
│   └── clients.json
├── state/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── sync.py
```

## Quick Start (Docker Compose)

### 1. Prepare folders

```text
.
├── config/
│   ├── sync-config.json
│   ├── sources.json
│   └── clients.json
├── state/
├── docker-compose.yml
└── Dockerfile
```

### 2. Default mounts

- `./config -> /app/config` (read-only)
- `./state -> /app/state`

Default container command:

```bash
python sync.py --json-config /app/config/sync-config.json
```

### 3. Start

```bash
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## Configuration

### 1) `sync-config.json` (entry file)

Responsibilities:
- Defines global behavior.
- Defines mapping relationships between sources and clients.

Key fields:
- `sources_file`: ICS source config filename.
- `clients_file`: CalDAV client config filename.
- `daemon_mode`: run as daemon or one-shot.
- `interval_seconds`: global default interval in seconds.
- `debug_level`: log level.
- `defaults`: default parameters for mappings.
- `mappings`: source/client pairs with optional overrides.

Example:

```json
{
  "sources_file": "sources.json",
  "clients_file": "clients.json",
  "daemon_mode": true,
  "interval_seconds": 600,
  "debug_level": "INFO",
  "defaults": {
    "timezone": "Europe/London",
    "range_past_days": 30,
    "range_future_days": 365,
    "request_timeout": 30,
    "max_retries": 5,
    "retry_base_seconds": 1.5
  },
  "mappings": [
    {
      "name": "main-sync",
      "source": "main_source",
      "client": "main_client",
      "overrides": {
        "interval_seconds": 300,
        "state_file": "/app/state/.mirror_sync_state_main.json"
      }
    }
  ]
}
```

Interval behavior:
- If `overrides.interval_seconds` is missing, the task uses global `interval_seconds`.
- If `overrides.interval_seconds` is set, the task runs on its own interval.

### 2) `sources.json` (ICS only)

Each source can define:
- `ics_urls` (multiple URLs supported)
- `ics_headers`
- `ics_basic_user` / `ics_basic_password`
- `ics_bearer_token`

### 3) `clients.json` (CalDAV only)

Each client can define:
- `caldav_url`
- `caldav_username`
- `caldav_password`
- `calendar_name` or `calendar_url` (one required)

## Hot Reload Behavior

When `daemon_mode=true`:
- The service watches config file changes and reloads automatically.
- New mappings and intervals take effect right after successful reload.
- If reload fails, an error is logged and the service continues with the current in-memory config.

## Runtime Logs

Startup summary includes:
- `debug_level`
- `daemon_mode`
- `interval_seconds`
- `hot_reload_enabled`
- `sync_count`
- For each mapping: `sync`, `source_count`, `calendar_name/calendar_url`, `state_file`, `interval_seconds`

## Debug Level Priority

Priority order for `debug_level`:
1. CLI `--debug-level`
2. Env var `DEBUG_LEVEL`
3. `sync-config.json` value
4. Default `INFO`

## Local Python Run (optional)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python sync.py --json-config ./config/sync-config.json
```

## FAQ

1. Why are events removed from target calendars?
Because this project uses a mirror model and aligns the target with ICS source-of-truth.

2. Do I need to restart after config changes?
Usually no in daemon mode. Config changes are hot reloaded.

3. I saw a `date_search` deprecation notice. What should I do?
The project has migrated to `calendar.search(...)`. Rebuild and restart to apply.

## License

This project is licensed under the repository `LICENSE` file.
