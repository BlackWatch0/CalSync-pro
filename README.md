# CalSync-pro (ICS -> CalDAV Mirror Sync)

[中文](README.md) | [English](README.en.md)

CalSync-pro 是一个面向生产场景的日历镜像同步工具：把一个或多个 ICS 源作为唯一真源，持续同步到 CalDAV 日历。

它适合以下场景：
- 团队统一维护 ICS 日程，需要自动分发到个人或共享 CalDAV 日历。
- 外部系统只提供 ICS 订阅，但你希望在 CalDAV 客户端（如 Apple Calendar、Thunderbird、DAVx5）中原生管理查看。
- 需要长期运行、可观测、可配置热更新的同步服务。

## 核心功能

- ICS -> CalDAV 镜像同步：自动创建、更新、删除目标日历事件。
- 多源聚合：单个同步任务可配置多个 `ics_urls`。
- 多任务映射：通过 `mappings` 绑定不同 source/client。
- 每任务独立同步周期：
  - 全局 `interval_seconds` 作为默认值。
  - 每个 mapping 可在 `overrides.interval_seconds` 覆盖。
- 配置热更新：`daemon_mode=true` 时，修改以下文件会自动重载：
  - `sync-config.json`
  - `sources.json`
  - `clients.json`
- 稳定性机制：请求超时、重试、指数退避。
- 运行日志分级：支持 `DEBUG/INFO/WARNING/ERROR/CRITICAL`。

## 同步模型说明

这是“镜像同步”模型：目标 CalDAV 日历会对齐到当前 ICS 实际内容。

高风险提示：目标日历中不在 ICS 里的事件会被删除。
建议使用专用目标日历，不要与人工维护日历混用。

## 目录结构

```text
.
├── mirror_sync/
│   ├── caldav_client.py
│   ├── config.py
│   ├── ics_source.py
│   ├── logging_utils.py
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

## 快速开始（Docker Compose）

### 1. 准备目录

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

### 2. 默认挂载关系

- `./config -> /app/config`（只读）
- `./state -> /app/state`

容器默认启动命令：

```bash
python sync.py --json-config /app/config/sync-config.json
```

### 3. 启动

```bash
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

## 配置说明

### 1) sync-config.json（总入口）

关键字段：
- `sources_file`
- `clients_file`
- `daemon_mode`
- `interval_seconds`（全局默认周期）
- `debug_level`
- `defaults`
- `mappings`

周期规则：
- 若 mapping 未设置 `overrides.interval_seconds`，使用全局 `interval_seconds`。
- 若 mapping 设置了 `overrides.interval_seconds`，该任务按独立周期调度。

### 2) sources.json（仅 ICS 源）

每个 source 可配置：
- `ics_urls`
- `ics_headers`
- `ics_basic_user` / `ics_basic_password`
- `ics_bearer_token`

### 3) clients.json（仅 CalDAV 客户端）

每个 client 可配置：
- `caldav_url`
- `caldav_username`
- `caldav_password`
- `calendar_name` 或 `calendar_url`（二选一）

## 配置热更新行为

在 `daemon_mode=true` 下：
- 程序会监听 `sync-config.json`、`sources.json`、`clients.json` 变更并自动重载。
- 重载成功后，新任务配置和新周期立即生效。
- 重载失败会记录错误日志，进程继续运行。

## License

本项目遵循仓库中的 `LICENSE`。
