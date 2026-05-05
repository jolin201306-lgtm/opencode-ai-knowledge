---
name: github-trending
description: 从 GitHub Trending 页面采集热门开源项目，过滤 AI/LLM/Agent/ML 相关领域，输出结构化 JSON 数据。支持按语言/时间范围/关键词过滤。Use when 用户请求包括：抓取/采集/搜集/收集 GitHub Trending/热榜/热门项目/热门仓库/趋势/动态；看看今天/本周/本月 GitHub 上什么火/流行/最火/最热门/增长最快/star最多；找/搜索/获取 GitHub 上 AI/LLM/Agent/ML/深度学习/大模型/智能体相关的开源项目/开源仓库；拉取/获取 GitHub trending 数据；看看 GitHub 上热门的技术项目；获取开源项目动态/技术趋势。
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 触发场景

当用户需要以下操作时使用此技能：
- 抓取 GitHub Trending 热门项目
- 采集 AI/LLM/Agent 领域开源项目动态
- 获取 GitHub 热榜数据
- 搜集技术趋势/开源动态

## 执行流程

### Step 1: 获取 Trending 页面
访问 `https://github.com/trending` 获取全语言热榜，或指定语言子页面如 `https://github.com/trending/python`。

**时间范围选项**（用户指定时追加）：
- 今日：`/trending`（默认）
- 本周：`/trending?since=weekly`
- 本月：`/trending?since=monthly`

### Step 2: 解析项目信息
从 HTML 中提取以下字段：
| 字段 | 来源 | 示例 |
|------|------|------|
| name | `<h2>` 标签中的 owner/repo | `langchain-ai/langchain` |
| url | 拼接完整 GitHub 链接 | `https://github.com/langchain-ai/langchain` |
| stars | 统计数字 | `136000` |
| topics | 标签区域 | `["ai", "llm", "agents"]` |
| description | `<p>` 描述文本 | `智能体工程平台...` |

### Step 3: 关键词过滤
**纳入条件**（满足任一）：
- description/topics 包含：`ai`, `llm`, `agent`, `ml`, `machine learning`, `deep learning`, `transformer`, `gpt`, `chatgpt`, `openai`, `claude`, `rag`, `multimodal`, `nlp`

**排除条件**（满足任一即跳过）：
- Awesome 列表类（`awesome-xxx`）
- 纯教程/课程/学习路线
- 非技术项目（游戏、主题、博客模板）

### Step 4: 排序与截断
按 stars 降序排列，默认取 Top 50。用户指定数量时按指定数量截取。

### Step 5: 输出 JSON
输出标准 JSON 数组到 stdout，**不保存文件**（由调用方决定存储路径）。

## 输出格式

```json
[
  {
    "name": "owner/repo",
    "url": "https://github.com/owner/repo",
    "stars": 136000,
    "topics": ["ai", "llm", "agents"],
    "description": "项目描述文本"
  }
]
```

## 边界条件

| 场景 | 处理方式 |
|------|----------|
| 网络请求失败 | 返回空数组 `[]`，不抛异常 |
| 过滤后无结果 | 返回空数组 `[]` |
| HTML 解析失败 | 返回空数组 `[]`，记录日志 |
| 执行超时 | 终止并返回已采集部分 |
| 单次执行 | < 10 秒 |

## 约束

- 不直接调用 GitHub API（rate limit 限制），走 HTML 解析
- 不存储到数据库，仅 stdout 输出
- 不做去重检查（由调用方处理）
- 输出必须为合法 JSON，可通过 jsonschema 验证

## 使用示例

```
用户：抓取今天 GitHub 热榜上 AI 相关的项目
→ 执行：访问 /trending → 解析 → 过滤 AI 关键词 → 输出 JSON

用户：帮我看看本周 GitHub 上最火的 LLM 项目 Top 10
→ 执行：访问 /trending?since=weekly → 解析 → 过滤 LLM → 取 Top 10 → 输出 JSON

用户：搜集 GitHub 上 Agent 相关的开源项目
→ 执行：访问 /trending → 解析 → 过滤 Agent 关键词 → 输出 JSON
```
