---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# 技术内容深度分析技能

## 使用场景

当需要对采集的技术内容进行深度分析总结时使用此技能，适用于：
- 对 GitHub Trending/Hacker News 采集的原始数据进行二次分析
- 提炼技术亮点、评估项目价值
- 发现行业趋势和共同主题

## 执行步骤

### 1. 读取最新采集文件
从 `knowledge/raw/` 目录下找到最新日期的采集文件（格式：`github-trending-YYYY-MM-DD.json` 或 `YYYYMMDD_trending.json`）。

### 2. 逐条深度分析
对每个项目执行以下分析：

- **精炼摘要**：50 字以内，说明"是什么 + 解决什么问题"
- **技术亮点**：2-3 个，用具体事实说话（如架构创新、性能指标、独特设计），避免营销话术
- **影响力评分**：1-10 分（附评分理由）
- **标签建议**：2-4 个分类标签

### 3. 趋势发现
分析全部项目，识别：
- **共同主题**：多个项目聚焦的同一技术方向
- **新概念/新模式**：首次出现或快速发展的技术趋势
- **技术演进信号**：从 demo 到 MVP 的关键转变

### 4. 输出分析结果
将分析结果保存为 JSON 文件至 `knowledge/raw/` 目录，文件名格式：`{source}-YYYY-MM-DD-analyzed.json`

## 评分标准

| 分数 | 等级 | 标准 | 示例特征 |
|------|------|------|----------|
| 9-10 | 改变格局 | 突破性创新，可能改变行业方向 | 新范式、新架构、新交互模式 |
| 7-8 | 直接有帮助 | 解决实际问题，可立即应用 | 工具链完善、文档清晰、有实际用例 |
| 5-6 | 值得了解 | 有新意但不够成熟，值得关注 | 概念验证、早期原型、小众但有潜力 |
| 1-4 | 可略过 | 热度高但实质内容有限 | 营销大于实质、fork/clone 类项目 |

## 约束条件

- 15 个项目中 **9-10 分不超过 2 个**，保持评分稀缺性
- 摘要必须为中文，严格控制在 50 字以内
- 技术亮点必须用事实/数据/代码特征支撑，不得使用"强大""领先"等空泛描述
- 标签来自预定义词表：AI, LLM, Agent, RAG, Multi-Agent, MCP, CV, NLP, DevTools, Infra, Database, UI, Security

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "tech-summary",
  "analyzed_at": "2026-05-05T03:00:00Z",
  "source_file": "knowledge/raw/github-trending-2026-05-05.json",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "50字以内的精炼摘要",
      "highlights": [
        "技术亮点1：具体事实描述",
        "技术亮点2：具体事实描述"
      ],
      "score": 8,
      "score_reason": "评分理由，说明为何给此分数",
      "tags": ["Agent", "LLM", "DevTools"]
    }
  ],
  "trends": {
    "common_themes": [
      {
        "theme": "多智能体协作",
        "count": 4,
        "projects": ["repo1", "repo2"]
      }
    ],
    "emerging_concepts": [
      "新概念/新模式描述"
    ],
    "signals": [
      "技术演进信号描述"
    ]
  }
}
```
