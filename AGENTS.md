# AGENTS.md

## 交互要求
1. 在处理所有问题时，**全程思考过程必须使用中文**（包括需求分析、逻辑拆解、方案选择、步骤推导等所有内部推理环节）；
2. 最终输出的所有回答内容（包括文字解释、代码注释、步骤说明等）**必须全部使用中文**，仅代码语法本身的英文关键词除外。

## 项目概述

AI 知识库助手——自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域的技术动态，经 AI 分析后结构化存储为 JSON，并支持多渠道分发至飞书等平台。


## 技术栈

| 组件 | 说明 |
|------|------|
| Python 3.12 | 运行时 |
| OpenCode + 国产大模型 | AI 推理引擎 |
| LangGraph | Agent 工作流编排 |
| OpenClaw | 任务调度与执行 |

## 编码规范

- 严格遵循 **PEP 8**
- 变量/函数命名统一 **snake_case**
- Docstring 采用 **Google 风格**
- **禁止裸 `print()`**，统一使用 `logging` 模块

## 项目结构

```
.opencode/
├── agents/          # Agent 定义与角色逻辑
│   ├── collector.py # 采集 Agent
│   ├── analyst.py   # 分析 Agent
│   └── publisher.py # 整理与分发 Agent
├── skills/          # 可复用技能模块
│   ├── fetch_trending.py
│   ├── fetch_hn.py
│   ├── parse_readme.py
│   └── feishu_push.py
knowledge/
├── raw/             # 原始采集数据（JSON）
└── articles/        # 分析后的结构化知识条目（JSON）
```

## 知识条目 JSON 格式

```json
{
  "id": "uuid-string",
  "title": "项目或文章标题",
  "source": "github_trending | hacker_news",
  "source_url": "https://...",
  "summary": "一段话总结",
  "highlights": ["技术亮点1", "技术亮点2"],
  "tags": ["AI", "LLM", "Agent"],
  "language": "Python",
  "stars": 1234,
  "status": "raw | analyzed | published",
  "created_at": "2026-05-01T00:00:00Z",
  "updated_at": "2026-05-01T00:00:00Z"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识（UUID） |
| `title` | string | 是 | 标题 |
| `source` | string | 是 | 数据来源：`github_trending` 或 `hacker_news` |
| `source_url` | string | 是 | 原始链接 |
| `summary` | string | 是 | 一段话总结 |
| `highlights` | array | 否 | 技术亮点列表 |
| `tags` | array | 是 | 分类标签 |
| `language` | string | 否 | 主要编程语言（仅 GitHub 来源） |
| `stars` | number | 否 | Star 数（仅 GitHub 来源） |
| `status` | string | 是 | 状态：`raw` → `analyzed` → `published` |
| `created_at` | string | 是 | ISO 8601 时间戳 |
| `updated_at` | string | 是 | ISO 8601 时间戳 |

## Agent 角色概览

| 角色 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **Collector（采集）** | 从 GitHub Trending、Hacker News 定时拉取原始数据 | 无 | `knowledge/raw/` 下的原始 JSON |
| **Analyst（分析）** | 对 raw 数据进行 AI 判断（是否 AI 相关）、提炼亮点、生成总结 | `knowledge/raw/` | `knowledge/articles/` 下的结构化 JSON |
| **Publisher（整理与分发）** | 按 tag 筛选、格式化，推送至飞书等渠道 | `knowledge/articles/` | 飞书消息卡片 / 群通知 |

## 红线

以下操作 **绝对禁止**：

1. **禁止**分析代码结构或依赖关系
2. **禁止**抓取 Trending / HN 页面以外的额外信息（README 除外）
3. **禁止**生成多语言版本的知识条目
4. **禁止**在代码中硬编码 API Key 或 Token（必须走环境变量或 .env）
5. **禁止**未经确认直接向生产环境推送数据
6. **禁止**跳过 `status` 状态机（raw → analyzed → published 不可逆跳）
7. **禁止**裸 `print()`，统一使用 `logging`