"""知识条目 5 维度质量评分工具."""

import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows 控制台编码兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8") if hasattr(sys.stdout, 'buffer') else sys.stdout
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8") if hasattr(sys.stderr, 'buffer') else sys.stderr

# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class DimensionScore:
    """单个维度评分."""
    name: str
    max_score: int
    score: int = 0
    detail: str = ""

    @property
    def ratio(self) -> float:
        return self.score / self.max_score if self.max_score > 0 else 0


@dataclass
class QualityReport:
    """质量报告."""
    file_path: Path
    title: str = ""
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: int = 0
    grade: str = "C"

    @property
    def max_total(self) -> int:
        return sum(d.max_score for d in self.dimensions)

    def compute(self) -> None:
        self.total_score = sum(d.score for d in self.dimensions)
        if self.total_score >= 80:
            self.grade = "A"
        elif self.total_score >= 60:
            self.grade = "B"
        else:
            self.grade = "C"


# ============================================================================
# 常量定义
# ============================================================================

STANDARD_TAGS = {
    "AI", "LLM", "Agent", "Multi-Agent", "RAG", "MCP", "CV", "NLP",
    "Fine-tuning", "Prompt Engineering", "Vector DB", "Embedding",
    "DevTools", "Infra", "Database", "UI", "Security", "Finance",
    "Orchestration", "Claude", "Langchain", "OpenAI",
}

EMPTY_WORDS_ZH = [
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑", "颗粒度",
    "对齐", "拉通", "沉淀", "强大的", "革命性的",
]

EMPTY_WORDS_EN = [
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "state-of-the-art", "unprecedented", "best-in-class", "next-gen",
    "industry-leading", "paradigm shift",
]

TECH_KEYWORDS = {
    "transformer", "attention", "fine-tuning", "rag", "agent",
    "multi-agent", "embedding", "vector", "quantization", "lora",
    "rlhf", "reinforcement", "graph", "knowledge graph", "pipeline",
    "microservice", "serverless", "grpc", "rest api", "websocket",
}


# ============================================================================
# 评分维度
# ============================================================================

def score_summary(data: dict) -> DimensionScore:
    """摘要质量评分 (25 分)."""
    dim = DimensionScore(name="摘要质量", max_score=25)
    summary = data.get("summary", "")

    if len(summary) >= 50:
        dim.score = 20
        dim.detail = f"{len(summary)} 字 (满分档)"
    elif len(summary) >= 20:
        dim.score = 15
        dim.detail = f"{len(summary)} 字 (基本档)"
    else:
        dim.score = max(0, len(summary))
        dim.detail = f"{len(summary)} 字 (不足 20 字)"

    # 技术关键词奖励 (+5)
    lower = summary.lower()
    if any(kw in lower for kw in TECH_KEYWORDS):
        dim.score = min(25, dim.score + 5)
        dim.detail += " + 技术关键词"

    return dim


def score_depth(data: dict) -> DimensionScore:
    """技术深度评分 (25 分)，基于 score 字段 1-10 映射到 0-25."""
    dim = DimensionScore(name="技术深度", max_score=25)
    raw_score = data.get("score")

    if raw_score is None:
        dim.score = 10
        dim.detail = "无 score 字段，默认 10/25"
    elif not isinstance(raw_score, (int, float)):
        dim.score = 0
        dim.detail = f"score 类型错误: {type(raw_score).__name__}"
    else:
        normalized = max(1, min(10, raw_score))
        dim.score = round((normalized - 1) / 9 * 25)
        dim.detail = f"score={raw_score} → {dim.score}/25"

    return dim


def score_format(data: dict) -> DimensionScore:
    """格式规范评分 (20 分)，5 项各 4 分."""
    dim = DimensionScore(name="格式规范", max_score=20)
    checks = {
        "id": lambda d: isinstance(d.get("id"), str) and len(d["id"]) > 0,
        "title": lambda d: isinstance(d.get("title"), str) and len(d["title"]) > 0,
        "source_url": lambda d: isinstance(d.get("source_url"), str) and d["source_url"].startswith("http"),
        "status": lambda d: isinstance(d.get("status"), str) and len(d["status"]) > 0,
        "timestamp": lambda d: any(d.get(k) for k in ["created_at", "updated_at", "collected_at"]),
    }

    passed = 0
    for name, check in checks.items():
        if check(data):
            passed += 1

    dim.score = passed * 4
    dim.detail = f"{passed}/5 项通过"
    return dim


def score_tags(data: dict) -> DimensionScore:
    """标签精度评分 (15 分)."""
    dim = DimensionScore(name="标签精度", max_score=15)
    tags = data.get("tags", [])

    if not isinstance(tags, list):
        dim.score = 0
        dim.detail = "tags 不是列表"
        return dim

    count = len(tags)

    # 数量评分
    if 1 <= count <= 3:
        dim.score = 10
        dim.detail = f"{count} 个标签 (最佳范围)"
    elif count == 0:
        dim.score = 0
        dim.detail = "无标签"
    elif count <= 5:
        dim.score = 7
        dim.detail = f"{count} 个标签 (偏多)"
    else:
        dim.score = 3
        dim.detail = f"{count} 个标签 (过多)"

    # 标准标签奖励 (+5)
    valid = [t for t in tags if t in STANDARD_TAGS]
    if valid and len(valid) == count:
        dim.score = min(15, dim.score + 5)
        dim.detail += ", 全部为标准标签"
    elif valid:
        dim.score = min(15, dim.score + 3)
        dim.detail += f", {len(valid)}/{count} 标准标签"

    return dim


def score_empty_words(data: dict) -> DimensionScore:
    """空洞词检测评分 (15 分)."""
    dim = DimensionScore(name="空洞词检测", max_score=15)
    text = " ".join([
        data.get("summary", ""),
        data.get("title", ""),
    ])

    found_zh = [w for w in EMPTY_WORDS_ZH if w in text]
    found_en = [w for w in EMPTY_WORDS_EN if w.lower() in text.lower()]
    found = found_zh + found_en

    if not found:
        dim.score = 15
        dim.detail = "未检测到空洞词"
    elif len(found) <= 2:
        dim.score = 10
        dim.detail = f"检测到 {len(found)} 个: {', '.join(found)}"
    else:
        dim.score = 0
        dim.detail = f"检测到 {len(found)} 个空洞词: {', '.join(found)}"

    return dim


# ============================================================================
# 可视化
# ============================================================================

def progress_bar(score: int, max_score: int, width: int = 20) -> str:
    """生成进度条."""
    filled = round(score / max_score * width) if max_score > 0 else 0
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {score}/{max_score}"


def grade_badge(grade: str) -> str:
    """等级标识."""
    if grade == "A":
        return "[A]"
    elif grade == "B":
        return "[B]"
    else:
        return "[C]"


def print_report(report: QualityReport) -> None:
    """打印质量报告."""
    print(f"\n{'=' * 60}")
    print(f"  {report.title}")
    print(f"  {report.file_path}")
    print(f"{'=' * 60}")

    for dim in report.dimensions:
        bar = progress_bar(dim.score, dim.max_score)
        print(f"  {dim.name:<8} {bar}  {dim.detail}")

    print(f"{'─' * 60}")
    total_bar = progress_bar(report.total_score, report.max_total, 30)
    print(f"  总分     {total_bar}  {grade_badge(report.grade)}")
    print(f"{'=' * 60}")


def print_summary(reports: list[QualityReport]) -> None:
    """打印汇总统计."""
    total = len(reports)
    grades = {"A": 0, "B": 0, "C": 0}
    for r in reports:
        grades[r.grade] += 1

    avg_score = sum(r.total_score for r in reports) / total if total > 0 else 0

    print(f"\n{'#' * 60}")
    print(f"  质量评分汇总")
    print(f"{'#' * 60}")
    print(f"  文件总数: {total}")
    print(f"  平均分数: {avg_score:.1f}")
    print(f"  A 级 (>=80): {grades['A']}")
    print(f"  B 级 (>=60): {grades['B']}")
    print(f"  C 级 (<60):  {grades['C']}")
    print(f"{'#' * 60}")


# ============================================================================
# 主流程
# ============================================================================

DIMENSION_SCORERS = [
    score_summary,
    score_depth,
    score_format,
    score_tags,
    score_empty_words,
]


def evaluate(file_path: Path) -> QualityReport:
    """评估单个文件."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    report = QualityReport(file_path=file_path, title=data.get("title", ""))

    for scorer in DIMENSION_SCORERS:
        report.dimensions.append(scorer(data))

    report.compute()
    return report


def collect_files(patterns: list[str]) -> list[Path]:
    """收集需要评估的文件."""
    files = []
    for pattern in patterns:
        path = Path(pattern)
        if "*" in pattern or "?" in pattern:
            matched = sorted(path.parent.glob(path.name))
            if not matched:
                print(f"警告: 未匹配到文件 - {pattern}", file=sys.stderr)
            files.extend(matched)
        elif path.exists():
            files.append(path)
        else:
            print(f"错误: 文件不存在 - {path}", file=sys.stderr)
            sys.exit(1)
    return files


def main() -> None:
    """主入口."""
    if len(sys.argv) < 2:
        print("用法: python hooks/check_quality.py <json_file> [json_file2 ...]", file=sys.stderr)
        print("      支持通配符: python hooks/check_quality.py knowledge/articles/*.json", file=sys.stderr)
        sys.exit(1)

    files = collect_files(sys.argv[1:])
    reports = []
    has_c = False

    for file_path in files:
        try:
            report = evaluate(file_path)
            reports.append(report)
            print_report(report)
            if report.grade == "C":
                has_c = True
        except json.JSONDecodeError as e:
            print(f"\n✗ {file_path}: JSON 解析失败 - {e}", file=sys.stderr)
            has_c = True
        except Exception as e:
            print(f"\n✗ {file_path}: 评估失败 - {e}", file=sys.stderr)
            has_c = True

    if len(reports) > 1:
        print_summary(reports)

    sys.exit(1 if has_c else 0)


if __name__ == "__main__":
    main()
