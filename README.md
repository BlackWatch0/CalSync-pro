# ICS → CalDAV 完全镜像同步器（Mirror Sync）

> ⚠️ **高风险删除提示**：本工具默认“以 ICS 为唯一真源（Source of Truth）”，会删除目标日历中 ICS 不存在的事件。请务必使用**专用目标日历**，避免误删业务日历数据。

## 1. 简要设计与数据流

1. 拉取一个或多个 ICS URL（支持 Header / Basic / Bearer）。
2. 使用 ETag / If-Modified-Since 做条件请求；若所有源均 `304 Not Modified`，则跳过同步。
3. 解析 ICS：按 `UID` 聚合 VEVENT（包含 `RECURRENCE-ID` 例外实例），同时保留 `VTIMEZONE`。
4. 查询 CalDAV 目标日历（按配置 time-range）。
5. 做镜像比对（幂等）：
   - ICS 有、服务器无 → 创建
   - 双方都有且内容变化 → 更新
   - 服务器有、ICS 无 → 删除
6. 输出结构化统计日志（新增/更新/删除/跳过/失败/耗时）。

## 2. 循环与例外处理说明（RRULE/RDATE/EXDATE/RECURRENCE-ID）

- 本项目**不展开实例**，而是以 UID 为单位镜像“原始事件组件集合”。
- 同一 UID 下会保留：
  - 主事件（可含 `RRULE`、`RDATE`、`EXDATE`）
  - 所有 `RECURRENCE-ID` 例外事件
- 这样可最大限度避免实例级重算导致的重复、错位、DST 偏差。
- 同步时尽量原样保留 ICS 属性，并附加 `X-CALSYNC-MIRROR:TRUE` 标记用于可审计性。

## 3. 时区处理

- 默认时区：`Europe/London`（可配置）。
- 对比时：
  - 保留 ICS 的 `TZID/VTIMEZONE`
  - 浮动时间（无 tzinfo）按配置默认时区解释
  - `DATE` 全日事件按日期边界处理
  - 夏令时由 `VTIMEZONE + TZID` 与时区库共同处理

## 4. 幂等策略

- 主键优先 `UID`。
- 若无 UID，使用可配置 fallback（默认 `sha256`）基于关键字段和原始组件内容生成稳定哈希。
- 指纹比较时忽略 `DTSTAMP/CREATED/LAST-MODIFIED/SEQUENCE` 等噪声字段，内容未变则不 PUT。

## 5. 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 6. 运行

### 6.1 one-shot

```bash
python sync.py \
  --ics-urls "https://example.com/a.ics,https://example.com/b.ics" \
  --ics-headers "User-Agent:CalSync-Mirror/1.0;X-Env:prod" \
  --ics-bearer-token "YOUR_TOKEN" \
  --caldav-url "https://caldav.example.com" \
  --caldav-username "alice" \
  --caldav-password "secret" \
  --calendar-name "Mirror-Calendar"
```

### 6.2 daemon 模式

```bash
python sync.py \
  --daemon \
  --interval-seconds 600 \
  --ics-urls "https://example.com/a.ics" \
  --caldav-url "https://caldav.example.com" \
  --caldav-username "alice" \
  --caldav-password "secret" \
  --calendar-url "https://caldav.example.com/calendars/alice/mirror/"
```

## 7. 环境变量示例

```bash
export ICS_URLS="https://example.com/a.ics,https://example.com/b.ics"
export ICS_HEADERS="User-Agent:CalSync-Mirror/1.0"
export ICS_BASIC_USER="feed_user"
export ICS_BASIC_PASSWORD="feed_pass"
# 或 Bearer
export ICS_BEARER_TOKEN="token123"

export CALDAV_URL="https://caldav.example.com"
export CALDAV_USERNAME="alice"
export CALDAV_PASSWORD="secret"
export CALENDAR_NAME="Mirror-Calendar"
# 或 CALENDAR_URL

export SYNC_DAEMON="true"
export SYNC_INTERVAL_SECONDS="600"
export SYNC_STATE_FILE=".mirror_sync_state.json"
export SYNC_TIMEZONE="Europe/London"
export SYNC_RANGE_PAST_DAYS="30"
export SYNC_RANGE_FUTURE_DAYS="365"
export MAX_RETRIES="5"
export RETRY_BASE_SECONDS="1.5"
export REQUEST_TIMEOUT="30"
```

## 8. 常见问题（FAQ）

### Q1：为什么会删除服务器事件？
因为是“完全镜像”模式。ICS 没有的 UID 会被视作应删除。建议专用日历隔离风险。

### Q2：服务器手工修改为什么会被覆盖？
因为 ICS 是唯一真源。下一轮同步会按 ICS 内容回写。

### Q3：如何降低全量扫描压力？
通过 `SYNC_RANGE_PAST_DAYS/SYNC_RANGE_FUTURE_DAYS` 限制查询窗口，CalDAV 端使用 time-range 搜索。

### Q4：网络抖动会退出吗？
不会。ICS 拉取、CalDAV 操作均有指数退避重试；daemon 轮次异常也会继续下一轮。

## 9. 项目结构

```
.
├── mirror_sync/
│   ├── __init__.py
│   ├── caldav_client.py
│   ├── config.py
│   ├── ics_source.py
│   ├── logging_utils.py
│   ├── normalizer.py
│   └── sync_engine.py
├── requirements.txt
├── sync.py
├── .gitignore
└── README.md
```

## 10. 安全建议

- 使用独立目标日历，不与人工编辑日历混用。
- 使用最小权限账号（仅该日历可写）。
- 保留 `X-CALSYNC-MIRROR:TRUE` 标记，便于审计来源。
- 生产环境建议先 dry-run（可通过只读账号 + 日志比对方式演练）。
