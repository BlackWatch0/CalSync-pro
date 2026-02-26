# CalSync-pro (ICS -> CalDAV Mirror Sync)

> 高风险提示：本工具是“镜像同步”模型，ICS 为唯一真源。目标日历中不在 ICS 内的事件会被删除。请使用专用目标日历，不要混用人工维护日历。

## 默认部署方式（Docker Compose）

本项目默认使用 **Docker + 配置文件映射** 运行。

### 1. 目录放置（宿主机）

在项目根目录准备以下结构：

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

- `config/`：只放同步配置与凭据映射。
- `state/`：持久化运行状态（ETag、Last-Modified 等）。

### 2. 路径映射（容器内）

`docker-compose.yml` 默认映射：

- `./config -> /app/config`（只读）
- `./state -> /app/state`

容器默认命令：

```bash
python sync.py --json-config /app/config/sync-config.json
```

### 3. 一键启动

```bash
mkdir -p state
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

## 配置文件说明（重点）

### sync-config.json（总入口）

- 负责声明：
  - `sources_file`：ICS 源定义文件名
  - `clients_file`：CalDAV 客户端定义文件名
  - `daemon_mode`、`interval_seconds`
  - `debug_level`
  - `mappings`：source 与 client 的映射关系

默认示例：`config/sync-config.json`

### sources.json（只放 ICS 源）

- 每个 source 可以配置：
  - `ics_urls`（支持多个）
  - `ics_headers`
  - `ics_basic_user` / `ics_basic_password`
  - `ics_bearer_token`

默认示例：`config/sources.json`

### clients.json（只放 CalDAV 连接）

- 每个 client 配置：
  - `caldav_url`
  - `caldav_username`
  - `caldav_password`
  - `calendar_name` 或 `calendar_url`（二选一）

默认示例：`config/clients.json`

## DebugLevel 运行信息

支持 `DEBUG_LEVEL`（或 json 内 `debug_level`）控制日志等级：

- `DEBUG`
- `INFO`（默认）
- `WARNING`
- `ERROR`
- `CRITICAL`

Docker Compose 默认：

```yaml
environment:
  - DEBUG_LEVEL=INFO
```

程序启动时会输出运行参数摘要：

- 当前 `debug_level`
- `daemon_mode`
- `interval_seconds`
- `sync_count`
- 每条 mapping 的 `sync`、`source_count`、`calendar_name/calendar_url`、`state_file`

## 配置优先级

1. 命令行参数 `--debug-level`
2. 环境变量 `DEBUG_LEVEL`
3. `sync-config.json` 内 `debug_level`
4. 默认 `INFO`

## 本地 Python 运行（可选）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python sync.py --json-config ./config/sync-config.json
```

## 重要变更说明

- 默认部署方式已改为 Docker Compose + `config/` 映射。
- 不再写入或依赖 `X-CALSYNC-MIRROR:TRUE` 字段。
- 新增 `DebugLevel` 控制和启动阶段运行摘要日志。

## 项目结构

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
