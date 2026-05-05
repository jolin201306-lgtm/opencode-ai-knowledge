# AI 知识库 · 项目愿景 v1.0

## 要做什么
- 每天抓取 GitHub Trending 页面精选 20 条
- 通过关键词粗筛（AI/ML/deep learning/LLM 等关键词）缩小范围到几十个项目
- 对通过粗筛的项目抓取 README
- 用 Agent 判断是否 AI 相关，并输出技术亮点 + 一段总结
- 输出结构化 JSON 知识条目

## 输出格式（JSON）
每个知识条目包含以下字段：
- `repo_name`：仓库名称
- `url`：仓库 URL
- `stars`：Star 数量
- `summary`：一段总结
- `highlights`：技术亮点
- `language`：主要编程语言

## 不做什么
- 不分析代码结构或依赖
- 不抓取 Trending 页面以外的额外信息（除了 README）
- 不做多语言版本的内容

## 边界 & 验收
- 每天自动运行一次
- 关键词粗筛命中率 > 50%
- Agent 判断准确率 > 80%
- 输出 JSON 格式符合 schema 定义

## 怎么验证
- 抽样检查输出的 JSON 条目
- 对 summary 和 highlights 进行人工质量评估
- 验证 JSON schema 合规性