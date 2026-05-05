# Issue #002: Analyzer 读取 raw 并打 3 维度标签

## Parent
002-agents-prd.md - Agent 职责：analyzer

## 类型
AFK

## What to build
实现 Analyzer Agent：读取 raw 数据 → 对每条打 3 维度标签 → 输出 annotated 文件

## 3 维度定义
1. **技术方向**：LLM / Agent / RAG / CV / NLP / Multi-Agent / ...
2. **成熟度**：demo / MVP / production-ready
3. **影响力评分**：1-10 分（附评分标准）

## Acceptance criteria
- [x] 读取 `knowledge/raw/YYYYMMDD_trending.json`
- [x] 对每条数据标注 3 维度标签
- [x] 输出至 `knowledge/raw/YYYYMMDD_trending_annotated.json`
- [x] JSON 符合 Issue #004 定义的 annotated schema
- [x] 评分有明确依据和标准
- [x] 执行时更新状态至 `knowledge/status/YYYYMMDD.json`

## 输出
- `src/analyzer.py` - Analyzer Agent 实现
- `knowledge/raw/20260505_trending_annotated.json` - 示例输出

## Blocked by
- #004（需先定义 annotated schema）
- #001（需有 raw 数据输入）