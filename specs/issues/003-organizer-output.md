# Issue #003: Organizer 读取标注数据生成 MD 报告

## Parent
002-agents-prd.md - Agent 职责：organizer

## 类型
AFK

## What to build
实现 Organizer Agent：读取已标注数据 → 按标签分类 → 生成 Markdown 格式知识库报告

## Acceptance criteria
- [x] 读取 `knowledge/raw/YYYYMMDD_trending_annotated.json`
- [x] 按技术方向标签分类聚合
- [x] 生成 Markdown 报告，包含：目录、摘要、标签索引、原文链接
- [x] 输出至 `knowledge/articles/YYYYMMDD_report.md`
- [x] MD 格式可读、链接完整

## 输出
- `src/organizer.py` - Organizer Agent 实现
- `knowledge/articles/20260505_report.md` - 示例报告
- [ ] 执行时更新状态至 `knowledge/status/YYYYMMDD.json`

## Blocked by
- #004（需先定义输出格式规范）
- #002（需有 annotated 数据输入）