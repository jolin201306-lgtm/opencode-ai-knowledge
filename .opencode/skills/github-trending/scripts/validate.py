#!/usr/bin/env python3
"""验证 github-trending 技能输出是否符合 JSON Schema."""

import json
import re
import sys


def validate(data: list) -> list[str]:
    """验证数据，返回错误列表."""
    errors = []

    if not isinstance(data, list):
        return ["输出必须是 JSON 数组"]

    for i, item in enumerate(data):
        prefix = f"[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须是对象")
            continue

        # 必填字段
        for field in ["name", "url", "stars", "topics", "description"]:
            if field not in item:
                errors.append(f"{prefix} 缺少必填字段: {field}")

        # name 格式: owner/repo
        name = item.get("name", "")
        if name and not re.match(r"^[^/]+/[^/]+$", name):
            errors.append(f"{prefix} name 格式错误，应为 owner/repo: {name}")

        # url 格式
        url = item.get("url", "")
        if url and not url.startswith("https://github.com/"):
            errors.append(f"{prefix} url 应为 GitHub 链接: {url}")

        # stars 类型
        stars = item.get("stars")
        if stars is not None and not isinstance(stars, int):
            errors.append(f"{prefix} stars 必须是整数: {stars}")

        # topics 类型
        topics = item.get("topics")
        if topics is not None and not isinstance(topics, list):
            errors.append(f"{prefix} topics 必须是数组")

        # description 类型
        desc = item.get("description")
        if desc is not None and not isinstance(desc, str):
            errors.append(f"{prefix} description 必须是字符串")

    return errors


def main():
    """主入口: 从 stdin 或文件读取 JSON 并验证."""
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    errors = validate(data)

    if errors:
        print("验证失败:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"验证通过 · 共 {len(data)} 条", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
