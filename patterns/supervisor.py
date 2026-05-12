"""Supervisor 监督模式——Worker 产出 + Supervisor 审核循环。

Worker 接收任务并输出 JSON 分析报告，
Supervisor 进行多维度质量审核，不通过则带反馈重做。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import json
import logging
import re
import time

from pipeline.model_client import quick_chat

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 7
DEFAULT_MAX_RETRIES = 3
ARTICLES_DIR = project_root / "knowledge" / "articles"

WORKER_PROMPT = """你是一个专业的分析助手。请对以下任务进行深度分析，并以 JSON 格式输出：

任务：{task}

输出格式（严格遵守，不要包含任何其他文本）：
{{
  "topic": "主题名称",
  "analysis": "详细分析内容（200字以上）",
  "key_points": ["要点1", "要点2", "要点3"],
  "conclusion": "总结结论",
  "references": ["相关参考或延伸阅读"]
}}"""

SUPERVISOR_PROMPT = """你是一个严格的质量审核员。请对以下分析报告进行多维度审核：

分析报告：
{report}

原始任务：
{task}

请从以下维度评分（1-10分），并输出 JSON：
- 准确性(accuracy)：内容是否准确、有无明显错误或编造
- 深度(depth)：分析是否深入、有独到见解、论据充分
- 格式(format)：结构是否清晰、字段是否完整、语言是否流畅

输出格式（严格遵守，不要包含任何其他文本）：
{{
  "accuracy": 分数(1-10),
  "depth": 分数(1-10),
  "format": 分数(1-10),
  "feedback": "具体改进建议"
}}"""

REWORK_PROMPT = """请根据审核员的反馈，重新分析报告并输出改进后的版本。

原始任务：
{task}

上次输出：
{last_report}

审核员反馈：
{feedback}

请针对反馈进行改进，保持 JSON 格式输出。"""


def _extract_json(text: str) -> dict | None:
    """从文本中提取第一个 JSON 对象。

    Args:
        text: 可能包含 JSON 的文本。

    Returns:
        解析后的字典，失败返回 None。
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _save_article(report: dict, score: int, attempts: int) -> str:
    """将审核通过的报告保存为知识条目 JSON 文件。

    Args:
        report: 分析报告字典。
        score: 最终评分。
        attempts: 尝试轮数。

    Returns:
        保存的文件路径。
    """
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w\s-]", "", report.get("topic", "untitled")).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)[:40]
    date_str = time.strftime("%Y%m%d")
    filename = f"{date_str}-supervisor-{slug}.json"
    filepath = ARTICLES_DIR / filename

    article = {
        "id": f"supervisor-{date_str}-{hash(report.get('topic', '')) % 1000:03d}",
        "title": report.get("topic", ""),
        "source": "supervisor",
        "source_url": "",
        "summary": report.get("conclusion", ""),
        "highlights": report.get("key_points", []),
        "tags": ["analysis", "supervisor"],
        "score": score,
        "attempts": attempts,
        "analysis": report.get("analysis", ""),
        "references": report.get("references", []),
        "status": "analyzed",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    logger.info("分析报告已保存至: %s", filepath)
    return str(filepath)


async def _worker(task: str) -> dict | None:
    """Worker Agent：执行任务并输出 JSON 分析报告。

    Args:
        task: 任务描述。

    Returns:
        解析后的分析报告字典，失败返回 None。
    """
    prompt = WORKER_PROMPT.format(task=task)
    raw = await quick_chat(prompt=prompt, temperature=0.3)
    return _extract_json(raw)


async def _supervisor(task: str, report: dict) -> dict:
    """Supervisor Agent：审核 Worker 输出的质量。

    Args:
        task: 原始任务描述。
        report: Worker 输出的报告字典。

    Returns:
        审核结果：{"accuracy": int, "depth": int, "format": int, "score": int, "passed": bool, "feedback": str}
    """
    prompt = SUPERVISOR_PROMPT.format(
        task=task,
        report=json.dumps(report, ensure_ascii=False, indent=2),
    )
    raw = await quick_chat(prompt=prompt, temperature=0.1)
    result = _extract_json(raw)

    if result:
        accuracy = max(1, min(10, result.get("accuracy", 5)))
        depth = max(1, min(10, result.get("depth", 5)))
        fmt = max(1, min(10, result.get("format", 5)))
        score = round(accuracy * 0.4 + depth * 0.4 + fmt * 0.2)

        return {
            "accuracy": accuracy,
            "depth": depth,
            "format": fmt,
            "score": score,
            "passed": score >= PASS_THRESHOLD,
            "feedback": result.get("feedback", "未提供反馈"),
        }

    return {"accuracy": 5, "depth": 5, "format": 5, "score": 5, "passed": False, "feedback": "审核结果解析失败"}


async def supervisor(task: str, max_retries: int = DEFAULT_MAX_RETRIES) -> dict:
    """Supervisor 监督模式入口。

    Worker 执行任务，Supervisor 审核输出质量，不通过则带反馈重做。

    Args:
        task: 任务描述。
        max_retries: 最大重试轮数。

    Returns:
        包含 output、attempts、final_score、warning(可选) 的字典。
    """
    attempts = 0
    report = None
    last_feedback = ""

    while attempts < max_retries:
        attempts += 1

        if attempts == 1:
            report = await _worker(task)
        else:
            prompt = REWORK_PROMPT.format(
                task=task,
                last_report=json.dumps(report, ensure_ascii=False, indent=2) if report else "",
                feedback=last_feedback,
            )
            raw = await quick_chat(prompt=prompt, temperature=0.3)
            report = _extract_json(raw)

        if not report:
            last_feedback = "输出格式无效，无法解析为 JSON"
            logger.warning("第 %d 轮 Worker 输出无效", attempts)
            continue

        review = await _supervisor(task, report)
        logger.info("第 %d 轮审核 | score=%d | passed=%s", attempts, review["score"], review["passed"])

        if review["passed"]:
            filepath = _save_article(report, review["score"], attempts)
            return {
                "output": report,
                "attempts": attempts,
                "final_score": review["score"],
                "saved_to": filepath,
            }

        last_feedback = review["feedback"]

    final_score = review.get("score", 0) if review else 0
    filepath = _save_article(report, final_score, attempts) if report else None

    return {
        "output": report,
        "attempts": attempts,
        "final_score": final_score,
        "warning": f"已达到最大重试次数 {max_retries}，返回最后一次结果",
        "saved_to": filepath,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    test_cases = [
        "请分析 LangGraph 框架的优缺点和适用场景",
    ]

    async def run_tests():
        for task in test_cases:
            logger.info("=" * 50)
            logger.info("任务: %s", task)
            result = await supervisor(task)
            logger.info("结果: attempts=%d, score=%d, warning=%s",
                        result["attempts"], result["final_score"], result.get("warning"))
            if result.get("saved_to"):
                logger.info("已保存至: %s", result["saved_to"])
            if result["output"]:
                logger.info("输出摘要: %s", result["output"].get("conclusion", "")[:100])
            logger.info("=" * 50)

    asyncio.run(run_tests())
