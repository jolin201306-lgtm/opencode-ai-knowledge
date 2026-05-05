# Issue #001: Collector 抓取 GitHub Trending 并存储 raw JSON

## Parent
002-agents-prd.md - Agent 职责：collector

## 类型
AFK

## What to build
实现 Collector Agent 的最小可用路径：抓取 GitHub Trending → 过滤 AI 相关 → 存储 raw JSON 到 `knowledge/raw/`

## Acceptance criteria
- [x] 访问 https://github.com/trending 获取 Top 50 项目
- [x] 根据关键词过滤 AI 相关项目（AI/ML/LLM/Agent 等）
- [x] 提取标题、URL、stars、stars_today、language、description
- [x] 按 stars_today 降序排列
- [x] 输出 JSON 至 `knowledge/raw/YYYYMMDD_trending.json`
- [x] JSON 符合 Issue #004 定义的 schema
- [x] 执行时更新状态至 `knowledge/status/YYYYMMDD.json`

## 输出
- `src/collector.py` - Collector Agent 实现
- `knowledge/raw/20260505_trending.json` - 示例输出
- `knowledge/status/20260505.json` - 状态文件

## Blocked by
- #004（需先定义 schema）