# Issue #004: Agent 间文件传递协议 + 状态码

## Parent
002-agents-prd.md - 开放问题：数据怎么传？文件 or 消息？

## 类型
HITL（需要人工决策 schema 设计）

## What to build
定义 Collector → Analyzer → Organizer 之间的文件传递协议，包括：
- 统一的 JSON schema
- 文件命名规范
- Agent 间状态码定义
- 错误类型枚举

## Acceptance criteria
- [x] 定义 raw 数据 schema（collector 输出）
- [x] 定义 annotated 数据 schema（analyzer 输出）
- [x] 定义 status 状态码（pending/running/success/failed/retry）
- [x] 定义错误类型枚举（network_timeout/parse_error/filter_empty/...）
- [x] 文件命名规范文档
- [x] 写入 `specs/schemas/` 目录

## 输出
- `specs/schemas/protocol.md` - 完整的数据传递协议文档

## Blocked by
None - 可以立即开始，但需要人工审核确认