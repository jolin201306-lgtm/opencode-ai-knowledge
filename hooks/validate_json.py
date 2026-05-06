"""知识条目 JSON 文件校验工具."""

import io
import json
import re
import sys
from pathlib import Path

# Windows 控制台编码兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8") if hasattr(sys.stdout, 'buffer') else sys.stdout
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8") if hasattr(sys.stderr, 'buffer') else sys.stderr

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = {"raw", "analyzed", "published"}
VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}

ID_PATTERN = re.compile(r"^[a-z]+-\d{8}-[0-9a-f]{3}$")
URL_PATTERN = re.compile(r"^https?://.+")


def validate_id(value: str) -> list[str]:
    """检查 ID 格式是否为 {source}-{YYYYMMDD}-{NNN}."""
    if not ID_PATTERN.match(value):
        return [f"ID 格式错误: '{value}'，应为 {{source}}-YYYYMMDD-NNN（如 github-20260317-001）"]
    return []


def validate_url(value: str) -> list[str]:
    """检查 URL 格式."""
    if not URL_PATTERN.match(value):
        return [f"URL 格式错误: '{value}'，应以 http:// 或 https:// 开头"]
    return []


def validate_status(value: str) -> list[str]:
    """检查 status 是否为有效值."""
    if value not in VALID_STATUSES:
        return [f"status 值无效: '{value}'，应为 {sorted(VALID_STATUSES)} 之一"]
    return []


def validate_summary(value: str) -> list[str]:
    """检查摘要最少 20 字."""
    if len(value) < 20:
        return [f"摘要过短: 仅 {len(value)} 字，最少 20 字"]
    return []


def validate_tags(value: list) -> list[str]:
    """检查标签至少 1 个."""
    if len(value) < 1:
        return ["标签列表为空，至少需要 1 个标签"]
    return []


def validate_score(value: int | float) -> list[str]:
    """检查 score 是否在 1-10 范围."""
    if not (1 <= value <= 10):
        return [f"score 超出范围: {value}，应在 1-10 之间"]
    return []


def validate_audience(value: str) -> list[str]:
    """检查 audience 是否为有效值."""
    if value not in VALID_AUDIENCES:
        return [f"audience 值无效: '{value}'，应为 {sorted(VALID_AUDIENCES)} 之一"]
    return []


def validate_entry(data: dict, file_path: Path) -> list[str]:
    """校验单条知识条目."""
    errors = []

    if not isinstance(data, dict):
        return [f"{file_path}: 根节点应为 JSON 对象，实际为 {type(data).__name__}"]

    # 必填字段检查
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"{file_path}: 缺少必填字段 '{field}'")
        elif not isinstance(data[field], expected_type):
            actual = type(data[field]).__name__
            errors.append(
                f"{file_path}: 字段 '{field}' 类型错误，期望 {expected_type.__name__}，实际 {actual}"
            )

    # 字段级校验（仅在场时检查）
    if "id" in data and isinstance(data["id"], str):
        errors.extend(f"{file_path}: {e}" for e in validate_id(data["id"]))

    if "source_url" in data and isinstance(data["source_url"], str):
        errors.extend(f"{file_path}: {e}" for e in validate_url(data["source_url"]))

    if "status" in data and isinstance(data["status"], str):
        errors.extend(f"{file_path}: {e}" for e in validate_status(data["status"]))

    if "summary" in data and isinstance(data["summary"], str):
        errors.extend(f"{file_path}: {e}" for e in validate_summary(data["summary"]))

    if "tags" in data and isinstance(data["tags"], list):
        errors.extend(f"{file_path}: {e}" for e in validate_tags(data["tags"]))

    # 可选字段校验
    if "score" in data:
        if not isinstance(data["score"], (int, float)):
            errors.append(f"{file_path}: score 应为数字，实际 {type(data['score']).__name__}")
        else:
            errors.extend(f"{file_path}: {e}" for e in validate_score(data["score"]))

    if "audience" in data:
        if not isinstance(data["audience"], str):
            errors.append(f"{file_path}: audience 应为字符串")
        else:
            errors.extend(f"{file_path}: {e}" for e in validate_audience(data["audience"]))

    return errors


def collect_files(patterns: list[str]) -> list[Path]:
    """收集需要校验的文件，支持通配符."""
    files = []
    for pattern in patterns:
        path = Path(pattern)
        if "*" in pattern or "?" in pattern:
            matched = sorted(path.parent.glob(path.name))
            if not matched:
                print(f"警告: 未匹配到任何文件 - {pattern}", file=sys.stderr)
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
        print("用法: python hooks/validate_json.py <json_file> [json_file2 ...]", file=sys.stderr)
        print("      支持通配符: python hooks/validate_json.py knowledge/articles/*.json", file=sys.stderr)
        sys.exit(1)

    files = collect_files(sys.argv[1:])

    total_files = len(files)
    total_errors = 0
    passed_files = 0
    failed_files = 0
    all_errors: list[str] = []

    for file_path in files:
        file_errors: list[str] = []

        # JSON 解析检查
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except json.JSONDecodeError as e:
            file_errors.append(f"{file_path}: JSON 解析失败 - {e}")
        except Exception as e:
            file_errors.append(f"{file_path}: 读取失败 - {e}")

        if not file_errors:
            file_errors.extend(validate_entry(data, file_path))

        if file_errors:
            failed_files += 1
            total_errors += len(file_errors)
            all_errors.extend(file_errors)
        else:
            passed_files += 1

    # 输出汇总
    if all_errors:
        print("\n校验失败:", file=sys.stderr)
        for err in all_errors:
            print(f"  ✗ {err}", file=sys.stderr)

    print(f"\n校验汇总:", file=sys.stderr)
    print(f"  文件总数: {total_files}", file=sys.stderr)
    print(f"  通过: {passed_files}", file=sys.stderr)
    print(f"  失败: {failed_files}", file=sys.stderr)
    print(f"  错误数: {total_errors}", file=sys.stderr)

    sys.exit(1 if failed_files > 0 else 0)


if __name__ == "__main__":
    main()
