# Issue #006: 按日期重跑单阶段任务

## Parent
002-agents-prd.md - 开放问题：重跑策略？

## 类型
AFK

## What to build
支持重新执行历史数据的能力，可按日期和阶段重跑

## Acceptance criteria
- [x] 支持命令：`rerun --date 2026-05-01`（重跑全天）
- [x] 支持命令：`rerun --date 2026-05-01 --stage analyzer`（重跑单阶段）
- [x] 重跑不覆盖原始数据，生成新版本文件（v1/v2/v3）
- [x] 保留历史版本，支持版本回滚
- [x] 有清单文件记录每次重跑的元信息
- [x] 支持对比不同版本差异

## 输出
- `src/rerun.py` - 重跑机制实现

## Blocked by
- #004（需先定义文件版本策略）