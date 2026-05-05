---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能，支持按关键词过滤和结构化输出
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要采集 GitHub 热门开源项目时使用此技能，适用于：
- 每日/每周 AI 技术动态采集
- 特定领域（AI/LLM/Agent）热门项目追踪
- 开源项目趋势分析

## 执行步骤

### 1. 搜索热门仓库
访问 GitHub Trending 页面或搜索 API，获取当前热门项目列表。
- 页面：`https://github.com/trending`
- 可选语言过滤：`https://github.com/trending/{language}`

### 2. 提取项目信息
从每个项目中提取以下信息：
- 仓库名称（owner/repo）
- 项目描述
- Star 数
- 编程语言
- Topics/标签

### 3. 关键词过滤
**纳入条件**（满足任一）：
- 包含 AI/LLM/Agent/ML/deep learning/transformer 等关键词
- Topics 中包含 ai, machine-learning, llm, agent, deep-learning

**排除条件**（满足任一）：
- Awesome 列表（如 awesome-llm, awesome-chatgpt）
- 纯教程/课程类仓库
- 非技术项目（游戏、主题、博客等）

### 4. 去重检查
与 `knowledge/raw/` 下已有文件比对，通过 URL 排除已采集的项目。

### 5. 撰写中文摘要
使用以下公式为每个项目撰写摘要：
```
{项目名} + {做什么} + {为什么值得关注}
```
示例：`LangGraph 是构建有状态多 Agent 工作流的框架，通过图结构实现复杂 Agent 编排，适合需要精确控制 Agent 流转逻辑的场景。`

### 6. 排序取 Top 15
按 Star 数降序排列，取前 15 个项目。

### 7. 输出 JSON
将结果保存至 `knowledge/raw/github-trending-YYYY-MM-DD.json`

## 注意事项

- 不编造数据，所有信息来自真实页面
- 摘要必须为中文，长度 30-60 字
- 若过滤后不足 15 个，返回全部实际数量
- 记录采集时间戳（ISO 8601 格式）
- 网络请求失败时记录错误日志，不中断流程

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-05-05T03:00:00Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "中文摘要",
      "stars": 12345,
      "language": "Python",
      "topics": ["ai", "llm", "agent"]
    }
  ]
}
```
