## week1
### No.1 手写项目愿景文档
1、我有一份初版 spec 在./specs/001-project-vision.md ,每个 ? 就是我没有想清楚的点。请你扮演一个苛刻的产品评审，一个一个追问。每问一个我答一个。问完把 spec 改为终态版。
2、按./specs/001-project-vision.md 的终态版，生成一份对应的 AGENTS.md 初稿。放在项目根目录，严格对齐 spec 的每个条款。

### No.2 创建AGENTS.md

```plain
请帮我为一个 AI 知识库助手项目创建 AGENTS.md 文件。
项目需求：
- 自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域的技术动态
- AI 分析后结构化存储为 JSON
- 支持多渠道分发（飞书）
请在 AGENTS.md 中包含：
1. 项目概述（一段话说清楚做什么）
2. 技术栈：Python 3.12、OpenCode + 国产大模型、LangGraph、OpenClaw
3. 编码规范：PEP 8、snake_case、Google 风格 docstring、禁止裸 print()
4. 项目结构：.opencode/agents/、.opencode/skills/、knowledge/raw/、knowledge/articles/
5. 知识条目的 JSON 格式（包含 id、title、source_url、summary、tags、status 等字段）
6. Agent 角色概览表格（采集/分析/整理三个角色）
7. 红线（绝对禁止的操作）
```

### No.3 通过prompt定义Agent & to-issue skill
1、请帮我创建 .opencode/agents/collector.md 文件，定义一个知识采集 Agent。
要求：
- 角色：AI 知识库助手的采集 Agent，从 GitHub Trending 和 Hacker News 采集技术动态
- 允许权限：Read, Grep, Glob, WebFetch（只看只搜不写）
- 禁止权限：Write, Edit, Bash（并说明为什么禁止）
- 工作职责：搜索采集、提取标题/链接/热度/摘要、初步筛选、按热度排序
- 输出格式：JSON 数组，每条含 title, url, source, popularity, summary
- 质量自查清单：条目>=15、信息完整、不编造、中文摘要

2、 请帮我创建.opencode/agents/analyzer.md，定义一个知识分析 Agent。
要求：
- 权限同 collector（Read/Grep/Glob/WebFetch，禁止 Write/Edit/Bash）
- 职责：读取 knowledge/raw/ 的数据，写摘要、提亮点、打评分(1-10)、建议标签
- 评分标准：9-10 改变格局，7-8 直接有帮助，5-6 值得了解，1-4 可略过

3、请帮我创建.opencode/agents/organizer.md，定义一个知识整理 Agent。
要求：
- 权限：允许 Read/Grep/Glob/Write/Edit，禁止 WebFetch/Bash
- 职责：去重检查、格式化为标准 JSON、分类存入 knowledge/articles/
- 文件命名规范：{date}-{source}-{slug}.json

4、用AI编程工具出发 Sub-Agent.md

@collector 搜集本周 AI 领域的 GitHub 热门开源项目 Top 10。
搜索完成后把 JSON 数据保存到 knowledge/raw/github-trending-今天日期.json

请用 Task 工具委派一个子任务给采集 Agent：
- 读取 .opencode/agents/collector.md 作为角色定义
- 搜集本周 AI 领域的 GitHub 热门开源项目 Top 10
- 返回结构化 JSON 结果
拿到结果后，你来把数据保存到 knowledge/raw/github-trending-task-今天日期.json

@analyzer 读取 knowledge/raw/ 中最新的采集数据，
对每条内容进行深度分析——写摘要、提亮点、打评分（1-10 分并附理由）。

@organizer 将上面的分析结果整理为标准知识条目，
去重后存入 knowledge/articles/ 目录，每个条目单独一个 JSON 文件。

**关键知识点**
@mention 快速切换角色，适合简单任务
Task 工具 创建隔离上下文，适合复杂独立任务
Agent 之间通过文件协作，不通过上下文共享

**agents-collaboration智能体协作**

4、多agent设计的文件为002-agents-prd.md，用 to-issues 细化成任务，输出内容保存在./specs/issues目录下；
5、完成#004（schema 设计），生成*.json文件，保存在./specs/schemas目录下
6、从 issue 派生，定义3个agent职责、权限、输出更是、质量自查清单、评分标准、文件命名规范等内容，定义职责文件保存在./.opencode/agents目录下

### No.4 写skill
```plain
1、请帮我创建 .opencode/skills/github-trending/SKILL.md 文件。

格式要求：
- 头部用 YAML frontmatter（name, description, allowed-tools）
- 正文用 Markdown，包含：使用场景、执行步骤（7步）、注意事项、输出格式

内容要求：
- name: github-trending
- description: 当需要采集 GitHub 热门开源项目时使用此技能
- allowed-tools: Read, Grep, Glob, WebFetch
- 7个执行步骤：搜索热门仓库(GitHub API) → 提取信息 → 过滤(纳入AI/LLM/Agent，排除Awesome列表) → 去重 → 撰写中文摘要(公式：项目名+做什么+为什么值得关注) → 排序取Top15 → 输出JSON到knowledge/raw/github-trending-YYYY-MM-DD.json
- JSON结构包含：source, skill, collected_at, items数组(name, url, summary, stars, language, topics)
```

```plain
2、参考 .opencode/skills/github-trending/SKILL.md 的格式，
帮我创建 .opencode/skills/tech-summary/SKILL.md。

- name: tech-summary
- description: 当需要对采集的技术内容进行深度分析总结时使用此技能
- allowed-tools: Read, Grep, Glob, WebFetch
- 4个执行步骤：
  1. 读取 knowledge/raw/ 最新采集文件
  2. 逐条深度分析（摘要<=50字、技术亮点2-3个用事实说话、评分1-10附理由、标签建议）
  3. 趋势发现（共同主题、新概念）
  4. 输出分析结果 JSON
- 评分标准：9-10改变格局, 7-8直接有帮助, 5-6值得了解, 1-4可略过
- 约束：15个项目中9-10分不超过2个
```
```plain
@collector 请调用 github-trending 技能，按照 .opencode/skills/github-trending/SKILL.md 的 7 个步骤，采集本周 AI 领域的 GitHub 热门项目。
搜索完成后把 JSON 数据保存到 knowledge/raw/github-trending-今天日期.json

@analyzer 请调用 tech-summary 技能，读取 knowledge/raw/ 中最新的采集数据，
按照 .opencode/skills/tech-summary/SKILL.md 的 4 个步骤进行深度分析。
输出分析结果。

@organizer 将上面的分析结果整理为标准知识条目：
1. 与 knowledge/articles/ 已有条目做去重检查
2. 格式化为标准 JSON（包含 id, title, source_url, summary, tags, status 字段）
3. 每个条目单独存为 knowledge/articles/{date}-{source}-{slug}.json
```