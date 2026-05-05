# Issue #007: 每日进度状态文件生成

## Parent
002-agents-prd.md - 开放问题：进度追踪

## 类型
AFK

## What to build
实现每日任务的状态追踪：每个 Agent 执行时更新状态文件，支持查询

## Acceptance criteria
- [x] 状态文件路径：`knowledge/status/YYYYMMDD.json`
- [x] 状态枚举：pending → running → success / failed
- [x] 每个 Agent 开始时更新为 running，结束时更新为终态
- [x] 状态包含：started_at、completed_at、items_processed、error_message
- [x] 支持查询命令：`status --date 2026-05-01`
- [x] 支持查询最近 N 天：`status --last 7`
- [x] 输出可读的进度报告

## 输出
- `src/status_tracker.py` - 状态追踪实现

## Blocked by
- #004（需先定义状态 schema）