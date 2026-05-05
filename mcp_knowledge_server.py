"""MCP Server：本地知识库搜索服务。

提供 3 个工具供 AI 工具调用：
- search_articles: 按关键词搜索文章
- get_article: 按 ID 获取文章详情
- knowledge_stats: 返回知识库统计信息

使用 JSON-RPC 2.0 over stdio 协议，无第三方依赖。
"""

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

ARTICLES_DIR = Path(__file__).resolve().parent / "knowledge" / "articles"


def normalize_url(url: str) -> str:
    """规范化 URL，用于去重和索引。

    Args:
        url: 原始 URL。

    Returns:
        规范化后的标识符。
    """
    url = url.strip().lower().rstrip("/")
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    if match:
        return match.group(1)
    return url


# ── 数据存储 ──────────────────────────────────────────────────────────────

class ArticleStore:
    """本地知识库存储。

    Attributes:
        articles_dir: 知识条目目录。
        _articles: 已加载的文章列表。
        _index: 规范化 URL/ID 到文章的索引，用于快速查找。
    """

    def __init__(self, articles_dir: Path = ARTICLES_DIR):
        """初始化存储。

        Args:
            articles_dir: 知识条目所在目录路径。
        """
        self.articles_dir = articles_dir
        self._articles: list[dict] = []
        self._index: dict[str, dict] = {}

    def load(self) -> int:
        """加载所有 JSON 文件。

        Returns:
            加载的文章数量。
        """
        self._articles = []
        self._index = {}
        
        # 临时集合用于去重
        seen_keys: set[str] = set()
        deduplicated_articles: list[dict] = []

        if not self.articles_dir.exists():
            logger.warning("目录不存在: %s", self.articles_dir)
            return 0

        for f in sorted(self.articles_dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                    data["_file"] = f.name
                    
                    # 在加载时执行去重逻辑
                    url = data.get("source_url", "")
                    key = normalize_url(url) if url else data.get("id", "")
                    
                    if key not in seen_keys:
                        seen_keys.add(key)
                        deduplicated_articles.append(data)
                        # 建立索引
                        self._index[key] = data
                        self._index[data.get("id", "")] = data
                    else:
                        logger.info("加载时发现重复数据，已跳过: %s (%s)", data.get("title"), f.name)
            except Exception as e:
                logger.warning("加载失败 [%s]: %s", f.name, e)

        self._articles = deduplicated_articles
        logger.info("已加载 %d 篇文章 (已去重)", len(self._articles))
        return len(self._articles)

    @property
    def articles(self) -> list[dict]:
        """获取已加载的文章列表。

        Returns:
            文章字典列表。
        """
        return self._articles


# ── 工具实现 ──────────────────────────────────────────────────────────────

TOOLS_SPEC = [
    {
        "name": "search_articles",
        "description": "按关键词搜索知识库文章的标题和摘要",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "number",
                    "description": "返回结果数量上限，默认 5",
                },
                "source": {
                    "type": "string",
                    "description": "按来源过滤（如 github_trending, rss）",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "返回知识库统计信息（文章总数、来源分布、热门标签）",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def search_articles(store: ArticleStore, keyword: str, limit: int = 5, source: Optional[str] = None) -> dict:
    """搜索文章。

    Args:
        store: 文章存储实例。
        keyword: 搜索关键词。
        limit: 返回结果数量上限。
        source: 来源过滤（可选）。

    Returns:
        搜索结果，包含匹配的文章列表。
    """
    keyword_lower = keyword.lower()
    results = []

    for article in store.articles:
        if source and article.get("source") != source:
            continue

        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = [t.lower() for t in article.get("tags", [])]

        if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
            results.append({
                "id": article.get("id"),
                "title": article.get("title"),
                "source": article.get("source"),
                "summary": article.get("summary", "")[:100],
                "score": article.get("score"),
                "tags": article.get("tags", []),
            })

    return {
        "keyword": keyword,
        "total_matches": len(results),
        "articles": results[:limit],
    }


def get_article(store: ArticleStore, article_id: str) -> dict:
    """按 ID 获取文章。

    Args:
        store: 文章存储实例。
        article_id: 文章唯一标识。

    Returns:
        文章完整内容，未找到时包含错误信息。
    """
    for article in store.articles:
        if article.get("id") == article_id:
            result = {k: v for k, v in article.items() if not k.startswith("_")}
            return {"found": True, "article": result}
    return {"found": False, "error": f"未找到 ID 为 '{article_id}' 的文章"}


def knowledge_stats(store: ArticleStore) -> dict:
    """获取统计信息。

    Args:
        store: 文章存储实例。

    Returns:
        统计信息字典。
    """
    articles = store.articles

    source_counter = Counter(a.get("source", "unknown") for a in articles)
    tag_counter = Counter()
    for a in articles:
        for tag in a.get("tags", []):
            tag_counter[tag] += 1

    score_distribution = Counter()
    for a in articles:
        score = a.get("score")
        if score:
            bucket = f"{(score // 2) * 2 + 1}-{(score // 2) * 2 + 2}"
            score_distribution[bucket] += 1

    return {
        "total_articles": len(articles),
        "sources": dict(source_counter.most_common()),
        "top_tags": dict(tag_counter.most_common(10)),
        "score_distribution": dict(score_distribution.most_common()),
        "avg_score": round(
            sum(a.get("score", 0) for a in articles) / len(articles), 1
        ) if articles else 0,
    }


# ── MCP Server ────────────────────────────────────────────────────────────

class MCPServer:
    """MCP JSON-RPC Server over stdio。

    Attributes:
        store: 文章存储实例。
        _request_id: 当前请求 ID。
    """

    def __init__(self, store: ArticleStore):
        """初始化 MCP 服务器。

        Args:
            store: 文章存储实例。
        """
        self.store = store
        self._request_id: Any = None

    def send_response(self, result: Any) -> None:
        """发送 JSON-RPC 响应。

        Args:
            result: 响应结果数据。
        """
        response = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "result": result,
        }
        self._send_json(response)

    def send_error(self, code: int, message: str, data: Optional[Any] = None) -> None:
        """发送 JSON-RPC 错误。

        Args:
            code: 错误码。
            message: 错误描述。
            data: 额外错误数据（可选）。
        """
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        response = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "error": error,
        }
        self._send_json(response)

    def send_notification(self, method: str, params: dict) -> None:
        """发送通知（无 ID）。

        Args:
            method: 通知方法名。
            params: 通知参数。
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send_json(notification)

    def _send_json(self, data: dict) -> None:
        """通过 stdout 发送 JSON 行。

        Args:
            data: 要发送的数据字典。
        """
        line = json.dumps(data, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def _log(self, message: str) -> None:
        """通过 stderr 输出日志（不干扰 stdio 协议）。

        Args:
            message: 日志消息。
        """
        sys.stderr.write(f"[MCP] {message}\n")
        sys.stderr.flush()

    def handle_request(self, request: dict) -> None:
        """处理单个 JSON-RPC 请求。

        Args:
            request: 解析后的 JSON-RPC 请求。
        """
        self._request_id = request.get("id")
        method = request.get("method")

        if method == "initialize":
            self._handle_initialize(request.get("params", {}))
        elif method == "tools/list":
            self._handle_tools_list()
        elif method == "tools/call":
            self._handle_tools_call(request.get("params", {}))
        elif method == "ping":
            self.send_response({})
        else:
            self.send_error(-32601, f"方法未实现: {method}")

    def _handle_initialize(self, params: dict) -> None:
        """处理 initialize 请求。

        Args:
            params: 初始化参数。
        """
        client_info = params.get("clientInfo", {})
        self._log(f"客户端连接: {client_info.get('name', 'unknown')} {client_info.get('version', '?')}")

        response = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
            },
            "serverInfo": {
                "name": "knowledge-base-server",
                "version": "1.0.0",
            },
        }
        self.send_response(response)

    def _handle_tools_list(self) -> None:
        """处理 tools/list 请求。"""
        self.send_response({"tools": TOOLS_SPEC})

    def _handle_tools_call(self, params: dict) -> None:
        """处理 tools/call 请求。

        Args:
            params: 调用参数，包含 name 和 arguments。
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        self._log(f"调用工具: {tool_name}({arguments})")

        try:
            if tool_name == "search_articles":
                keyword = arguments.get("keyword", "")
                limit = int(arguments.get("limit", 5))
                source = arguments.get("source")
                result = search_articles(self.store, keyword, limit, source)
                self.send_response({
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2),
                        }
                    ],
                })

            elif tool_name == "get_article":
                article_id = arguments.get("article_id", "")
                result = get_article(self.store, article_id)
                self.send_response({
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2),
                        }
                    ],
                })

            elif tool_name == "knowledge_stats":
                result = knowledge_stats(self.store)
                self.send_response({
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2),
                        }
                    ],
                })

            else:
                self.send_error(-32601, f"未知工具: {tool_name}")

        except Exception as e:
            self._log(f"工具调用异常: {e}")
            self.send_error(-32603, f"工具执行失败: {str(e)}")


# ── 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    """MCP Server 入口函数。"""
    # 配置日志（使用 stderr，不干扰 stdio 协议）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        stream=sys.stderr,
    )

    # 启动时立即加载数据
    store = ArticleStore()
    store.load()

    server = MCPServer(store)
    server._log("MCP Server 已启动")

    # 处理 stdin 请求
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                server.handle_request(request)
            except json.JSONDecodeError as e:
                server._log(f"JSON 解析失败: {e}")
                server.send_error(-32700, f"JSON 解析失败: {e}")
    except KeyboardInterrupt:
        server._log("服务器已停止")


if __name__ == "__main__":
    main()
