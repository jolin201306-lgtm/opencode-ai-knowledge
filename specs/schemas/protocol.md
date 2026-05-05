# Agent 间数据传递协议 v1.0

## 概述
定义 Collector → Analyzer → Organizer 之间的文件传递协议，包括 JSON schema、状态码、错误类型和文件命名规范。

---

## 1. Raw 数据 Schema（Collector 输出）

文件路径：`knowledge/raw/{YYYYMMDD}_trending.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "source_agent": { "const": "collector" },
        "created_at": { "type": "string", "format": "date-time" },
        "version": { "type": "string", "pattern": "^v\\d+$" },
        "status": { "$ref": "#/$defs/status" },
        "error": { "$ref": "#/$defs/error" }
      },
      "required": ["source_agent", "created_at", "version", "status"]
    },
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/trending_item" }
    }
  },
  "required": ["meta", "items"],
  "$defs": {
    "trending_item": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "url": { "type": "string", "format": "uri" },
        "source": { "const": "github_trending" },
        "popularity": {
          "type": "object",
          "properties": {
            "stars": { "type": "integer", "minimum": 0 },
            "stars_today": { "type": "integer", "minimum": 0 }
          },
          "required": ["stars", "stars_today"]
        },
        "language": { "type": "string" },
        "description": { "type": "string" },
        "summary_zh": { "type": "string" }
      },
      "required": ["title", "url", "source", "popularity"]
    }
  }
}
```

---

## 2. Annotated 数据 Schema（Analyzer 输出）

文件路径：`knowledge/raw/{YYYYMMDD}_trending_annotated.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "source_agent": { "const": "analyzer" },
        "created_at": { "type": "string", "format": "date-time" },
        "version": { "type": "string", "pattern": "^v\\d+$" },
        "status": { "$ref": "#/$defs/status" },
        "error": { "$ref": "#/$defs/error" },
        "source_file": { "type": "string" }
      },
      "required": ["source_agent", "created_at", "version", "status", "source_file"]
    },
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/annotated_item" }
    }
  },
  "required": ["meta", "items"],
  "$defs": {
    "annotated_item": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "url": { "type": "string", "format": "uri" },
        "source": { "const": "github_trending" },
        "popularity": {
          "type": "object",
          "properties": {
            "stars": { "type": "integer", "minimum": 0 },
            "stars_today": { "type": "integer", "minimum": 0 }
          },
          "required": ["stars", "stars_today"]
        },
        "language": { "type": "string" },
        "description": { "type": "string" },
        "summary_zh": { "type": "string" },
        "tags": {
          "type": "object",
          "properties": {
            "tech_direction": {
              "type": "array",
              "items": {
                "type": "string",
                "enum": [
                  "LLM", "Agent", "RAG", "CV", "NLP",
                  "Multi-Agent", "MCP", "Embedding",
                  "Vector DB", "Fine-tuning", "Prompt Engineering"
                ]
              },
              "minItems": 1
            },
            "maturity": {
              "type": "string",
              "enum": ["demo", "MVP", "production-ready"]
            },
            "impact_score": {
              "type": "integer",
              "minimum": 1,
              "maximum": 10
            },
            "impact_reason": { "type": "string" }
          },
          "required": ["tech_direction", "maturity", "impact_score", "impact_reason"]
        }
      },
      "required": ["title", "url", "source", "popularity", "tags"]
    }
  }
}
```

---

## 3. 输出报告 Schema（Organizer 输出）

文件路径：`knowledge/articles/{YYYYMMDD}_report.md`

Markdown 格式，结构如下：
```markdown
# AI 知识库日报 - YYYY-MM-DD

## 概览
- 采集总数：XX
- AI 相关数：XX
- 平均影响力评分：X.X

## 按技术方向分类

### LLM
| 项目 | 影响力 | 成熟度 | 摘要 |
|------|--------|--------|------|

### Agent
...

## 标签索引
- #LLM (X)
- #Agent (X)
- #RAG (X)
```

---

## 4. 状态文件 Schema

文件路径：`knowledge/status/{YYYYMMDD}.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "date": { "type": "string", "format": "date" },
    "collector": { "$ref": "#/$defs/agent_status" },
    "analyzer": { "$ref": "#/$defs/agent_status" },
    "organizer": { "$ref": "#/$defs/agent_status" }
  },
  "required": ["date", "collector", "analyzer", "organizer"],
  "$defs": {
    "agent_status": {
      "type": "object",
      "properties": {
        "status": { "$ref": "#/$defs/status" },
        "started_at": { "type": "string", "format": "date-time" },
        "completed_at": { "type": "string", "format": "date-time" },
        "items_processed": { "type": "integer", "minimum": 0 },
        "error": { "$ref": "#/$defs/error" },
        "retry_count": { "type": "integer", "minimum": 0 }
      },
      "required": ["status", "started_at"]
    }
  }
}
```

---

## 5. 状态码定义

| 状态码 | 说明 | 下游行为 |
|--------|------|----------|
| `pending` | 等待执行 | 下游等待 |
| `running` | 正在执行 | 下游等待（超时 30 分钟后检查） |
| `success` | 执行成功 | 下游正常执行 |
| `failed` | 执行失败 | 下游记录 skip 并写入日志 |
| `skipped` | 被跳过 | 下游记录 skip 并写入日志 |
| `partial` | 部分成功 | 下游正常继续（数据量可能较少） |

---

## 6. 错误类型枚举

| 错误码 | 说明 | 可重试 |
|--------|------|--------|
| `network_timeout` | 网络请求超时 | 是 |
| `parse_error` | 页面解析失败 | 是 |
| `filter_empty` | 过滤后无结果 | 否 |
| `schema_validation_error` | 数据格式不符合 schema | 否 |
| `file_not_found` | 上游文件不存在 | 否 |
| `rate_limited` | 触发频率限制 | 是（等待后重试） |
| `internal_error` | 内部未知错误 | 是 |

---

## 7. 文件命名规范

| 文件类型 | 命名格式 | 示例 |
|----------|----------|------|
| Raw 数据 | `{YYYYMMDD}_trending_v{n}.json` | `20260501_trending_v1.json` |
| Annotated 数据 | `{YYYYMMDD}_trending_annotated_v{n}.json` | `20260501_trending_annotated_v1.json` |
| 状态文件 | `{YYYYMMDD}.json` | `20260501.json` |
| 输出报告 | `{YYYYMMDD}_report_v{n}.md` | `20260501_report_v1.md` |
| 重跑版本 | 文件名末尾递增 `_v{n}` | `20260501_trending_v2.json` |

---

## 8. 重跑策略

- 首次运行：版本号为 `v1`
- 每次重跑：版本号递增（`v2`, `v3`...）
- 不覆盖历史版本
- 状态文件记录每次运行的元信息
- 支持版本对比：比较不同版本间的差异

---

## 9. 目录结构

```
knowledge/
├── raw/
│   ├── 20260501_trending_v1.json
│   └── 20260501_trending_annotated_v1.json
├── articles/
│   └── 20260501_report_v1.md
└── status/
    └── 20260501.json

specs/
└── schemas/
    └── protocol.md  ← 本文件
```