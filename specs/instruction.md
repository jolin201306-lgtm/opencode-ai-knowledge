## week1
### No.1 手写项目愿景文档
1、我有一份初版 spec 在./specs/001-project-vision.md ,每个 ? 就是我没有想清楚的点。请你扮演一个苛刻的产品评审，一个一个追问。每问一个我答一个。问完把 spec 改为终态版。
2、按./specs/001-project-vision.md 的终态版，生成一份对应的 AGENTS.md 初稿。放在项目根目录，严格对齐 spec 的每个条款。

### No.2 创建 AGENTS.md 文件

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

4、用AI编程工具触发 Sub-Agent.md

```plain
请用 Task 工具委派一个子任务给采集 Agent：
- 读取 .opencode/agents/collector.md 作为角色定义
- 搜集本周 AI 领域的 GitHub 热门开源项目 Top 10
- 返回结构化 JSON 结果
拿到结果后，你来把数据保存到 knowledge/raw/github-trending-task-今天日期.json
```

```plain
@collector 搜集本周 AI 领域的 GitHub 热门开源项目 Top 10。
搜索完成后把 JSON 数据保存到 knowledge/raw/github-trending-今天日期.json

@analyzer 读取 knowledge/raw/ 中最新的采集数据，
对每条内容进行深度分析——写摘要、提亮点、打评分（1-10 分并附理由）。

@organizer 将上面的分析结果整理为标准知识条目，
去重后存入 knowledge/articles/ 目录，每个条目单独一个 JSON 文件。
```
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

## week2
### No.5 hook

```plain
1、请帮我编写一个 Python 脚本 hooks/validate_json.py，用于校验知识条目 JSON 文件：

需求：
1. 支持单文件和多文件（通配符 *.json）两种输入模式
2. 检查 JSON 是否能正确解析
3. 必填字段使用 dict[str, type] 格式，同时校验字段存在性和类型：
   id(str), title(str), source_url(str), summary(str), tags(list), status(str)
4. 检查 ID 格式是否为 {source}-{YYYYMMDD}-{NNN}（如 github-20260317-001）
5. 检查 status 是否为 draft/review/published/archived 之一
6. 检查 URL 格式（https?://...）
7. 检查摘要最少 20 字、标签至少 1 个
8. 检查 score（如有）是否在 1-10 范围，audience（如有）是否为 beginner/intermediate/advanced
9. 命令行用法：python hooks/validate_json.py <json_file> [json_file2 ...]
10. 校验通过 exit 0，失败 exit 1 + 错误列表 + 汇总统计

编码规范：遵循 PEP 8，使用 pathlib，不依赖第三方库
```
```plain
请帮我编写一个 Python 脚本 hooks/check_quality.py，用于给知识条目做 5 维度质量评分：

需求：
1. 支持单文件和多文件（通配符 *.json）两种输入模式
2. 使用 dataclass 定义 DimensionScore 和 QualityReport 结构
3. 5 个评分维度及满分（加权总分 100 分）：
   - 摘要质量 (25 分)：>= 50 字满分，>= 20 字基本分，含技术关键词有奖励
   - 技术深度 (25 分)：基于文章 score 字段（1-10 映射到 0-25）
   - 格式规范 (20 分)：id、title、source_url、status、时间戳五项各 4 分
   - 标签精度 (15 分)：1-3 个合法标签最佳，有标准标签列表校验
   - 空洞词检测 (15 分)：不含"赋能""抓手""闭环""打通"等空洞词
4. 空洞词黑名单分中英两组：
   - 中文：赋能、抓手、闭环、打通、全链路、底层逻辑、颗粒度、对齐、拉通、沉淀、强大的、革命性的
   - 英文：groundbreaking、revolutionary、game-changing、cutting-edge 等
5. 输出可视化进度条 + 每维度得分 + 等级 A/B/C
6. 等级标准：A >= 80, B >= 60, C < 60
7. 退出码：存在 C 级返回 1，否则返回 0

编码规范：遵循 PEP 8，使用 pathlib 和 dataclass，不依赖第三方库
```
```plain
请帮我编写一个 OpenCode TypeScript 插件 .opencode/plugins/validate.ts：

需求：
1. 监听 tool.execute.after 事件
2. 当 Agent 使用 write 或 edit 工具写入 knowledge/articles/*.json 时触发
3. 触发时调用 python3 hooks/validate_json.py <file_path>
4. 使用 Bun Shell API（$ 模板字符串）执行命令
5. 必须使用 .nothrow() 而非 .quiet()（.quiet() 会导致 OpenCode 卡死）
6. 必须用 try/catch 包裹所有 shell 调用（未捕获异常会阻塞 Agent）

关键 API：
- import type { Plugin } from "@opencode-ai/plugin"
- input.tool 是工具名（如 "write"、"edit"）
- input.args.file_path 或 input.args.filePath 是文件路径
```

@collector 请调用 github-trending 技能，采集今日 AI 领域的 GitHub 热门项目。
@analyzer 请调用 tech-summary 技能，输出分析结果。
@organizer 将上面的分析结果整理为标准知识条目。

### No.6 pipeline & MCP
```plain
请帮我编写一个 Python 模块 pipeline/model_client.py，作为统一的 LLM 调用客户端：

需求：
1. 支持 DeepSeek、Qwen、OpenAI 三种模型提供商
2. 通过环境变量切换：LLM_PROVIDER（默认 deepseek）、对应的 API_KEY
3. 使用 httpx 直接调用 OpenAI 兼容 API（不依赖 openai SDK）
4. 用抽象基类 LLMProvider 定义接口，OpenAICompatibleProvider 实现
5. 统一返回 LLMResponse dataclass，包含 content 和 Usage 用量统计
6. 包含带重试的 chat_with_retry() 函数（3次，指数退避）和 60 秒超时
7. 包含 Token 消耗估算和成本计算函数（USD 计价）
8. 包含 quick_chat() 便捷函数，一句话调用 LLM
9. 最后有 if __name__ == "__main__" 的测试代码

编码规范：遵循 PEP 8，Google 风格 docstring，使用 logging 不用 print
```

```plain
请帮我编写 pipeline/pipeline.py，一个四步知识库自动化流水线：

需求：
1. Step 1: 采集（Collect）— 从 GitHub Search API 和 RSS 源采集 AI 相关内容
2. Step 2: 分析（Analyze）— 调用 LLM 对每条内容进行摘要/评分/标签分析
3. Step 3: 整理（Organize）— 去重 + 格式标准化 + 校验
4. Step 4: 保存（Save）— 将文章保存为独立 JSON 文件到 knowledge/articles/

CLI 设计：
- python pipeline/pipeline.py --sources github,rss --limit 20   # 完整流水线
- python pipeline/pipeline.py --sources github --limit 5         # 只采集 GitHub
- python pipeline/pipeline.py --sources rss --limit 10           # 只采集 RSS
- python pipeline/pipeline.py --sources github --limit 5 --dry-run  # 干跑模式
- python pipeline/pipeline.py --verbose                          # 详细日志

关键约束：
- 采集层用 httpx 发 HTTP 请求，RSS 用简易正则解析
- 分析层调用 model_client 的 chat_with_retry()（需要 API Key）
- 采集数据存入 knowledge/raw/，最终文章存入 knowledge/articles/
- model_client 在同目录下，用 from model_client import create_provider, chat_with_retry

编码规范：遵循 PEP 8，用 argparse 解析参数，用 pathlib 处理路径
```

```plain
请帮我创建 pipeline/rss_sources.yaml，配置知识库的 RSS 数据源：

需求：
1. YAML 格式，每个源包含 name、url、category、enabled 字段
2. 包含以下分类的数据源：
   - 综合技术：Hacker News Best (AI 相关)、Lobsters AI/ML
   - AI 研究：arXiv cs.AI
   - 公司博客：OpenAI Blog、Anthropic Research、Hugging Face Blog
   - 中文社区：机器之心、量子位（默认 disabled，需确认 RSS 可用性）
3. 每个源的 enabled 字段控制是否采集
4. 量太大的源默认设为 enabled: false
```

```plain
请帮我写一个 MCP Server（mcp_knowledge_server.py），让 AI 工具可以搜索本地知识库：

需求：
1. 读取 knowledge/articles/ 目录下的所有 JSON 文件
2. 提供 3 个 MCP 工具：
   - search_articles(keyword, limit=5): 按关键词搜索文章标题和摘要
   - get_article(article_id): 按 ID 获取文章完整内容
   - knowledge_stats(): 返回统计信息（文章总数、来源分布、热门标签）
3. 使用 JSON-RPC 2.0 over stdio 协议
4. 支持 MCP initialize、tools/list、tools/call 方法
5. 无第三方依赖，只用 Python 标准库

文章 JSON 格式参考：
{
  "id": "github-20260326-001",
  "title": "langgenius/dify",
  "source": "github",
  "summary": "...",
  "score": 7,
  "tags": ["agent", "llm"]
}
```
### No.7 CI/CD
```plain
请帮我创建 .github/workflows/daily-collect.yml，一个 GitHub Actions 工作流：

需求：
1. 每天 UTC 08:00（北京时间 16:00）自动运行
2. 同时支持手动触发（workflow_dispatch）
3. 添加 permissions: contents: write
4. 使用 Python 3.11，启用 pip 缓存
5. 通过 pip install -r requirements.txt 安装依赖
6. 运行命令：python pipeline/pipeline.py --sources github,rss --limit 20 --verbose
7. 支持多个 LLM 密钥（LLM_PROVIDER、DEEPSEEK_API_KEY、QWEN_API_KEY、OPENAI_API_KEY）
8. 采集后运行 validate_json.py 和 check_quality.py 校验文章
9. 自动 git commit + push，commit 消息包含文章数量和日期
10. 如果没有新数据则不提交（避免空 commit）
```
### No.8 CostTracker费用跟踪

```plain
请帮我在 pipeline/model_client.py 中添加 CostTracker 功能：

需求：
1. 创建一个 CostTracker 类，追踪 LLM 调用的 token 消耗和成本
2. 包含国产模型价格表（单位：元/百万 tokens）：
   - deepseek: 输入 1, 输出 2
   - qwen: 输入 4, 输出 12
   - openai (gpt-4o-mini): 输入 150, 输出 600
3. CostTracker 方法：
   - record(usage, provider): 记录一次 API 调用
   - estimated_cost(provider): 返回估算成本（元）
   - report(provider): 打印成本报告
4. 在 chat() 函数中，每次调用成功后自动 record
5. 创建全局 tracker 实例，Pipeline 结束时可以调 tracker.report()

编码规范：遵循 PEP 8，Google 风格 docstring
```
