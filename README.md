# ICS → CalDAV 完全镜像同步器（Mirror Sync）

> ⚠️ **高风险删除提示**：本工具默认“以 ICS 为唯一真源（Source of Truth）”，会删除目标日历中 ICS 不存在的事件。请务必使用**专用目标日历**。

## 1. 设计要点（简要）

- 支持多源、多客户端、多目标日历同步（一个进程可跑多个 job）。
- `sources.json` 仅存 ICS URL 与其拉取认证信息。
- `clients.json` 仅存 CalDAV 客户端凭据。
- `jobs.json` 只做映射：`source_id -> client_id -> calendar`。
- 幂等镜像：`UID` 主键（无 UID 时 fallback hash），仅内容变化才更新。
- 完全镜像：新增/更新/删除。

## 2. 配置文件拆分（你要的方式）

### 2.1 sources.json（只放 ICS 源）

```json
{
  "sources": [
    {
      "id": "team_a_feed",
      "url": "https://example.com/team-a.ics",
      "headers": {"User-Agent": "CalSync-Mirror/1.0"},
      "auth": {"type": "bearer", "token": "YOUR_ICS_TOKEN"}
    }
  ]
}
```

### 2.2 clients.json（只放 CalDAV 客户端凭据）

```json
{
  "clients": [
    {
      "id": "office365_main",
      "caldav_url": "https://caldav-a.example.com",
      "username": "alice",
      "password": "secret"
    }
  ]
}
```

### 2.3 jobs.json（映射关系）

```json
{
  "jobs": [
    {
      "id": "sync_team_a",
      "source_id": "team_a_feed",
      "client_id": "office365_main",
      "calendar_name": "Team-A-Mirror",
      "timezone": "Europe/London",
      "range_past_days": 30,
      "range_future_days": 365
    }
  ]
}
```

> 仓库里提供了完整可改的示例：`examples/sources.json`、`examples/clients.json`、`examples/jobs.json`。

## 3. 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. 运行

### 4.1 one-shot

```bash
python sync.py \
  --sources-config examples/sources.json \
  --clients-config examples/clients.json \
  --jobs-config examples/jobs.json
```

### 4.2 daemon

```bash
python sync.py \
  --daemon \
  --interval-seconds 600 \
  --sources-config examples/sources.json \
  --clients-config examples/clients.json \
  --jobs-config examples/jobs.json
```

## 5. Docker 打包与测试

### 构建镜像

```bash
docker build -t calsync-mirror:latest .
```

### one-shot 测试

```bash
docker run --rm \
  -v "$(pwd)/examples:/config:ro" \
  -v "$(pwd)/state:/data" \
  calsync-mirror:latest \
  --sources-config /config/sources.json \
  --clients-config /config/clients.json \
  --jobs-config /config/jobs.json \
  --state-file /data/.mirror_sync_state.json
```

### daemon 运行

```bash
docker run -d --name calsync-mirror \
  -v "$(pwd)/examples:/config:ro" \
  -v "$(pwd)/state:/data" \
  calsync-mirror:latest \
  --daemon \
  --interval-seconds 600 \
  --sources-config /config/sources.json \
  --clients-config /config/clients.json \
  --jobs-config /config/jobs.json \
  --state-file /data/.mirror_sync_state.json
```

## 6. 循环与时区说明

- 循环事件不做实例展开，按 UID 组包镜像（含 `RRULE/RDATE/EXDATE/RECURRENCE-ID`）。
- 保留 `VTIMEZONE/TZID`；浮动时间用 job 的 `timezone` 解释；全日事件按 DATE 边界处理。

## 7. 环境变量（可选）

- `SOURCES_CONFIG`（默认 `sources.json`）
- `CLIENTS_CONFIG`（默认 `clients.json`）
- `JOBS_CONFIG`（默认 `jobs.json`）
- `SYNC_DAEMON`、`SYNC_INTERVAL_SECONDS`、`SYNC_STATE_FILE`
- `REQUEST_TIMEOUT`、`MAX_RETRIES`、`RETRY_BASE_SECONDS`

## 8. FAQ（与你的问题相关）

### Q：如何实现“多个 ICS URL 分别同步到不同远程日历客户端”？
A：在 `sources.json` 放所有 ICS，在 `clients.json` 放所有客户端凭据，然后在 `jobs.json` 按 `source_id/client_id` 一一或一对多映射即可。
